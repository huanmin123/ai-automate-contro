# sleep

## 用途

让当前流程暂停一段时间。

相比显式等待，`sleep` 更适合放在没有特定状态可等待、只是想整体缓一缓的场景里。

## 必填字段

- `action`: 固定写成 `sleep`

## 可选字段

- `seconds`: 等待秒数，默认 `1`

## 注意事项

- browser plan 优先使用 `wait` 等页面状态等待。
- desktop plan 优先使用 `desktop_wait` 或 `desktop_element type=wait` 等桌面状态等待。
