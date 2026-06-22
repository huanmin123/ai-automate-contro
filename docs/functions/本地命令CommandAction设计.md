# 本地命令Command Action设计

## 背景

计划执行过程中经常需要调用本机脚本处理 HTTP 响应、转换文件、做本地校验或生成中间产物。因此新增 `command` action，让 plan 可以直接组合本地命令。

## 定位

`command` 是执行器级工具 action，不依赖浏览器。它只做同步命令调用，并把结果保存为变量或写入当前 plan 包 `output/commands/`。本项目按本地调试原文优先处理，不做危险命令关键词拦截，不隐藏 stdout 或 stderr。

它不负责后台进程、桌面控制、系统信息采集、进程管理或坐标级键鼠输入。

## 目标

- 支持 `argv` 直接执行程序，减少 shell quoting 风险。
- 支持 `command` shell 字符串和 `commands` 平台分支。
- Windows 默认 shell 使用 PowerShell 7 (`pwsh`)。
- 支持 stdin、stdout/stderr 捕获、JSON stdout 解析、退出码断言和输出落盘。
- 支持 `cwd` 使用当前 plan 包或包内子目录；输入文件默认放在当前 plan 包 `resources/`。
- 限制 stdout/stderr 文件产物写入当前 plan 包 `output/commands/`。
- 不做危险命令关键词拒绝；命令内容按 plan 原样执行。

## 非目标

- 不支持后台服务、daemon、进程保活或进程停止。
- 不支持把 stdout/stderr 写到源码、`resources/`、`docs/` 或仓库其他目录。
- 不绕过操作系统权限、UAC、管理员权限或安全桌面。
- 不让开放式 AI 直接执行命令；AI 仍应生成、校验和运行 plan。

## Schema

```json
{
  "action": "command",
  "type": "run",
  "argv": ["python", "resources/tool.py"],
  "stdin": "{{http_response.body_path}}",
  "stdout_type": "json",
  "stdout_path": "tool-stdout.json",
  "stderr_path": "tool-stderr.txt",
  "save_as": "tool_result"
}
```

平台命令：

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

## 输出变量

- `exit_code`: 进程退出码
- `ok`: 退出码是否命中 `expect_exit_code`
- `stdout`: stdout 文本，受 `max_output_bytes` 限幅
- `stderr`: stderr 文本，受 `max_output_bytes` 限幅
- `stdout_path`: stdout 落盘路径
- `stderr_path`: stderr 落盘路径
- `stdout_json`: `stdout_type=json` 时的解析结果
- `stdout_truncated`、`stderr_truncated`: 变量内容是否被截断
- `cwd`: 实际工作目录

## 本地执行边界

- 默认 cwd 是当前 plan 包根目录。
- `cwd` 默认是当前 plan 包根目录，也可以使用包内子目录；`stdin_path` 默认使用 `resources/...`。
- AI 创建 plan 时，用户给出本机 stdin 文件但没有明确要求长期依赖该路径，必须先导入当前 plan 包 `resources/`。
- `cwd` 和 `stdin_path` 支持绝对路径、共享盘、外部工作目录和越出 plan 包的相对路径；不需要任何额外审批字段。
- plan JSON 内部路径统一使用 `/`，不要使用 Windows 反斜杠。
- `stdout_path`、`stderr_path` 通过 output 路径规则写入 `output/commands/`。
- 命令变量和输出文件保留 stdout/stderr 原文；日志保留执行摘要，完整内容以输出文件和变量为准。

## 测试

- `test-plans/basic/command-run/plan.json`: 覆盖 argv、stdin、stdout JSON、stdout/stderr 落盘、变量继续参与 if 条件。
- `test-plans/http/client-request/plan.json`: 覆盖 HTTP 响应进入 command，command 读取 HTTP 下载文件，command JSON 输出继续进入 HTTP 请求。
- `test-plans/regression/http-command-validation-negative/resources/negative-cases.json`: 覆盖缺少命令、HTTP 参数错误和路径可移植性等负向校验；危险命令仍不作为安全关键词拦截。
