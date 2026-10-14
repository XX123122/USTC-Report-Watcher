from datetime import datetime
from zoneinfo import ZoneInfo
from logging.handlers import RotatingFileHandler
import logging
from .auth import AuthExpired, StructureError
from .classifier import classify
from .fetcher import fetch, fixture_batch, PartialFetch
from .filters import matches
from .locking import run_lock, AlreadyRunning
from .storage import Store
from .notifier import dispatch
from .security import secure_directory


def logger(config):
    log = logging.getLogger("ustc_report_watcher")
    if not log.handlers:
        secure_directory(config.path("log_dir"))
        handler = RotatingFileHandler(config.path("log_dir") / "watcher.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)
    return log


def run_once(config, dry_run=False, fixture=None):
    timezone = ZoneInfo(config["app"]["timezone"])
    started_at = datetime.now(timezone)
    def collect():
        batch = fixture_batch(fixture, config["app"]["timezone"]) if fixture else fetch(config)
        if batch.status != "success":
            raise PartialFetch("数据批次不完整，保留旧快照。")
        batch.reports = [classify(report, config["subscriptions"].get("online_keywords", [])) for report in batch.reports]
        return batch

    if dry_run:
        batch = collect()
        now = datetime.now(timezone)
        return {"status": "dry_run", "reports": len(batch.reports), "matching": sum(matches(r, config, now) for r in batch.reports), "health": batch.health}
    # Fixtures always use a separate database and never send desktop notifications.
    database = config.root / "data/demo.db" if fixture else config.path("database")
    lock = database.with_suffix(".lock")
    log = logger(config)
    try:
        with run_lock(lock):
            store = Store(database)
            try:
                store.recover_outbox()
                try:
                    batch = collect()
                    now = datetime.now(timezone)
                    baseline = store.commit_batch(batch.reports, config, now, batch.health, started_at=started_at)
                except Exception as error:
                    now = datetime.now(timezone)
                    kind = "auth_expired" if isinstance(error, AuthExpired) else "partial" if isinstance(error, PartialFetch) else "failed"
                    message = str(error) if isinstance(error, (AuthExpired, StructureError, PartialFetch)) else "网络或采集操作失败；请检查网络及接口配置。"
                    store.failure(kind, message, now, started_at=started_at)
                    notification = "demo" if fixture else dispatch(store, config, now)
                    log.warning("sync status=%s exception=%s notification=%s", kind, type(error).__name__, notification)
                    return {"status": kind, "error": message, "notification": notification}
                notification = "demo" if fixture else dispatch(store, config, now)
                log.info("sync success reports=%s pages=%s baseline=%s notification=%s demo=%s", len(batch.reports), batch.health.get("pages"), baseline, notification, bool(fixture))
                return {"status": "success", "reports": len(batch.reports), "matching": sum(matches(r, config, now) for r in batch.reports), "baseline": baseline, "notification": notification, "health": batch.health, "completed_at": now.isoformat()}
            finally:
                store.close()
    except AlreadyRunning:
        return {"status": "skipped", "reason": "已有检查正在运行"}
