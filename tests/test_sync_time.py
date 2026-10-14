from datetime import timedelta
from pathlib import Path
from ustc_report_watcher.main import run_once
from ustc_report_watcher.storage import Store


def test_success_time_is_completion_not_start(config, now, monkeypatch):
    finished = now + timedelta(minutes=2)
    readings = iter([now, finished])

    class Clock:
        @staticmethod
        def now(timezone):
            return next(readings)

    monkeypatch.setattr('ustc_report_watcher.main.datetime', Clock)
    fixture = Path(__file__).parent / 'fixtures/baseline.json'
    result = run_once(config, fixture=fixture)
    store = Store(config.root / 'data/demo.db')
    try:
        status = store.status()
        assert result['completed_at'] == finished.isoformat()
        assert status['last_success'] == finished.isoformat()
        assert status['last_run']['started_at'] == now.isoformat()
        assert status['last_run']['finished_at'] == finished.isoformat()
    finally:
        store.close()


def test_existing_database_migration_preserves_history(tmp_path):
    import sqlite3
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE runs (id INTEGER PRIMARY KEY, started_at TEXT,status TEXT,report_count INTEGER,error TEXT,health TEXT)')
        db.execute("INSERT INTO runs(started_at,status,report_count) VALUES ('2026-10-14T20:00:00+08:00','success',10)")
    store = Store(path)
    try:
        row = store.status()['last_run']
        assert row['report_count'] == 10
        assert row['finished_at'] is None
    finally:
        store.close()
