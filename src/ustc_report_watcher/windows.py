import base64
import os
import subprocess
import sys
from pathlib import Path


class WindowsOperationError(RuntimeError):
    def __init__(self, diagnostic):
        super().__init__("Windows 操作失败，请检查任务计划程序/通知权限。")
        self.diagnostic = diagnostic


def powershell(script, timeout=45):
    if os.name != "nt":
        raise RuntimeError("此功能需要 Windows 10/11。")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        # Do not return PowerShell source or arbitrary payloads on errors.
        raise WindowsOperationError(result.stderr)
    return result.stdout.strip()


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def launch_args(config, command, *extras, windowless=True):
    executable = Path(sys.executable)
    if windowless:
        candidate = executable.with_name("pythonw.exe")
        if candidate.exists():
            executable = candidate
    runner = Path(__file__).resolve().parents[2] / "scripts" / "runner.py"
    return [str(executable), str(runner), "--config", str(config.file), command, *extras]
