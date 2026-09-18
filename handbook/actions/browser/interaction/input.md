# input

## 用途

`input` 是浏览器页面级输入的统一 action，用于 Playwright 页面内的键盘、鼠标、触控和滚动操作。

浏览器页面级输入只使用 `input`，不要拆成单独的键盘、鼠标或滚动 action。

## 必填字段

- `action`: 固定写成 `input`
- `type`: 输入类型
- `browser`: 浏览器会话名

## device

- `device`: 可选，`keyboard`、`mouse`、`scroll`
- `press`、`type` 自动按 `keyboard` 处理
- `move`、`click`、`wheel`、`tap`、`swipe` 自动按 `mouse` 处理
- `into_view`、`by` 自动按 `scroll` 处理
- `down`、`up` 同时可能表示键盘按下/释放或鼠标按下/释放，必须显式写 `device`

## 类型说明

| device | type | 额外字段 | 说明 |
| --- | --- | --- | --- |
| `keyboard` | `press` | `key` | 按下并释放按键 |
| `keyboard` | `type` | `value` | 输入文本 |
| `keyboard` | `down` | `key` | 按下按键不释放 |
| `keyboard` | `up` | `key` | 释放按键 |
| `mouse` | `move` | `x`、`y` | 移动鼠标 |
| `mouse` | `click` | `x`、`y` | 点击坐标 |
| `mouse` | `down` | 无 | 按下鼠标键 |
| `mouse` | `up` | 无 | 释放鼠标键 |
| `mouse` | `wheel` | `delta_x` / `delta_y` | 鼠标滚轮 |
| `mouse` | `tap` | `x`、`y` | 触摸点击坐标 |
| `mouse` | `swipe` | `start_x`、`start_y`、`end_x`、`end_y` | 触控滑动手势 |
| `scroll` | `by` | `delta_x` / `delta_y` | 页面按偏移滚动 |
| `scroll` | `into_view` | locator | 滚动到元素可见 |

## 可选字段

- `delay_ms`: `device=keyboard type=type` 有效，默认 `50`
- `button`: 鼠标键，默认 `left`
- `click_count`: `device=mouse type=click` 有效，默认 `1`
- `steps`: `swipe` 分段数量，默认 `10`
- `duration_ms`: `swipe` 持续时间，默认 `300`
- `touch`: `swipe` 是否优先使用 Chromium CDP 触摸事件，默认 `true`
- `dom_touch_fallback`: `swipe` 的 CDP 触摸事件成功后，是否再向页面派发一轮 DOM 级 `touchstart` / `touchmove` / `touchend` 事件，默认 `true`。部分页面只监听 DOM touch 事件而不响应 CDP 输入层事件，关闭后这类页面可能收不到滑动
- `fallback_to_mouse`: 触摸事件不可用时是否回退鼠标拖动，默认 `true`；设为 `false` 且触摸事件失败时步骤直接报错

`swipe` 的触摸链路依赖 Chromium CDP（`Input.dispatchTouchEvent`），只有 `browser_type: chromium` 可用；Firefox 和 WebKit 上触摸事件会失败并按 `fallback_to_mouse` 回退为鼠标按下、逐步移动、释放的模拟拖动。

## 示例

键盘输入：

```json
{
  "action": "input",
  "device": "keyboard",
  "type": "type",
  "browser": "main",
  "value": "hello"
}
```

按回车：

```json
{
  "action": "input",
  "type": "press",
  "browser": "main",
  "key": "Enter"
}
```

页面滚动：

```json
{
  "action": "input",
  "type": "by",
  "browser": "main",
  "delta_y": 300
}
```

触控滑动：

```json
{
  "action": "input",
  "device": "mouse",
  "type": "swipe",
  "browser": "mobile",
  "start_x": 40,
  "start_y": 190,
  "end_x": 300,
  "end_y": 190,
  "steps": 8,
  "duration_ms": 240,
  "touch": true
}
```
