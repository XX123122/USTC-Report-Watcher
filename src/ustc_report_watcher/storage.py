import json
import sqlite3
from datetime import datetime, timedelta
from .models import Report, digest
from .filters import matches
from .security import secure_directory


class Store:
    def __init__(self, path):
        secure_directory(path.parent)
        self.db = sqlite3.connect(path, timeout=20)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS reports (
          id TEXT PRIMARY KEY, payload TEXT NOT NULL, fingerprint TEXT NOT NULL,
          first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, changed_at TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 1, revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS report_changes (
          id INTEGER PRIMARY KEY, report_id TEXT, event_type TEXT, old_fingerprint TEXT,
          content_fingerprint TEXT, created_at TEXT, revision INTEGER,
          UNIQUE(report_id,event_type,revision));
        CREATE TABLE IF NOT EXISTS notifications (
          event_key TEXT PRIMARY KEY, report_id TEXT, event_type TEXT, state TEXT,
          created_at TEXT, sent_at TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS watchlist (report_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, started_at TEXT, status TEXT, report_count INTEGER,
          error TEXT, health TEXT, finished_at TEXT);
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT);
        """)
        if 'finished_at' not in {row[1] for row in self.db.execute('PRAGMA table_info(runs)')}:
            self.db.execute('ALTER TABLE runs ADD COLUMN finished_at TEXT')
        self.db.commit()

    def recover_outbox(self):
        # Call only while holding the run lock, never from a viewer/status reader.
        with self.db:
            self.db.execute("UPDATE notifications SET state='uncertain' WHERE state='sending'")

    def close(self):
        self.db.close()

    def meta(self, key):
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def put_meta(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))

    def event(self, key, report_id, kind, now):
        self.db.execute("INSERT OR IGNORE INTO notifications VALUES (?,?,?,'prepared',?,NULL,NULL)", (key, report_id, kind, now))

    def commit_batch(self, reports, config, now, health=None, started_at=None):
        instant = now.isoformat()
        first = self.meta("baseline") is None
        with self.db:
            self.db.execute("DELETE FROM watchlist")
            self.db.executemany("INSERT INTO watchlist VALUES (?)", [(str(i),) for i in config["subscriptions"]["watch_report_ids"]])
            self.db.execute("UPDATE reports SET active=0")
            for report in reports:
                old = self.db.execute("SELECT * FROM reports WHERE id=?", (report.report_id,)).fetchone()
                fingerprint = digest(report.important())
                previous = Report(**json.loads(old["payload"])) if old else None
                changed = old is None or fingerprint != old["fingerprint"]
                revision = old["revision"] + int(changed) if old else 1
                first_seen = old["first_seen_at"] if old else instant
                changed_at = instant if changed else old["changed_at"]
                self.db.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,1,?)",
                                (report.report_id, json.dumps(report.dict(), ensure_ascii=False), fingerprint,
                                 first_seen, instant, changed_at, revision))
                if changed:
                    kind = "new" if old is None else "update"
                    self.db.execute("INSERT OR IGNORE INTO report_changes(report_id,event_type,old_fingerprint,content_fingerprint,created_at,revision) VALUES (?,?,?,?,?,?)",
                                    (report.report_id, kind, old["fingerprint"] if old else None, fingerprint, instant, revision))
                    relevant = matches(report, config, now)
                    entered = previous is not None and not matches(previous, config, now) and relevant
                    if not first and relevant and (old is None or entered or config["subscriptions"]["notify_on_update"]):
                        self.event(f"{report.report_id}:{kind}:{revision}:{fingerprint}", report.report_id, kind, instant)
            self.put_meta("baseline", instant)
            self.put_meta("last_success", instant)
            self.put_meta("failure_state", "")
            self.db.execute("UPDATE notifications SET state='suppressed' WHERE event_type IN ('failed','partial','auth_expired') AND state IN ('prepared','failed')")
            if first and config["notification"]["first_run_mode"] == "summary":
                self.event("baseline-summary", None, "baseline", instant)
            self.db.execute("INSERT INTO runs(started_at,finished_at,status,report_count,health) VALUES (?,?,'success',?,?)", ((started_at or now).isoformat(), instant, len(reports), json.dumps(health or {})))
            hours = config["subscriptions"]["remind_before_hours"]
            if hours is not None:
                for report in reports:
                    if report.start_at and matches(report, config, now):
                        start = datetime.fromisoformat(report.start_at)
                        if now <= start <= now + timedelta(hours=float(hours)):
                            self.event(f"reminder:{report.report_id}:{report.start_at}", report.report_id, "reminder", instant)
        return first

    def failure(self, kind, message, now, started_at=None):
        with self.db:
            self.db.execute("INSERT INTO runs(started_at,finished_at,status,report_count,error) VALUES (?,?,?,NULL,?)", ((started_at or now).isoformat(), now.isoformat(), kind, message))
            if self.meta("failure_state") != kind:
                self.event(f"failure:{kind}:{now.isoformat()}", None, kind, now.isoformat())
            self.put_meta("failure_state", kind)

    def reports(self, active=True):
        sql = "SELECT * FROM reports" + (" WHERE active=1" if active else "") + " ORDER BY changed_at DESC"
        return [dict(row) | {"report": Report(**json.loads(row["payload"]))} for row in self.db.execute(sql)]

    def pending(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM notifications WHERE state IN ('prepared','failed') ORDER BY created_at")]

    def mark(self, keys, state, now, error=None):
        with self.db:
            self.db.executemany("UPDATE notifications SET state=?,sent_at=?,error=? WHERE event_key=?", [(state, now.isoformat(), error, key) for key in keys])

    def status(self):
        row = self.db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        last_run = dict(row) if row else None
        if last_run and last_run['health']:
            last_run['health'] = json.loads(last_run['health'])
        return {"last_success": self.meta("last_success"), "last_run": last_run,
                "active_reports": self.db.execute("SELECT count(*) FROM reports WHERE active=1").fetchone()[0],
                "notifications": {row[0]: row[1] for row in self.db.execute("SELECT state,count(*) FROM notifications GROUP BY state")}}
