from datetime import datetime
from zoneinfo import ZoneInfo
from .models import Report, normalize, safe_url, digest
from .auth import StructureError
from html.parser import HTMLParser


class ContentText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag == "a":
            href = dict(attrs).get("href")
            if safe_url(href):
                self.parts.append(href)
        if tag in ("p", "div", "br", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden-1)
        if tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def content_text(value):
    parser = ContentText()
    parser.feed(str(value or ""))
    return normalize(" ".join(parser.parts))


def at_path(value, path, default=None):
    if isinstance(path, list):
        return "\n".join(str(at_path(value, p, "") or "") for p in path)
    if not path:
        return value
    try:
        for key in path.split("."):
            value = value[int(key)] if isinstance(value, list) else value[key]
        return value
    except (KeyError, IndexError, TypeError, ValueError):
        return default


def parse_time(value, timezone="Asia/Shanghai"):
    if not value:
        return None
    text = normalize(value)
    # Never guess a year or a start time from an incomplete date.
    try:
        date = datetime.fromisoformat(text.replace("Z", "+00:00")) if "T" in text else None
        if date is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y年%m月%d日 %H:%M"):
                try:
                    date = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
        if date is None:
            return None
        if date.tzinfo is None:
            date = date.replace(tzinfo=ZoneInfo(timezone))
        return date.isoformat()
    except (ValueError, TypeError):
        return None


def parse_report(row, mapping=None, timezone="Asia/Shanghai"):
    mapping = mapping or {key: key for key in Report.__dataclass_fields__}
    values = {key: at_path(row, path) for key, path in mapping.items() if key in Report.__dataclass_fields__ and path and at_path(row, path) is not None}
    for key in ("title_zh", "title_en", "speaker", "department", "location_raw", "location_full", "description"):
        values[key] = content_text(values.get(key)) if key == "description" else normalize(values.get(key))
    if not values["title_zh"] and values["title_en"]:
        values["title_zh"] = values["title_en"]
    if not values["title_zh"]:
        raise StructureError("报告标题字段缺失，停止该批次；请检查字段映射。")
    values["location_full"] = values["location_full"] or values["location_raw"]
    values["start_at"] = parse_time(values.get("start_at"), timezone)
    values["end_at"] = parse_time(values.get("end_at"), timezone)
    values["registration_deadline"] = parse_time(values.get("registration_deadline"), timezone)
    flag = values.get("selectable_flag")
    if flag is not None:
        if str(flag).strip().lower() in ("1", "true", "是", "可选"):
            values["selectable_flag"] = True
        elif str(flag).strip().lower() in ("0", "false", "否", "不可选"):
            values["selectable_flag"] = False
        else:
            values["selectable_flag"] = None
    values["detail_url"] = safe_url(values.get("detail_url"))
    if not values.get("report_id"):
        if not values["speaker"] or not values["start_at"]:
            raise StructureError("来源缺少稳定 ID，且报告人/开始时间不足以生成稳定标识。")
        values["report_id"] = digest([values["speaker"], values["department"], values["start_at"]])
    values["report_id"] = str(values["report_id"])
    values["complete"] = values.get("complete", True) is not False
    return Report(**values)
