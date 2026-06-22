# wait_for_file_chooser

## 用途

等待页面打开文件选择器，并把本地文件设置进去。

当页面不是直接暴露 `<input type="file">`，而是点击按钮后由 JS 调起文件选择器时，使用这个动作。

## 必填字段

- `action`: 固定写成 `wait_for_file_chooser`
- `type`: 固定写成 `set_files`
- `browser`: 浏览器会话名
- `files`: 文件路径字符串或数组，默认使用当前 plan 包 `resources/...`
- `trigger`: 触发文件选择器的单个动作对象

## 可选字段

- `page`: 页面名，默认当前页面
- `save_as`: 把最终文件路径数组保存为变量

## 示例

```json
{
  "action": "wait_for_file_chooser",
  "type": "set_files",
  "browser": "main",
  "files": "resources/avatar.png",
  "trigger": {
    "action": "element",
    "type": "click",
    "browser": "main",
    "selector": "#upload-avatar"
  }
}
```

## 路径约束

- 上传文件默认放在当前 plan 包 `resources/`。
- AI 创建 plan 时，用户没有指定固定本机文件路径时，推荐先把文件导入当前包 `resources/`，再写 `resources/...`。
- `files` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
