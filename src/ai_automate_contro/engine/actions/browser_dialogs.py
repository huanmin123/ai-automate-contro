from __future__ import annotations

from typing import Any


def dialog(executor: Any, step: dict[str, Any]) -> None:
    dialog_type = step["type"]
    if dialog_type == "accept":
        _handle_dialog_action(executor, step, accept=True)
        return
    if dialog_type == "dismiss":
        _handle_dialog_action(executor, step, accept=False)
        return
    raise ValueError(f"不支持的 dialog type：{dialog_type}")


def _handle_dialog_action(executor: Any, step: dict[str, Any], *, accept: bool) -> None:
    trigger = step.get("trigger")
    if trigger:
        target_page = executor._page(step)
        prompt_text = step.get("prompt_text")

        def handler(dialog_object: Any) -> None:
            executor.state.last_dialog_message = dialog_object.message
            executor.state.logger.log(
                "info",
                "dialog auto-accepted" if accept else "dialog auto-dismissed",
                dialog_type=dialog_object.type,
                dialog_message=dialog_object.message,
            )
            if accept:
                dialog_object.accept(prompt_text)
            else:
                dialog_object.dismiss()

        target_page.once("dialog", handler)
        executor.run([trigger])
        executor.state.pending_dialog = None
        return

    if executor.state.pending_dialog is None:
        raise RuntimeError("当前没有等待处理的浏览器弹窗。")
    if accept:
        prompt_text = step.get("prompt_text")
        executor.state.pending_dialog.accept(prompt_text)
        executor.state.logger.log("info", "dialog accepted", message=executor.state.last_dialog_message)
    else:
        executor.state.pending_dialog.dismiss()
        executor.state.logger.log("info", "dialog dismissed", message=executor.state.last_dialog_message)
    executor.state.pending_dialog = None


ACTION_HANDLERS = {
    "dialog": dialog,
}
