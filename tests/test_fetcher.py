from copy import deepcopy
from pathlib import Path
import pytest
from ustc_report_watcher.fetcher import ApiFetcher, PartialFetch, fixture_batch
from ustc_report_watcher.auth import AuthExpired, StructureError
from ustc_report_watcher.main import run_once
from ustc_report_watcher.parser import parse_time, parse_report


class Response:
    def __init__(self, data, status=200):
        self.data, self.status = data, status
        self.url = "https://yjs1.ustc.edu.cn/observed-test"
        self.ok = 200 <= status < 300

    def json(self):
        return self.data


class Context:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def fetch(self, url, **kwargs):
        self.calls.append((url,deepcopy(kwargs)))
        return next(self.responses)


def source():
    return {"api": {"url": "https://yjs1.ustc.edu.cn/observed-test", "method": "POST",
                    "parameters": {"page": 1}, "rows_path": "rows", "fields": {"report_id":"id","title_zh":"title"},
                    "pagination": {"page_parameter":"page","total_path":"total"}}}


def test_complete_pagination(config):
    context = Context([Response({"rows":[{"id":"a","title":"A"}],"total":2}), Response({"rows":[{"id":"b","title":"B"}],"total":2})])
    config["fetch"]["min_interval_seconds"] = 0
    result = ApiFetcher(config, source(), context).fetch()
    assert len(result.reports) == 2
    assert result.health["pages"] == 2
    assert [call[1]["form"]["page"] for call in context.calls] == [1, 2]


@pytest.mark.parametrize("second", [
    {"rows":[{"id":"a","title":"A"}],"total":2},
    {"rows":[],"total":2},
    {"rows":[{"id":"b","title":"B"}],"total":3},
])
def test_incomplete_is_never_success(config, second):
    config["fetch"]["min_interval_seconds"] = 0
    context = Context([Response({"rows":[{"id":"a","title":"A"}],"total":2}), Response(second)])
    with pytest.raises(PartialFetch):
        ApiFetcher(config, source(), context).fetch()


def test_auth_and_domain(config):
    with pytest.raises(AuthExpired):
        ApiFetcher(config, source(), Context([Response({}, 401)])).fetch()
    bad = source()
    bad["api"]["url"] = "https://third-party.example/test"
    with pytest.raises(StructureError):
        ApiFetcher(config, bad, Context([])).fetch()


def test_unknown_structure(config):
    with pytest.raises(StructureError):
        ApiFetcher(config, source(), Context([Response({"login":True})])).fetch()


def test_dry_run_no_files_and_fixture_isolation(config):
    fixture = Path(__file__).parent / "fixtures/baseline.json"
    result = run_once(config, dry_run=True, fixture=fixture)
    assert result["reports"] == 2
    assert not config.path("database").exists()
    assert not config.path("log_dir").exists()
    run_once(config, fixture=fixture)
    assert (config.root / "data/demo.db").exists()
    assert not config.path("database").exists()


def test_partial_preserves_database(config, monkeypatch):
    from ustc_report_watcher.storage import Store
    from ustc_report_watcher.models import Report
    from datetime import datetime
    from zoneinfo import ZoneInfo
    value = Store(config.path("database"))
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    value.commit_batch([Report("keep", "保留报告")], config, now)
    value.close()
    def partial(*args):
        raise PartialFetch("不完整")
    monkeypatch.setattr("ustc_report_watcher.main.fetch", partial)
    monkeypatch.setattr("ustc_report_watcher.main.dispatch", lambda *args: "none")
    assert run_once(config)["status"] == "partial"
    value = Store(config.path("database"))
    assert value.reports()[0]["report"].report_id == "keep"
    value.close()


def test_time_and_html():
    assert parse_time("10-19 10:00") is None
    assert parse_time("2026-10-19") is None
    report = parse_report({"report_id":"r","title_zh":"报告","description":'<p>线上参会：<a href="https://zoom.us/j/example">入会</a></p><script>password</script>'})
    assert "https://zoom.us/j/example" in report.description
    assert "<p>" not in report.description
    assert "password" not in report.description
