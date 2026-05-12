# wait_for_popup

## 用途

等待一次新弹出的页面，并把它注册成当前浏览器会话里的一个命名页面。

这个组件适合“点击按钮后打开新窗口 / 新标签页”的场景。

## 必填字段

- `action`: 固定写成 `wait_for_popup`
- `browser`: 浏览器会话名
- `popup_page`: 给新页面起的名字
- `trigger`: 触发弹窗的单个动作对象

## 可选字段

- `page`: 从哪个已存在页面触发，默认当前页
- `switch`: 捕获后是否切换到新页面，默认 `true`
- `save_as`: 把新页面名保存为变量

## 示例

```json
{
  "action": "wait_for_popup",
  "browser": "demo",
  "popup_page": "help",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "demo",
    "selector": "#open-help"
  }
}
```
