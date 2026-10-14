from dataclasses import dataclass, field
import json
import time
from urllib.parse import urljoin
from pathlib import Path
from .auth import AuthExpired, StructureError, school_url, require_session
from .parser import at_path, parse_report
from .security import load_secret
from .models import digest, normalize, safe_url
from datetime import datetime
from zoneinfo import ZoneInfo
from .parser import parse_time


@dataclass
class Batch:
    reports: list
    health: dict = field(default_factory=dict)
    status: str = "success"


class PartialFetch(RuntimeError):
    pass


def read_source(config):
    path = config.root / config["fetch"]["source_file"]
    if not path.exists():
        raise StructureError("尚未确认报告接口：先运行 login，在报告列表翻页并打开详情，再执行 discover。")
    source = load_secret(path) if path.suffix == ".bin" else json.loads(path.read_text(encoding="utf-8"))
    if not source.get("verified"):
        raise StructureError("数据源配置尚未经过实际网页请求核实，拒绝执行。")
    return source


def fixture_batch(path, timezone):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("status", "success") != "success":
        raise PartialFetch("离线样例模拟分页不完整。")
    return Batch([parse_report(row, timezone=timezone) for row in data["reports"]], {"source": "offline_fixture", "pages": 1})


def set_path(data, path, value):
    keys = path.split(".")
    for key in keys[:-1]:
        data = data[key]
    data[keys[-1]] = value


class ApiFetcher:
    def __init__(self, config, source, request_context, clock=time.monotonic, sleep=time.sleep):
        self.config, self.source, self.context = config, source, request_context
        self.clock, self.sleep = clock, sleep
        self.deadline = clock() + config["fetch"]["total_timeout_seconds"]
        self.previous = None

    def request(self, spec, parameters):
        url = spec["url"]
        if not school_url(url):
            raise StructureError("报告数据请求只允许学校研究生系统 HTTPS 原始域名。")
        method = spec.get("method", "POST").upper()
        if method not in ("GET", "POST"):
            raise StructureError("报告读取只支持已核实的 GET/POST 请求。")
        for attempt in range(int(self.config["fetch"]["retries"]) + 1):
            if self.previous is not None:
                self.sleep(max(0, self.config["fetch"]["min_interval_seconds"] - (self.clock() - self.previous)))
            remaining = self.deadline - self.clock()
            if remaining <= 0:
                raise PartialFetch("任务总超时，保留旧快照。")
            self.previous = self.clock()
            arguments = {"timeout": min(self.config["fetch"]["request_timeout_seconds"], remaining)*1000, "max_redirects": 0}
            if method == "GET":
                arguments["params"] = parameters
            elif spec.get("encoding", "form") == "json":
                arguments["data"] = parameters
            else:
                arguments["form"] = parameters
            try:
                response = self.context.fetch(url, method=method, **arguments)
            except Exception:
                if attempt >= self.config["fetch"]["retries"]:
                    raise RuntimeError("请求超时或网络不可用；上次成功快照已保留。") from None
                self.sleep(2 ** attempt)
                continue
            if response.status in (301, 302, 303, 307, 308, 401, 403):
                raise AuthExpired("学校会话失效或权限不足，请重新运行 login。")
            if response.status in (429, 500, 502, 503, 504):
                if attempt < self.config["fetch"]["retries"]:
                    self.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError("学校接口暂时不可用或限流，请稍后重试。")
            if not response.ok:
                raise RuntimeError(f"学校数据请求失败（HTTP {response.status}）。")
            if not school_url(response.url):
                raise AuthExpired("数据请求已离开研究生系统，请重新登录。")
            try:
                data = response.json()
            except Exception:
                text = response.text().lower()
                if any(word in text for word in ("统一身份认证", 'type="password"', "cas/login", "sso/login")):
                    raise AuthExpired("接口返回登录页面，请重新登录。") from None
                raise StructureError("接口未返回预期 JSON，停止同步。") from None
            if spec.get("success_path") and at_path(data, spec["success_path"]) != spec["success_value"]:
                raise StructureError("学校接口返回业务错误；拒绝视为空报告。")
            return data
        raise RuntimeError("请求失败。")

    def fetch(self):
        spec = self.source["api"]
        parameters = json.loads(json.dumps(spec.get("parameters", {})))
        pagination = spec["pagination"]
        all_reports = {}
        seen_pages = set()
        page = pagination.get("first_page", 1)
        total = None
        pages = 0
        detail_count = 0
        now = datetime.now(ZoneInfo(self.config["app"]["timezone"]))
        while pages < int(self.config["fetch"]["max_pages"]):
            set_path(parameters, pagination["page_parameter"], page)
            data = self.request(spec, parameters)
            rows = at_path(data, spec["rows_path"])
            if not isinstance(rows, list):
                raise StructureError("报告列表字段结构变化，未覆盖旧数据。")
            if pagination.get("total_path"):
                observed_total = at_path(data, pagination["total_path"])
                try:
                    observed_total = int(observed_total)
                except (TypeError, ValueError):
                    raise StructureError("分页总数字段缺失或异常。") from None
                if total is not None and observed_total != total:
                    raise PartialFetch("抓取期间报告总数变化，下次重试以避免漏页。")
                total = observed_total
            pages += 1
            signature = digest(rows)
            if rows and signature in seen_pages:
                raise PartialFetch("分页响应重复，无法确认已抓取所有报告。")
            seen_pages.add(signature)
            for row in rows:
                detail = spec.get("detail")
                merged = dict(row)
                start_path = spec["fields"].get("start_at")
                start_at = parse_time(at_path(row, start_path), self.config["app"]["timezone"]) if start_path else None
                needs_detail = bool(detail)
                if detail and detail.get("strategy") == "upcoming_or_unknown":
                    needs_detail = (start_at is None or datetime.fromisoformat(start_at) >= now or str(at_path(row, spec["fields"]["report_id"])) in self.config["subscriptions"]["watch_report_ids"])
                if needs_detail:
                    detail_parameters = dict(detail.get("parameters", {}))
                    identity = at_path(row, detail["row_id_path"])
                    if identity is None:
                        raise StructureError("报告详情 ID 缺失。")
                    set_path(detail_parameters, detail["id_parameter"], identity)
                    response = self.request(detail, detail_parameters)
                    value = at_path(response, detail.get("object_path", ""))
                    if not isinstance(value, dict):
                        raise PartialFetch("报告详情未返回完整对象，保留旧快照。")
                    if detail.get("id_path") and str(at_path(value, detail["id_path"])) != str(identity):
                        raise PartialFetch("详情返回的报告 ID 不匹配，保留旧快照。")
                    detail_count += 1
                    for field, field_path in detail.get("fields", {}).items():
                        merged[field] = at_path(value, field_path)
                mapping = dict(spec["fields"])
                if needs_detail:
                    mapping.update({field: field for field in detail.get("fields", {})})
                report = parse_report(merged, mapping, self.config["app"]["timezone"])
                if "…" in report.location_full or "..." in report.location_full:
                    report.complete = False
                if report.report_id in all_reports and all_reports[report.report_id].dict() != report.dict():
                    raise PartialFetch("同一报告 ID 内容冲突，拒绝覆盖快照。")
                all_reports[report.report_id] = report
            if total is not None:
                if len(all_reports) == total:
                    break
                if len(all_reports) > total or not rows:
                    raise PartialFetch("实际报告数与分页总数不符。")
            elif not rows:
                break
            page += 1
        else:
            raise PartialFetch("达到最大页数，尚未确认分页完整。")
        return Batch(list(all_reports.values()), {"pages": pages, "total": total, "details_checked": detail_count, "source": "verified_api", "missing_location": sum(not r.location_full for r in all_reports.values())})


class BrowserFetcher:
    def __init__(self, config, source, browser):
        self.config, self.source, self.browser = config, source, browser

    def fetch(self):
        spec = self.source.get("playwright")
        if not spec:
            raise StructureError("尚未核实页面选择器，无法使用 Playwright 页面回退。")
        if not school_url(spec["list_url"]):
            raise StructureError("列表入口必须为已核实的学校 URL。")
        page = self.browser.new_page()
        page.set_default_timeout(self.config["fetch"]["request_timeout_seconds"] * 1000)
        response = page.goto(spec["list_url"], wait_until="domcontentloaded")
        if not school_url(page.url) or (response and response.status in (401, 403)):
            raise AuthExpired("学校页面需要重新登录。")
        frame = page.frame_locator(spec["frame_selector"]) if spec.get("frame_selector") else page
        frame.locator(spec["ready_selector"]).wait_for()
        reports = {}
        seen = set()
        started = time.monotonic()
        for page_number in range(1, self.config["fetch"]["max_pages"] + 1):
            if time.monotonic() - started > self.config["fetch"]["total_timeout_seconds"]:
                raise PartialFetch("页面抓取总超时。")
            rows = frame.locator(spec["rows_selector"])
            parsed = []
            for index in range(rows.count()):
                row = rows.nth(index)
                value = {}
                for field, rule in spec["fields"].items():
                    cell = row.locator(rule["selector"]) if rule.get("selector") else row
                    value[field] = cell.get_attribute(rule["attribute"]) if rule.get("attribute") else cell.inner_text()
                    if field == "detail_url" and value[field]:
                        value[field] = urljoin(page.url, value[field])
                if spec.get("detail"):
                    detail = spec["detail"]
                    row.locator(detail["open_selector"]).click()
                    frame.locator(detail["ready_selector"]).wait_for()
                    for field, selector in detail["fields"].items():
                        value[field] = frame.locator(selector).inner_text()
                    frame.locator(detail["close_selector"]).click()
                report = parse_report(value, timezone=self.config["app"]["timezone"])
                if re_truncated(report.location_full):
                    report.complete = False
                parsed.append(report)
            signature = digest([r.dict() for r in parsed])
            if signature in seen and parsed:
                raise PartialFetch("页面翻页未生效或重复。")
            seen.add(signature)
            reports.update({r.report_id: r for r in parsed})
            next_button = frame.locator(spec["next_selector"])
            if not next_button.count():
                raise PartialFetch("下一页控制缺失，无法确认分页完整。")
            disabled = next_button.is_disabled() or next_button.get_attribute("aria-disabled") == "true"
            if spec.get("next_disabled_class"):
                disabled = disabled or spec["next_disabled_class"] in (next_button.get_attribute("class") or "").split()
            if disabled:
                if not parsed and not frame.locator(spec["empty_selector"]).count():
                    raise StructureError("列表为空但未发现明确空状态，拒绝覆盖历史。")
                return Batch(list(reports.values()), {"pages": page_number, "source": "verified_dom"})
            next_button.click()
            page.wait_for_timeout(self.config["fetch"]["min_interval_seconds"] * 1000)
        raise PartialFetch("达到最大页数，页面抓取不完整。")


def re_truncated(value):
    return "…" in value or "..." in value


def fetch(config):
    from playwright.sync_api import sync_playwright
    state = require_session(config.path("auth_state"))
    source = read_source(config)
    with sync_playwright() as p:
        request = p.request.new_context(storage_state=state)
        try:
            if config["fetch"]["mode"] != "playwright" and source.get("api"):
                try:
                    return ApiFetcher(config, source, request).fetch()
                except StructureError:
                    if config["fetch"]["mode"] != "auto" or not source.get("playwright"):
                        raise
            if config["fetch"]["mode"] == "api":
                raise StructureError("没有经过核实的 API 配置。")
            browser = p.chromium.launch(channel="msedge", headless=True)
            try:
                context = browser.new_context(storage_state=state)
                return BrowserFetcher(config, source, context).fetch()
            finally:
                browser.close()
        finally:
            request.dispose()
