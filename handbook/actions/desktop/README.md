# 桌面 action

本目录只给 `automation_type: "desktop"` 使用。它控制本机桌面 session、App、窗口、控件、键鼠、截图和桌面状态。

## Action 清单

| action | 作用 | 关键参数 | 场景 |
| --- | --- | --- | --- |
| [open_desktop](./open_desktop.md) | 创建桌面 session | `name`、`platform`、`backend`、`request_permissions` | 桌面 plan 第一步、权限检测 |
| [close_desktop](./close_desktop.md) | 关闭桌面 session | `desktop` | 释放 backend 资源 |
| [desktop_app](./desktop_app.md) | 启动本机 App 或命令 | `type=launch`、`app/path/command`、`args` | 打开 Notepad、TextEdit、业务软件 |
| [desktop_window](./desktop_window.md) | 列出、聚焦、控制窗口 | `type`、Window Query | 等待窗口、聚焦、关闭、最小化、最大化 |
| [desktop_element](./desktop_element.md) | 控件树定位和操作 | `type`、Window Query、Element Locator、`tree_path`、`menu_path`、`open_context_menu`、`amount/scroll_to` | 找按钮/输入框、读文本、写值、选择项、表格、树、菜单栏、上下文菜单、滚动容器、点击 |
| [desktop_input](./desktop_input.md) | 系统键鼠输入 | `type`、`value`、`keys`、`x/y`、`target` | 输入文本、快捷键、坐标点击/双击/右键、滚动、拖拽 |
| [desktop_capture](./desktop_capture.md) | 截图和状态快照 | `type`、`target`、`path`、Window Query、Element Locator、`region` | 保存全屏、区域、窗口、控件截图和状态快照 |
| [desktop_vision](./desktop_vision.md) | 图像定位取证 | `type=locate_image`、`template_path`、`source_path/source_target`、`threshold` | 控件树不可见、自绘 UI、已有截图、窗口或控件内定位 |
| [desktop_wait](./desktop_wait.md) | 等待桌面状态 | `type=window`、Window Query、`state` | App 启动后等窗口、关闭后等消失 |
| [desktop_assert](./desktop_assert.md) | 桌面断言 | `type`、Window Query、Element Locator | 校验窗口、截图、控件文本或状态 |

## 使用规则

- 桌面 action 不接受浏览器 DOM selector。
- 桌面键鼠是操作系统级输入，不等同于浏览器 `mouse`/`keyboard`。
- 坐标级鼠标输入只作兜底；优先使用 `desktop_window` 和 `desktop_element` 的语义定位。表格、树、菜单和滚动容器优先使用 `desktop_element` 的语义 type；上下文菜单项优先使用 `desktop_element type=invoke_menu open_context_menu=true`；控件树不可用或只需要系统级鼠标事件时再用 `desktop_input target=element_center` 或坐标滚轮。定位选择见 [桌面定位策略](./locator_strategy.md)。
- `open_desktop` 和 `desktop_capture type=snapshot` 会返回 `capability_matrix`；AI 应先看能力矩阵再选择控件、键鼠、截图或人工确认。
- 鼠标类 `desktop_input` 和操作类 `desktop_element click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 会尽力写入 `output/<run>/desktop-annotations/` 的 PNG+JSON 标注证据。
- 真实桌面流程先取证，再操作：先探测 `capability_matrix`、窗口、控件、截图、权限和依赖，再写最终 plan；plan 内继续用窗口列表、控件树、截图、状态快照、等待、断言或人工确认保存运行证据。
- `desktop_vision type=locate_image` 可用于可运行 plan；它只输出 bounds/point/证据，不直接点击。
- Open/Save 系统文件对话框按真实桌面窗口处理：先等待和截图，再用 `desktop_input type_text method=clipboard` 输入完整路径并 `hotkey enter` 确认。示例见 [desktop_input](./desktop_input.md)。
