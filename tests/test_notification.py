from datetime import timedelta
from ustc_report_watcher.models import Report
from ustc_report_watcher.notifier import dispatch, toast_xml, public_title


class FakeNotifier:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def send(self, title, body, target):
        self.calls.append((title, body, target))
        if self.fail:
            raise RuntimeError("test")
        return "submitted"


def test_aggregation_and_no_duplicate(store, config, now):
    config["notification"]["first_run_mode"] = "silent"
    store.commit_batch([], config, now)
    store.commit_batch([Report("a", "A", modality="online"), Report("b", "B", modality="online")], config, now + timedelta(hours=6))
    notifier = FakeNotifier()
    assert dispatch(store, config, now, notifier) == "submitted"
    assert len(notifier.calls) == 1
    assert notifier.calls[0][2] == "ustc-report-watcher://show"
    assert dispatch(store, config, now, notifier) == "none"


def test_failure_is_retryable_and_disabled_suppresses(store, config, now):
    store.event("test", None, "baseline", now.isoformat())
    store.db.commit()
    assert dispatch(store, config, now, FakeNotifier(True)) == "failed"
    assert store.pending()[0]["state"] == "failed"
    config["notification"]["enabled"] = False
    notifier = FakeNotifier()
    assert dispatch(store, config, now, notifier) == "suppressed"
    assert not notifier.calls


def test_protocol_xml_and_sensitive_summary():
    import xml.etree.ElementTree as ET
    element = ET.fromstring(toast_xml("A&B", '<x>', "ustc-report-watcher://show?id=a%20b"))
    assert element.attrib["activationType"] == "protocol"
    assert "999" not in public_title("报告 会议号：999 密码：secret")
    assert "secret" not in public_title("报告 会议号：999 密码：secret")


def test_crash_ambiguity_does_not_replay(store, config, now, tmp_path):
    from ustc_report_watcher.storage import Store
    store.event('crash',None,'baseline',now.isoformat())
    store.mark(['crash'],'sending',now)
    reader = Store(tmp_path / 'reports.db')
    try:
        assert reader.status()['notifications']['sending'] == 1
        reader.recover_outbox()
        assert reader.status()['notifications']['uncertain'] == 1
        assert not reader.pending()
    finally:
        reader.close()
