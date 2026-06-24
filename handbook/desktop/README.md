# 桌面控制手册入口

本目录是 `automation_type: "desktop"` plan 的阅读入口。桌面线控制 Windows/macOS 真实桌面会话里的本机应用、窗口、菜单、控件、系统权限、截图、键盘、鼠标、图像定位和 OCR。

桌面控制不是终端命令扩展，也不是只控制某一个 App。它的长期目标是在操作系统允许、用户已登录、桌面未锁屏且权限齐备的前提下，尽量覆盖人像平时操作电脑一样完成的本机操作。

浏览器 DOM、Playwright selector、浏览器网络事件、浏览器 storage state 和页面内 `mouse`/`keyboard` 不属于桌面线；这些能力进入 [浏览器自动化手册入口](../browser/README.md)。

当前已落地桌面基础 action：`open_desktop`、`close_desktop`、`desktop_window`、`desktop_input`、`desktop_capture`、`desktop_wait`、`desktop_assert`。本入口负责隔离桌面线手册，避免把浏览器 DOM、Playwright selector、浏览器 `mouse`/`keyboard` 当成桌面键鼠使用。

Phase 0 编码必须先遵守 [桌面Action与Runtime契约](../../docs/functions/桌面Action与Runtime契约.md)。该契约定义 action schema、backend payload、输出分区、失败证据、validator 和 self-check。

## 适用 plan

```json
{
  "automation_type": "desktop",
  "variables": {},
  "steps": []
}
```

## 当前 action 范围

能力域：

- App 和窗口：打开、连接、聚焦、切换、移动、调整大小、最小化、最大化、关闭。
- 键盘鼠标：输入文本、快捷键、复制粘贴、点击、双击、右键、拖拽、滚轮。
- 控件操作：按钮、输入框、菜单、列表、表格、树、对话框、文件选择和保存窗口。
- 视觉识别：截图、区域截图、图像定位、OCR、标注图和失败证据。
- 人工交接：系统权限、验证码、二次验证、安全弹窗和无法可靠判断的 UI。

桌面专属 action：

- `open_desktop`
- `close_desktop`
- `desktop_window`
- `desktop_input`
- `desktop_capture`
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

禁止在 desktop plan 中使用 `open_browser`、`navigate`、`element`、浏览器 `mouse`、浏览器 `keyboard`、浏览器 `capture` 等浏览器专属 action。

## 文档落点

桌面 action 文档放在：

```text
handbook/desktop/actions/
  open_desktop.md
  close_desktop.md
  desktop_window.md
  desktop_input.md
  desktop_capture.md
  desktop_wait.md
  desktop_assert.md
```

每个 action 文档必须说明：

- 支持的 `type`。
- Windows backend 行为。
- macOS backend 行为。
- 需要的权限。
- 输出分区。
- 失败证据。
- 不能跨越的系统边界。

当前已补充：

- [desktop_assert](./actions/desktop_assert.md)

## 取证规则

真实桌面应用流程不能凭用户文字猜坐标。AI 创建最终 desktop plan 前必须先获取窗口列表、控件树、截图、图像定位结果、OCR 结果或人工确认。

Windows 优先使用 UI Automation / Win32 控件语义，坐标和图像定位只作为兜底。macOS 必须检测 Accessibility、Screen Recording、Automation 等权限；代码可以触发授权提示、打开系统设置并暂停等待用户确认，但不能静默替用户授权。

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
