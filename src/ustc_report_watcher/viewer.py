from datetime import datetime
from zoneinfo import ZoneInfo
import queue
import json
import time
import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from urllib.parse import urlsplit, parse_qs
from .auth import PORTAL
from .storage import Store
from .windows import launch_args
from .models import currently_selectable, upcoming

LABELS = {"online": "线上", "hybrid": "混合", "possible_online": "疑似线上", "offline": "线下", "unknown": "待确认"}


def sync_status_text(status, timezone="Asia/Shanghai", command=None, elapsed=0, notice=""):
    value = status.get('last_success')
    completed = datetime.fromisoformat(value).astimezone(ZoneInfo(timezone)).strftime('%Y-%m-%d %H:%M:%S') if value else '尚未成功同步'
    text = f'上次成功同步（完成时间）：{completed}'
    latest = status.get('last_run')
    if command == 'run-once':
        text += f'  |  正在刷新，已用时 {int(elapsed)} 秒（完整检查通常约 2 分钟）'
    elif command == 'login':
        text += '  |  正在重新登录…'
    elif notice:
        text += f'  |  {notice}'
    elif latest and latest['status'] != 'success':
        text += f"  |  最近同步失败：{latest['error']}（显示旧数据）"
    elif latest:
        text += '  |  最近检查成功'
    return text + '  |  通知提交不代表已阅读'


def status_stamp(status):
    latest = status.get('last_run')
    return status.get('last_success'), latest.get('id') if latest else None


def build_window(config, demo=False, uri=None, hidden=False):
    root = tk.Tk()
    if hidden:
        root.withdraw()
    root.option_add("*Font", ("Microsoft YaHei UI", 10))
    root.title("USTC Report Watcher · 学术报告")
    root.geometry("1060x680")
    root.minsize(850, 550)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 10))
    status_text = tk.StringVar()
    ttk.Label(root, text="中科大学术报告", font=("Microsoft YaHei UI", 20, "bold")).pack(anchor="w", padx=20, pady=(16, 8))
    ttk.Label(root, textvariable=status_text, wraplength=1000).pack(anchor="w", padx=20, pady=(0, 10))
    toolbar = ttk.Frame(root)
    toolbar.pack(fill="x", padx=20, pady=5)
    mode = tk.StringVar(value="selectable")
    include_history = tk.BooleanVar(value=False)
    counts_text = tk.StringVar()
    ttk.Label(root, textvariable=counts_text).pack(anchor="w", padx=20, pady=(6, 0))
    tabs = ttk.Notebook(root)
    selectable_tab, online_tab = ttk.Frame(tabs), ttk.Frame(tabs)
    tabs.add(selectable_tab, text="当前可选")
    tabs.add(online_tab, text="线上会议")
    tabs.pack(fill="x", padx=20, pady=(8, 0))
    panes = ttk.Panedwindow(root, orient="vertical")
    list_frame, detail_frame = ttk.Frame(panes), ttk.Frame(panes)
    panes.add(list_frame, weight=3)
    panes.add(detail_frame, weight=2)
    tree = ttk.Treeview(list_frame, columns=("title", "speaker", "time", "type", "change"), show="headings", height=5)
    for key, title, width in (("title", "报告标题", 410), ("speaker", "报告人", 130), ("time", "开始时间", 170), ("type", "方式", 90), ("change", "最近变化", 170)):
        tree.heading(key, text=title)
        tree.column(key, width=width)
    tree.grid(row=0, column=0, sticky="nsew")
    list_frame.rowconfigure(0, weight=1)
    list_frame.columnconfigure(0, weight=1)
    tree_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
    tree_scroll.grid(row=0,column=1,sticky="ns")
    tree.configure(yscrollcommand=tree_scroll.set)
    details = tk.Text(detail_frame, height=5, wrap="word", font=("Microsoft YaHei UI", 10), padx=12, pady=10)
    details.pack(side="left",fill="both",expand=True)
    detail_scroll = ttk.Scrollbar(detail_frame, orient="vertical", command=details.yview)
    detail_scroll.pack(side="right",fill="y")
    details.configure(yscrollcommand=detail_scroll.set)
    actions = ttk.Frame(root)
    actions.pack(side="bottom", fill="x", padx=20, pady=(0, 15))
    panes.pack(fill="both",expand=True,padx=20,pady=10)
    data = {}
    results = queue.Queue()
    busy = {"value": False, "command": None, "started": 0, "notice": "", "stamp": None, "last_check": 0}
    saved_status = {"last_success": None, "last_run": None}
    database = config.root / "data/demo.db" if demo else config.path("database")

    def update_status():
        text = sync_status_text(saved_status, config['app']['timezone'], busy['command'],
                                time.monotonic() - busy['started'], busy['notice'])
        status_text.set(('离线演示 · ' if demo else '') + text)

    def selected():
        selection = tree.selection()
        return data.get(selection[0]) if selection else None

    def choose(event=None):
        item = selected()
        details.configure(state="normal")
        details.delete("1.0", "end")
        if item:
            report = item["report"]
            details.insert("end", f"{report.title_zh}\n报告 ID：{report.report_id}\n院系：{report.department}\n完整地点：{report.location_full or '未提供'}\n"
                           f"判别依据：{'；'.join(report.modality_reason)}\n开始：{report.start_at or '时间未确认'}\n结束：{report.end_at or '未提供'}\n"
                           f"选课截止：{report.registration_deadline or '未提供'}\n学校可选标记：{'是' if report.selectable_flag else '否或未确认'}\n"
                           f"首次发现：{item['first_seen_at']}\n最近检查：{item['last_seen_at']}\n详情：{report.description or '未提供'}")
        else:
            if not data and mode.get() == "online":
                details.insert("end", "当前没有待参加的线上/混合报告。勾选“包含历史报告”可以查看以往线上报告。")
            elif not data:
                details.insert("end", "当前可选列表为空。请查看上方同步状态，确认已成功同步。")
            else:
                details.insert("end", "选择一条报告查看完整地点、判别依据与参会信息。")
        details.configure(state="disabled")

    def reload():
        store = Store(database)
        try:
            status = store.status()
            items = store.reports()
        finally:
            store.close()
        stamp = status_stamp(status)
        if busy['stamp'] is not None and stamp != busy['stamp']:
            busy['notice'] = ''
        busy['stamp'] = stamp
        saved_status.clear()
        saved_status.update(status)
        update_status()
        previous = tree.selection()
        tree.delete(*tree.get_children())
        data.clear()
        now = datetime.now(ZoneInfo(config["app"]["timezone"]))
        selectable_count = sum(currently_selectable(item["report"], now) for item in items)
        online_count = sum(item["report"].modality in ("online", "hybrid") and (include_history.get() or upcoming(item["report"], now)) for item in items)
        counts_text.set(f"当前可选 {selectable_count} 场 · 线上会议 {online_count} 场（含混合报告{'、历史报告' if include_history.get() else '，仅待参加'}）")
        tabs.tab(selectable_tab, text=f"当前可选 ({selectable_count})")
        tabs.tab(online_tab, text=f"线上会议 ({online_count})")
        for index, item in enumerate(items):
            report = item["report"]
            if mode.get() == "selectable":
                if not currently_selectable(report, now):
                    continue
            elif report.modality not in ("online", "hybrid") or (not include_history.get() and not upcoming(report, now)):
                continue
            key = str(index)
            data[key] = item
            tree.insert("", "end", iid=key, values=(report.title_zh, report.speaker, (report.start_at or "未确认")[:16].replace("T", " "), LABELS[report.modality], item["changed_at"][:16].replace("T", " ")))
        selected_id = parse_qs(urlsplit(uri or "").query).get("id", [None])[0]
        if selected_id:
            selected_keys = [key for key, item in data.items() if item["report"].report_id == selected_id]
            if selected_keys:
                tree.selection_set(selected_keys[0])
        elif previous and previous[0] in data:
            tree.selection_set(previous[0])
        choose()

    def switch_tab(event=None):
        mode.set("selectable" if tabs.select() == str(selectable_tab) else "online")
        reload()

    def start(command):
        if busy["value"]:
            return
        if demo and command == "run-once":
            messagebox.showinfo("离线演示", "演示数据通过 run-once --fixture 更新。真实刷新请打开普通列表。")
            return
        busy["value"] = True
        busy.update(command=command, started=time.monotonic(), notice='')
        update_status()
        buttons[0].configure(text='刷新中…' if command == 'run-once' else '立即刷新')
        for button in buttons:
            button.configure(state="disabled")

        def worker():
            try:
                result = subprocess.run(launch_args(config, command, windowless=False),
                                        capture_output=True, text=True, encoding='utf-8',
                                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0, timeout=1000)
                payload = json.loads(result.stdout)
                results.put((command, result.returncode, payload))
            except Exception:
                results.put((command, 1, {'status': 'error', 'message': '启动检查或读取结果失败，请查看日志。'}))
        threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            command, code, payload = results.get_nowait()
            busy["value"] = False
            busy['command'] = None
            for button in buttons:
                button.configure(state="normal")
            buttons[0].configure(text='立即刷新')
            previous_stamp = busy['stamp']
            reload()
            if payload.get('status') == 'skipped' and busy['stamp'] == previous_stamp:
                busy['notice'] = '已有检查正在运行，正在等待完成；结果将自动更新'
            elif code:
                busy['notice'] = payload.get('error') or payload.get('message') or '操作未完成，请查看同步状态'
            elif command == 'login':
                busy['notice'] = '登录已保存，点击“立即刷新”同步报告'
            update_status()
            if code:
                messagebox.showinfo("未完成", "操作未成功，请查看同步状态或 logs 中的诊断。")
        except queue.Empty:
            pass
        if busy['value']:
            update_status()
        elif time.monotonic() - busy['last_check'] >= 3:
            busy['last_check'] = time.monotonic()
            store = Store(database)
            try:
                current = store.status()
            finally:
                store.close()
            if status_stamp(current) != busy['stamp']:
                reload()
        root.after(400, poll)

    def open_report():
        item = selected()
        webbrowser.open(item["report"].detail_url if item and item["report"].detail_url else PORTAL)

    buttons = [ttk.Button(toolbar, text="立即刷新", command=lambda: start("run-once")),
               ttk.Button(toolbar, text="重新登录", command=lambda: start("login")),
               ttk.Button(toolbar, text="查看本地最新结果", command=reload)]
    for button in buttons:
        button.pack(side="left", padx=(0, 10))
    ttk.Checkbutton(toolbar, text="线上列表包含历史报告", variable=include_history, command=reload).pack(side="left", padx=10)
    ttk.Button(actions, text="打开原始报告 / 学校入口", command=open_report).pack(side="left")
    tree.bind("<<TreeviewSelect>>", choose)
    tabs.bind("<<NotebookTabChanged>>", switch_tab)
    tree.bind("<Double-1>", lambda event: open_report())
    reload()
    poll()
    return root


def show(config, demo=False, uri=None):
    build_window(config, demo, uri).mainloop()
