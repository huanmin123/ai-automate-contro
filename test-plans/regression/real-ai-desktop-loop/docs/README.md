# real-ai-desktop-loop

## 目标

验证桌面执行线的 smoke plan 可被确定性运行，并提供真实模型驱动 AI 终端闭环的回归入口。

## 前置条件

- Windows 或 macOS 图形桌面会话。
- 确定性 smoke 不需要真实模型。
- 真实模型闭环需要 OpenAI-compatible 账户；本机可用 `D:\模型密钥.txt`，命令会临时解析 URL 和 `sk-*` key，不修改仓库配置。

## 运行方式

确定性运行固定 desktop plan：

```powershell
python .\cplan.py run --file .\test-plans\regression\real-ai-desktop-loop\plan.json
```

真实模型驱动 AI 终端创建并运行临时 desktop smoke plan：

```powershell
python .\main.py self-check ai-real-desktop-loop --api-key-file D:\模型密钥.txt
```

只验证桌面工具链和 debug 修复闭环、不调用真实模型：

```powershell
python .\main.py self-check ai-desktop-loop
```
