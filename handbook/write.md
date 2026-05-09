# write

## 用途

把运行过程中的数据写入当前 plan 包的 `output/`。

`write` 是统一写文件组件。能共用同一组核心参数的写入能力都放在这里，通过 `type` 控制输出格式。

## 必填字段

- `action`: 固定写成 `write`
- `type`: 写入类型，支持 `json`、`text`、`csv`、`variables`
- `path`: 相对于对应输出分区的路径

## 类型说明

| type | 输出分区 | 数据字段 | 说明 |
| --- | --- | --- | --- |
| `json` | `output/json/` | `value` | 把任意 JSON 可序列化值写成 JSON |
| `text` | `output/text/` | `value` | 把值转成文本写入 |
| `csv` | `output/csv/` | `value` | 把数组写成 CSV |
| `variables` | `output/variables/` | 不需要 | 导出当前变量池 |

## 可选字段

- `append`: 仅 `type: text` 有效，追加写入，默认 `false`
- `headers`: 仅 `type: csv` 有效，自定义 CSV 表头
- `indent`: 仅 `type: json` 和 `type: variables` 有效，默认 `2`

## 示例

写 JSON：

```json
{
  "action": "write",
  "type": "json",
  "path": "result.json",
  "value": {
    "status": "passed"
  }
}
```

写文本并追加：

```json
{
  "action": "write",
  "type": "text",
  "append": true,
  "path": "log.txt",
  "value": "second line\n"
}
```

写 CSV：

```json
{
  "action": "write",
  "type": "csv",
  "path": "accounts.csv",
  "value": "{{rows}}"
}
```

导出变量：

```json
{
  "action": "write",
  "type": "variables",
  "path": "snapshot.json"
}
```

## 输出路径约束

- `path` 是相对于组件输出分区的路径，不要以 `output/` 开头。
- 不能写入绝对路径。
- 不能写入 `resources/`、`docs/`、`sub-plans/`。
- 运行产物必须留在当前 plan 包的 `output/` 下。
