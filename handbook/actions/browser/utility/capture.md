# capture

## 用途

统一保存页面或浏览器上下文产物。

浏览器不会在普通 action 成功后自动截图；需要页面图片证据时必须显式使用 `type: "screenshot"`。

## 必填字段

- `action`: 固定写成 `capture`
- `type`: `screenshot`、`html`、`storage_state`
- `browser`: 浏览器会话名
- `path`: 相对于对应输出分区的路径

## 类型说明

| type | 输出分区 | 说明 |
| --- | --- | --- |
| `screenshot` | `output/screenshots/` | 保存页面截图 |
| `html` | `output/html/` | 保存当前页面 HTML |
| `storage_state` | `output/storage-states/` | 保存浏览器状态 |

## 使用经验

- 普通流程不自动截图。只有用户要求页面图片证据、需要人工复盘或调试失败现场时才显式写 `capture type=screenshot`。
- `full_page=true` 可能很慢，且会生成较大的图片。只需要证明当前状态时优先截当前视口；需要完整长页面证据时再用 full page。
- 保存 HTML 适合调试 selector、页面结构和服务端渲染结果。含敏感数据的页面仍按本地调试原文处理，是否提交由用户决定。
- `storage_state` 适合导出可复用登录态文件；同一个 plan 包长期复用状态时优先用 `open_browser use_profile=true`。

## 可选字段

- `full_page`: 仅 `type: screenshot` 有效，默认 `false`

## 示例

```json
{
  "action": "capture",
  "type": "screenshot",
  "browser": "main",
  "path": "login-page.png",
  "full_page": true
}
```
