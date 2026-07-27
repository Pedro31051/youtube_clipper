"""Audited clip-selection stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="select")
def run_select(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
