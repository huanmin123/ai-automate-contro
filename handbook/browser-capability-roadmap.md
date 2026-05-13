# 浏览器能力落地清单

## 已优先落地

- 浏览器上下文配置：多浏览器类型、viewport、locale、timezone、user_agent、headers、proxy、权限、移动端基础参数、HAR 录制、视频录制。
- 定位能力：普通 selector、iframe 内定位、role/text/label/placeholder/alt/title/test_id 语义定位。
- 元素能力：双击、右键、拖拽、强制点击、位置点击、修饰键、文件选择器。
- 等待能力：load state、element state、JS 条件等待。
- 网络能力：request/response 捕获增强、响应体读取、route mock、abort、continue、headers。
- 脚本与状态：evaluate、add_init_script、cookies、localStorage、sessionStorage。
- 观测能力：trace start/stop、console、pageerror、requestfailed、WebSocket 起始事件采集。
- 数据与断言：URL、title、bounding box、CSS 提取；attribute、CSS、checked、enabled、visible、hidden、title 断言。

## 后续再做

- HAR 回放。
- coverage 采集。
- 更完整的移动设备预设和复杂触摸手势。
- WebSocket 帧内容和 SSE 事件观测。
- 多 frame 名称/URL 定位和 frame 列表提取。
- accessibility snapshot。

## 推荐优先级

1. HAR 回放。
2. coverage 采集。
3. WebSocket 帧内容和 SSE 事件观测。
4. 移动端设备预设和复杂触摸手势。
5. accessibility snapshot。
