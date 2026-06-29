# Windows 桌面能力清单

本文记录当前 Windows 开发机已经验证的桌面控制能力、依赖状态和回归入口。这里是开发验收说明，不是 AI 写 plan 的教程；AI 创建 plan 仍读取 `handbook/`。

## 当前能力

- 执行线隔离：`automation_type=desktop` 独立于 browser，桌面 action、handbook 目录和质量门禁已分区。
- 桌面探测：`open_desktop`、`inspect_desktop`、`desktop_capture type=observe/snapshot` 返回 `capability_matrix`、`coordinate_profile`、窗口摘要、候选和诊断；`desktop_capture type=observe` 和 `desktop_vision` 会保存当前 session 最近 `target_candidates`。
- 窗口能力：窗口列表、查询、活动窗口读取、聚焦、关闭、最小化、最大化、还原。
- 真实 App：受控 WinForms 编辑器、Explorer、可见 PowerShell 终端、临时 WinForms Open/Save 文件对话框。
- 控件能力：WinForms TextBox、Button、CheckBox、ComboBox、ListBox、DataGridView、TreeView、MenuStrip、ContextMenuStrip、滚动 Panel；WPF TextBox、Button、CheckBox、ComboBox、ListBox、DataGrid、TreeView、Menu、ContextMenu、ScrollViewer 已有独立严格回归。
- 控件操作：控件树 dump、find、get_text、get_state、click、set_text、select、invoke、get_table、select_cell、get_tree、expand_tree、collapse_tree、select_tree、invoke_menu、scroll_element。
- 输入能力：键盘、快捷键、剪贴板输入、鼠标点击、双击、右键、滚轮、拖拽、`current_window_offset`、`element_center`、`bounds_center`、`target=candidate`、`candidate_source=latest`。
- 断言能力：窗口、截图、控件状态、控件文本、控件属性和控件候选数量断言。
- 截图和标注：全屏、区域、窗口、控件截图，桌面输入/控件操作 PNG+JSON 标注。
- 坐标诊断：`CoordinateMapper` v1 封装 local/screen offset 转换和输入安全边界检查；当前只记录 scale，不把未校准 DPI/缩放直接乘进点击坐标。
- 视觉定位：OpenCV 模板匹配，支持全图、区域、窗口 source、控件 source、离线 source_path，输出全局/局部坐标。
- OCR：Tesseract 英文和简体中文 OCR，支持 `desktop_vision type=locate_text`、TSV blocks、全局/局部坐标和标注证据。
- 失败诊断：失败桌面截图、桌面状态 JSON、活动窗口、鼠标位置、Window Query/Element Locator near matches、`target_candidates` 和修复建议。
- AI 终端闭环：`inspect_desktop -> create/write/validate/review/run_plan`、桌面失败 debug workspace、`propose_debug_fix`、debug plan、patch 生成、HITL apply 守卫。
- 真实模型回归：真实 gpt-5.5 已验证桌面 smoke plan 工具链、JSON 产物读取、执行线确认、PowerShell 终端和 Explorer 意图分类。

## 当前依赖

- PowerShell 7 可用。
- WPF runtime 可用，PowerShell STA 可加载 `PresentationFramework`、`PresentationCore`、`WindowsBase`。
- `pyautogui`、`pyperclip` 可用。
- `Pillow.ImageGrab` 和 `opencv-python` 可用。
- Tesseract 安装在 `E:\Tesseract`，`eng`、`chi_sim`、`osd` 语言包可用。
- `mss=false`、`pywinauto=false` 当前不阻断能力；它们属于后续增强依赖。

详细安装来源、PATH、Tesseract installer 和语言包下载记录见 [桌面依赖安装说明](./桌面依赖安装说明.md)。

## 已通过验收

2026-06-28 当前机器已通过：

```powershell
python .\cplan.py self-check release-matrix --strict-desktop --fail-fast --step-timeout-seconds 1200
python .\cplan.py self-check release-matrix --strict-desktop --only desktop_components --only desktop_real_app --only ai_desktop_loop --repeat 2 --fail-fast --step-timeout-seconds 1200
python .\main.py self-check ai-real-desktop-loop --api-key-file D:\模型密钥.txt --model gpt-5.5 --timeout-seconds 240 --max-attempts 5 --retry-delay-seconds 3
python .\main.py self-check ai-real-execution-line --api-key-file D:\模型密钥.txt --model gpt-5.5 --timeout-seconds 240 --max-attempts 5 --retry-delay-seconds 3
```

其中完整 strict release matrix 覆盖 `compileall`、`tool_check`、`handbook`、`workspace_clean`、`ai_tools`、`ai_terminal`、`ai_plan_generation`、`desktop_env --require-input --require-vision --require-ocr --require-ocr-zh`、`desktop_examples --require-vision`、`desktop_components --require-input --require-vision --require-ocr --require-ocr-zh`、`desktop_real_app` 和 `ai_desktop_loop`；WPF 用 `--require-desktop-wpf` 单独加严。

稳定性复跑两轮覆盖：

- `desktop_components --require-input --require-vision --require-ocr --require-ocr-zh`
- `desktop_real_app`
- `ai_desktop_loop`

2026-06-29 当前机器新增通过：

```powershell
python .\cplan.py self-check desktop-examples --require-vision
python .\cplan.py self-check desktop-components --require-input
python .\cplan.py self-check desktop-components --require-wpf
python .\cplan.py self-check desktop-components --require-vision --require-ocr --require-ocr-zh
python .\cplan.py self-check release-matrix --only desktop_components --require-desktop-input --require-desktop-wpf --fail-fast --step-timeout-seconds 1200
```

本次补充覆盖 `candidate_source=latest`、`desktop_assert type=element` 属性/数量断言、`desktop-examples` 的 observe/vision 产物结构断言、组件级严格输入门禁、`CoordinateMapper` v1 诊断和 WPF 复杂控件夹具。`--require-desktop-wpf` 是独立严格开关，不随 `--strict-desktop` 自动启用。

## 常用定位入口

- 环境依赖：`python .\cplan.py self-check desktop-env --require-input --require-vision --require-ocr --require-ocr-zh`
- 静态示例：`python .\cplan.py self-check desktop-examples --require-vision`
- 组件输入：`python .\cplan.py self-check desktop-components --require-input`
- WPF 复杂控件：`python .\cplan.py self-check desktop-components --require-wpf`
- 组件视觉和 OCR：`python .\cplan.py self-check desktop-components --require-vision --require-ocr --require-ocr-zh`
- 真实 App、终端、文件对话框：`python .\cplan.py self-check desktop-real-app`
- AI 工具链：`python .\main.py self-check ai-desktop-loop`
- 真实模型桌面闭环：`python .\main.py self-check ai-real-desktop-loop --api-key-file D:\模型密钥.txt --model gpt-5.5`
- 真实模型执行线确认：`python .\main.py self-check ai-real-execution-line --api-key-file D:\模型密钥.txt --model gpt-5.5`

## 边界

- 当前 Windows 能力不代表 macOS 已完成真机验收。
- macOS 的 Accessibility、Screen Recording、Automation 授权、Retina/DPI、多显示器、Finder/TextEdit、AX 表格/树/菜单和系统文件对话框仍需 Mac 真机回归。
- 真实 AI 回归只验证模型按 AI 终端规则调用工具和判断执行线，不承担 WinForms/Explorer/终端/OCR 的重型桌面矩阵；这些由确定性自检负责。
