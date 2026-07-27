"""Audited subtitle stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="subtitles")
def run_subtitles(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
