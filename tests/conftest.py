from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from ustc_report_watcher.config import Config
from ustc_report_watcher.storage import Store


@pytest.fixture
def config(tmp_path):
    return Config(tmp_path / "config.yaml")


@pytest.fixture
def now():
    return datetime(2026, 10, 14, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


@pytest.fixture
def store(tmp_path):
    value = Store(tmp_path / "reports.db")
    yield value
    value.close()
