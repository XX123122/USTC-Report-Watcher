from datetime import timedelta
from ustc_report_watcher.models import Report, currently_selectable, upcoming
from ustc_report_watcher.parser import parse_report


def test_currently_selectable_includes_offline(now):
    report = Report('r', '线下可选报告', modality='offline', selectable_flag=True,
                    start_at=(now+timedelta(days=2)).isoformat(), registration_deadline=(now+timedelta(days=1)).isoformat())
    assert currently_selectable(report, now)


def test_expired_or_disallowed_is_not_selectable(now):
    report = Report('r','报告',selectable_flag=True,registration_deadline=(now-timedelta(hours=1)).isoformat())
    assert not currently_selectable(report, now)
    report.registration_deadline = (now+timedelta(hours=1)).isoformat()
    report.selectable_flag = False
    assert not currently_selectable(report, now)


def test_cutoff_is_not_end_time(now):
    report = parse_report({'BGBM':'r','BGTMZW':'报告','SFKXK':'1','BGSJ':'2026-10-19 10:00','JZSJ':'2026-10-19 09:00'},
                          {'report_id':'BGBM','title_zh':'BGTMZW','selectable_flag':'SFKXK','start_at':'BGSJ','registration_deadline':'JZSJ'})
    assert report.selectable_flag is True
    assert report.end_at is None
    assert currently_selectable(report, now)
    report.selectable_flag = False
    assert upcoming(report,now)  # Online pane is independent of enrollment eligibility.
