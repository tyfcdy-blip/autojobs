"""通过明确句柄白名单挂起创建子进程，避免泄漏监督句柄。"""

from __future__ import annotations

import ctypes
import subprocess
from ctypes import wintypes
from pathlib import Path


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _StartupInfoEx(ctypes.Structure):
    _fields_ = [("StartupInfo", _StartupInfo), ("lpAttributeList", wintypes.LPVOID)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def create_suspended(
    python: Path,
    entrypoint: Path,
    cwd: Path,
    env: dict[str, str],
    stdin_handle: int,
    stdout_handle: int,
    stderr_handle: int,
) -> tuple[int, int, int]:
    """返回进程句柄、主线程句柄和 PID，成功后句柄归调用方所有。"""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    initialize = kernel.InitializeProcThreadAttributeList
    initialize.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    initialize.restype = wintypes.BOOL
    update = kernel.UpdateProcThreadAttribute
    update.argtypes = [
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.c_size_t,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    update.restype = wintypes.BOOL
    delete = kernel.DeleteProcThreadAttributeList
    delete.argtypes = [wintypes.LPVOID]
    delete.restype = None
    create = kernel.CreateProcessW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPCWSTR,
        ctypes.POINTER(_StartupInfoEx),
        ctypes.POINTER(_ProcessInfo),
    ]
    create.restype = wintypes.BOOL

    size = ctypes.c_size_t()
    initialize(None, 1, 0, ctypes.byref(size))
    if not size.value:
        raise ctypes.WinError(ctypes.get_last_error())
    attributes = ctypes.create_string_buffer(size.value)
    if not initialize(attributes, 1, 0, ctypes.byref(size)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        handles = (wintypes.HANDLE * 3)(stdin_handle, stdout_handle, stderr_handle)
        if not update(attributes, 0, 0x00020002, handles, ctypes.sizeof(handles), None, None):
            raise ctypes.WinError(ctypes.get_last_error())
        startup = _StartupInfoEx()
        startup.StartupInfo.cb = ctypes.sizeof(startup)
        startup.StartupInfo.dwFlags = 0x00000100  # STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = stdin_handle
        startup.StartupInfo.hStdOutput = stdout_handle
        startup.StartupInfo.hStdError = stderr_handle
        startup.lpAttributeList = ctypes.addressof(attributes)
        command = ctypes.create_unicode_buffer(
            subprocess.list2cmdline([str(python), "-u", str(entrypoint)])
        )
        environment = ctypes.create_unicode_buffer(
            "\x00".join(
                f"{key}={value}"
                for key, value in sorted(env.items(), key=lambda pair: pair[0].upper())
            )
            + "\x00\x00"
        )
        process = _ProcessInfo()
        # CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT | EXTENDED_STARTUPINFO_PRESENT
        # CREATE_NO_WINDOW 避免后台测试/任务弹出控制台，桌面应用另由脚本创建。
        flags = 0x00000004 | 0x00000400 | 0x00080000 | 0x08000000
        if not create(
            str(python),
            command,
            None,
            None,
            True,
            flags,
            environment,
            str(cwd),
            ctypes.byref(startup),
            ctypes.byref(process),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(process.hProcess), int(process.hThread), int(process.dwProcessId)
    finally:
        delete(attributes)
