from __future__ import annotations

from ai_automate_contro.engine.actions.browser_assertions import action_assert
from ai_automate_contro.engine.actions.common import action_manual_confirm, action_print, action_sleep
from ai_automate_contro.engine.actions.file_io import action_read, action_write
from ai_automate_contro.engine.actions.table import action_table
from ai_automate_contro.engine.actions.variables import action_variable


ACTION_HANDLERS = {
    "assert": action_assert,
    "manual_confirm": action_manual_confirm,
    "print": action_print,
    "read": action_read,
    "sleep": action_sleep,
    "table": action_table,
    "variable": action_variable,
    "write": action_write,
}

__all__ = [
    "ACTION_HANDLERS",
    "action_assert",
    "action_manual_confirm",
    "action_print",
    "action_read",
    "action_sleep",
    "action_table",
    "action_variable",
    "action_write",
]
