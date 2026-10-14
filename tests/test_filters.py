from ustc_report_watcher.models import Report
from ustc_report_watcher.filters import matches


def test_watch_overrides_interest_but_not_exclusion(config):
    rules = config["subscriptions"]
    rules["title_keywords_any"] = ["量子"]
    rules["watch_report_ids"] = ["r"]
    report = Report("r", "智能体", modality="online")
    assert matches(report, config)
    rules["exclude_keywords"] = ["智能体"]
    assert not matches(report, config)


def test_default_and_all_keywords(config):
    report = Report("r", "智能体科学", modality="online")
    assert matches(report, config)
    report.modality = "offline"
    assert not matches(report, config)
    report.modality = "hybrid"
    config["subscriptions"]["title_keywords_all"] = ["智能体", "量子"]
    assert not matches(report, config)


def test_possible_is_opt_in(config):
    report = Report("r", "报告", modality="possible_online")
    assert not matches(report, config)
    config["notification"]["notify_possible_online"] = True
    assert matches(report, config)
