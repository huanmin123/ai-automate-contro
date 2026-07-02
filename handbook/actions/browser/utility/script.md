# script

## 用途

在页面或浏览器上下文中执行受控 JavaScript。

## 必填字段

- `action`: 固定写成 `script`
- `type`: `evaluate` 或 `add_init_script`
- `browser`: 浏览器会话名
- `js`: JavaScript 表达式或函数

## 类型说明

| type | 说明 |
| --- | --- |
| `evaluate` | 在当前页面执行 JS，可保存返回值 |
| `add_init_script` | 给上下文注册初始化脚本，后续新页面加载前注入 |

## 可选字段

- `page`: 页面名，默认当前页面
- `arg`: `evaluate` 的参数
- `output.as`: `evaluate` 返回值保存为变量

## 示例

```json
{
  "action": "script",
  "type": "evaluate",
  "browser": "main",
  "js": "() => document.title",
  "output": {"as": "page_title"}
}
```

注册初始化脚本：

```json
{
  "action": "script",
  "type": "add_init_script",
  "browser": "main",
  "js": "window.__automation = true;"
}
```
