"""Absolute-path launcher for Task Scheduler, protocol activation and pythonw."""
from pathlib import Path
import sys
from datetime import datetime

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
if __name__ == "__main__":
    try:
        from ustc_report_watcher.cli import main
        raise SystemExit(main())
    except Exception as error:
        # Avoid an invisible pythonw failure, without logging credential-containing exceptions.
        (root / "logs").mkdir(exist_ok=True)
        with (root / "logs/launcher.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now().isoformat()} launcher failed: {type(error).__name__}\n")
        raise SystemExit(1)
