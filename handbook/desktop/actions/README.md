# 桌面 action 手册

本目录只记录 `automation_type: "desktop"` 可用的桌面专属 action。浏览器 DOM、Playwright selector、浏览器 `mouse`、浏览器 `keyboard` 和浏览器 `capture` 不放在这里。

当前文档：

- [desktop_assert](./desktop_assert.md)

新增或修改桌面 action 时，需要同步：

- `src/ai_automate_contro/engine/actions/desktop.py`
- `src/ai_automate_contro/plans/validation_rules.py`
- `src/ai_automate_contro/plans/validation_fields.py`
- [桌面 Action 与 Runtime 契约](../../../docs/functions/桌面Action与Runtime契约.md)
- `python .\cplan.py self-check desktop-components`
