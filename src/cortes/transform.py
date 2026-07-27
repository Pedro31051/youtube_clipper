"""Audited transform stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="transform")
def run_transform(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
