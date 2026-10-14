from datetime import timedelta
from tkinter import ttk
from ustc_report_watcher.models import Report
from ustc_report_watcher.viewer import build_window, sync_status_text


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def close_window(root):
    for callback in root.tk.call('after', 'info'):
        root.after_cancel(callback)
    root.destroy()


def test_two_independent_views(store, config, now):
    from ustc_report_watcher.storage import Store
    value = Store(config.path('database'))
    # Future relative to actual machine time so this stays a real GUI integration test.
    future = '2099-10-19T10:00:00+08:00'
    cutoff = '2099-10-19T09:00:00+08:00'
    value.commit_batch([
        Report('offline','可选线下报告',modality='offline',selectable_flag=True,start_at=future,registration_deadline=cutoff),
        Report('online','线上报告',modality='online',selectable_flag=False,start_at=future),
    ],config,now)
    value.close()
    root = build_window(config, hidden=True)
    try:
        root.update()
        notebook = next(widget for widget in root.winfo_children() if isinstance(widget,ttk.Notebook))
        table = next(widget for widget in descendants(root) if isinstance(widget,ttk.Treeview))
        assert '当前可选 (1)' == notebook.tab(0,'text')
        assert '线上会议 (1)' == notebook.tab(1,'text')
        assert table.item(table.get_children()[0],'values')[0] == '可选线下报告'
        notebook.select(1)
        root.update()
        assert len(table.get_children()) == 1
        assert table.item(table.get_children()[0],'values')[0] == '线上报告'
    finally:
        close_window(root)


def test_refresh_stays_visible_across_tab_changes_and_updates_on_completion(config, now, monkeypatch):
    import threading
    import json
    import time
    from subprocess import CompletedProcess
    from ustc_report_watcher.storage import Store
    value = Store(config.path('database'))
    config['notification']['first_run_mode'] = 'silent'
    value.commit_batch([],config,now)
    value.close()
    release = threading.Event()
    completed = threading.Event()
    finished = now + timedelta(minutes=2)

    def fake_process(args, **kwargs):
        assert release.wait(3)
        value = Store(config.path('database'))
        try:
            value.commit_batch([],config,finished,started_at=now)
        finally:
            value.close()
        completed.set()
        return CompletedProcess(args,0,stdout=json.dumps({'status':'success','completed_at':finished.isoformat()}))

    monkeypatch.setattr('ustc_report_watcher.viewer.execute_command',fake_process)
    root = build_window(config,hidden=True)
    try:
        root.update()
        button = next(w for w in descendants(root) if isinstance(w,ttk.Button) and w.cget('text')=='立即刷新')
        notebook = next(w for w in descendants(root) if isinstance(w,ttk.Notebook))
        button.invoke()
        notebook.select(1)
        root.update()
        labels = [w for w in descendants(root) if isinstance(w,ttk.Label)]
        assert button.cget('text') == '刷新中…'
        assert button.instate(['disabled'])
        assert any('正在刷新' in str(w.cget('text')) for w in labels)
        release.set()
        assert completed.wait(3)
        deadline = time.monotonic()+3
        while button.instate(['disabled']) and time.monotonic()<deadline:
            root.update()
            time.sleep(0.01)
        assert not button.instate(['disabled'])
        assert any(finished.strftime('%Y-%m-%d %H:%M:%S') in str(w.cget('text')) for w in labels)
        assert not any('正在刷新' in str(w.cget('text')) for w in labels)
    finally:
        release.set()
        close_window(root)


def test_background_sync_automatically_updates_an_open_window(config, now, monkeypatch):
    import time
    from ustc_report_watcher.storage import Store
    value = Store(config.path('database'))
    value.commit_batch([],config,now)
    value.close()
    root = build_window(config,hidden=True)
    try:
        root.update()
        finished = now+timedelta(hours=1)
        value = Store(config.path('database'))
        value.commit_batch([],config,finished)
        value.close()
        real_monotonic = time.monotonic
        monkeypatch.setattr('ustc_report_watcher.viewer.time.monotonic',lambda: real_monotonic()+4)
        deadline = real_monotonic()+3
        while real_monotonic()<deadline:
            root.update()
            labels = [w for w in descendants(root) if isinstance(w,ttk.Label)]
            if any(finished.strftime('%Y-%m-%d %H:%M:%S') in str(w.cget('text')) for w in labels):
                break
            time.sleep(0.01)
        assert any(finished.strftime('%Y-%m-%d %H:%M:%S') in str(w.cget('text')) for w in labels)
    finally:
        close_window(root)


def test_status_text_distinguishes_waiting_and_failure(now):
    status={'last_success':now.isoformat(),'last_run':{'id':1,'status':'failed','error':'网络不可用'}}
    assert '最近同步失败' in sync_status_text(status)
    assert '正在刷新，已用时 30 秒' in sync_status_text(status,command='run-once',elapsed=30)
    assert '正在等待' in sync_status_text(status,notice='已有检查正在运行，正在等待完成')


def test_skipped_refresh_waits_for_existing_check_instead_of_claiming_success(config, now, monkeypatch):
    import json
    import time
    from subprocess import CompletedProcess
    from ustc_report_watcher.storage import Store
    value=Store(config.path('database'))
    value.commit_batch([],config,now)
    value.close()
    monkeypatch.setattr('ustc_report_watcher.viewer.execute_command',lambda args,**kwargs: CompletedProcess(args,0,stdout=json.dumps({'status':'skipped'})))
    root=build_window(config,hidden=True)
    try:
        root.update()
        button=next(w for w in descendants(root) if isinstance(w,ttk.Button) and w.cget('text')=='立即刷新')
        button.invoke()
        deadline=time.monotonic()+3
        while button.instate(['disabled']) and time.monotonic()<deadline:
            root.update()
            time.sleep(0.01)
        labels=[w for w in descendants(root) if isinstance(w,ttk.Label)]
        assert any('已有检查正在运行，正在等待完成' in str(w.cget('text')) for w in labels)
        assert any(now.strftime('%Y-%m-%d %H:%M:%S') in str(w.cget('text')) for w in labels)
    finally:
        close_window(root)
