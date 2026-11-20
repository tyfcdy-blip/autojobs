"""模板工具的回归测试：真实临时文件和进程，不触碰用户配置。"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from check_project import REQUIRED_DIRS, REQUIRED_FILES
from init_project import initialize
from project_support import ProjectError, validate_config


class ProjectToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="codex-template-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "项目 with spaces"
        self.root.mkdir()
        for relative in REQUIRED_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        for relative in REQUIRED_DIRS:
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        self.config_path = self.root / "project.config.json"
        self.original_config = self.config_path.read_bytes()
        self.config = json.loads(self.original_config)

    def run_script(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / script), *arguments],
            cwd=self.temporary.name, env=environment, text=True,
            encoding="utf-8", capture_output=True, timeout=20, check=False,
        )

    def assert_unchanged(self) -> None:
        self.assertEqual(self.original_config, self.config_path.read_bytes())
        self.assertFalse((self.root / ".env").exists())
        self.assertEqual([], list(self.root.glob(".project-config-*.tmp")))

    def test_fresh_initialization(self) -> None:
        result = self.run_script("init_project.py", "--name", "my-project", "--description", "中文项目")
        self.assertEqual(0, result.returncode, result.stderr)
        config = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual({"name": "my-project", "description": "中文项目"}, config["project"])
        self.assertEqual((self.root / ".env.example").read_bytes(), (self.root / ".env").read_bytes())
        self.assertFalse((self.root / ".git").exists())
        self.assertEqual([], list(self.root.glob(".project-config-*.tmp")))

    def test_default_arguments_keep_config_bytes_and_timestamp(self) -> None:
        timestamp = self.config_path.stat().st_mtime_ns
        result = self.run_script("init_project.py")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(self.original_config, self.config_path.read_bytes())
        self.assertEqual(timestamp, self.config_path.stat().st_mtime_ns)

    def test_repeat_preserves_existing_environment(self) -> None:
        env_path = self.root / ".env"
        env_path.write_bytes(b"LOCAL_VALUE=private-test-value\r\n")
        for _ in range(2):
            result = self.run_script("init_project.py", "--name", "repeat-project")
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("private-test-value", result.stdout + result.stderr)
        self.assertEqual(b"LOCAL_VALUE=private-test-value\r\n", env_path.read_bytes())

    def test_initialization_keeps_stack_and_commands(self) -> None:
        self.config["stack"]["jobs"] = "Python 3.12"
        self.config["verification"]["unit"] = ["python -m unittest discover -s tests/unit -v"]
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        result = self.run_script("init_project.py", "--name", "renamed")
        self.assertEqual(0, result.returncode, result.stderr)
        updated = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(self.config["stack"], updated["stack"])
        self.assertEqual(self.config["verification"], updated["verification"])

    def test_invalid_names_fail_without_writes(self) -> None:
        for name in ("", "../outside", "UPPER", "a b", "a--b", "a-", "1abc", "项目", "a" * 64, "x;whoami"):
            with self.subTest(name=name):
                result = self.run_script("init_project.py", f"--name={name}")
                self.assertNotEqual(0, result.returncode)
                self.assert_unchanged()

    def test_name_length_boundaries(self) -> None:
        for name in ("a", "a" * 63, "a-1"):
            with self.subTest(length=len(name)):
                result = self.run_script("init_project.py", "--name", name)
                self.assertEqual(0, result.returncode, result.stderr)

    def test_description_boundaries(self) -> None:
        rejected = self.run_script("init_project.py", "--description", "字" * 501)
        self.assertNotEqual(0, rejected.returncode)
        self.assert_unchanged()
        for description in ("", "字" * 500):
            with self.subTest(length=len(description)):
                accepted = self.run_script("init_project.py", f"--description={description}")
                self.assertEqual(0, accepted.returncode, accepted.stderr)
                actual = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.assertEqual(description, actual["project"]["description"])

    def test_invalid_json_is_not_echoed_or_modified(self) -> None:
        invalid_bytes = b'{"sensitive-marker": "not-closed'
        self.config_path.write_bytes(invalid_bytes)
        for script in ("init_project.py", "check_project.py"):
            result = self.run_script(script)
            self.assertNotEqual(0, result.returncode)
            self.assertNotIn("sensitive-marker", result.stdout + result.stderr)
            self.assertEqual(invalid_bytes, self.config_path.read_bytes())
        self.assertFalse((self.root / ".env").exists())

    def test_invalid_utf8_fails_cleanly(self) -> None:
        self.config_path.write_bytes(b"\xff\xfe")
        result = self.run_script("init_project.py")
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / ".env").exists())

    def test_unpaired_unicode_surrogates_fail_before_writes(self) -> None:
        for section, field, value in (
            ("project", "description", "\ud800"),
            ("stack", "jobs", "\udfff"),
            ("verification", "unit", ["\ud800"]),
        ):
            with self.subTest(section=section):
                config = copy.deepcopy(self.config)
                config[section][field] = value
                encoded = json.dumps(config).encode("utf-8")
                self.config_path.write_bytes(encoded)
                for script in ("init_project.py", "check_project.py"):
                    arguments = ("--name", "changed") if script == "init_project.py" else ()
                    result = self.run_script(script, *arguments)
                    self.assertNotEqual(0, result.returncode)
                    self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(encoded, self.config_path.read_bytes())
                self.assertFalse((self.root / ".env").exists())
                self.assertEqual([], list(self.root.glob(".project-config-*.tmp")))

    def test_utf8_bom_is_accepted(self) -> None:
        self.config_path.write_bytes(b"\xef\xbb\xbf" + self.original_config)
        result = self.run_script("init_project.py", "--name", "bom-test")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.config_path.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_invalid_configuration_types_are_rejected(self) -> None:
        invalid_configs = [None, [], {**self.config, "unknown": True}]
        mutations = (
            ("format_version", True), ("format_version", 2), ("project", []),
            ("project", {"name": "valid", "description": 3}),
            ("stack", {"backend": "", "frontend": None, "jobs": None}),
            ("stack", {"backend": None}),
            ("verification", {**self.config["verification"], "unit": "python -m unittest"}),
            ("verification", {**self.config["verification"], "unit": [" "]}),
            ("verification", {**self.config["verification"], "unit": [1]}),
        )
        for key, value in mutations:
            config = copy.deepcopy(self.config)
            config[key] = value
            invalid_configs.append(config)
        for config in invalid_configs:
            with self.subTest(config=config):
                with self.assertRaises(ProjectError):
                    validate_config(config)

    def test_missing_example_prevents_metadata_update(self) -> None:
        (self.root / ".env.example").unlink()
        result = self.run_script("init_project.py", "--name", "changed")
        self.assertNotEqual(0, result.returncode)
        self.assert_unchanged()

    def test_environment_directory_is_preserved(self) -> None:
        env_path = self.root / ".env"
        env_path.mkdir()
        (env_path / "keep.txt").write_text("preserve", encoding="utf-8")
        result = self.run_script("init_project.py", "--name", "changed")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.original_config, self.config_path.read_bytes())
        self.assertEqual("preserve", (env_path / "keep.txt").read_text(encoding="utf-8"))

    def make_symlink(self, path: Path, target: Path) -> None:
        try:
            path.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"当前环境不支持创建符号链接：{type(exc).__name__}")

    def test_environment_symlink_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside.env"
        outside.write_text("unchanged", encoding="utf-8")
        self.make_symlink(self.root / ".env", outside)
        result = self.run_script("init_project.py", "--name", "changed")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("unchanged", outside.read_text(encoding="utf-8"))
        self.assertEqual(self.original_config, self.config_path.read_bytes())

    def test_dangling_environment_symlink_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "missing.env"
        self.make_symlink(self.root / ".env", outside)
        result = self.run_script("init_project.py")
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(outside.exists())
        self.assertEqual(self.original_config, self.config_path.read_bytes())

    def test_config_symlink_is_rejected(self) -> None:
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_bytes(self.original_config)
        self.config_path.unlink()
        self.make_symlink(self.config_path, outside)
        result = self.run_script("init_project.py", "--name", "changed")
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(self.original_config, outside.read_bytes())
        self.assertFalse((self.root / ".env").exists())

    def test_failed_replace_rolls_back_new_environment(self) -> None:
        with patch("init_project.os.replace", side_effect=PermissionError("injected failure")):
            with self.assertRaises(PermissionError):
                initialize(self.root, "changed", None)
        self.assert_unchanged()

    def test_failed_replace_preserves_existing_environment(self) -> None:
        (self.root / ".env").write_bytes(b"preserve")
        with patch("init_project.os.replace", side_effect=PermissionError("injected failure")):
            with self.assertRaises(PermissionError):
                initialize(self.root, "changed", None)
        self.assertEqual(b"preserve", (self.root / ".env").read_bytes())
        self.assertEqual(self.original_config, self.config_path.read_bytes())
        self.assertEqual([], list(self.root.glob(".project-config-*.tmp")))

    def test_check_passes_and_does_not_create_environment(self) -> None:
        # 此用例验证未登记命令的模板，不依赖当前项目是否已经开始业务开发。
        self.config["verification"] = {name: [] for name in self.config["verification"]}
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.original_config = self.config_path.read_bytes()
        result = self.run_script("check_project.py")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("尚未配置", result.stdout)
        self.assert_unchanged()

    def test_check_reports_missing_file(self) -> None:
        (self.root / "AGENTS.md").unlink()
        result = self.run_script("check_project.py")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("AGENTS.md", result.stderr)

    def test_check_reports_empty_file(self) -> None:
        (self.root / "README.md").write_bytes(b"")
        result = self.run_script("check_project.py")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("README.md", result.stderr)

    def test_check_reports_missing_directory(self) -> None:
        (self.root / "tests" / "e2e").rmdir()
        result = self.run_script("check_project.py")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("tests/e2e", result.stderr)

    def test_registered_commands_are_never_executed(self) -> None:
        self.config["verification"]["build"] = ["command-that-does-not-exist"]
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        result = self.run_script("check_project.py")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("build", result.stdout)

    def test_foreign_working_directory_is_untouched(self) -> None:
        result = self.run_script("init_project.py", "--name", "foreign-cwd")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((Path(self.temporary.name) / ".env").exists())
        self.assertFalse((Path(self.temporary.name) / "project.config.json").exists())

    def test_powershell_wrapper_forwards_arguments_and_failure(self) -> None:
        powershell = shutil.which("pwsh")
        if powershell is None:
            self.skipTest("PowerShell 7 不可用；Python 入口由其他用例验证。")
        prefix = [powershell, "-NoProfile", "-File", str(self.root / "scripts" / "init.ps1")]
        description = '中文 with "quotes" and spaces'
        success = subprocess.run(
            [*prefix, "-Name", "wrapped", "-Description", description],
            cwd=self.temporary.name, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, success.returncode, success.stderr)
        actual = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(description, actual["project"]["description"])
        self.assertEqual("wrapped", actual["project"]["name"])
        failure = subprocess.run(
            [*prefix, "-Name", "Invalid"], cwd=self.temporary.name,
            capture_output=True, timeout=30, check=False,
        )
        self.assertNotEqual(0, failure.returncode)

    def test_legacy_powershell_is_rejected_before_writes(self) -> None:
        powershell = shutil.which("powershell") if os.name == "nt" else None
        if powershell is None:
            self.skipTest("Windows PowerShell 5.1 不可用。")
        result = subprocess.run(
            [powershell, "-NoProfile", "-File", str(self.root / "scripts" / "init.ps1"),
             "-Name", "legacy", "-Description", 'quote "inside" text'],
            cwd=self.temporary.name, capture_output=True, timeout=30, check=False,
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn(b"PowerShell 7.3+", result.stderr)
        self.assert_unchanged()


if __name__ == "__main__":
    unittest.main()
