# load_storage_state

## 用途

把一个 storage state 文件路径保存为变量，常用于后续 `open_browser` 读取。

## 必填字段

- `action`: 固定写成 `load_storage_state`
- `path`: storage state 文件路径
- `save_as`: 保存变量名
