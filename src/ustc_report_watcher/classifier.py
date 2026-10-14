import re
from .models import normalize

PLATFORMS = r"腾讯会议|zoom|teams会议|microsoft teams|飞书会议|钉钉会议|webex|线上参会|线上会议|线上报告|在线参会|线上参加"
LINK = r"https?://(?:[\w.-]+\.)?(?:zoom\.us|voovmeeting\.com|meeting\.tencent\.com|teams\.microsoft\.com|webex\.com|live\.bilibili\.com)(?:/|\b)"
LIVE = r"B\s*站直播|哔哩哔哩直播|视频号直播|观看直播|直播地址|直播链接|直播间"
PHYSICAL = r"(?:(?:[\w\u4e00-\u9fff]+)?(?:楼|馆|教室|报告厅|会议室|礼堂|校区|大厦)(?:\s*\d+)?|\broom\s*\d+|lecture hall)"
POSSIBLE = r"线上地址待[发定]|会议形式待定|线上.*(?:待定|待发|另行通知)|直播.*(?:待定|待发)|(?:腾讯会议|zoom).*待定"
NEGATED = r"(?:不设|不提供|没有|取消|无|不支持)(?:\s*)(?:线上参会|线上会议|线上|直播|腾讯会议|zoom)|仅(?:限)?线下"


def classify(report, extra_keywords=()):
    location = normalize(report.location_full)
    description = normalize(report.description)
    truncated = bool(re.search(r"(?:\.\.\.|…)", location))
    reasons = []
    physical = re.search(PHYSICAL, location, re.I)
    if not physical:
        # Abstracts mentioning buildings/libraries are not proof of a physical venue.
        physical = re.search(r"(?:线下(?:地点|会场)?|会场|报告地点|报告地址)\s*[:：]?\s*" + PHYSICAL, description, re.I)
    possible = False
    certain = False
    for label, text in (("地点", location), ("详情", description), ("标题", report.title_zh)):
        if label == "标题":
            match = re.search(r"线上参会|线上报告|线上会议|线上参加|直播链接", text, re.I)
            if match:
                possible = True
                reasons.append(f"标题提示：{match.group()}（待核验参会方式）")
            continue
        if label == "地点" and truncated:
            reasons.append("地点文本截断，未使用该文本判断参会方式")
            continue
        if re.search(NEGATED, text, re.I):
            # Handle each sentence, so a canceled Zoom mention does not mask a new Tencent venue.
            text = "；".join(part for part in re.split(r"[。；;\n]", text) if not re.search(NEGATED, part, re.I))
        if re.search(POSSIBLE, text, re.I):
            possible = True
            reasons.append(f"{label}提示线上方式尚待确认")
            text = re.sub(POSSIBLE, "", text, flags=re.I)
        for pattern in (PLATFORMS, LINK, *map(re.escape, extra_keywords)):
            match = re.search(pattern, text, re.I)
            if match:
                certain = True
                # URL evidence omits private query parameters.
                reasons.append(f"{label}包含：{match.group().split('?')[0]}")
        match = re.search(LIVE, text, re.I)
        if match:
            if re.search(r"直播间|直播地址|直播链接", match.group()) and not re.search(LINK, text, re.I) and not re.search(r"https?://", text):
                possible = True
                reasons.append(f"{label}提到直播，地址待核验")
            else:
                certain = True
                reasons.append(f"{label}包含：{match.group()}")
    if certain:
        modality = "hybrid" if physical else "online"
    elif possible:
        modality = "possible_online"
    elif truncated or not report.complete or not location:
        modality = "unknown"
        reasons.append("地点截断、为空或详情不完整")
    else:
        modality = "offline"
        reasons.append("完整地点和详情中未发现线上参会方式")
    report.modality = modality
    report.modality_reason = list(dict.fromkeys(reasons))
    return report
