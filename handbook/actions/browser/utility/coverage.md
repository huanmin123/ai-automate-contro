# coverage

## 用途

通过 Chromium CDP 采集页面 JavaScript 和 CSS coverage，并写入 JSON 产物。

## 必填字段

- `action`: 固定写成 `coverage`
- `type`: `start`、`stop` 或 `clear`
- `browser`: 浏览器会话名

`type: stop` 还必须提供：

- `path`: 相对于 `output/json/` 的 JSON 路径

## 可选字段

- `page`: 页面名，默认当前页面
- `js`: 是否采集 JS coverage，默认 `true`
- `css`: 是否采集 CSS coverage，默认 `true`
- `output.as`: `type: stop` 时把 coverage 结果保存为变量

## 注意事项

- coverage 依赖 Chromium CDP；Firefox/WebKit 不支持时会明确报错。
- `type: start` 应在目标页面加载和交互前执行，`type: stop` 应在交互完成后执行。

## 示例

```json
{
  "action": "coverage",
  "type": "start",
  "browser": "main",
  "js": true,
  "css": true
}
```

```json
{
  "action": "coverage",
  "type": "stop",
  "browser": "main",
  "path": "coverage.json",
  "output": {"as": "coverage_result"}
}
```
