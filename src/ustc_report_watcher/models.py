from dataclasses import dataclass, field, asdict
from datetime import datetime
import hashlib
import json
import re
import unicodedata
from urllib.parse import urlsplit


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def safe_url(value):
    value = normalize(value)
    parts = urlsplit(value)
    return value if parts.scheme in ("https", "http") and parts.hostname and not parts.username else None


@dataclass
class Report:
    report_id: str
    title_zh: str
    title_en: str | None = None
    speaker: str = ""
    department: str = ""
    location_raw: str = ""
    location_full: str = ""
    description: str = ""
    start_at: str | None = None
    end_at: str | None = None
    detail_url: str | None = None
    complete: bool = True
    modality: str = "unknown"
    modality_reason: list[str] = field(default_factory=list)
    source: str = "ustc_graduate_report"
    selectable_flag: bool | None = None
    registration_deadline: str | None = None

    def dict(self):
        return asdict(self)

    def important(self):
        # Details may contain links/meeting numbers not present in the venue.
        meeting = re.findall(r"https?://[^\s<>]+|(?:会议号|会议ID|入会密码|密码)\s*[:：]?\s*[\w -]+", self.description, re.I)
        return [self.location_full, self.start_at, self.end_at, self.detail_url, self.modality, meeting]


def upcoming(report, now):
    if not report.start_at:
        return True
    return datetime.fromisoformat(report.end_at or report.start_at) >= now


def currently_selectable(report, now):
    if report.selectable_flag is not True:
        return False
    if report.registration_deadline and datetime.fromisoformat(report.registration_deadline) < now:
        return False
    return upcoming(report, now)
