import time
from pathlib import Path
from urllib.parse import urlsplit
from .security import save_secret, load_secret

PORTAL = "https://yjs1.ustc.edu.cn/gsapp/sys/yjsemaphome/portal/index.do?forceCas=1"


class AuthExpired(RuntimeError):
    pass


class StructureError(RuntimeError):
    pass


def school_url(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == "yjs1.ustc.edu.cn"


def require_session(path):
    if not path.exists():
        raise AuthExpired("尚未登录，请运行 login 并进入学校学术报告列表。")
    return load_secret(path)


def login(config, timeout_seconds=900):
    """User operates official authentication; separate profile from everyday Edge."""
    from playwright.sync_api import sync_playwright
    import tkinter as tk
    from tkinter import messagebox
    captures = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=False)
        context = browser.new_context()

        def capture(response):
            if not school_url(response.url) or '/sys/xsbgglappustc/modules/' not in response.url or response.request.resource_type not in ("xhr", "fetch"):
                return
            if "json" not in response.headers.get("content-type", ""):
                return
            try:
                body = response.json()
                if len(str(body)) < 5_000_000 and len(captures) < 300:
                    request = response.request
                    captures.append({"url": response.url, "method": request.method,
                                     "body": request.post_data, "json": body})
            except Exception:
                pass  # Non-JSON browser responses are not report candidates.

        context.on("response", capture)
        page = context.new_page()
        page.goto(PORTAL, wait_until="domcontentloaded", timeout=60000)
        panel = tk.Tk()
        panel.title("USTC Report Watcher · 保存登录")
        panel.geometry("520x220")
        tk.Label(panel, text="请在新开的 Edge 窗口中自行登录。\n进入学术报告列表，翻一次页并打开一条详情，\n然后点击下面的保存按钮。\n账号密码不会保存；会话使用当前用户 DPAPI 加密。", padx=15, pady=15).pack()
        done = {"save": False, "closed": False}

        def finish():
            pages = [item for item in context.pages if school_url(item.url)]
            if not pages:
                messagebox.showerror("尚未完成", "请先完成学校登录并进入研究生系统。")
                return
            done["save"] = True

        tk.Button(panel, text="保存登录态和接口调查，完成", command=finish).pack(pady=6)
        panel.protocol("WM_DELETE_WINDOW", lambda: done.update(closed=True))
        deadline = time.monotonic() + timeout_seconds
        try:
            while not done["save"] and not done["closed"] and time.monotonic() < deadline:
                panel.update()
                page.wait_for_timeout(150)
            if not done["save"]:
                raise AuthExpired("登录未保存，可再次运行 login。")
            save_secret(config.path("auth_state"), context.storage_state(indexed_db=True))
            for item in captures:
                if isinstance(item['json'], dict) and 'models' in item['json']:
                    item['json']['models'] = [model for model in item['json']['models'] if model.get('name') == 'wxbgbgdz']
            save_secret(config.root / ".auth/discovery.bin", captures)
            # Save only actual observed URLs, including the current list page.
            save_secret(config.root / ".auth/pages.bin", [item.url for item in context.pages if school_url(item.url)])
            from .discovery import configure_verified_source
            configure_verified_source(config, captures)
        finally:
            panel.destroy()
            browser.close()
    return len(captures)
