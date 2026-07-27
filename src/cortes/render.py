"""Audited render stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="render")
def run_render(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
