from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClientCommandSpec:
    name: str
    description: str
    scope: str
    usage: str = ""

    @property
    def slash(self) -> str:
        return f"/{self.name}"


LOCAL_COMMANDS: dict[str, str] = {
    "clear": "清空当前屏幕对话",
    "copy-last": "把最近一条 AI 回复写入本地剪贴板文件",
    "details": "切换工具调用细节显示",
    "exit": "关闭客户端",
    "export": "导出当前可见对话为 Markdown：/export [path]",
    "help": "查看客户端和 AI 会话命令",
    "plan": "查看当前 AI 工作计划",
    "status": "查看客户端、AI 会话和当前 plan 状态",
}
LOCAL_VISIBLE_COMMANDS: dict[str, str] = {
    "help": LOCAL_COMMANDS["help"],
    "status": LOCAL_COMMANDS["status"],
    "plan": LOCAL_COMMANDS["plan"],
    "clear": LOCAL_COMMANDS["clear"],
    "copy-last": LOCAL_COMMANDS["copy-last"],
    "export": LOCAL_COMMANDS["export"],
    "exit": LOCAL_COMMANDS["exit"],
}

AI_SESSION_COMMANDS: dict[str, str] = {
    "approve": "批准当前等待的受保护操作",
    "image": "把本地图片加入下一条消息",
    "new": "新建一个 AI 会话",
    "reject": "拒绝当前等待审批的操作",
    "resume": "恢复已保存的 AI 会话",
    "sessions": "列出已保存 AI 会话",
}
AI_SESSION_VISIBLE_COMMANDS: dict[str, str] = {
    "sessions": AI_SESSION_COMMANDS["sessions"],
    "resume": AI_SESSION_COMMANDS["resume"],
    "new": AI_SESSION_COMMANDS["new"],
    "image": AI_SESSION_COMMANDS["image"],
    "approve": AI_SESSION_COMMANDS["approve"],
    "reject": AI_SESSION_COMMANDS["reject"],
}
CONTEXTUAL_COMMANDS = frozenset({"approve", "reject"})
APPROVAL_COMMANDS = frozenset({"approve", "reject"})

SCOPE_LABELS = {
    "client": "客户端",
    "ai": "AI 会话",
}


def all_client_commands() -> list[ClientCommandSpec]:
    commands: list[ClientCommandSpec] = []
    seen: set[str] = set()

    def append(name: str, description: str, scope: str) -> None:
        if name in seen:
            return
        seen.add(name)
        commands.append(ClientCommandSpec(name=name, description=description, scope=scope))

    for name, description in LOCAL_VISIBLE_COMMANDS.items():
        append(name, description, "client")
    for name, description in AI_SESSION_VISIBLE_COMMANDS.items():
        append(name, description, "ai")
    return commands


def client_command_suggestions(text: str, *, limit: int = 40) -> list[ClientCommandSpec]:
    raw = str(text)
    if not raw.startswith("/") or "\n" in raw:
        return []
    token = raw[1:]
    if " " in token or "\t" in token:
        return []
    normalized = token.lower()
    candidates = [
        command
        for command in all_client_commands()
        if command.name.startswith(normalized)
    ]
    return candidates[:limit]


def format_client_command_help() -> str:
    lines = [
        "可用命令：",
        "  自然语言会直接发给 AI；无 AI 的 plan 控制请使用 cplan。",
        "",
    ]
    current_scope = ""
    for command in all_client_commands():
        if command.scope != current_scope:
            current_scope = command.scope
            lines.append(f"{SCOPE_LABELS.get(current_scope, current_scope)}：")
        lines.append(f"  /{command.name:<10} {command.description}")
    return "\n".join(lines)
