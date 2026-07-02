# wait_for_download

## 用途

等待一次下载事件发生，并把下载文件保存到指定位置。

## 必填字段

- `action`: 固定写成 `wait_for_download`
- `browser`: 浏览器会话名
- `path`: 相对于下载分区的保存路径，最终写入 `output/downloads/`
- `trigger`: 触发下载的单个动作对象

## 可选字段

- `output.as`: 把最终下载路径保存为变量
