# read

## 用途

从当前 plan 包内读取 JSON、文本或 CSV 数据，并保存为变量。

`read` 是统一读文件组件。能共用 `path`、`type`、`save_as` 的读取能力都放在这里，通过 `type` 控制解析方式。

## 必填字段

- `action`: 固定写成 `read`
- `type`: 读取类型，支持 `json`、`text`、`csv`、`storage_state`
- `path`: 输入文件路径
- `save_as`: 保存到变量池的变量名

## 类型说明

| type | 读取结果 |
| --- | --- |
| `json` | JSON 对象、数组或值 |
| `text` | 字符串 |
| `csv` | 字典数组 |
| `storage_state` | storage state 文件的绝对路径字符串 |

## 可选字段

- `split_lines`: 仅 `type: text` 有效，设置为 `true` 时按行拆分，并过滤空行。

## 示例

读取资源 JSON：

```json
{
  "action": "read",
  "type": "json",
  "path": "resources/accounts.json",
  "save_as": "accounts"
}
```

读取输出 CSV：

```json
{
  "action": "read",
  "type": "csv",
  "path": "output/csv/accounts.csv",
  "save_as": "rows"
}
```

读取文本并按行拆分：

```json
{
  "action": "read",
  "type": "text",
  "path": "resources/accounts.txt",
  "split_lines": true,
  "save_as": "lines"
}
```

读取浏览器状态文件路径：

```json
{
  "action": "read",
  "type": "storage_state",
  "path": "output/storage-states/state-demo.json",
  "save_as": "saved_state_path"
}
```

## 路径约束

- 资源输入优先放在当前 plan 包的 `resources/`。
- 需要读取运行产物时，可以读取当前 plan 包的 `output/<component>/...`。
- 不建议跨 plan 包读取文件；不同需求包之间保持独立。
