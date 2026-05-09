# run_sub_plan

在主 `plan.json` 中执行同一需求包内的子计划。

## 字段

- `path`: 子计划路径，必须是以 `sub-plans/` 开头的相对路径。

## 约束

- 只能引用当前 plan 包内的文件。
- 子计划必须放在当前 plan 包的 `sub-plans/` 目录下。
- 不能引用任何名为 `plan.json` 的主入口。
- 子计划文件名必须符合 `*-plan.json`。
- 推荐使用 kebab-case；顺序敏感时可以使用 `01-xxx-plan.json`。

## 示例

```json
{
  "action": "run_sub_plan",
  "path": "sub-plans/login-plan.json"
}
```
