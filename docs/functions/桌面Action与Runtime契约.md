# 桌面 Action 与 Runtime 契约

## 定位

本文是跨平台桌面控制 Phase 0 基线和计划-0007 第一批复杂控件增量的实现契约。它不描述愿景，而是约束编码时必须遵守的 plan 字段、action 分区、runtime 对象、backend 返回 payload、输出目录、失败证据、自检和既有 browser plan 迁移规则。

桌面控制的长期设计见 [跨平台电脑控制设计](./跨平台电脑控制设计.md)，执行线隔离见 [执行线隔离与Plan类型设计](../architecture/执行线隔离与Plan类型设计.md)。

## Phase 0 范围

Phase 0 目标是先把执行线和桌面基础 runtime 打稳，不追求完整桌面 RPA。

必须实现：

- 顶层 `automation_type` 校验和执行线 action 分区。
- `cplan create --automation-type browser|desktop`。
- browser plan 示例和回归包补齐 `automation_type: "browser"`。
- `DesktopSession`、backend adapter 基类和最小 Windows/macOS 探测。
- `open_desktop`、`close_desktop`。
- `desktop_app type=launch`，支持可选启动后等待窗口和聚焦。
- `desktop_window type=list/find/active/focus/close/minimize/maximize/restore`。
- `desktop_element type=list/dump/find/wait/get_text/get_state/click/set_text/select/invoke`，其中 `dump` 为控件树和 selector 诊断导出，`click` 为控件 bounds 中心点击，`set_text` 优先原生 UIA/AX 写值，`select` 优先 UIA SelectionItemPattern/AX 可选项，`invoke` 优先 UIA InvokePattern/AXPress。
- `desktop_input type=type_text/hotkey/click/double_click/right_click/scroll/drag`，其中鼠标类输入为系统级坐标动作，并支持 candidate、当前窗口中心/偏移、控件中心、给定 bounds 中心和绝对坐标。
- `desktop_capture type=screenshot/snapshot/observe`，其中 `observe` 输出 AI 可读的统一桌面观察 payload。
- `desktop_vision type=locate_image`，使用 OpenCV 模板匹配输出 bounds、point、候选分数和 `output/desktop-vision/` 证据。
- `desktop_vision type=locate_text`，使用 Tesseract OCR 输出 raw text、OCR blocks、文本命中 bounds、point、置信度和 `output/desktop-vision/` 证据。
- `desktop_wait type=window`。
- `desktop_assert type=window/screenshot/element`。
- 桌面失败截图、窗口列表、backend 诊断和权限状态采集。
- `python .\cplan.py self-check desktop-components` 三层自检。
- `python .\cplan.py self-check desktop-real-app` 真实 App 回归入口。

Phase 0 基线明确不做：

- 多显示器和 DPI/Retina 的完整校准。
- 录制用户操作。
- Appium/WinAppDriver/FlaUI sidecar。
- `hybrid` plan 或浏览器/桌面混合普通 plan。

计划-0007 第一批增量已扩展 `desktop_element`：

- `get_table/select_cell`: 表格读取和单元格选择。
- `get_tree/expand_tree/collapse_tree/select_tree`: 树读取、展开、折叠和选择。
- `invoke_menu`: 菜单路径触发。
- `scroll_element`: 滚动容器语义滚动。

这些能力仍沿用 `desktop_element`、`output/desktop-elements/`、`desktop-annotations`、Element Locator、Window Query 和 AI 质量门禁，不新增平行桌面 DSL。

视觉定位契约见 [桌面视觉定位设计](./桌面视觉定位设计.md)。AI 只有在能力矩阵声明可用时才能生成 `desktop_vision type=locate_image` 或 `type=locate_text`。

## 顶层 Plan 契约

主 `plan.json` 必须包含：

```json
{
  "automation_type": "desktop",
  "variables": {},
  "steps": []
}
```

规则：

- `automation_type` 必填，允许值只包括 `browser`、`desktop`。
- `steps` 仍是顺序执行数组。
- `variables` 仍是 plan 变量字典。
- 子计划默认继承主 plan 的 `automation_type`。
- 子计划如果显式声明 `automation_type`，必须和主 plan 一致。
- validator 不允许根据 action 反推类型。
- 缺少 `automation_type` 的主 plan 必须校验失败。

## Action 分区

### Browser 专属

仅 `automation_type: "browser"` 可用：

- `open_browser`
- `close_browser`
- `page`
- `navigate`
- `element`
- 浏览器 `mouse`
- 浏览器 `keyboard`
- `scroll`
- 浏览器 `capture`
- `storage`
- `detect_challenge`
- `dialog`
- `network`
- `wait_for_popup`
- `wait_for_download`
- `wait_for_file_chooser`
- `wait_for_network`
- `event`
- `coverage`
- `trace`
- `script`

### Desktop 专属

仅 `automation_type: "desktop"` 可用：

- `open_desktop`
- `close_desktop`
- `desktop_app`
- `desktop_window`
- `desktop_element`
- `desktop_input`
- `desktop_capture`
- `desktop_vision`
- `desktop_wait`
- `desktop_assert`

### Common 通用

两条执行线都可用：

- `if`
- `foreach`
- `retry`
- `trigger`
- `run_sub_plan`
- `read`
- `write`
- `http`
- `command`
- `print`
- `sleep`
- `manual_confirm`
- `ai`

通用 action 不得隐式依赖 browser 或 desktop runtime。需要运行时上下文时由 step 字段显式指定，例如 `browser` 或 `desktop`。

## AI 质量门禁契约

AI 终端为真实 desktop 任务写最终 plan 前，必须先有 plan 外探测证据，再有 plan 内运行证据。

- plan 外探测证据来自 `inspect_desktop` 或等价上下文，至少能说明平台、backend、`capability_matrix`、`coordinate_profile`、窗口列表、权限/依赖、控件树摘要、截图路径或人工确认之一。`inspect_desktop` 返回结构与 `desktop_capture type=observe` 的统一观察 payload 对齐。
- plan 内运行证据必须由桌面 action 产出，例如 `desktop_capture type=observe`、`desktop_window type=list/find/active/focus`、`desktop_element list/dump/find/get_text/get_state/wait/get_table/get_tree`、`desktop_capture screenshot/snapshot`、`desktop_vision locate_image/locate_text`、`desktop_wait` 或 `desktop_assert`。
- `desktop_element click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element`、`desktop_input click/type_text/hotkey/drag/scroll` 和 `desktop_window close/minimize/maximize/restore` 只算操作推进，不单独算识别证据。
- `review_plan_quality` 缺少桌面探测证据时返回 `missing_desktop_inspection_evidence` fail；缺少 plan 内桌面运行证据时返回 `missing_desktop_evidence_step` fail。
- `run_plan` 仍要求最新质量复查通过，复查后 plan 被修改必须重新 review。

## Runtime 对象

### DesktopSession

```python
@dataclass
class DesktopSession:
    name: str
    backend: DesktopBackend
    platform: str
    backend_name: str
    permissions: dict[str, Any] = field(default_factory=dict)
    capability_matrix: dict[str, Any] = field(default_factory=dict)
    coordinate_profile: dict[str, Any] = field(default_factory=dict)
    target_candidates: dict[str, Any] = field(default_factory=dict)
    runtime_config: dict[str, Any] = field(default_factory=dict)
    current_window: dict[str, Any] | None = None
```

`RuntimeState` 增加：

```python
desktop_sessions: dict[str, DesktopSession]
```

辅助方法：

```python
def require_desktop_session(self, name: str) -> DesktopSession: ...
```

`close_all()` 必须同时关闭 browser sessions 和 desktop sessions。桌面 backend 的 `close()` 必须容忍重复调用和部分初始化失败。

### DesktopBackend

Phase 0 backend 接口：

```python
class DesktopBackend:
    def probe(self, *, request_permissions: bool = False) -> dict[str, Any]: ...
    def list_windows(self, *, include_invisible: bool = False) -> list[dict[str, Any]]: ...
    def diagnose_window(self, query: dict[str, Any]) -> dict[str, Any]: ...
    def find_windows(self, query: dict[str, Any], *, include_invisible: bool = False) -> list[dict[str, Any]]: ...
    def get_active_window(self) -> dict[str, Any]: ...
    def focus_window(self, query: dict[str, Any]) -> dict[str, Any]: ...
    def control_window(self, query: dict[str, Any], operation: str) -> dict[str, Any]: ...
    def list_elements(self, window_query: dict[str, Any], *, locator: dict[str, Any] | None = None, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def dump_elements(self, window_query: dict[str, Any], *, locator: dict[str, Any] | None = None, max_depth: int = 6, max_elements: int = 200, include_tree: bool = True, include_selector_hints: bool = True, text_limit: int = 160) -> dict[str, Any]: ...
    def find_element(self, window_query: dict[str, Any], locator: dict[str, Any], *, state: str = "exists", timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def click_element(self, window_query: dict[str, Any], locator: dict[str, Any], *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def invoke_element(self, window_query: dict[str, Any], locator: dict[str, Any], *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def select_element(self, window_query: dict[str, Any], locator: dict[str, Any], value: str = "", *, option_index: int | None = None, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def set_element_text(self, window_query: dict[str, Any], locator: dict[str, Any], value: str, *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200, preserve_clipboard: bool = True) -> dict[str, Any]: ...
    def get_element_text(self, window_query: dict[str, Any], locator: dict[str, Any], *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def get_element_state(self, window_query: dict[str, Any], locator: dict[str, Any], *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def get_table(self, window_query: dict[str, Any], locator: dict[str, Any], *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200, max_rows: int = 50, max_columns: int = 20, visible_only: bool = True, text_limit: int = 160) -> dict[str, Any]: ...
    def select_cell(self, window_query: dict[str, Any], locator: dict[str, Any], *, row: int, column: str = "", column_index: int | None = None, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def get_tree(self, window_query: dict[str, Any], locator: dict[str, Any], *, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200, max_nodes: int = 200, text_limit: int = 160) -> dict[str, Any]: ...
    def tree_element_action(self, window_query: dict[str, Any], locator: dict[str, Any], *, operation: str, tree_path: list[str], timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def invoke_menu(self, window_query: dict[str, Any], *, locator: dict[str, Any] | None = None, menu_path: list[str], open_context_menu: bool = False, timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def scroll_element(self, window_query: dict[str, Any], locator: dict[str, Any], *, amount: int | None = None, scroll_to: str = "", timeout_ms: int = 1000, interval_ms: int = 100, max_depth: int = 6, max_elements: int = 200) -> dict[str, Any]: ...
    def launch_app(self, *, app: str = "", path: str = "", command: str = "", args: list[str] | None = None, wait: bool = False, timeout_ms: int = 10000) -> dict[str, Any]: ...
    def type_text(self, value: str, *, method: str = "auto", delay_ms: int = 0, preserve_clipboard: bool = True) -> dict[str, Any]: ...
    def hotkey(self, keys: list[str]) -> dict[str, Any]: ...
    def click(self, *, x: int, y: int, button: str = "left", clicks: int = 1, interval_ms: int = 0) -> dict[str, Any]: ...
    def double_click(self, *, x: int, y: int, interval_ms: int = 0) -> dict[str, Any]: ...
    def right_click(self, *, x: int, y: int) -> dict[str, Any]: ...
    def scroll(self, *, x: int, y: int, amount: int) -> dict[str, Any]: ...
    def drag(self, *, start_x: int, start_y: int, end_x: int, end_y: int, button: str = "left", duration_ms: int = 0) -> dict[str, Any]: ...
    def screenshot(self, path: Path, *, region: dict[str, Any] | None = None, include_cursor: bool = False) -> dict[str, Any]: ...
    def snapshot(self, *, include_windows: bool = True, include_displays: bool = True) -> dict[str, Any]: ...
    def wait_window(self, query: dict[str, Any], state: str, timeout_ms: int, interval_ms: int) -> dict[str, Any]: ...
    def close(self) -> None: ...
```

Backend 不直接读写 plan 变量。Action 层负责把 backend payload 保存到 `save_as` 和输出文件。

## Payload 字段

desktop action 的 `save_as` 变量应尽量返回可诊断字段。不同 action 的业务字段不同，不强制统一包一层 `result/artifacts`；下列字段是推荐公共字段和诊断字段：

```json
{
  "ok": true,
  "action": "desktop_window",
  "type": "focus",
  "desktop": "desk",
  "platform": "windows",
  "backend": "native",
  "elapsed_ms": 120,
  "window": {},
  "result": {},
  "artifacts": {},
  "diagnostics": {}
}
```

字段规则：

- `ok`: action 是否按自身断言成功。
- `action`: step 的 action 名。
- `type`: step 的 type，没有 type 的生命周期 action 使用空字符串或固定类型。
- `desktop`: 桌面 session 名。
- `platform`: 规范化平台名，当前使用 `windows`、`macos`、`linux` 或 `unknown`。
- `backend`: 实际 backend 名，不是用户传入的 `auto`。
- `capability_matrix`: `open_desktop`、`desktop_capture type=snapshot/observe` 和失败现场必须包含的桌面能力矩阵。
- `coordinate_profile`: `open_desktop`、`desktop_capture`、`desktop_vision`、`desktop-annotations`、`inspect_desktop` 和失败现场可返回的坐标事实，包含坐标空间、显示器摘要、source bounds、`screen_clickable` 和 local/screen 转换偏移。
- `coordinate_diagnostics.mapper`: 坐标映射摘要，包含 `source_bounds`、`display_virtual_bounds`、`screen_clickable` 和 `scale_applied=false`。当前 `CoordinateMapper` v1 只执行 offset 映射和安全边界检查，记录 scale 但不把未校准缩放直接应用到点击坐标。
- `target_candidates`: `desktop_capture type=observe`、`inspect_desktop`、`desktop_vision` 和失败现场可返回的定位候选摘要，用于让 AI 选择语义 locator、窗口锚点、视觉 bounds 或人工确认。
- `elapsed_ms`: action 耗时。
- `window`: 当前窗口或命中窗口摘要。
- `result`: action 业务结果；当前实现可用业务字段直接表达，不要求所有 action 都有该字段。
- `artifacts`: 输出文件路径；当前实现可用 `path` 或类型专属字段直接表达。
- `diagnostics`: 权限、DPI、显示器、候选数量、跳过原因等诊断信息；失败现场和桌面分析工具必须优先保留。

失败时可以不保存变量，但失败现场必须写入 `failure-desktop-*` 分区。

### Desktop Observation

`desktop_capture type=observe` 和 `inspect_desktop` 共享统一观察 payload，用于给 AI 和调试工具提供稳定的桌面状态摘要：

```json
{
  "schema_version": 1,
  "kind": "desktop_observation",
  "platform": "windows",
  "backend": "native",
  "capability_matrix": {},
  "coordinate_profile": {},
  "window_query": {},
  "element_locator": {},
  "current_window": {},
  "selected_window": {},
  "windows": [],
  "window_count": 0,
  "elements": {},
  "screenshot": {},
  "target_candidates": {
    "schema_version": 1,
    "kind": "desktop_target_candidates",
    "candidate_count": 0,
    "best_candidate": {},
    "candidates": []
  },
  "summary": {
    "window_count": 0,
    "element_count": 0,
    "element_match_count": 0,
    "target_candidate_count": 0,
    "best_target_strategy": "",
    "screenshot_path": "",
    "limitations": []
  },
  "artifacts": {}
}
```

规则：

- `kind` 固定为 `desktop_observation`，`schema_version` 当前为 `1`。
- `selected_window` 由 Window Query、当前窗口、聚焦窗口或第一个可见窗口解析。
- `include_elements=true` 时 `elements` 使用 `dump_elements(..., include_tree=false)` 的精简结果，保留 `matches`、`selector_hints`、`near_matches` 和 `diagnostics`。
- `include_screenshot=true` 时保存全屏截图；plan action 的截图和 JSON 同名，扩展名为 `.png`。
- `target_candidates` 把窗口、控件匹配、近似控件、截图证据归一成候选；候选必须包含 `id`、`candidate_id`、`strategy`、`confidence`、`score`、`locator`/`bounds`、`point`、`reason`、`screen_clickable` 和可选 `action_templates`。
- `strategy=semantic_locator` 优先用于 `desktop_element`；需要真实鼠标事件时使用 `desktop_input target=candidate`，运行时会重新用候选 `window_query + locator` 查找控件。`strategy=visual_bounds` 只有在 `screen_clickable=true` 且置信度达标时才能作为 `desktop_input target=candidate` 或 `bounds_center` 的坐标兜底；`strategy=visual_evidence`、低置信候选和 `screen_clickable=false` 需要继续用 `desktop_vision` 或人工确认。
- 顶层字段必须保持跨平台，不把 Windows UIA 或 macOS AX 私有字段提升为稳定契约。

### Capability Matrix

`capability_matrix` 是 AI 和调试工具选择桌面能力的稳定契约：

```json
{
  "schema_version": 1,
  "platform": "windows",
  "backend": "native",
  "source": "probe",
  "capabilities": {
    "semantic": {
      "window_list": true,
      "elements": true,
      "get_text": true,
      "get_state": true,
      "set_text": true,
      "select": true,
      "invoke": true,
      "get_table": true,
      "select_cell": true,
      "get_tree": true,
      "expand_tree": true,
      "collapse_tree": true,
      "select_tree": true,
      "invoke_menu": true,
      "scroll_element": true
    },
    "input": {"keyboard": true, "mouse": true, "clipboard": true, "hotkey": true, "drag": true, "scroll": true},
    "screenshot": {"full_screen": true, "region": true, "window": true, "element": true, "annotation": true},
    "vision": {"image_locator": true, "template_matching": true, "ocr": true}
  },
  "permissions": {"accessibility": "unknown", "screen_recording": "unknown", "input_control": "available_or_not_required"},
  "dependencies": {
    "Pillow.ImageGrab": true,
    "opencv-python": true,
    "tesseract": true,
    "tessdata.eng": true,
    "tessdata.chi_sim": false,
    "pyautogui": true,
    "pyperclip": true
  },
  "limitations": []
}
```

输出位置：

- `open_desktop` payload 顶层和 `probe.capability_matrix`。
- `desktop_capture type=snapshot` payload 顶层和 `snapshot.capability_matrix`。
- `desktop_capture type=observe` payload 顶层。
- `failure-desktop-state/*.json` 顶层和 `diagnostics.capability_matrix`。
- `inspect_desktop` 工具顶层、`probe.capability_matrix` 和统一观察 payload。

AI 生成桌面 plan 前必须先读能力矩阵；缺 `pyautogui` 时不要写键鼠动作，缺 `Pillow.ImageGrab` 时不要依赖截图、标注、OCR 或图像定位，缺 `opencv-python` 时不要写 `desktop_vision type=locate_image`，缺 `tesseract` 或所需 `tessdata.*` 时不要写 `desktop_vision type=locate_text`，`limitations` 非空时先修复依赖/权限或改用人工确认。`tesseract` 和 `tessdata.*` 的探测会读取合并后的 `config.json` 中 `desktop.ocr.tesseract_path` / `desktop.ocr.tessdata_dir`，因此 plan 包局部配置可以覆盖集合级配置。

`capabilities.semantic` 的键集合应保持跨平台一致，值按当前平台和 backend 真实能力返回。计划-0007 第一批复杂控件在 Windows native backend 上可用；macOS AX 复杂控件映射未真机落地前，对应值应为 `false`，AI 必须改用截图、图像定位或人工确认兜底。

## 通用查询结构

### Window Query

Phase 0 支持：

```json
{
  "title": "Untitled - Notepad",
  "title_contains": "Notepad",
  "title_regex": ".*Notepad.*",
  "process_name": "notepad.exe",
  "app": "TextEdit",
  "window_id": "0x0012039A",
  "profile": "notepad",
  "match_index": 0
}
```

规则：

- 至少提供一种定位字段。
- 多字段表示同时过滤。
- `profile` / `app_profile` 可从 app profile 补充 `window_query`；显式 step 字段覆盖 profile 默认字段。
- `match_index` 只在多个候选时使用，默认 `0`。
- 返回 payload 必须记录候选数量和最终命中字段。

### Desktop App Profile

`profile` 是桌面 App/窗口定位预设，作用是把常用 App、系统文件对话框和业务客户端的启动参数、Window Query 和默认等待参数集中到配置里。运行时在 action 层应用 profile，再把合并后的字段交给 backend。

内置 profile 至少包含 `notepad`、`explorer`、`powershell`、`file_dialog_open`、`file_dialog_save` 和 `textedit`。自定义 profile 放在合并后的 `config.json` 顶层 `desktop_profiles`，结构为 `platforms.windows/macos.launch`、`window_query`、`defaults`。`desktop_app type=launch` 可以只写 `profile`；窗口类 action 可以把 `profile` 当作 Window Query 来源。payload 使用 `profile` 字段记录 `id/requested/platform/source/applied`。

### Element Locator

`desktop_element` 在 Window Query 命中的窗口内使用 Element Locator。控件定位字段不使用 Playwright selector 语义：

```json
{
  "automation_id": "num5Button",
  "name_contains": "Five",
  "text_regex": "Save|保存",
  "control_type": "Button",
  "role": "AXButton",
  "element_match_index": 0
}
```

字段：

- `element_id`: backend 返回的控件 id/runtime id。
- `automation_id`: Windows UIA AutomationId；macOS Phase 0 通常为空。
- `name` / `name_contains` / `name_regex`: 控件名称匹配。
- `text` / `text_contains` / `text_regex`: 控件文本匹配。
- `control_type`: 控件类型，例如 `Button`、`Edit`、`Window`。
- `role`: 平台角色；Windows 映射自 control type，macOS 映射 AX role。
- `element_class_name`: Windows 控件 class name 包含匹配；macOS 通常为空。
- `element_match_index`: 多个控件候选时选择索引，默认 `0`，不能单独作为定位字段。

除 `desktop_element type=list/dump/invoke_menu` 外，控件操作必须至少提供一种非 `element_match_index` 的控件定位字段。`list` 可以不写 Element Locator；写了则表示枚举后过滤。`dump` 可以不写 Element Locator；写了则表示在控件树诊断中标出精确命中、近似候选和 selector 建议。`invoke_menu` 默认使用 Window Query 和 `menu_path` 定位菜单栏；`open_context_menu=true` 时必须提供 Element Locator，用于先右键目标控件并触发上下文菜单项。

标准窗口摘要：

```json
{
  "id": "0x0012039A",
  "title": "Untitled - Notepad",
  "process_name": "notepad.exe",
  "class_name": "Notepad",
  "bounds": {"x": 10, "y": 20, "width": 900, "height": 600},
  "focused": true,
  "visible": true,
  "enabled": true
}
```

平台拿不到的字段使用空字符串、`null` 或不返回；不要编造。

### Region

截图和后续视觉定位使用：

```json
{
  "x": 0,
  "y": 0,
  "width": 1200,
  "height": 800
}
```

当前支持全屏截图、基础 `{x,y,width,height}` region，以及由 Window Query / Element Locator 解析出的窗口和控件截图区域。桌面截图 region 允许负 `x/y` 以支持虚拟屏幕原点在主屏左侧或上方的多显示器布局，`width/height` 必须大于 `0`。Retina/高 DPI 的完整换算在后续阶段继续加强，但 snapshot 里必须尽力记录显示器和缩放诊断。

## Action Schema

### open_desktop

```json
{
  "action": "open_desktop",
  "name": "desk",
  "platform": "auto",
  "backend": "auto",
  "request_permissions": false,
  "permissions": ["accessibility", "screen_recording", "automation"],
  "timeout_ms": 10000,
  "save_as": "desktop_open"
}
```

字段：

- `name`: 必填，桌面 session 名。
- `platform`: `auto`、`windows`、`macos`。默认 `auto`。
- `backend`: `auto`、`native`。当前 Phase 0 只接入这两个取值。
- `request_permissions`: 缺权限时是否触发授权提示或打开设置。默认 `false`。
- `permissions`: macOS 需要检测的权限。默认按 backend 决定。
- `timeout_ms`: 初始化和权限等待超时。
- `save_as`: 可选，保存 probe payload。

输出：

- 变量 payload 包含 `ok`、`desktop`、`platform`、`backend`、`probe`、`capability_matrix`、`coordinate_profile`、`elapsed_ms`。
- `probe` 包含 backend、平台、权限、依赖、显示器、窗口枚举错误、`capability_matrix` 和 `coordinate_profile`。
- `open_desktop` 当前不自动写文件；需要落盘时使用通用 `write type=json value="{{desktop_probe}}"`。

错误：

- 平台不支持。
- backend 依赖缺失。
- 没有 GUI 会话。
- 权限缺失且 `request_permissions=false`。

### close_desktop

```json
{
  "action": "close_desktop",
  "desktop": "desk"
}
```

字段：

- `desktop`: 必填，session 名。

行为：

- 关闭 backend 资源并从 `state.desktop_sessions` 移除。
- 默认不关闭用户 App，除非后续 action 明确提供关闭窗口语义。

### desktop_app

#### type=launch

```json
{
  "action": "desktop_app",
  "type": "launch",
  "desktop": "desk",
  "app": "notepad.exe",
  "args": ["C:/tmp/demo.txt"],
  "wait": false,
  "timeout_ms": 10000,
  "wait_for_window": true,
  "title_contains": "demo.txt",
  "focus": true,
  "window_timeout_ms": 10000,
  "interval_ms": 250,
  "save_as": "app_launch"
}
```

字段：

- `desktop`: 必填。
- `type`: 必填，固定为 `launch`。
- `profile`: 可选，App/窗口预设，可提供启动目标、Window Query 和默认等待参数。
- `app` / `path` / `command`: 三选一；没有 `profile` 时必须提供一个非空目标，不能同时提供多个。显式字段覆盖 profile 提供的启动目标。
- `args`: 可选，非空字符串数组。
- `wait`: 可选，默认 `false`。为 `true` 时等待启动进程退出。
- `timeout_ms`: 可选，`wait=true` 时的等待超时。
- `wait_for_window`: 可选，默认 `false`。为 `true` 时启动后等待 Window Query 命中的窗口出现。
- Window Query: `wait_for_window=true` 时必填，可由 `profile` 提供。
- `focus`: 可选，默认 `false`。为 `true` 且 `wait_for_window=true` 时聚焦等待到的窗口。
- `window_timeout_ms`: 可选，等待窗口超时；未设置时沿用 `timeout_ms` 或默认 `10000`。
- `interval_ms`: 可选，等待窗口轮询间隔。
- `save_as`: 可选。

行为：

- Windows: `app`、`path`、`command` 直接作为进程启动目标，`args` 作为参数数组。
- macOS: `app` 使用 `open -a <app>`，`path` 使用 `open <path>`，`command` 直接作为命令启动目标。
- GUI App 启动后应使用 `wait_for_window/focus` 或继续接 `desktop_wait type=window`、`desktop_window type=focus`、`desktop_capture`、`desktop_window type=find/active` 或 `desktop_assert` 获取状态证据。

输出 payload：

```json
{
  "ok": true,
  "platform": "windows",
  "backend": "native",
  "app": "notepad.exe",
  "path": "",
  "command": "",
  "args": ["C:/tmp/demo.txt"],
  "command_line": ["notepad.exe", "C:/tmp/demo.txt"],
  "pid": 1234,
  "wait": false,
  "wait_for_window": true,
  "focus": true,
  "window_query": {"title_contains": "demo.txt"},
  "window": {"title": "demo.txt - Notepad"},
  "window_wait": {"state": "exists"},
  "window_focus": {"title": "demo.txt - Notepad"}
}
```

`wait=true` 时额外包含 `exit_code`、`stdout`、`stderr`。

### desktop_window

Window Query 字段：

- `title`
- `title_contains`
- `title_regex`
- `app`
- `process`
- `process_name`
- `class_name`
- `window_id`
- `match_index`

`find/focus/close/minimize/maximize/restore` 需要至少一种定位字段。`list` 和 `active` 不要求定位字段。`match_index` 只用于多个候选时选择第几个，不能单独作为定位字段。

#### type=list

```json
{
  "action": "desktop_window",
  "type": "list",
  "desktop": "desk",
  "title_contains": "demo",
  "max_windows": 20,
  "path": "windows.json",
  "save_as": "windows"
}
```

字段：

- `desktop`: 必填。
- Window Query: 可选；提供时只返回匹配窗口。
- `include_invisible`: 可选，Windows 下是否包含不可见窗口，默认 `false`。macOS 当前 native backend 不支持不可见窗口枚举；请求后 payload 会返回 `diagnostics.include_invisible_supported=false` 和 warning。
- `max_windows`: 可选，限制返回窗口数量。
- `path`: 可选，写入 `output/desktop-windows/`。
- `save_as`: 可选，保存窗口数组和诊断。

输出 payload：

```json
{
  "windows": [],
  "count": 0,
  "total_count": 0,
  "truncated": false
}
```

请求 `include_invisible=true` 时，输出可额外包含：

```json
{
  "diagnostics": {
    "include_invisible_requested": true,
    "include_invisible_supported": true,
    "warnings": []
  }
}
```

#### type=find

```json
{
  "action": "desktop_window",
  "type": "find",
  "desktop": "desk",
  "title_contains": "Notepad",
  "process_name": "notepad.exe",
  "path": "matched-window.json",
  "save_as": "matched_window"
}
```

字段：

- `desktop`: 必填。
- Window Query 字段至少一个。
- `include_invisible`: 可选；Windows 支持，macOS 当前 native backend 会返回不支持诊断。
- `max_windows`: 可选，限制返回候选数量。
- `path`: 可选，写入 `output/desktop-windows/`。
- `save_as`: 可选。

行为：

- 只查询窗口并返回 `matches`、`match_count` 和 `selected_window`。
- 不聚焦、不控制窗口、不更新 `session.current_window`。

#### type=active

```json
{
  "action": "desktop_window",
  "type": "active",
  "desktop": "desk",
  "path": "active-window.json",
  "save_as": "active_window"
}
```

行为：

- 读取当前系统活动窗口。
- 找到活动窗口时更新 `session.current_window`。
- 返回 `found` 和 `window`。

#### type=focus

```json
{
  "action": "desktop_window",
  "type": "focus",
  "desktop": "desk",
  "title_contains": "Notepad",
  "save_as": "focused_window"
}
```

字段：

- `desktop`: 必填。
- Window Query 字段至少一个。
- `save_as`: 可选。

行为：

- 查找窗口。
- 聚焦窗口。
- 更新 `session.current_window`。
- 返回命中窗口摘要。

#### type=close/minimize/maximize/restore

```json
{
  "action": "desktop_window",
  "type": "close",
  "desktop": "desk",
  "title_contains": "Notepad",
  "save_as": "window_control"
}
```

字段：

- `desktop`: 必填。
- `type`: `close`、`minimize`、`maximize`、`restore`。
- Window Query 字段至少一个。
- `save_as`: 可选。

行为：

- 通过 backend `control_window(query, operation)` 对匹配窗口发起控制。
- `close` 只请求窗口正常关闭，不强杀进程；未保存确认框或 App 拒绝关闭时，后续 `desktop_wait state=not_exists` 应超时失败。
- `minimize`、`maximize`、`restore` 更新 `session.current_window`；`close` 请求发送后清空 `session.current_window`。
- Windows backend 使用 `WM_CLOSE` 和 `ShowWindow`；macOS backend 使用 System Events/AppleScript，`maximize` 和 `restore` 属于 best-effort。

输出 payload：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "close",
  "operation": "close",
  "query": {"title_contains": "Notepad"},
  "window": {"id": 1234, "title": "demo.txt - Notepad", "close_requested": true},
  "before": {"id": 1234, "title": "demo.txt - Notepad"},
  "elapsed_ms": 5
}
```

`desktop_window close/minimize/maximize/restore` 是窗口控制步骤，不算桌面状态采集证据；需要质量门禁通过时仍应使用 `desktop_window list/find/active`、`desktop_element list/dump/find/get_text/get_state/get_table/get_tree`、`desktop_assert type=element`、`desktop_capture`、`desktop_wait` 或 `desktop_assert`。

### desktop_element

`desktop_element` 是控件级语义契约。它先用 Window Query 命中窗口，再在该窗口控件树里用 Element Locator、表格坐标、树路径、菜单路径或滚动参数执行读取和操作。

支持类型：

- `list`
- `dump`
- `find`
- `wait`
- `get_text`
- `get_state`
- `get_table`
- `select_cell`
- `get_tree`
- `expand_tree`
- `collapse_tree`
- `select_tree`
- `invoke_menu`
- `scroll_element`
- `click`
- `set_text`
- `invoke`

#### type=list

```json
{
  "action": "desktop_element",
  "type": "list",
  "desktop": "desk",
  "title_contains": "Notepad",
  "path": "notepad-elements.json",
  "save_as": "elements",
  "max_depth": 4,
  "max_elements": 250
}
```

字段：

- `desktop`: 必填。
- Window Query: 必填，至少一种定位字段。
- Element Locator: 可选；提供时枚举后过滤。
- `max_depth`: 可选，默认 `6`。
- `max_elements`: 可选，默认 `200`。
- `path`: 可选，写入 `output/desktop-elements/`。
- `save_as`: 可选。

`list` 是桌面状态采集证据。

#### type=dump

```json
{
  "action": "desktop_element",
  "type": "dump",
  "desktop": "desk",
  "title_contains": "Demo",
  "automation_id": "DesktopElementTextBox",
  "control_type": "Edit",
  "path": "demo-elements-dump.json",
  "save_as": "element_dump",
  "max_depth": 6,
  "max_elements": 300
}
```

字段：

- `desktop`: 必填。
- Window Query: 必填，至少一种定位字段。
- Element Locator: 可选；提供时标出精确命中、近似候选和 selector 建议。
- `include_tree`: 可选，默认 `true`。
- `include_selector_hints`: 可选，默认 `true`。
- `text_limit`: 可选，默认 `160`，`0` 表示不裁剪文本字段。
- `path`: 可选，写入 `output/desktop-elements/`。
- `save_as`: 可选。

payload 必须包含：

```json
{
  "elements": [],
  "tree": [],
  "matches": [],
  "selected_element": null,
  "near_matches": [],
  "selector_hints": [],
  "diagnostics": {
    "locator_applied": true,
    "ambiguous": false,
    "enumeration_depth_supported": 6,
    "backend_limitations": [],
    "recommendations": []
  }
}
```

`selector_hints` 中 `automation_id + control_type` 优先级最高；`element_id`/`runtime_id` 只适合同一次会话调试，不应作为长期 plan 的首选定位字段。`dump` 是桌面状态采集证据。

#### type=find/wait/get_text/get_state/click/set_text/select/invoke

```json
{
  "action": "desktop_element",
  "type": "find",
  "desktop": "desk",
  "title_contains": "Calculator",
  "name": "Five",
  "control_type": "Button",
  "timeout_ms": 1000,
  "interval_ms": 100,
  "save_as": "five_button"
}
```

字段：

- `desktop`: 必填。
- Window Query: 必填，至少一种定位字段。
- Element Locator: 必填，至少一种非 `element_match_index` 的控件定位字段。
- `timeout_ms`: 可选，默认 `1000`。
- `interval_ms`: 可选，默认 `100`。
- `max_depth`: 可选，默认 `6`。
- `max_elements`: 可选，默认 `200`。
- `path`: 可选，写入 `output/desktop-elements/`。建议只给识别类步骤使用。
- `save_as`: 可选。
- `value`: `set_text` 必填；`select` 可用来按选项文本选择。
- `option_index`: `select` 可用，从 `0` 开始选择选项；`select` 的 `value` 和 `option_index` 至少提供一个。
- `preserve_clipboard`: `set_text` fallback 使用剪贴板时是否恢复原剪贴板，默认 `true`。

`wait.state` 可选值：`exists`、`not_exists`、`enabled`、`disabled`、`focused`。

输出 payload 主要字段：

```json
{
  "ok": true,
  "desktop": "desk",
  "type": "find",
  "query": {"title_contains": "Calculator"},
  "locator": {"name": "Five", "control_type": "Button"},
  "window": {},
  "element": {
    "id": "42.1.5",
    "name": "Five",
    "text": "Five",
    "automation_id": "num5Button",
    "control_type": "Button",
    "role": "Button",
    "enabled": true,
    "visible": true,
    "focused": false,
    "bounds": {"x": 10, "y": 10, "width": 80, "height": 40}
  },
  "matches": [],
  "candidates_count": 1
}
```

行为：

- `find`: 返回命中控件和候选。
- `wait`: 按 `state` 重试，成功返回命中状态。
- `get_text`: 返回 `text`，来源优先级为控件 `text`、`value`、`name`。
- `get_state`: 返回 `element_state.enabled/visible/focused/bounds`。
- `click`: 定位控件后点击 bounds 中心。它是操作推进步骤，不是桌面状态采集证据。
- `set_text`: 定位控件后优先使用 Windows ValuePattern 或 macOS AX value 写入文本；失败时退到点击控件、全选和剪贴板粘贴。它是输入/操作推进步骤，不是桌面状态采集证据。
- `select`: 定位控件后优先使用 Windows SelectionItemPattern 或 macOS AX/System Events 选择选项；ComboBox/ListBox 也支持 `option_index` 键盘 fallback。它是操作推进步骤，不是桌面状态采集证据。
- `invoke`: 定位控件后优先使用 Windows InvokePattern 或 macOS AXPress 触发；失败时退到 bounds 中心点击。它是操作推进步骤，不是桌面状态采集证据。

#### type=get_table/select_cell

`get_table` 使用 Window Query + 表格 Element Locator 读取列、行和单元格；它是桌面状态采集证据。`select_cell` 使用同一表格 locator，按 `row` + `column` 或 `column_index` 选择单元格；它是操作推进步骤，不是桌面状态采集证据。

字段：

- `max_rows` / `max_columns`: `get_table` 可选，限制读取行列数。
- `visible_only`: `get_table` 可选，默认只读当前可见/已加载单元格。
- `text_limit`: `get_table` 可选，限制单元格文本长度。
- `row`: `select_cell` 必填，从 `0` 开始。
- `column`: `select_cell` 可选，按列名匹配。
- `column_index`: `select_cell` 可选，从 `0` 开始；`column` 和 `column_index` 至少一个。

主要 payload：

- `table.columns`
- `table.rows`
- `table.cells`
- `table.row_count`
- `table.column_count`
- `selected_cell`

#### type=get_tree/expand_tree/collapse_tree/select_tree

`get_tree` 使用 Window Query + 树 Element Locator 读取树节点；它是桌面状态采集证据。`expand_tree`、`collapse_tree` 和 `select_tree` 按 `tree_path` 操作节点；它们是操作推进步骤，不是桌面状态采集证据。

字段：

- `tree_path`: `expand_tree/collapse_tree/select_tree` 必填，非空字符串数组，例如 `["Settings", "Accounts"]`。
- `max_nodes`: `get_tree` 可选，限制返回节点数。
- `text_limit`: `get_tree` 可选，限制节点文本长度。

主要 payload：

- `tree.nodes`
- `tree.count`
- `tree.truncated`
- `tree_node.path`
- `tree_node.name`

#### type=invoke_menu

`invoke_menu` 使用 Window Query + `menu_path` 触发菜单项；它是操作推进步骤，不是桌面状态采集证据。默认模式触发窗口菜单栏，不要求 Element Locator；`open_context_menu=true` 时先按 Element Locator 定位目标控件并右键，再在弹出的上下文菜单里触发 `menu_path`。

字段：

- `menu_path`: 必填，非空字符串数组，例如 `["File", "Save"]`。
- `open_context_menu`: 可选布尔值，默认 `false`；为 `true` 时 Element Locator 必填。
- Element Locator: 仅上下文菜单模式必填，用于定位要右键的控件。

主要 payload：

- `menu_path`
- `menu_item`
- `open_context_menu`
- `context_target`
- `context_open`
- `method`

#### type=scroll_element

`scroll_element` 使用 Window Query + 滚动容器 Element Locator 做语义滚动；它是操作推进步骤，不是桌面状态采集证据。

字段：

- `amount`: 可选，整数，不能为 `0`。
- `scroll_to`: 可选，`start/end/top/bottom/left/right`。
- `amount` 和 `scroll_to` 至少提供一个。

主要 payload：

- `scroll_target`
- `amount`
- `scroll_to`
- `method`

平台：

- Windows native backend 使用系统 UIAutomationClient 枚举控件树，运行时不强制安装 `pywinauto`。
- macOS native backend 使用 System Events/Accessibility 做有限深度 AX 控件枚举。
- `click`、`double_click`、`right_click`、`scroll`、`drag` 通过 `pyautogui` 发送鼠标输入；`set_text`/`select`/`invoke`/复杂控件操作的 fallback 也可能使用鼠标、键盘和剪贴板。

### 运行时自复查与 plan 简洁边界

桌面 plan 主要描述“要对哪个 App/窗口/控件做什么”，不应把焦点抢占、窗口被遮挡、最小化恢复、前台校验、坐标边界、安全失败诊断和短暂系统抖动都展开成多步流程。能由 runtime 稳定处理的细节必须下沉到 action 执行层。

运行时默认负责：

- `automation_type=desktop` 的 plan 在 `ActionExecutor.run()` 外层获取运行互斥锁；默认配置为 `desktop.run_mutex.enabled=true`、`scope=project`、`on_conflict=fail`，锁冲突必须失败并写入 `result.json/report.md`，不能让两个桌面 plan 同时争抢同一前台、鼠标和键盘。
- 操作前按 Window Query、候选 `window_query` 或 `session.current_window` 恢复并激活目标窗口。
- 对真实键盘/鼠标输入执行有限次数 `restore/focus/active-window` 复查；当前默认最多 3 次，失败直接返回诊断，不进入无限循环。次数和间隔由 `desktop.foreground_protection.activation_attempts`、`retry_delay_ms` 配置。
- Windows native backend 在交互守卫里会对目标窗口执行 z-order 提升；目标窗口被其他 topmost 测试窗体或用户窗口遮挡时，runtime 优先把目标窗口提升到前台再发送输入，避免鼠标落到遮挡窗口。
- 对坐标级鼠标动作执行屏幕边界、可点击来源、激活窗口 bounds 和支持平台的点命中窗口归属检查。
- 失败时写入失败现场、活动窗口、窗口候选、控件候选、指针位置和能力矩阵，供 AI 修复 plan。

plan 只在这些情况承担额外细节：

- 需要明确目标时提供 Window Query、Element Locator、`candidate_id` 或业务断言。
- 需要确认业务结果时写 `desktop_assert`、读取输出文件或等待明确状态。
- 需要窗口外弹层、跨窗口拖拽、系统托盘等目标窗口外坐标时，显式写 `allow_outside_window=true`。
- runtime 无法可靠推断业务下一步时，用 `manual_confirm` 或更明确的窗口/控件定位信息。

### desktop_input

#### type=type_text

```json
{
  "action": "desktop_input",
  "type": "type_text",
  "desktop": "desk",
  "value": "hello",
  "method": "auto",
  "delay_ms": 20,
  "preserve_clipboard": true,
  "save_as": "typed"
}
```

字段：

- `desktop`: 必填。
- `value`: 必填，待输入文本。
- `method`: `auto`、`type`、`clipboard`。默认 `auto`。
- `delay_ms`: 逐字符输入延迟，默认 `0`。
- `preserve_clipboard`: 使用剪贴板时是否恢复原文本，默认 `true`。

行为：

- 输入发送前运行时会执行 `interaction_guard`：根据当前 action 的 Window Query、候选 `window_query` 或 `session.current_window` 执行有上限的 `restore/focus`，再读取活动窗口验证目标已成为前台窗口。payload 会记录 `attempt_count/max_attempts/attempts`。
- Windows 上 `interaction_guard` 会使用更强的前台提升策略处理 topmost/z-order 遮挡；这属于 runtime 责任，plan 不需要为“先把窗口提到最前”额外拆步骤。
- 如果无法确定目标窗口，或系统不允许目标窗口成为前台窗口，真实键盘/鼠标输入会失败并返回诊断，避免盲目操作当前用户焦点窗口。
- 输入作用于激活保护确认后的前台窗口或控件。
- 长文本可由 backend 自动选择剪贴板粘贴。
- plan 仍应优先显式提供 Window Query，或先执行 `desktop_window type=focus` / `desktop_wait type=window` 写入 `session.current_window`。

#### type=hotkey

```json
{
  "action": "desktop_input",
  "type": "hotkey",
  "desktop": "desk",
  "keys": ["ctrl", "s"],
  "save_as": "hotkey"
}
```

字段：

- `desktop`: 必填。
- `keys`: 必填，非空数组。

按键命名：

- Windows 常用 `ctrl`、`alt`、`shift`、`win`、`enter`、`esc`、`tab`。
- macOS 常用 `cmd`、`option`、`ctrl`、`shift`、`enter`、`esc`、`tab`。
- `auto` backend 不负责把业务含义翻译成平台快捷键；plan 应按平台写明确 keys，或后续用平台分支字段扩展。

#### type=click

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "target": "current_window_center",
  "button": "left",
  "clicks": 1,
  "interval_ms": 0,
  "save_as": "clicked"
}
```

或使用绝对屏幕坐标：

```json
{
  "action": "desktop_input",
  "type": "click",
  "desktop": "desk",
  "x": 640,
  "y": 360,
  "button": "left"
}
```

字段：

- `desktop`: 必填。
- `target`: 可选，支持 `candidate`、`current_window_center`、`focused_window_center`、`current_window_offset`、`focused_window_offset`、`element_center`、`bounds_center`。
- `x` / `y`: 可选，绝对屏幕坐标；使用坐标时必须同时提供，不能和 `target` 同时使用。
- `target_candidates`: `target=candidate` 可用，传入同一次 `desktop_capture type=observe`、`desktop_vision` 或 `inspect_desktop` 返回的 `target_candidates` 对象。
- `candidate_source`: `target=candidate` 可用。`latest`、`last`、`session` 或 `latest_target_candidates` 表示使用当前 desktop session 最近一次 `desktop_capture type=observe` 或 `desktop_vision` 保存的 `target_candidates`。
- `candidate_id`: `target=candidate` 必填，对应候选的 `candidate_id`。`target_candidate_id` 是等价别名。
- `min_confidence`: `target=candidate` 可选，默认 `medium`。
- `offset_x` / `offset_y`: `current_window_offset` 和 `focused_window_offset` 必填，表示相对当前窗口左上角的像素偏移。
- `bounds`: `bounds_center` 必填，形如 `{"x": 10, "y": 10, "width": 120, "height": 32}`，`width/height` 必须大于 `0`。
- Window Query + Element Locator: `element_center` 必填，用于先定位控件再取 bounds 中心。
- `allow_outside_window`: 可选布尔值，默认 `false`。坐标级鼠标动作必须落在激活后的目标窗口 bounds 内；支持点命中检测的平台还会确认屏幕点属于目标窗口或其子控件。确需窗口外弹层、跨窗口拖拽或系统区域时才显式设为 `true`。
- `button`: `left`、`right`、`middle`，默认 `left`。
- `clicks`: 点击次数，默认 `1`。
- `interval_ms`: 多次点击之间的间隔，默认 `0`。
- `save_as`: 可选。

行为：

- `target=current_window_center/focused_window_center/current_window_offset/focused_window_offset` 基于 `session.current_window.bounds`；运行时会先激活当前窗口并刷新 `session.current_window`，但仍需要前序 `desktop_window type=focus` 或 `desktop_wait type=window` 建立窗口上下文。
- `target=candidate` 只接受 `semantic_locator` 和可点击 `visual_bounds`。`semantic_locator` 会重新查找控件后点击实时中心；`visual_bounds` 必须 `screen_clickable=true` 且置信度达到 `min_confidence`。中间又执行新的 observe/vision 时，`candidate_source=latest` 会指向新候选，跨多步复用应传显式 `target_candidates`。
- `target=element_center` 使用 Window Query 和 Element Locator 定位控件，然后把控件 bounds 中心转成系统鼠标坐标。
- `target=bounds_center` 使用前一步 `desktop_element get_state/dump`、截图识别或其他工具返回的 bounds 计算中心点。
- 坐标级鼠标动作在真实输入前会执行窗口范围检查：默认要求 point 落在激活后的目标窗口 bounds 内；支持点命中检测的平台会进一步确认 `WindowFromPoint`/等价能力命中的窗口属于目标窗口或其子控件；drag 会同时检查起点和终点。设置 `allow_outside_window=true` 时只记录 `window_safety_check.bypassed_reason`，不拦截。
- 目标窗口被其它窗口挡住时，运行时会先通过 `interaction_guard` 抢回前台；如果点击点仍命中其它窗口，输入前会失败并在 `window_safety_check.points[].ownership` 中记录命中窗口、root 窗口、期望窗口和失败原因；若输入后活动窗口变成非目标窗口，失败现场会记录 `active_window`、截图和候选诊断，供后续修复。
- 鼠标点击是系统级坐标动作，不是浏览器 DOM selector；需要稳定控件操作时优先用 `desktop_element click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element`。
- 鼠标类 payload 会返回 `interaction_guard`、`window_safety_check`、`input_resolution` 和 `safety_check`。`window_safety_check.points[].ownership` 记录点命中归属；`target=candidate` 会记录 `candidate_id`、候选策略、置信度、`screen_clickable`、最终 point/bounds 和安全检查结果。
- 坐标可能受窗口遮挡、多显示器、DPI/Retina 换算影响；失败或不确定时必须保留截图和状态证据。

#### type=double_click

```json
{
  "action": "desktop_input",
  "type": "double_click",
  "desktop": "desk",
  "target": "current_window_center",
  "interval_ms": 50,
  "save_as": "double_clicked"
}
```

字段：

- `desktop`: 必填。
- `target` 或 `x/y`: 必填，规则同 `click`。
- `interval_ms`: 双击两次点击之间的间隔，默认 `0`。

行为：

- 固定发送左键双击，backend 返回 `x/y/button/clicks/interval_ms`。
- 需要右键或中键多次点击时使用 `type=click`。

#### type=right_click

```json
{
  "action": "desktop_input",
  "type": "right_click",
  "desktop": "desk",
  "target": "current_window_center",
  "save_as": "right_clicked"
}
```

字段：

- `desktop`: 必填。
- `target` 或 `x/y`: 必填，规则同 `click`。

行为：

- 固定发送右键单击。
- 打开上下文菜单后，plan 通常应显式发送 `desktop_input type=hotkey keys=["esc"]` 或选择菜单项，避免菜单遮挡后续操作。

#### type=scroll

```json
{
  "action": "desktop_input",
  "type": "scroll",
  "desktop": "desk",
  "target": "current_window_center",
  "amount": -3,
  "save_as": "scrolled"
}
```

字段：

- `desktop`: 必填。
- `target` 或 `x/y`: 必填，规则同 `click`。
- `amount`: 必填整数，不能为 `0`。正数向上滚动，负数向下滚动。

行为：

- 在解析出的坐标位置发送系统滚轮事件。
- 滚动是否生效取决于鼠标下方控件、窗口焦点和平台消息派发。

#### type=drag

以当前窗口中心为起点拖拽：

```json
{
  "action": "desktop_input",
  "type": "drag",
  "desktop": "desk",
  "target": "current_window_center",
  "delta_x": 80,
  "delta_y": 0,
  "duration_ms": 150,
  "save_as": "dragged"
}
```

或使用绝对坐标：

```json
{
  "action": "desktop_input",
  "type": "drag",
  "desktop": "desk",
  "start_x": 300,
  "start_y": 300,
  "end_x": 420,
  "end_y": 300,
  "duration_ms": 150
}
```

字段：

- `target` + `delta_x/delta_y`: `target` 解析为起点，可使用窗口中心/偏移、控件中心或 bounds 中心；`delta_x` 和 `delta_y` 至少提供一个，不能同时为 `0`。
- `start_x/start_y/end_x/end_y`: 绝对坐标模式，四个字段必填。
- `button`: `left`、`right`、`middle`，默认 `left`。
- `duration_ms`: 拖拽持续时间，默认 `0`；Windows 真实桌面建议使用 `100-300`。

行为：

- backend 先移动到起点，再按住指定按钮拖到终点。
- 坐标级拖拽易受 DPI、多显示器、边界、窗口抢焦点和 pyautogui fail-safe 影响；优先在自建临时窗口或已取证区域验证。

### desktop_capture

#### type=screenshot

```json
{
  "action": "desktop_capture",
  "type": "screenshot",
  "desktop": "desk",
  "path": "screen.png",
  "target": "region",
  "region": {"x": 0, "y": 0, "width": 1200, "height": 800},
  "save_as": "shot"
}
```

字段：

- `desktop`: 必填。
- `path`: 必填，写入 `output/desktop-screenshots/`。
- `target`: 可选，`screen`、`region`、`window`、`element`。省略时默认全屏；省略 `target` 但提供 `region` 时按区域截图处理。
- `region`: `target=region` 时必填，格式为 `{x,y,width,height}`；`x/y` 可以为负，`width/height` 必须大于 `0`；`target=window/element` 不能同时使用 `region`。
- Window Query: `target=window/element` 必须至少提供一种窗口定位字段。
- Element Locator: `target=element` 必须至少提供一种控件定位字段。
- `state`: 仅 `target=element` 使用，可选 `exists/enabled/disabled/focused`，默认 `exists`。
- `timeout_ms`、`interval_ms`: 等待窗口或控件的超时和轮询间隔。
- `max_depth`、`max_elements`: `target=element` 的控件树遍历限制。
- `include_cursor`: 可选，表示请求截图包含鼠标指针；backend payload 必须区分 `include_cursor_requested` 和 `cursor_included`，不能把未实际绘制的光标报告为已包含。
- `save_as`: 可选。

输出：

- `output/desktop-screenshots/<path>`。
- payload 包含 `ok`、`path`、`width`、`height`、`target`、`source_bounds`、`coordinate_space`、`coordinate_profile`、`coordinate_diagnostics`。
- `target=window` payload 包含 `target_query` 和 `window`。
- `target=element` payload 包含 `target_query`、`locator`、`window` 和 `element`。

窗口截图示例：

```json
{
  "action": "desktop_capture",
  "type": "screenshot",
  "desktop": "desk",
  "target": "window",
  "title_contains": "Demo",
  "path": "demo-window.png",
  "save_as": "window_shot"
}
```

控件截图示例：

```json
{
  "action": "desktop_capture",
  "type": "screenshot",
  "desktop": "desk",
  "target": "element",
  "title_contains": "Demo",
  "automation_id": "UsernameTextBox",
  "control_type": "Edit",
  "path": "username-field.png",
  "save_as": "element_shot"
}
```

#### type=snapshot

```json
{
  "action": "desktop_capture",
  "type": "snapshot",
  "desktop": "desk",
  "path": "state.json",
  "save_as": "desktop_state"
}
```

字段：

- `desktop`: 必填。
- `path`: 必填，写入 `output/desktop-state/`。
- `save_as`: 可选。

内容：

- 当前窗口。
- 窗口列表摘要。
- 显示器和 DPI/Retina 信息。
- 权限状态。
- `capability_matrix`。

### desktop_vision

#### type=locate_image

```json
{
  "action": "desktop_vision",
  "type": "locate_image",
  "desktop": "desk",
  "template_path": "resources/save-button.png",
  "source_path": "output/desktop-screenshots/screen.png",
  "region": {"x": 0, "y": 0, "width": 1200, "height": 800},
  "threshold": 0.88,
  "match_index": 0,
  "max_matches": 10,
  "path": "save-button-match.json",
  "save_as": "save_button"
}
```

字段：

- `desktop`: 必填。
- `template_path`: 必填，模板图路径，可指向 `resources/` 或已有本机路径。
- `source_path`: 可选，已有截图或图片；不能和 `source_target` 同时使用。
- `source_target`: 可选，`screen`、`window`、`element`。省略且未传 `source_path` 时抓取当前桌面截图。
- Window Query: `source_target=window/element` 必须至少提供一种窗口定位字段。`match_index` 保留给图像命中选择，不作为窗口定位字段使用。
- `window_match_index`: 可选，仅 `source_target=window/element` 使用，选择第几个窗口候选，默认 `0`；多窗口同名时优先使用更具体的 Window Query 或 `window_id`，确实需要按候选序号选择时再使用它。
- Element Locator: `source_target=element` 必须至少提供一种控件定位字段。
- `region`: 可选，限制匹配区域。使用 `source_path` 时相对图片，`source_target=screen` 时相对屏幕截图，`source_target=window/element` 时相对窗口或控件截图。
- `state`: 仅 `source_target=element` 使用，可选 `exists/enabled/disabled/focused`，默认 `exists`。
- `threshold`: 可选，默认 `0.85`，取值 `0..1`。
- `match_index`: 可选，多图像命中时选择第几个，默认 `0`。
- `max_matches`: 可选，最多保存候选数量，默认 `10`。
- `timeout_ms` / `interval_ms`: 未传 `source_path` 时可等待目标出现在屏幕上。
- `max_depth`、`max_elements`: `source_target=element` 的控件树遍历限制。
- `path`: 必填，写入 `output/desktop-vision/`。
- `save_as`: 可选，保存 payload 到变量。

输出：

- `output/desktop-vision/<path>` JSON。
- `<stem>-source.png`: 搜索原图。
- `<stem>-crop.png`: 命中裁剪图。
- `<stem>-annotated.png`: 候选和命中标注图。
- payload 包含 `source_target`、`source_bounds`、`matches[]`、`match.bounds`、`match.local_bounds`、`match.point`、`match.local_point`、`match.score`、`coordinate_space`、`coordinate_profile`、`coordinate_diagnostics`、`artifacts` 和 `source`。
- payload 包含 `target_candidates`，其中 `strategy=visual_bounds` 且 `screen_clickable=true` 的候选可用 `desktop_input target=candidate` 消费 `candidate_id`，也可生成 `desktop_input target=bounds_center` 动作模板；`source_path` 离线图片候选必须 `screen_clickable=false` 且不能生成点击模板。
- `match.bounds` / `match.point` 是屏幕全局逻辑像素；`match.local_bounds` / `match.local_point` 相对 `source_bounds`。
- `source_target=window` payload 包含 `target_query` 和 `window`。
- `source_target=element` payload 包含 `target_query`、`locator`、`window` 和 `element`。

后续点击优先使用 `desktop_input target=candidate` 消费 `{{save_button.target_candidates}}` 和 `candidate_id`；确实需要展开坐标时再使用 `desktop_input target=bounds_center` 消费 `{{save_button.match.bounds}}`。`desktop_vision` 只算取证，不算最终操作或断言。

#### type=locate_text

```json
{
  "action": "desktop_vision",
  "type": "locate_text",
  "desktop": "desk",
  "source_path": "output/desktop-screenshots/screen.png",
  "text_contains": "Order Total",
  "language": "eng",
  "provider": "tesseract",
  "min_confidence": 0.6,
  "match_index": 0,
  "max_matches": 10,
  "path": "order-total-ocr.json",
  "save_as": "order_total"
}
```

字段：

- `desktop`: 必填。
- `text`、`text_contains`、`text_regex`: 至少提供一个，建议只提供一个。
- `language`: 可选，默认 `eng`；支持 Tesseract 语言组合，例如 `eng+chi_sim`。
- `provider`: 可选，`auto` 或 `tesseract`。
- `min_confidence`: 可选，默认 `0.6`，取值 `0..1`。
- `case_sensitive`: 可选，默认 `false`。
- `source_path`、`source_target`、Window Query、`window_match_index`、Element Locator、`region`、`state`、`match_index`、`max_matches`、`timeout_ms`、`interval_ms`、`max_depth`、`max_elements`、`path`、`save_as` 与 `locate_image` 一致。

输出：

- `output/desktop-vision/<path>` JSON。
- `<stem>-source.png`: OCR source。
- `<stem>-crop.png`: 命中文本裁剪图。
- `<stem>-annotated.png`: OCR 命中标注图。
- payload 包含 `raw_text`、`ocr_blocks`、`matches[]`、`match.text`、`match.confidence`、`match.bounds`、`match.local_bounds`、`match.point`、`match.local_point`、`coordinate_space`、`coordinate_profile`、`coordinate_diagnostics`、`artifacts`、`diagnostics` 和 `source`。
- payload 包含 `target_candidates`，用于把 OCR 命中的文本 bounds 转成可审查的坐标候选。
- `diagnostics` 必须包含 OCR provider、语言、engine version、word/line/candidate 计数和 source 尺寸。

### desktop_wait

#### type=window

```json
{
  "action": "desktop_wait",
  "type": "window",
  "desktop": "desk",
  "title_contains": "Save As",
  "state": "exists",
  "timeout_ms": 5000,
  "interval_ms": 250,
  "save_as": "save_dialog"
}
```

字段：

- `desktop`: 必填。
- Window Query 字段至少一个。
- `state`: `exists`、`not_exists`、`focused`。默认 `exists`。
- `timeout_ms`: 默认 session timeout。
- `interval_ms`: 默认 `250`。
- `save_as`: 可选。

行为：

- 在超时内轮询窗口状态。
- 成功返回命中窗口摘要。
- 超时失败并触发桌面失败采集。

### desktop_assert

#### type=window

```json
{
  "action": "desktop_assert",
  "type": "window",
  "desktop": "desk",
  "state": "focused",
  "title_contains": "Notepad",
  "timeout_ms": 2000,
  "interval_ms": 100,
  "save_as": "focused_window"
}
```

字段：

- `desktop`: 必填。
- Window Query 字段至少一个。
- `state`: `exists`、`not_exists`、`focused`。默认 `exists`。
- `timeout_ms`: 默认 `1000`。
- `interval_ms`: 默认 `100`。
- `save_as`: 可选。

行为：

- 复用 `desktop_wait type=window` 的窗口匹配和轮询逻辑。
- `state=focused` 成功时更新 `session.current_window`。
- 超时抛出断言错误并触发桌面失败现场。

#### type=screenshot

```json
{
  "action": "desktop_assert",
  "type": "screenshot",
  "desktop": "desk",
  "path": "screen.png",
  "min_bytes": 1,
  "save_as": "screen_assertion"
}
```

字段：

- `desktop`: 必填。
- `path`: 必填，相对于 `output/desktop-screenshots/`。
- `min_bytes`: 最小文件字节数，默认 `1`。
- `save_as`: 可选。

行为：

- 断言 `output/desktop-screenshots/<path>` 存在且文件大小不小于 `min_bytes`。
- 常用于 `desktop_capture type=screenshot` 之后验证截图产物。

#### type=element

```json
{
  "action": "desktop_assert",
  "type": "element",
  "desktop": "desk",
  "title_contains": "Notepad",
  "automation_id": "statusText",
  "state": "exists",
  "expected": "Saved",
  "mode": "contains",
  "path": "status-assertion.json",
  "save_as": "status_assertion"
}
```

字段：

- `desktop`: 必填。
- Window Query 字段至少一个。
- Element Locator 字段至少一个。
- `state`: `exists`、`not_exists`、`enabled`、`disabled`、`focused`，默认 `exists`。
- `expected`: 可选，控件文本期望。
- `mode`: `equals`、`contains`、`not_contains`，默认 `equals`。
- `text_source`: `auto`、`text`、`value`、`name`，默认 `auto`。
- `expected_count`: 可选，断言匹配候选数量等于该值。
- `min_count` / `max_count`: 可选，断言匹配候选数量范围；不能和 `expected_count` 同时使用。
- `property`: 可选，断言命中控件属性，例如 `enabled`、`visible`、`focused`、`name`、`text`、`value`、`automation_id`、`control_type`、`role`、`class_name`、`bounds`。
- `property_expected`: 使用 `property` 时必填。
- `property_mode`: `equals`、`contains`、`not_contains`，默认 `equals`。
- `path`: 可选，写入 `output/desktop-elements/`。
- `timeout_ms`、`interval_ms`、`max_depth`、`max_elements`: 控件定位参数。

`desktop_assert type=element` 是桌面状态采集证据。`state=not_exists` 不能同时使用 `expected` 或属性断言。成功 payload 包含可选 `text_assertion`、`count_assertion` 和 `property_assertion`。

## 输出分区

固定分类：

- `desktop-screenshots`: `desktop_capture type=screenshot`。
- `desktop-state`: `open_desktop` probe、`desktop_capture type=snapshot/observe`。
- `desktop-windows`: `desktop_window type=list/find/active`。
- `desktop-elements`: `desktop_element type=list/dump/find/wait/get_text/get_state/click/set_text/select/invoke/get_table/select_cell/get_tree/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 和 `desktop_assert type=element` 的控件树、selector 建议、候选控件、匹配结果和操作/断言 payload。
- `desktop-annotations`: 位于 `output/<run>/desktop-annotations/`，保存鼠标类 `desktop_input` 和操作类 `desktop_element click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 的 PNG 标注图和同名 JSON 结构化标注。
- `desktop-vision`: `desktop_vision type=locate_image/locate_text` JSON、原图、裁剪图、标注图和 OCR 原文。
- `failure-desktop-screenshots`: 失败桌面截图。
- `failure-desktop-state`: 失败时 backend、权限、窗口列表、当前窗口、活动窗口、鼠标位置、step 摘要和 `diagnostics.window/diagnostics.element` 分组诊断。

输出路径规则沿用现有 `resolve_output_path()`：

- action 配置里的输出路径相对于当前 plan 包 `output/`。
- 不允许以 `output/`、`resources/`、`docs/`、`sub-plans/` 开头。
- 不允许绝对输出路径。

### Desktop Annotation

成功执行下列动作后，runtime 必须尽力写入 `output/<run>/desktop-annotations/`：

- `desktop_input type=click/double_click/right_click/scroll/drag`
- `desktop_element type=click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element`

每个标注由一张 PNG 和一个同名 JSON 组成。JSON 最小结构：

```json
{
  "schema_version": 1,
  "ok": true,
  "step": 8,
  "action": "desktop_input.click",
  "desktop": "desk",
  "type": "pointer",
  "annotated_screenshot_path": "...png",
  "json_path": "...json",
  "coordinate_space": {"origin": "screen", "unit": "logical_px", "scale": null},
  "target": {},
  "points": [{"x": 640, "y": 360, "label": "click"}],
  "bounds": [{"x": 100, "y": 100, "width": 200, "height": 80}],
  "overlays": [],
  "warnings": []
}
```

标注失败不得覆盖原动作结果；action payload 中写入 `annotation.ok=false`、`error`、`error_type`，并记录 warning。

### Desktop Vision

`desktop_vision type=locate_image` 和 `type=locate_text` 已实现。实现和扩展时保持下列边界：

- `desktop_vision` 只做定位和取证，不直接执行点击、输入、拖拽。
- 图像/OCR 命中后输出 `match.bounds`、`match.point`、`match.local_bounds`、`match.local_point`、`matches`、`coordinate_space`、`coordinate_diagnostics` 和 `artifacts`。
- 后续操作优先使用 `desktop_input target=candidate` 消费 `{{vision_result.target_candidates}}` 和候选 `candidate_id`；展开坐标时再使用 `desktop_input target=bounds_center` 消费 `{{vision_result.match.bounds}}`。
- 输出 JSON、原图、裁剪图、标注图和 OCR 原文写入 `output/desktop-vision/`。
- `capability_matrix.capabilities.vision` 必须暴露图像定位、模板匹配和 OCR 能力状态；`capability_matrix.dependencies` 必须暴露 `Pillow.ImageGrab`、`opencv-python`、`tesseract`、`tessdata.eng`、`tessdata.chi_sim`、`pyautogui` 和 `pyperclip`。
- validator 必须校验 `type=locate_image/locate_text`、模板路径或文本匹配条件、source path/source target 互斥、region、threshold/min_confidence、timeout/interval、path 和输出路径。
- AI 质量门禁必须把 `desktop_vision` 视为取证 action，而不是操作 action；视觉证据不替代最终断言。

最小 action schema、payload 和 AI 使用规则见 [桌面视觉定位设计](./桌面视觉定位设计.md)。

## 失败采集

任何 desktop action 失败时，除现有 run 日志外，必须尽力写入：

```text
output/<run>/failure-desktop-screenshots/
output/<run>/failure-desktop-state/
```

最小失败状态 JSON：

```json
{
  "step": 3,
  "action": "desktop_wait",
  "step_name": "wait save dialog",
  "desktop": "desk",
  "platform": "windows",
  "backend": "native",
  "capability_matrix": {},
  "error": "window not found",
  "target": {},
  "current_window": {},
  "active_window": {},
  "pointer_position": {},
  "window_diagnostics": {},
  "element_diagnostics": {},
  "diagnostics": {
    "window": {
      "query": {},
      "current_window": {},
      "total_windows": 0,
      "match_count": 0,
      "matches": [],
      "near_matches": []
    },
    "element": {
      "window_query": {},
      "locator": {},
      "matches": [],
      "near_matches": [],
      "selector_hints": []
    },
    "permissions": {},
    "capability_matrix": {},
    "current_window": {},
    "active_window": {},
    "pointer_position": {},
    "snapshot": {}
  },
  "artifacts": {
    "screenshot_path": "..."
  }
}
```

失败采集不得因截图失败覆盖原始错误；截图失败只记录 warning。

## Validator 契约

必须新增校验：

- 主 plan 缺少 `automation_type` 失败。
- `automation_type` 不是 `browser|desktop` 失败。
- 子计划显式类型和主 plan 不一致失败。
- browser plan 使用 desktop action 失败。
- desktop plan 使用 browser action 失败。
- desktop action 缺少 `desktop` 或必填字段失败。
- desktop 输出路径非法失败。
- `desktop_app type=launch` 缺少 `profile/app/path/command` 失败。
- `desktop_app type=launch` 同时使用多个启动目标失败。
- `desktop_app args` 不是非空字符串数组失败。
- `desktop_app type=launch wait_for_window=true` 缺少 Window Query 或 profile 失败。
- `desktop_input type=hotkey` 的 `keys` 为空失败。
- `desktop_input type=type_text` 缺少 `value` 失败。
- `desktop_input type=click` 缺少 `target` 或 `x/y` 失败。
- `desktop_input type=click` 同时使用 `target` 和 `x/y` 失败。
- `desktop_input type=click/double_click/right_click/scroll/drag` 使用未知 `target` 失败。
- `desktop_input target=current_window_offset/focused_window_offset` 缺少 `offset_x/offset_y` 失败。
- `desktop_input target=candidate` 缺少候选来源或 `candidate_id` 失败；候选来源可以是 `target_candidates`、`candidate_source` 或单个 `candidate`；同时展开 `bounds`、Window Query、`profile` 或 Element Locator 失败。
- `desktop_input target=element_center` 缺少 Window Query 或 Element Locator 失败。
- `desktop_input target=bounds_center` 缺少 `bounds` 或 `bounds.width/height <= 0` 失败。
- `desktop_input type=double_click/right_click/scroll` 缺少 `target` 或 `x/y` 失败。
- `desktop_input type=double_click/right_click/scroll` 同时使用 `target` 和 `x/y` 失败。
- `desktop_input type=scroll` 缺少 `amount` 或 `amount=0` 失败。
- `desktop_input type=drag` 缺少 `target+delta_x/delta_y` 或 `start_x/start_y/end_x/end_y` 失败。
- `desktop_input type=drag` 同时使用 `target` 和 `start/end` 坐标失败。
- `desktop_input type=drag` 的 `delta_x` 和 `delta_y` 同时为 `0` 失败。
- `desktop_input type=drag` 的 `button` 非 `left/right/middle` 失败。
- `desktop_window type=find/focus/close/minimize/maximize/restore` 或 `desktop_wait type=window` 缺少 Window Query 失败。
- `desktop_element type=list/dump` 缺少 Window Query 失败。
- `desktop_element type=find/wait/get_text/get_state/click/set_text/select/invoke/get_table/select_cell/get_tree/expand_tree/collapse_tree/select_tree/scroll_element` 缺少 Window Query 或 Element Locator 失败。
- `desktop_element type=invoke_menu` 缺少 Window Query 或 `menu_path` 失败。
- `desktop_element type=invoke_menu open_context_menu=true` 缺少 Element Locator 失败。
- `desktop_element type=set_text` 缺少 `value` 失败。
- `desktop_element type=select` 缺少 `value` 和 `option_index` 失败。
- `desktop_element type=get_table` 的 `max_rows/max_columns/text_limit` 类型或范围非法失败。
- `desktop_element type=select_cell` 缺少 `row` 或同时缺少 `column/column_index` 失败。
- `desktop_element type=select_cell` 的 `row/column_index` 类型或范围非法失败。
- `desktop_element type=get_tree` 的 `max_nodes/text_limit` 类型或范围非法失败。
- `desktop_element type=expand_tree/collapse_tree/select_tree` 缺少非空字符串数组 `tree_path` 失败。
- `desktop_element type=invoke_menu` 缺少非空字符串数组 `menu_path` 失败。
- `desktop_element type=scroll_element` 缺少 `amount/scroll_to`、`amount=0` 或 `scroll_to` 非 `start/end/top/bottom/left/right` 失败。
- `desktop_element state` 不在 `exists/not_exists/enabled/disabled/focused` 内失败。
- `desktop_capture type=screenshot` 的 `target` 非 `screen/region/window/element` 失败。
- `desktop_capture type=screenshot target=region` 缺少 `{x,y,width,height}` region 或 `width/height <= 0` 失败；`x/y` 可以为负。
- `desktop_capture type=screenshot target=window` 缺少 Window Query 失败。
- `desktop_capture type=screenshot target=element` 缺少 Window Query 或 Element Locator 失败。
- `desktop_capture type=screenshot target=element` 的 `state` 非 `exists/enabled/disabled/focused` 失败。
- `desktop_capture type=screenshot target=window/element` 同时使用 `region` 失败。
- `desktop_assert type=window` 缺少 Window Query 失败。
- `desktop_assert type=screenshot` 缺少 `path` 失败。
- `desktop_assert type=element` 缺少 Window Query 或 Element Locator 失败。
- `desktop_assert type=element` 的 `mode`、`state`、`text_source`、`property_mode` 非枚举值失败；属性断言缺少 `property_expected`、`expected_count` 与 `min_count/max_count` 混用、`min_count > max_count` 或 `state=not_exists` 同时使用属性断言失败。
- `desktop_vision type=locate_image` 缺少 `template_path` 失败。
- `desktop_vision type=locate_image` 同时使用 `source_path` 和 `source_target` 失败。
- `desktop_vision type=locate_image source_target=window` 缺少 Window Query 失败。
- `desktop_vision type=locate_image source_target=element` 缺少 Window Query 或 Element Locator 失败。
- `desktop_vision type=locate_image source_target=element` 的 `state` 非 `exists/enabled/disabled/focused` 失败。
- `desktop_vision type=locate_image` 的 `threshold` 不在 `0..1` 失败。
- `desktop_vision type=locate_image` 的 `source_target`、`region`、`match_index`、`window_match_index`、`max_matches`、`timeout_ms`、`interval_ms`、`max_depth`、`max_elements` 类型或范围非法失败。
- `desktop_vision type=locate_image` 的 `path` 必须写入 `output/desktop-vision/` 分类。
- `desktop_vision type=locate_text` 缺少 `text/text_contains/text_regex` 失败。
- `desktop_vision type=locate_text` 同时使用 `source_path` 和 `source_target` 失败。
- `desktop_vision type=locate_text source_target=window` 缺少 Window Query 失败。
- `desktop_vision type=locate_text source_target=element` 缺少 Window Query 或 Element Locator 失败。
- `desktop_vision type=locate_text` 的 `provider` 非 `auto/tesseract` 失败。
- `desktop_vision type=locate_text` 的 `min_confidence` 不在 `0..1` 失败。
- `desktop_vision type=locate_text` 的 `source_target`、`region`、`match_index`、`window_match_index`、`max_matches`、`timeout_ms`、`interval_ms`、`max_depth`、`max_elements` 类型或范围非法失败。

错误消息必须包含 step index、plan 类型和违规 action。

## Self-check 契约

新增：

```powershell
python .\cplan.py self-check desktop-components
python .\cplan.py self-check desktop-env
python .\cplan.py self-check desktop-real-app
python .\main.py self-check ai-desktop-loop
python .\main.py self-check ai-real-desktop-loop --api-key-file D:\模型密钥.txt --max-attempts 5 --retry-delay-seconds 3
python .\main.py self-check ai-real-execution-line --api-key-file D:\模型密钥.txt --max-attempts 5 --retry-delay-seconds 3
```

`desktop-env` 默认只做诊断；任意 `--require-*` 严格参数启用后，必须同时确认当前平台 native backend probe 可用，Windows 上还必须确认 PowerShell 7 可用。

发布前可用 `python .\cplan.py self-check release-matrix --strict-desktop --fail-fast --step-timeout-seconds 1200` 聚合强制桌面输入、视觉、英文 OCR 和简体中文 OCR 回归。WPF 复杂控件用 `--require-desktop-wpf` 单独加严，不随 `--strict-desktop` 自动启用。

分层执行：

1. `schema`: 不依赖 GUI，验证 `automation_type`、跨线 action、必填字段、输出路径和子计划继承。
2. `probe`: 探测当前平台、可用 backend、GUI 会话、权限、显示器和窗口列表能力。
3. `live`: 轻量运行层。执行 `open_desktop`、`desktop_window list`、`desktop_capture screenshot/snapshot/observe`、`desktop_assert screenshot`、`close_desktop`，验证不启动 Playwright 的桌面 runtime 链路，并检查 snapshot/observe 顶层 `capability_matrix` 和 `coordinate_profile`。该层不依赖当前桌面已有 focused 窗口。
4. `failure`: 使用不存在窗口和不存在控件触发失败，验证 `failure-desktop-screenshots/`、`failure-desktop-state/`、原始错误、目标定位摘要、`diagnostics.window`、`diagnostics.element`、`active_window`、`pointer_position`、`target_candidates`、`capability_matrix`、`coordinate_profile`、窗口候选诊断、近似匹配摘要，以及 `analyze_latest_run_failure` 返回的 `desktop_diagnostics` 和 `desktop_repair_suggestions`。
5. `launch/profile`: 不依赖 `pyautogui`，用 `desktop_app type=launch` 启动短生命周期命令并 `wait=true`，验证 `pid`、`exit_code`、`stdout`、`open_desktop.capability_matrix`、变量写出和自定义 `desktop_profiles` profile 应用。
6. `vision`: 使用自生成 source/template 图片运行 `desktop_vision type=locate_image`，验证 OpenCV 模板匹配、`match.bounds`、`match.point`、`matches`、`output/desktop-vision/` JSON、原图、裁剪图和标注图；缺少 `opencv-python` 或截图依赖时返回 `skipped` 和原因；发布前可用 `--require-vision` 强制通过。
7. `ocr`: 使用自生成英文图片运行 `desktop_vision type=locate_text`，验证 Tesseract OCR、`raw_text`、`ocr_blocks`、`match.text/confidence`、全局/局部 bounds、`coordinate_profile.source.screen_clickable=false`、`coordinate_diagnostics`、JSON、原图、裁剪图和标注图；缺少 Tesseract 或 `tessdata.eng` 时默认返回 `skipped` 和原因；发布前可用 `--require-ocr` 强制通过。
8. `real app`: Windows 用 `desktop_app type=launch wait_for_window/focus` 启动受控 WinForms 编辑器覆盖活动窗口读取、窗口查询、控件写入、保存、截图和关闭，启动 Explorer 打开临时目录覆盖真实系统窗口等待、聚焦、窗口查询、控件列表、目标文件语义定位、截图、正常关闭和关闭后 `not_exists`，启动可见 PowerShell 终端覆盖窗口等待、查询、活动窗口读取、截图、剪贴板输入命令、回车执行、结果文件断言和退出清理，并用临时 WinForms 窗口触发系统 Open/Save common dialog，覆盖文件选择、保存、对话框截图、对话框控件列表和结果文件校验；macOS 用 `desktop_app type=launch` 启动 TextEdit 或系统可用轻量 App。该层可通过 `python .\cplan.py self-check desktop-real-app` 单独运行，便于隔离真实系统 App 问题；受控编辑器链路失败时用新的临时包最多重试 1 次并返回 `attempts` 摘要；无 GUI、锁屏、权限不足或依赖缺失时返回 `skipped` 和原因。
9. `element action`: 用自建临时表单验证 `desktop_element dump`、`desktop_element find/get_state/click/set_text/select/invoke/get_table/select_cell/get_tree/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element`、`desktop_capture type=observe`、`desktop_capture target=window/element`、`desktop_vision source_target=window/element`、`desktop_assert type=element`、`desktop_input click/double_click/right_click/scroll/drag`、`target=candidate`、`candidate_source=latest`、`element_center`、`bounds_center`、`output/desktop-state/`、`output/desktop-elements/`、`output/desktop-screenshots/`、`output/desktop-vision/` 和 `output/desktop-annotations/` 产物；按当前运行环境选择夹具，Windows 使用 WinForms 覆盖 TextBox、Button、CheckBox、ComboBox、ListBox、DataGridView、TreeView、MenuStrip、ContextMenuStrip、滚动 Panel、鼠标事件面板、上下文菜单面板和状态文本，并校验统一观察 payload、`target_candidates` 最佳语义候选、candidate click 的 `input_resolution/safety_check/window_safety_check/candidate_id`、控件属性/数量断言、窗口/控件截图尺寸接近 `source_bounds`、窗口/控件 source 视觉定位的 `bounds`、`local_bounds`、`coordinate_profile.source.screen_clickable=true` 和视觉候选；`--require-input` 会强制 pyautogui/pyperclip、candidate/bounds 点击、上下文菜单、滚动、拖拽、双击、右键和剪贴板恢复全部真实通过；macOS 使用 Tkinter。该层是控件级和输入级回归的主路径，避免依赖用户机器上已有业务 App。
10. `wpf action`: Windows 独立严格项，用 `python .\cplan.py self-check desktop-components --require-wpf` 或 release matrix `--require-desktop-wpf` 启用。临时 WPF 表单覆盖 TextBox、Button、CheckBox、ComboBox、ListBox、DataGrid、TreeView、Menu、ContextMenu、ScrollViewer、窗口/控件截图和输出 JSON。缺 WPF runtime、STA 或 pattern 差异时严格模式失败；该项不随 `--strict-desktop` 自动启用。

`ai-desktop-loop` 是确定性 AI 工具链闭环，不新增 action 契约。它通过 AI 终端工具注册表先调用 `inspect_desktop`，再创建临时 desktop plan、调用 `review_plan_quality` 和 `run_plan`，读取 `desktop-annotations` JSON；失败分支验证 `analyze_latest_run_failure`、`prepare_failure_debug_workspace`、`propose_debug_fix`、`validate_debug_plan`、`run_debug_plan` 和 `generate_debug_patch` 能串起桌面控件定位修复。`analyze_latest_run_failure` 会返回压缩后的 `desktop_diagnostics[].target_candidates`；`propose_debug_fix` 会从 `desktop_diagnostics.element.near_matches[].element.selector_hints` 生成 Element Locator 候选，优先使用唯一且高稳定度的 `automation_id/control_type`；Window Query 候选来自 `diagnostics.window.near_matches`，默认更保守，通常需要明确 `user_hint` 或人工 review。

`ai-real-desktop-loop` 是真实模型回归。它用 OpenAI-compatible 服务驱动 AI 终端，让模型调用 `inspect_desktop`、创建 desktop smoke plan、写入、校验、质量复查、运行并读取 JSON 产物。自检会断言 `inspect_desktop` 参数、`capability_matrix`/`coordinate_profile` 探测结果、桌面产物结构和 `result.json status=passed`。连接、超时或中转服务瞬态错误默认最多尝试 5 次，每次外层重试按 `--retry-delay-seconds` 线性退避等待，可用 `--max-attempts` 和 `--retry-delay-seconds` 调整；该命令需要真实模型账户，缺少密钥时跳过，不纳入默认确定性自检。

`ai-real-execution-line` 是真实模型执行线确认回归。它只让模型判断用户需求应走 browser、desktop 还是先向用户确认，不创建 plan；覆盖明确网页、明确桌面、PowerShell 终端窗口、Windows Explorer、混合不明确、平台词浏览器和 Open/Save 文件对话框，防止模型在歧义场景直接写 plan 或调用 plan 写入/运行工具。

输出状态：

- `passed`: 全部可执行检查通过。
- `failed`: 框架逻辑或已声明能力失败。
- `skipped`: 平台不支持、无 GUI、锁屏、权限缺失、依赖缺失、CI 环境不可执行。

`skipped` 必须附原因，不能静默通过。

## Browser Plan 迁移

桌面线落地前，应一次性迁移已有 browser plan：

1. 所有主 `plan.json` 添加 `"automation_type": "browser"`。
2. 子计划默认不需要添加；如果添加，必须为 `"browser"`。
3. 文档示例和 handbook 示例同步补齐。
4. `plans/` 和 `test-plans/` 全量校验。
5. 不在运行时代码里长期保留“缺省 browser”分支。

迁移验证：

```powershell
python .\cplan.py self-check browser-components
python .\cplan.py self-check desktop-components
```

如果需要离线脚本批量补字段，脚本应作为一次性维护工具记录，不进入正常运行路径。

## 文档同步

实现或修改本文契约时，同步更新：

- [跨平台电脑控制设计](./跨平台电脑控制设计.md)
- [执行线隔离与Plan类型设计](../architecture/执行线隔离与Plan类型设计.md)
- [计划-0006-跨平台桌面自动化第二线落地](../plans/计划-0006-跨平台桌面自动化第二线落地.md)
- [桌面 action 手册入口](../../handbook/actions/desktop/README.md)
- [测试与验证说明](../develop/测试与验证说明.md)
