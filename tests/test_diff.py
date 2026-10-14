from datetime import timedelta
from dataclasses import replace
from ustc_report_watcher.models import Report
from ustc_report_watcher.classifier import classify
from ustc_report_watcher.storage import Store


def test_baseline_transition_update_and_restart(store, config, now, tmp_path):
    config["notification"]["first_run_mode"] = "silent"
    offline = classify(Report("r", "报告", location_full="教室101"))
    store.commit_batch([offline], config, now)
    assert not store.pending()
    online = classify(replace(offline, location_full="教室101；腾讯会议"))
    store.commit_batch([online], config, now + timedelta(days=2))
    assert len(store.pending()) == 1
    store.commit_batch([online], config, now + timedelta(days=3))
    assert len(store.pending()) == 1
    store.close()
    reopened = Store(tmp_path / "reports.db")
    try:
        reopened.commit_batch([online], config, now + timedelta(days=4))
        assert len(reopened.pending()) == 1
        assert reopened.status()["active_reports"] == 1
    finally:
        reopened.close()
    # Restore a live connection for fixture cleanup.
    import sqlite3
    store.db = sqlite3.connect(tmp_path / "reports.db")


def test_failure_preserves_history_and_throttles(store, config, now):
    report = classify(Report("r", "报告", location_full="Zoom"))
    store.commit_batch([report], config, now)
    store.failure("auth_expired", "重新登录", now + timedelta(hours=6))
    count = len(store.pending())
    store.failure("auth_expired", "重新登录", now + timedelta(hours=12))
    assert len(store.pending()) == count
    assert store.reports()[0]["report"].report_id == "r"
    assert store.meta("last_success") == now.isoformat()
    store.commit_batch([report], config, now + timedelta(hours=18))
    assert not any(e["event_type"] == "auth_expired" for e in store.pending())


def test_time_and_meeting_change(store, config, now):
    config["notification"]["first_run_mode"] = "silent"
    report = classify(Report("r", "报告", location_full="Zoom", start_at="2099-10-14T14:00:00+08:00"))
    store.commit_batch([report], config, now)
    changed = replace(report, start_at="2099-10-14T15:00:00+08:00", description="会议号：000 111 222（示例）")
    store.commit_batch([changed], config, now + timedelta(hours=6))
    assert len(store.pending()) == 1


def test_disabled_updates_still_notify_transition(store, config, now):
    config["subscriptions"]["notify_on_update"] = False
    config["notification"]["first_run_mode"] = "silent"
    old = classify(Report("r", "报告", location_full="教室"))
    store.commit_batch([old], config, now)
    new = classify(replace(old, location_full="Zoom"))
    store.commit_batch([new], config, now + timedelta(hours=6))
    assert len(store.pending()) == 1


def test_reminder_dedup_and_new_start_time(store, config, now):
    config['subscriptions']['remind_before_hours'] = 24
    config['notification']['first_run_mode'] = 'silent'
    report = Report('r','报告',modality='online',start_at=(now+timedelta(hours=20)).isoformat())
    store.commit_batch([report],config,now)
    store.commit_batch([report],config,now+timedelta(hours=6))
    assert len([event for event in store.pending() if event['event_type']=='reminder']) == 1
    changed = replace(report,start_at=(now+timedelta(hours=23)).isoformat())
    store.commit_batch([changed],config,now+timedelta(hours=12))
    assert len([event for event in store.pending() if event['event_type']=='reminder']) == 2
