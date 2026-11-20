"""由被检查的 Python 执行；仅读取版本和包元数据，不导入业务依赖。"""

import importlib.metadata
import json
import os
import platform
import sys


def main() -> None:
    names = json.loads(os.environ.get("AUTOJOBS_PROBE_PACKAGES", "[]"))
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    print(json.dumps({
        "executable": sys.executable,
        "version": platform.python_version(),
        "architecture": platform.machine(),
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "packages": versions,
        "markers": {
            "implementation_name": sys.implementation.name,
            "implementation_version": platform.python_version(),
            "os_name": os.name,
            "platform_machine": platform.machine(),
            "platform_release": platform.release(),
            "platform_system": platform.system(),
            "platform_version": platform.version(),
            "python_full_version": platform.python_version(),
            "platform_python_implementation": platform.python_implementation(),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "sys_platform": sys.platform,
        },
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
