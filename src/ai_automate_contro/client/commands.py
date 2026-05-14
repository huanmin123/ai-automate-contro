from __future__ import annotations

from dataclasses import dataclass

from ai_automate_contro.client.management import MANAGEMENT_COMMANDS


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
    "details": "切换工具调用细节显示",
    "export": "导出当前可见对话为 Markdown：/export [path]",
    "help": "查看客户端、plan 管理和 AI 会话命令",
}

AI_SESSION_COMMANDS: dict[str, str] = {
    "approve": "批准当前等待的受保护操作",
    "back": "关闭客户端",
    "compact": "压缩并归档当前会话，等同 /compress",
    "compress": "压缩并归档当前会话",
    "exit": "关闭客户端",
    "history": "查看最近几条会话消息",
    "image": "把本地图片加入下一条消息",
    "keyboard": "查看键盘快捷键和输入说明",
    "new": "新建一个 AI 会话",
    "pending": "查看等待审批的受保护操作",
    "quit": "关闭客户端",
    "reject": "拒绝当前等待审批的操作",
    "render": "查看或切换 AI 回复渲染方式",
    "resume": "恢复已保存的 AI 会话",
    "sessions": "列出已保存 AI 会话",
}

SCOPE_LABELS = {
    "client": "客户端",
    "plan": "plan",
    "ai": "AI 会话",
}


def all_client_commands() -> list[ClientCommandSpec]:
    commands: dict[str, ClientCommandSpec] = {}
    for name, description in LOCAL_COMMANDS.items():
        commands[name] = ClientCommandSpec(name=name, description=description, scope="client")
    for name, description in MANAGEMENT_COMMANDS.items():
        commands.setdefault(name, ClientCommandSpec(name=name, description=description, scope="plan"))
    for name, description in AI_SESSION_COMMANDS.items():
        commands.setdefault(name, ClientCommandSpec(name=name, description=description, scope="ai"))
    return sorted(commands.values(), key=lambda command: (command.name != "help", command.name))


def client_command_suggestions(text: str, *, limit: int = 8) -> list[ClientCommandSpec]:
    raw = str(text)
    if not raw.startswith("/") or "\n" in raw:
        return []
    token = raw[1:]
    if " " in token or "\t" in token:
        return []
    normalized = token.lower().replace("-", "_")
    candidates = [command for command in all_client_commands() if command.name.startswith(normalized)]
    return candidates[:limit]


def format_client_command_help() -> str:
    lines = [
        "可用命令：",
        "  自然语言会直接发给 AI；plan 管理、会话和客户端动作都用行首 /command。",
        "  需要把斜杠开头的文字发给 AI 时，用 /ai <message>。",
        "",
    ]
    current_scope = ""
    for command in all_client_commands():
        if command.scope != current_scope:
            current_scope = command.scope
            lines.append(f"{SCOPE_LABELS.get(current_scope, current_scope)}：")
        lines.append(f"  /{command.name:<10} {command.description}")
    return "\n".join(lines)
