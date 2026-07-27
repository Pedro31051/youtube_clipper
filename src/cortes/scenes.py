"""Audited scene-detection stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="scenes")
def run_scenes(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
