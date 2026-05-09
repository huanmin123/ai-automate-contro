# wait_for_response

## 用途

等待一次指定响应返回，并可把响应信息保存到变量。

适合确认接口真正返回成功，而不是只确认请求发出。

## 必填字段

- `action`: 固定写成 `wait_for_response`
- `browser`: 浏览器会话名
- `url`: 要等待的响应地址或可匹配的 URL
- `trigger`: 触发响应的单个动作对象

## 可选字段

- `page`: 从哪个页面触发，默认当前页
- `save_as`: 把响应信息保存成变量

## 保存结果

如果填写了 `save_as`，变量里会保存：

- `url`
- `status`
- `ok`

## 示例

```json
{
  "action": "wait_for_response",
  "browser": "demo",
  "url": "https://httpbin.org/get?case=response-demo",
  "save_as": "response_info",
  "trigger": {
    "action": "click",
    "browser": "demo",
    "selector": "#response-btn"
  }
}
```
