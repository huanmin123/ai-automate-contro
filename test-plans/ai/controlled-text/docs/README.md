# controlled-text-ai

## 目标

验证受控 `ai` 组件可以使用 `test-plans/config.json` 的全局 AI 服务完成真实模型调用，并把请求、响应、解析结果和 schema 校验产物写入当前 plan 包 `output/ai/`。

## 覆盖场景

- `type: connectivity`: 模型连通性测试。
- `type: extract_data`: 从客服工单文本中抽取结构化字段。
- `type: classify_text`: 从固定标签中分类。
- `write type: variables`: 保存变量快照到 `output/variables/`，便于人工检查流程结果。

## 运行方式

```powershell
python .\cplan.py validate --file .\test-plans\ai\controlled-text\plan.json
python .\cplan.py run --file .\test-plans\ai\controlled-text\plan.json --run-name ai-controlled-text
```

## 输出

- `output/ai/connectivity/result.json`
- `output/ai/extract-data/ticket-fields.json`
- `output/ai/classify-text/ticket-category.json`
- `output/variables/ai-results.json`
- `output/<run>/state.json`
- `output/<run>/events.jsonl`
