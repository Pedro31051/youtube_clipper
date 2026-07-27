"""Audited ingest stage boundary."""

from typing import Any, Callable

from cortes.log import audited


@audited(stage="ingest")
def run_ingest(action: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    return action(*args, **kwargs)
