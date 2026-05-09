# screenshot

## 用途

对当前页面截图并保存到文件。

## 必填字段

- `action`: 固定写成 `screenshot`
- `browser`: 目标浏览器会话名称
- `path`: 截图输出路径

## 可选字段

- `full_page`: 是否截取整页，默认 `false`

## 示例

```json
{
  "action": "screenshot",
  "browser": "main",
  "path": "output/login-page.png",
  "full_page": true
}
```

## 什么时候用

- 验证页面当前状态
- 记录失败现场
- 做手册或调试存档

## 注意事项

- 相对路径会基于项目根目录解析。
- 输出目录不存在时，执行器会自动创建。
