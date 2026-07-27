"""Audited media-cut stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="cut")
def run_cut(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
