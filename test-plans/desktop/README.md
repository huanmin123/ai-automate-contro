# 桌面回归计划

`test-plans/desktop/basic/plan.json` 是稳定 smoke 示例，只验证桌面 backend 探测、窗口列表、截图、snapshot、截图断言和 `capability_matrix`。

`test-plans/desktop/readonly-observe/plan.json` 是只读观察示例，输出 `observe.json`、`capability-matrix.json`、`target-candidates.json` 和窗口列表，适合验证 `desktop_capture type=observe` 与候选结构。

`test-plans/desktop/offline-vision/plan.json` 是离线图像定位示例，使用 plan 包内 PPM 图片作为 `source_path/template_path`，验证 `desktop_vision locate_image`、离线 source 的 `screen_clickable=false` 候选和视觉产物结构。

静态示例自检入口：

```powershell
python .\cplan.py self-check desktop-env --require-input --require-vision --require-ocr --require-ocr-zh
python .\cplan.py self-check desktop-examples --require-vision
```

真实系统 App 回归不要固定成长期静态 plan。使用动态自检入口：

```powershell
python .\cplan.py self-check desktop-real-app
```

该入口会创建临时 plan 包和临时资源文件。Windows 当前启动 Notepad、Explorer、可见 PowerShell 终端和临时 WinForms Open/Save 文件对话框，macOS 启动 TextEdit 或系统可用轻量 App，覆盖启动后等待窗口、活动窗口读取、窗口查询、聚焦、控件列表/定位、输入、保存、终端命令执行、文件选择、对话框截图、关闭和关闭后 `not_exists`。

综合桌面组件回归：

```powershell
python .\cplan.py self-check desktop-components
```

`desktop-components` 还会运行 schema、失败采集、launch-only、`desktop_vision locate_image`、临时表单、输入依赖和 capability diagnostics。

场景级桌面回归：

```powershell
python .\cplan.py self-check desktop-scenarios
python .\cplan.py self-check desktop-scenario-apps
```

`desktop-scenarios` 使用纯 mock 状态机覆盖游戏日常、聊天发送、定时群消息、窗口恢复、弹窗处理、重复观察和防无限循环。

`desktop-scenario-apps` 在 Windows 上动态生成受控 WinForms mock chat、mock game、mock recovery 和 mock interference 窗口，运行真实 desktop plan，覆盖窗口启动、聚焦、控件操作、消息发送、游戏奖励/副本、最小化恢复、阻塞弹窗、同标题多窗口、topmost 遮挡、用户抢焦点、目标窗口移动、`window_id` 锁定、`desktop_input target=element_center` 点击归属、截图证据、状态断言、结果文件、关闭链路和 plan 合同检查。

桌面稳定性复跑使用 release matrix 的重复入口：

```powershell
python .\cplan.py self-check release-matrix --only desktop_env,desktop_examples,desktop_scenarios,desktop_scenario_apps,desktop_components,desktop_real_app,ai_desktop_loop --repeat 3 --fail-fast --step-timeout-seconds 1200
```
