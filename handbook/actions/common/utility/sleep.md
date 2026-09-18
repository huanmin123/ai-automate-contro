# sleep

## 用途

让当前流程暂停一段时间。

相比显式等待，`sleep` 更适合放在没有特定状态可等待、只是想整体缓一缓的场景里。

## 必填字段

- `action`: 固定写成 `sleep`
- `seconds`: 等待秒数，数字。plan 校验要求必须显式提供，缺失时校验直接拒绝。

## 可选字段

无。

## 注意事项

- 运行时代码里保留 `seconds` 缺省时的兜底值 `1`，但正常 plan 都会先经过校验，缺失 `seconds` 无法通过；新 plan 不要依赖这个兜底值，应显式写 `seconds`（例如 `"seconds": 1`）。
- browser plan 优先使用 `wait` 等页面状态等待。
- desktop plan 优先使用 `desktop_wait` 或 `desktop_element type=wait` 等桌面状态等待。
