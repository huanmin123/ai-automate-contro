# command

## 用途

同步调用本地命令，适合调用项目脚本、任意本机脚本、转换文件、校验 HTTP 响应、生成中间产物。

`command` 按本地调试原文优先处理。它限制 stdout/stderr 文件产物写入 `output/commands/`，但不做危险命令关键词拦截，不隐藏 stdout/stderr，也不因为本机输入路径位于 plan 包外而拒绝。

## 必填字段

- `action`: 固定写成 `command`
- `type`: 固定写成 `run`
- `command`、`commands` 或 `argv`: 三选一

## 命令字段

使用 `argv` 直接执行程序，优先用于可移植脚本：

```json
{
  "action": "command",
  "type": "run",
  "argv": ["python", "resources/tool.py"],
  "save_as": "tool_result"
}
```

使用 `command` 通过 shell 执行字符串：

```json
{
  "action": "command",
  "type": "run",
  "command": "Get-ChildItem resources",
  "shell": "pwsh",
  "save_as": "listing"
}
```

使用 `commands` 按平台提供命令：

```json
{
  "action": "command",
  "type": "run",
  "commands": {
    "windows": "Get-ChildItem resources",
    "linux": "ls resources",
    "macos": "ls resources"
  },
  "save_as": "listing"
}
```

## 可选字段

- `cwd`: 工作目录，默认当前 plan 包根目录；非绝对路径相对当前 plan 包
- `stdin`: 传给命令的标准输入文本
- `stdin_path`: 从本机文件读取标准输入，默认使用当前 plan 包 `resources/...`
- `stdout_type`: `text` 或 `json`；为 `json` 时解析 stdout 并保存到 `stdout_json`
- `stdout_path`: stdout 写入当前 plan 包 `output/commands/`
- `stderr_path`: stderr 写入当前 plan 包 `output/commands/`
- `expect_exit_code`: 期望退出码，默认 `0`，可写数字或数组
- `timeout_ms`: 超时毫秒，默认 `30000`
- `max_output_bytes`: 保存到变量里的 stdout/stderr 字节上限
- `encoding`: 输出解码，默认 `utf-8`
- `shell`: `auto`、`pwsh`、`powershell`、`cmd`、`sh`、`bash`
- `env`: 追加环境变量对象
- `save_as`: 保存命令结果变量名

## 响应变量

```json
{
  "exit_code": 0,
  "ok": true,
  "stdout": "{\"ok\": true}",
  "stderr": "",
  "stdout_path": "<plan-package>/output/commands/tool.json",
  "stderr_path": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "cwd": "<plan-package>",
  "stdout_json": {
    "ok": true
  }
}
```

## 约束

- `command`、`commands`、`argv` 只能选一种。
- `cwd` 默认使用当前 plan 包或包内子目录；`stdin_path` 默认使用当前 plan 包 `resources/...`。
- AI 创建 plan 时，用户没有指定固定本机 stdin 文件时，推荐把文件导入当前包 `resources/`，再写 `resources/...`。
- `cwd`、`stdin_path` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
- `stdout_path`、`stderr_path` 只能写入当前 plan 包 `output/commands/`。
- 响应变量和输出文件保留 stdout/stderr 原文；日志保留执行摘要。
- 只支持同步命令；不管理后台进程或长期服务。
