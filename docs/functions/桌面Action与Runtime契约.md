# 桌面 Action 与 Runtime 契约

## 定位

本文是跨平台桌面控制 Phase 0 的实现契约。它不描述愿景，而是约束编码时必须遵守的 plan 字段、action 分区、runtime 对象、backend 返回 payload、输出目录、失败证据、自检和既有 browser plan 迁移规则。

桌面控制的长期设计见 [跨平台电脑控制设计](./跨平台电脑控制设计.md)，执行线隔离见 [执行线隔离与Plan类型设计](../architecture/执行线隔离与Plan类型设计.md)。

## Phase 0 范围

Phase 0 目标是先把执行线和桌面基础 runtime 打稳，不追求完整桌面 RPA。

必须实现：

- 顶层 `automation_type` 校验和执行线 action 分区。
- `cplan create --automation-type browser|desktop`。
- browser plan 示例和回归包补齐 `automation_type: "browser"`。
- `DesktopSession`、backend adapter 基类和最小 Windows/macOS 探测。
- `open_desktop`、`close_desktop`。
- `desktop_window type=list/focus`。
- `desktop_input type=type_text/hotkey`。
- `desktop_capture type=screenshot/snapshot`。
- `desktop_wait type=window`。
- `desktop_assert type=window/screenshot`。
- 桌面失败截图、窗口列表、backend 诊断和权限状态采集。
- `python .\cplan.py self-check desktop-components` 三层自检。

明确不做：

- 控件级 `click/set_text/get_text` 的完整实现。
- OpenCV 图像 locator。
- OCR locator。
- 多显示器和 DPI/Retina 的完整校准。
- 录制用户操作。
- Appium/WinAppDriver/FlaUI sidecar。
- `hybrid` plan 或浏览器/桌面混合普通 plan。

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
- `desktop_window`
- `desktop_input`
- `desktop_capture`
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

## Runtime 对象

### DesktopSession

```python
@dataclass
class DesktopSession:
    name: str
    platform: str
    backend_name: str
    backend: DesktopBackend
    timeout_ms: int = 10000
    current_window: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
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
    def probe(self) -> dict[str, Any]: ...
    def snapshot(self) -> dict[str, Any]: ...
    def screenshot(self, path: Path, region: dict[str, Any] | None = None) -> dict[str, Any]: ...
    def list_windows(self) -> list[dict[str, Any]]: ...
    def focus_window(self, query: dict[str, Any]) -> dict[str, Any]: ...
    def type_text(self, text: str, delay_ms: int = 0, method: str = "auto") -> dict[str, Any]: ...
    def hotkey(self, keys: list[str]) -> dict[str, Any]: ...
    def wait_window(self, query: dict[str, Any], state: str, timeout_ms: int, interval_ms: int) -> dict[str, Any]: ...
    def close(self) -> None: ...
```

Backend 不直接读写 plan 变量。Action 层负责把 backend payload 保存到 `save_as` 和输出文件。

## 标准 Payload

所有 desktop action 的 `save_as` 变量应使用统一结构：

```json
{
  "ok": true,
  "action": "desktop_window",
  "type": "focus",
  "desktop": "desk",
  "platform": "Windows",
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
- `platform`: `Windows`、`Darwin`、`Linux` 或实际 `platform.system()`。
- `backend`: 实际 backend 名，不是用户传入的 `auto`。
- `elapsed_ms`: action 耗时。
- `window`: 当前窗口或命中窗口摘要。
- `result`: action 业务结果。
- `artifacts`: 输出文件路径。
- `diagnostics`: 权限、DPI、显示器、候选数量、跳过原因等诊断信息。

失败时可以不保存变量，但失败现场必须写入 `failure-desktop-*` 分区。

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
  "match_index": 0
}
```

规则：

- 至少提供一种定位字段。
- 多字段表示同时过滤。
- `match_index` 只在多个候选时使用，默认 `0`。
- 返回 payload 必须记录候选数量和最终命中字段。

标准窗口摘要：

```json
{
  "window_id": "0x0012039A",
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

当前只要求支持全屏截图和基础 `{x,y,width,height}` region。多显示器、负坐标和 Retina/高 DPI 的完整换算在后续阶段实现，但 snapshot 里必须尽力记录显示器和缩放诊断。

## Action Schema

### open_desktop

```json
{
  "action": "open_desktop",
  "name": "desk",
  "platform": "auto",
  "backend": "auto",
  "request_permissions": true,
  "permissions": ["accessibility", "screen_recording", "automation"],
  "timeout_ms": 10000,
  "save_as": "desktop_open"
}
```

字段：

- `name`: 必填，桌面 session 名。
- `platform`: `auto`、`windows`、`macos`。默认 `auto`。
- `backend`: `auto`、`windows-uia`、`windows-win32`、`macos-ax`、`vision`。Phase 0 可只实现 `auto`。
- `request_permissions`: 缺权限时是否触发授权提示或打开设置。默认 `true`。
- `permissions`: macOS 需要检测的权限。默认按 backend 决定。
- `timeout_ms`: 初始化和权限等待超时。
- `save_as`: 可选，保存 probe payload。

输出：

- `output/desktop-state/<session>-open.json`，可选实现。
- 变量 payload 包含 backend、平台、权限、显示器、当前用户会话诊断。

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

### desktop_window

#### type=list

```json
{
  "action": "desktop_window",
  "type": "list",
  "desktop": "desk",
  "path": "windows.json",
  "save_as": "windows"
}
```

字段：

- `desktop`: 必填。
- `path`: 可选，写入 `output/desktop-windows/`。
- `save_as`: 可选，保存窗口数组和诊断。

输出 payload：

```json
{
  "windows": [],
  "count": 0
}
```

#### type=focus

```json
{
  "action": "desktop_window",
  "type": "focus",
  "desktop": "desk",
  "title_contains": "Notepad",
  "timeout_ms": 5000,
  "save_as": "focused_window"
}
```

字段：

- `desktop`: 必填。
- Window Query 字段至少一个。
- `timeout_ms`: 默认 session timeout。
- `save_as`: 可选。

行为：

- 查找窗口。
- 聚焦窗口。
- 更新 `session.current_window`。
- 返回命中窗口摘要。

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

- 输入作用于当前焦点窗口或控件。
- 长文本可由 backend 自动选择剪贴板粘贴。
- 不自动聚焦窗口；需要先用 `desktop_window type=focus`。

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

### desktop_capture

#### type=screenshot

```json
{
  "action": "desktop_capture",
  "type": "screenshot",
  "desktop": "desk",
  "path": "screen.png",
  "region": {"monitor": "primary"},
  "save_as": "shot"
}
```

字段：

- `desktop`: 必填。
- `path`: 必填，写入 `output/desktop-screenshots/`。
- `region`: 可选。
- `save_as`: 可选。

输出：

- `output/desktop-screenshots/<path>`。
- payload `artifacts.screenshot_path`。

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

- backend probe。
- 当前窗口。
- 窗口列表摘要。
- 显示器和 DPI/Retina 信息。
- 权限状态。

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

后续控件级断言方向：

```json
{
  "action": "desktop_assert",
  "type": "element_exists",
  "desktop": "desk",
  "title_contains": "Notepad"
}
```

后续候选 type：

- `element_exists`，控件树 backend 接入后实现
- `element_text`，控件树 backend 接入后实现

## 输出分区

固定分类：

- `desktop-screenshots`: `desktop_capture type=screenshot`。
- `desktop-state`: `open_desktop` probe、`desktop_capture type=snapshot`。
- `desktop-windows`: `desktop_window type=list`。
- `desktop-elements`: Phase 1 控件树和候选控件。
- `desktop-vision`: Phase 2 图像/OCR 证据。
- `failure-desktop-screenshots`: 失败桌面截图。
- `failure-desktop-state`: 失败时 backend、权限、窗口列表、当前窗口和 step 摘要。

输出路径规则沿用现有 `resolve_output_path()`：

- action 配置里的输出路径相对于当前 plan 包 `output/`。
- 不允许以 `output/`、`resources/`、`docs/`、`sub-plans/` 开头。
- 不允许绝对输出路径。

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
  "platform": "Windows",
  "backend": "native",
  "error": "window not found",
  "current_window": {},
  "windows": [],
  "permissions": {},
  "monitors": [],
  "target": {},
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
- `desktop_input type=hotkey` 的 `keys` 为空失败。
- `desktop_input type=type_text` 缺少 `value` 失败。
- `desktop_window type=focus` 或 `desktop_wait type=window` 缺少 Window Query 失败。
- `desktop_assert type=window` 缺少 Window Query 失败。
- `desktop_assert type=screenshot` 缺少 `path` 失败。

错误消息必须包含 step index、plan 类型和违规 action。

## Self-check 契约

新增：

```powershell
python .\cplan.py self-check desktop-components
```

分层执行：

1. `schema`: 不依赖 GUI，验证 `automation_type`、跨线 action、必填字段、输出路径和子计划继承。
2. `probe`: 探测当前平台、可用 backend、GUI 会话、权限、显示器和窗口列表能力。
3. `live`: 轻量运行层。执行 `open_desktop`、`desktop_window list`、`desktop_capture screenshot/snapshot`、`desktop_assert screenshot/window`、`close_desktop`，验证不启动 Playwright 的桌面 runtime 链路。
4. `failure`: 使用不存在窗口触发失败，验证 `failure-desktop-screenshots/`、`failure-desktop-state/`、原始错误和目标定位摘要。
5. `real app`: Windows 用 Notepad，macOS 用 TextEdit 或系统可用轻量 App，验证聚焦、输入、保存、截图、断言和关闭。无 GUI、锁屏、权限不足或依赖缺失时返回 `skipped` 和原因。

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
- [桌面控制手册入口](../../handbook/desktop/README.md)
- [测试与验证说明](../develop/测试与验证说明.md)
