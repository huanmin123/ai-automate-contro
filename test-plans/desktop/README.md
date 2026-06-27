# 桌面回归计划

`test-plans/desktop/basic/plan.json` 是稳定 smoke 示例，只验证桌面 backend 探测、窗口列表、截图、snapshot、截图断言和 `capability_matrix`。

真实系统 App 回归不要固定成长期静态 plan。使用动态自检入口：

```powershell
python .\cplan.py self-check desktop-real-app
```

该入口会创建临时 plan 包和临时资源文件。Windows 当前启动 Notepad、Explorer 和临时 WinForms Open/Save 文件对话框，macOS 启动 TextEdit 或系统可用轻量 App，覆盖窗口等待、聚焦、控件列表/定位、输入、保存、文件选择、对话框截图、关闭和关闭后 `not_exists`。

综合桌面组件回归：

```powershell
python .\cplan.py self-check desktop-components
```

`desktop-components` 还会运行 schema、失败采集、launch-only、`desktop_vision locate_image`、临时表单、输入依赖和 capability diagnostics。
