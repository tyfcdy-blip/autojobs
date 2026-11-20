"""为 pywin32 当前存根缺失的句柄构造声明精确类型。"""

from __future__ import annotations

from typing import Protocol


class NativeHandle(Protocol):
    def __int__(self) -> int: ...

    def Close(self) -> None: ...
