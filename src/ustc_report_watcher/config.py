from copy import deepcopy
from pathlib import Path
import yaml

DEFAULTS = {
    "app": {"timezone": "Asia/Shanghai"},
    "schedule": {"interval_hours": 6},
    "fetch": {"mode": "auto", "min_interval_seconds": 2, "max_pages": 30,
              "request_timeout_seconds": 20, "total_timeout_seconds": 600,
              "retries": 2, "source_file": ".auth/source.json"},
    "subscriptions": {"include_modalities": ["online", "hybrid"], "title_keywords_any": [],
                      "title_keywords_all": [], "department_keywords": [], "speaker_keywords": [],
                      "exclude_keywords": [], "watch_report_ids": [], "notify_on_update": True,
                      "remind_before_hours": None},
    "notification": {"enabled": True, "first_run_mode": "summary", "max_titles_in_toast": 3,
                     "notify_possible_online": False, "notify_on_auth_expiry": True},
    "paths": {"auth_state": ".auth/session.bin", "database": "data/reports.db", "log_dir": "logs"},
}


class Config:
    def __init__(self, path="config.yaml"):
        self.file = Path(path).resolve()
        self.root = self.file.parent
        self.data = deepcopy(DEFAULTS)
        if self.file.exists():
            custom = yaml.safe_load(self.file.read_text(encoding="utf-8")) or {}
            for section, values in custom.items():
                if section not in self.data or not isinstance(values, dict):
                    raise ValueError(f"无效配置节：{section}")
                self.data[section].update(values)
        if not 1 <= float(self.data["schedule"]["interval_hours"]) <= 24:
            raise ValueError("检查间隔必须为 1–24 小时。")
        if self.data["fetch"]["mode"] not in ("auto", "api", "playwright"):
            raise ValueError("fetch.mode 必须为 auto/api/playwright。")
        for key in ("request_timeout_seconds", "total_timeout_seconds", "max_pages"):
            if float(self.data["fetch"][key]) <= 0:
                raise ValueError(f"fetch.{key} 必须大于零。")
        if self.data['fetch']['min_interval_seconds'] < 0 or self.data['fetch']['retries'] < 0:
            raise ValueError('请求间隔与重试次数不能为负数。')
        if self.data['notification']['first_run_mode'] not in ('summary','silent'):
            raise ValueError('first_run_mode 必须为 summary 或 silent。')
        if not 1 <= int(self.data['notification']['max_titles_in_toast']) <= 10:
            raise ValueError('单条通知标题数量必须为 1–10。')
        hours = self.data['subscriptions']['remind_before_hours']
        if hours is not None and float(hours) <= 0:
            raise ValueError('提前提醒小时数必须大于零或为 null。')
        self.data['subscriptions']['watch_report_ids'] = [str(value) for value in self.data['subscriptions']['watch_report_ids']]

    def __getitem__(self, key):
        return self.data[key]

    def path(self, key):
        return (self.root / self.data["paths"][key]).resolve()
