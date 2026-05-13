from __future__ import annotations

from prompt_toolkit.styles import Style


COMPLETION_MENU_STYLE: dict[str, str] = {
    "completion-menu": "bg:#ffffff",
    "completion-menu.completion": "fg:#000000 bg:#ffffff noreverse",
    "completion-menu.completion.current": "fg:#00a6b2 bg:#ffffff bold noreverse",
    "completion-menu.meta.completion": "fg:#a8a8a8 bg:#ffffff noreverse",
    "completion-menu.meta.completion.current": "fg:#00a6b2 bg:#ffffff bold noreverse",
    "scrollbar.background": "bg:#ffffff",
    "scrollbar.button": "fg:#a8a8a8 bg:#ffffff noreverse",
}


def terminal_input_style(extra: dict[str, str] | None = None) -> Style:
    styles = dict(COMPLETION_MENU_STYLE)
    if extra:
        styles.update(extra)
    return Style.from_dict(styles)
