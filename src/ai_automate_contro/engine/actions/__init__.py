from ai_automate_contro.engine.actions.executor import ActionExecutor

SUPPORTED_ACTIONS = {
    name.removeprefix("_action_")
    for name in dir(ActionExecutor)
    if name.startswith("_action_")
} | set(ActionExecutor.external_action_handlers())

__all__ = ["ActionExecutor", "SUPPORTED_ACTIONS"]
