# AI 能力重构设计

## 目标

AI 能力分成两类，避免执行器、终端和专项模型能力混在一起：

- plan 级 AI：帮助用户创建、管理、调试、修复和总结 plan。
- 专项 AI：在 plan 执行中处理明确的数据、图像或文本任务。

执行器本身仍保持确定性。AI 终端可以调用管理命令和工具，但不直接接管浏览器控制。

## 非目标

- 不让自然语言对话节点进入普通执行链路。
- 不让 AI 绕过人工验证、验证码、二次认证或人工确认。
- 不在 plan、文档、输出或仓库配置中保存密钥。
- 不让专项 AI 修改文件系统、执行命令或控制浏览器。

## plan 级 AI

plan 级 AI 运行在 AI 终端中，面向整个 plan 包生命周期：

- 需求澄清。
- 创建 plan 包。
- 生成 `plan.json`。
- 生成 `config.json` 和 `docs/README.md`。
- 校验 plan 结构、路径和输出约束。
- 运行 plan。
- 读取日志、事件和输出产物。
- 分析失败原因。
- 生成修复补丁。
- 经用户确认后应用补丁。
- 生成运行报告。

plan 级 AI 不是 plan action，不写入 `steps`。

## 专项 AI

专项 AI 是受控组件，只处理输入输出明确的任务：

- `ai_ocr`: 图像文字识别。
- `ai_extract_data`: 从文本中抽取结构化数据。
- `ai_transform_data`: 数据清洗和格式转换。
- `ai_classify_text`: 文本分类。
- `ai_summarize_text`: 文本摘要。

专项 AI 可以作为 plan action，但每个组件必须有固定字段、固定系统提示词、固定输出 schema 和输出校验。

示例：

```json
{
  "action": "ai_extract_data",
  "service": "text_extractor",
  "input": "{{raw_text}}",
  "schema": {
    "email": "string",
    "status": "string"
  },
  "save_as": "parsed"
}
```

## 配置模型

AI 服务注册进入当前 plan 集合配置或 plan 局部配置：

```text
plans/config.json
test-plans/config.json
<plan-package>/config.json
```

优先级：

```text
集合级 config < plan 局部 config < plan.json variables
```

建议字段：

```json
{
  "ai_services": {
    "text_extractor": {
      "provider": "openai-compatible",
      "base_url": "http://127.0.0.1:18733/v1",
      "model": "model-name",
      "api_key_env": "TEXT_EXTRACTOR_API_KEY",
      "timeout_seconds": 60
    }
  }
}
```

密钥只通过环境变量读取。公开示例配置只能放服务别名、模型名、超时等非敏感字段。

## 输出约束

专项 AI 的运行产物必须写入当前 plan 包的 `output/ai/`：

```text
output/ai/
  ocr/
  extract-data/
  transform-data/
  classify-text/
  summarize-text/
```

每次调用至少保留：

- 请求摘要。
- 原始响应。
- 解析结果。
- schema 校验结果。
- 错误信息。

禁止写入源码目录、`resources/`、`docs/` 或其他 plan 包。

## AI 终端工作流

### 创建 plan

```text
用户描述需求
  -> AI 澄清目标页面、输入数据、断言和输出
  -> 生成 plan 包结构
  -> 写入 plan.json / config.json / docs
  -> 校验 plan
  -> 用户确认
```

### 调试 plan

```text
用户选择 plan
  -> AI 读取 plan、docs、最近 output
  -> 调用管理终端运行
  -> 读取 events.jsonl / run.log / result.json
  -> 定位失败 step 和原因
  -> 生成修复补丁
  -> 用户确认
  -> 应用补丁并再次验证
```

### 生成报告

```text
读取 result.json
读取关键 artifacts
读取失败截图或输出文件
生成 Markdown 报告到 output/reports/
```

## 验收标准

- 用户可以通过 AI 终端创建一个新 plan 包。
- AI 终端可以运行 plan 并解释失败原因。
- AI 终端可以生成修复补丁，并在用户确认后应用。
- 专项 AI 组件输出可被 schema 校验。
- 所有专项 AI 调试产物都落在当前 plan 包 `output/ai/`。
