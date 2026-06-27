# 桌面控制手册入口

本入口只给 `automation_type: "desktop"` plan 使用。桌面线控制 Windows/macOS 真实桌面里的本机 App、窗口、控件、系统级键鼠、截图、图像/OCR 证据和系统权限。

浏览器 DOM、Playwright selector、浏览器网络事件、浏览器 storage state 和页面内 `mouse`/`keyboard` 进入 [浏览器自动化手册入口](../browser/README.md)。

AI 写 desktop plan 时优先读取本手册的 action 文档。

## 适用 plan

```json
{
  "automation_type": "desktop",
  "variables": {},
  "steps": []
}
```

## 可用 action

桌面专属 action：

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

通用 action：

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
- `variable`

禁止在 desktop plan 中使用 `open_browser`、`navigate`、`element`、浏览器 `mouse`、浏览器 `keyboard`、浏览器 `capture` 等浏览器专属 action。

## 文档落点

桌面 action 文档放在：

```text
handbook/actions/desktop/
  open_desktop.md
  close_desktop.md
  desktop_app.md
  desktop_window.md
  desktop_element.md
  desktop_input.md
  desktop_capture.md
  desktop_wait.md
  desktop_assert.md
  locator_strategy.md
  desktop_vision.md
```

动作入口：[actions/desktop](../actions/desktop/README.md)。

## 取证规则

真实桌面应用流程不能凭用户文字猜坐标。AI 创建最终 desktop plan 前必须先获取窗口列表、控件树、截图、图像定位结果或人工确认。

最终 plan 前先探测 `capability_matrix`、窗口列表、控件摘要、截图路径、权限/依赖或人工确认。plan 内还应使用 `desktop_window`、`desktop_element list/dump/find/get_text/get_state/wait/get_table/get_tree`、`desktop_capture`、`desktop_vision`、`desktop_wait` 或 `desktop_assert` 保存运行证据。`desktop_element click/set_text/select/invoke/select_cell/expand_tree/collapse_tree/select_tree/invoke_menu/scroll_element` 和 `desktop_input` 只算操作推进，不单独算识别证据。

桌面线按当前运行环境选择平台能力：Windows 环境使用 UI Automation / Win32 控件语义，macOS 环境使用 Accessibility/AX 能力；坐标和图像定位只作为兜底。macOS 必须检测 Accessibility、Screen Recording、Automation 等权限；代码可以触发授权提示、打开系统设置并暂停等待用户确认，但不能静默替用户授权。

菜单和滚动容器可能受焦点、短生命周期弹出层或自绘 UI 影响；必要时配合截图、等待、状态断言或人工确认。

## 能力边界

桌面 plan 可以尽量模拟人类可见操作，但不承诺突破系统安全边界。以下场景应失败、跳过或交给 `manual_confirm`：

- 锁屏、无 GUI、远程会话断开、未登录桌面。
- Windows UAC 安全桌面、管理员权限窗口和高完整性级别进程。
- macOS 未授权 Accessibility、Screen Recording 或 Automation。
- 验证码、人机验证、短信/邮箱二次验证、真实支付、真实删除或生产数据变更。
- DRM/受保护内容、银行安全控件、反作弊游戏、刻意阻止自动化的软件。
- 控件树不可见且截图/OCR/图像特征不稳定的界面。

## 最小示例

```json
{
  "automation_type": "desktop",
  "variables": {},
  "steps": [
    {
      "action": "open_desktop",
      "name": "desk",
      "backend": "auto",
      "request_permissions": true
    },
    {
      "action": "desktop_app",
      "type": "launch",
      "desktop": "desk",
      "app": "notepad.exe",
      "save_as": "app_launch"
    },
    {
      "action": "desktop_window",
      "type": "list",
      "desktop": "desk",
      "save_as": "windows"
    },
    {
      "action": "desktop_capture",
      "type": "screenshot",
      "desktop": "desk",
      "path": "initial-screen.png"
    }
  ]
}
```
