import pytest
from ustc_report_watcher.models import Report
from ustc_report_watcher.classifier import classify


@pytest.mark.parametrize("venue,description,title,expected", [
    ("腾讯会议", "", "报告", "online"),
    ("Ｚｏｏｍ", "", "报告", "online"),
    ("教学楼301", "观看直播 https://live.bilibili.com/123", "报告", "hybrid"),
    ("", "B站直播", "报告", "online"),
    ("视频号直播", "", "报告", "online"),
    ("报告厅", "", "网络安全报告", "offline"),
    ("", "", "在线算法研究", "unknown"),
    ("", "", "Zoom算法研究", "unknown"),
    ("线上地址待发", "", "报告", "possible_online"),
    ("腾讯会议…", "", "报告", "unknown"),
    ("教室…", "腾讯会议", "报告", "hybrid"),
    ("会议室", "不提供线上参会", "报告", "offline"),
    ("会议室", "取消Zoom；腾讯会议", "报告", "hybrid"),
    ("直播间", "", "报告", "possible_online"),
    ("", "https://meeting.tencent.com/dw/test", "报告", "online"),
])
def test_cases(venue, description, title, expected):
    result = classify(Report("r", title, location_full=venue, description=description))
    assert result.modality == expected
    assert result.modality_reason
