import argparse
import json
import os
import sys
from .config import Config


def output(value):
    if sys.stdout:
        print(json.dumps(value, ensure_ascii=False, indent=2) if not isinstance(value, str) else value)


def main(argv=None):
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Windows 本地中科大学术报告监控")
    parser.add_argument("--config", default="config.yaml", help="配置文件，所有相对路径基于其目录")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="写入默认配置（不覆盖现有文件）")
    login_parser = sub.add_parser("login", help="在独立 Edge 窗口正常登录并加密保存会话")
    login_parser.add_argument("--timeout", type=int, default=900)
    sub.add_parser("discover", help="从本机调查数据导出脱敏字段结构")
    run = sub.add_parser("run-once", help="立即检查一次")
    run.add_argument("--dry-run", action="store_true", help="只采集分类，不写历史或通知")
    run.add_argument("--fixture", help="离线样例，只写独立 demo 数据库，不发送通知")
    view = sub.add_parser("show", help="打开本地汇总窗口")
    view.add_argument("--demo", action="store_true")
    view.add_argument("--uri", help=argparse.SUPPRESS)
    sub.add_parser("test-notification", help="发送一条可点击的原生通知")
    sub.add_parser("install-task", help="安装当前用户登录和周期任务")
    sub.add_parser("uninstall-task", help="卸载自动检查任务，保留历史和登录态")
    status = sub.add_parser("status", help="同步状态和 Windows 任务状态")
    status.add_argument("--demo", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = Config(args.config)
        if args.command == "init":
            import yaml
            if not config.file.exists():
                config.file.parent.mkdir(parents=True, exist_ok=True)
                config.file.write_text(yaml.safe_dump(config.data, allow_unicode=True, sort_keys=False), encoding="utf-8")
            output(f"配置已准备：{config.file}")
        elif args.command == "login":
            from .auth import login
            from .locking import run_lock
            with run_lock(config.root / '.auth/login.lock'):
                count = login(config, args.timeout)
            output({"status": "saved", "captured_json_responses": count, "encryption": "Windows DPAPI current user"})
        elif args.command == "discover":
            from .discovery import discover, configure_verified_source
            configure_verified_source(config)
            output(discover(config))
        elif args.command == "run-once":
            from .main import run_once
            result = run_once(config, args.dry_run, args.fixture)
            output(result)
            return 0 if result["status"] in ("success", "dry_run", "skipped") else 2
        elif args.command == "show":
            from .viewer import show
            show(config, args.demo, args.uri)
        elif args.command == "test-notification":
            from .notifier import Notifier
            result = Notifier(config).send("中科大学术报告 · 通知测试", "点击此通知，打开本地报告列表。检查进程退出后仍可点击。")
            output({"notification": result, "note": "提交成功不代表已显示；请检查通知中心及勿扰模式。"})
        elif args.command == "install-task":
            from .scheduler import install
            output(json.loads(install(config)))
        elif args.command == "uninstall-task":
            from .scheduler import uninstall
            uninstall()
            output("自动检查任务已卸载，历史与登录态保留。")
        elif args.command == "status":
            from .storage import Store
            from .scheduler import status
            database = config.root / "data/demo.db" if args.demo else config.path("database")
            if database.exists():
                store = Store(database)
                try:
                    value = store.status()
                finally:
                    store.close()
            else:
                value = {"last_success": None, "last_run": None}
            value["auth_saved"] = config.path("auth_state").exists()
            try:
                value["task"] = json.loads(status()) if os.name == "nt" else {"installed": False}
            except RuntimeError:
                value["task"] = {"error": "无法查询任务计划程序。"}
            output(value)
        return 0
    except Exception as error:
        from .auth import AuthExpired, StructureError
        from .fetcher import PartialFetch
        from .windows import WindowsOperationError
        message = str(error) if isinstance(error, (AuthExpired, StructureError, PartialFetch, ValueError, WindowsOperationError)) else "操作失败，请检查依赖、网络、Windows 权限或本地配置。"
        output({"status": "error", "error_type": type(error).__name__, "message": message})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
