# llm_extract_json

## 用途

调用已配置的大模型，把一段文本提取成结构化 JSON 对象。

这个组件特别适合：

- OCR 结果二次清洗
- 文本规则归一化
- 页面提示文案解析
- 把自然语言转成后续可编排字段

## 必填字段

- `action`: 固定写成 `llm_extract_json`
- `service`: 模型服务别名
- `input`: 要提取的原始文本
- `save_as`: 保存解析后 JSON 对象的变量名

## 可选字段

- `schema_description`: 目标结构说明
- `system_prompt`: 自定义系统提示词
- `model`: 覆盖服务默认模型
- `temperature`: 默认 `0`
- `save_text_as`: 额外保存模型原始文本输出

## 输出要求

执行器会要求模型只输出 JSON。

如果模型包了代码块，执行器会自动尝试提取其中的 JSON。

## 示例

```json
{
  "action": "llm_extract_json",
  "service": "remote_openai_compatible",
  "input": "账号: test@example.com, 状态: 可用",
  "schema_description": "输出 {\"account\": string, \"status\": string}",
  "save_as": "parsed"
}
```

## 配置建议

- 推荐把真实 API key 放在环境变量里，例如 `KEYGEN_DLI_API_KEY`
- 计划里只写 `service` 别名，不直接写密钥
