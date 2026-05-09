# load_txt

## 用途

读取文本文件，可以按整段读取，也可以按行拆分成数组。

## 必填字段

- `action`: 固定写成 `load_txt`
- `path`: 文本文件路径
- `save_as`: 保存变量名

## 可选字段

- `split_lines`: 是否按行拆分，默认 `false`

## 示例

```json
{
  "action": "load_txt",
  "path": "../data/sample_lines.txt",
  "save_as": "emails",
  "split_lines": true
}
```

如果你运行的是 `examples/scenarios/data-driven/` 下的示例，那么这里的 `../../data/` 实际会指向 `examples/data/`。
