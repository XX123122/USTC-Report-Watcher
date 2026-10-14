"""Current-user Windows DPAPI; never log credential payloads."""
import ctypes
import json
import os
import subprocess
import csv
from pathlib import Path
from ctypes import wintypes

_secured = set()
_sid = None


def secure_directory(path: Path):
    """Restrict inherited project-directory access; children inherit user/SYSTEM permissions."""
    global _sid
    path.mkdir(parents=True, exist_ok=True)
    if os.name != 'nt' or path.resolve() in _secured:
        return
    if _sid is None:
        identity = subprocess.run(['whoami.exe','/user','/fo','csv','/nh'], capture_output=True,
                                  text=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if identity.returncode:
            raise RuntimeError('无法确认 Windows 用户以限制本地目录权限。')
        _sid = next(csv.reader(identity.stdout.strip().splitlines()))[-1]
    command = ['icacls.exe', str(path.resolve()), '/inheritance:r', '/grant:r',
               f'*{_sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F',
               '/remove:g', '*S-1-1-0', '*S-1-5-11', '*S-1-5-32-545']
    result = subprocess.run(command, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError('无法限制登录态/数据目录权限；请确认当前用户拥有项目目录。')
    _secured.add(path.resolve())


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def crypt(data: bytes, decrypt=False) -> bytes:
    if os.name != "nt":
        raise RuntimeError("登录态加密需要 Windows DPAPI。")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise RuntimeError("无法读取/保存当前 Windows 用户的加密登录态。")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


def save_secret(path: Path, value):
    secure_directory(path.parent)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(crypt(json.dumps(value, ensure_ascii=False).encode("utf-8")))
    os.replace(temporary, path)


def load_secret(path: Path):
    return json.loads(crypt(path.read_bytes(), decrypt=True))
