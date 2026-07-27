"""Audited audio stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="audio")
def run_audio(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
