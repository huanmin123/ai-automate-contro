# ai-text-processing

## 目标

验证受控 `ai` 组件的文本转换和摘要能力可以使用 `test-plans/config.json` 的全局 AI 服务完成真实模型调用。

## 覆盖场景

- `type: transform_data`: 按固定指令清洗和规范化文本。
- `type: summarize_text`: 按固定指令生成结构化摘要字段。
- `write type: variables`: 保存变量快照到 `output/variables/`，便于人工检查结果。

## 运行方式

```powershell
python .\main.py plan validate --file .\test-plans\ai\text-processing\plan.json
python .\main.py plan run --file .\test-plans\ai\text-processing\plan.json --run-name ai-text-processing
```

## 输出

- `output/ai/transform-data/cleaned-emails.json`
- `output/ai/summarize-text/incident-summary.json`
- `output/variables/ai-text-processing-results.json`
- `output/<run>/state.json`
- `output/<run>/events.jsonl`
