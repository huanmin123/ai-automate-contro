# ai

`ai` 是受控专项 AI 组件，用于在 plan 执行中处理明确的数据任务。

它不是 AI 终端，也不是开放聊天节点。`ai` 组件不能创建、运行、调试或修复 plan；这些属于 plan 级 AI 终端能力，不能写进普通 plan `steps`。

## 支持类型

| type | 用途 |
| --- | --- |
| `connectivity` | 测试模型服务是否可用 |
| `extract_data` | 从文本中抽取结构化数据 |
| `classify_text` | 在固定标签中分类 |
| `transform_data` | 按指令转换数据 |
| `summarize_text` | 生成摘要 |

## 字段

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `action` | 是 | 固定为 `ai` |
| `type` | 是 | AI 任务类型 |
| `service` | 否 | `config.ai_services` 中的服务名，默认 `default` |
| `input` | 是 | 输入数据，可以使用变量 |
| `instruction` | 否 | 当前任务的补充指令 |
| `schema` | 部分类型必填 | 输出 JSON Schema；`extract_data` 必填 |
| `labels` | 分类必填 | `classify_text` 的候选标签；如果已提供 `schema` 可省略 |
| `save_as` | 是 | 保存解析结果的变量名 |
| `path` | 否 | 调试产物路径，相对于 `output/ai/` |

## 配置

AI 服务注册在集合级或局部 `config.json`：

```json
{
  "ai_services": {
    "default": {
      "provider": "openai-compatible",
      "api": "chat_completions",
      "base_url": "https://example.com/v1",
      "model": "model-name",
      "api_key": "temporary-test-key",
      "timeout_seconds": 90,
      "response_format": "json_schema",
      "strict_schema": true
    }
  }
}
```

`response_format` 可选 `json_schema`、`json_object` 或 `plain`，默认 `json_schema`。框架只按当前配置调用模型服务；如果用户提供的模型、余额、网关或 OpenAI-compatible 协议返回错误，会直接失败，不做自动降级、手动重试或格式兜底。SDK/LangChain 自身的传输重试可以通过 `max_retries` 显式配置。

不要把真实密钥写入要分发或提交的配置。需要真实服务时，只保留在本机运行根或当前 plan 包的配置中。

## 输出

所有 `ai` 调试产物必须写入当前 plan 包：

```text
output/ai/
  connectivity/
  extract-data/
  classify-text/
  transform-data/
  summarize-text/
```

`path` 是相对于 `output/ai/` 的路径，不能以 `output/`、`resources/`、`docs/` 或 `sub-plans/` 开头。

## 示例

```json
{
  "action": "ai",
  "type": "extract_data",
  "service": "default",
  "instruction": "从客服工单中抽取联系人姓名、邮箱和问题。",
  "input": "{{ticket_text}}",
  "schema": {
    "contact_name": "string",
    "email": "string",
    "issue": "string"
  },
  "save_as": "ticket_fields",
  "path": "extract-data/ticket-fields.json"
}
```

执行后：

- 解析后的 JSON 保存到变量 `ticket_fields`。
- 调试产物保存到 `output/ai/extract-data/ticket-fields.json`。
