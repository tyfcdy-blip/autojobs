# 测试组织

当前 `unit/test_project_tools.py` 使用标准库 unittest，包含配置单元测试和通过独立进程执行工具的集成检查，统一入口为：

```text
python -m unittest discover -s tests/unit -v
```

用例在临时目录创建最小输入副本，不读取真实 `.env` 或业务数据；测试结束清理临时目录。工具测试不代表业务系统存在或通过验证。

应用内部测试遵循技术栈约定；根 `integration/` 留给真实跨模块集成，`e2e/` 留给真实用户流程。当前这两类业务测试未建立，不填写虚假的通过状态。完整规范见 `docs/standards/testing.md`。
