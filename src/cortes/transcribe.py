"""Audited transcription stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="transcribe")
def run_transcribe(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
