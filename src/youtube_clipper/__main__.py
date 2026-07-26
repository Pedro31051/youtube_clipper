"""Module entrypoint for python -m youtube_clipper execution."""

from __future__ import annotations

import sys
from typing import List, Optional

from youtube_clipper.cli import main as cli_main


def main(argv: Optional[List[str]] = None) -> int:
    """Entrypoint function for python -m youtube_clipper.

    Args:
        argv: Optional list of argument strings. Defaults to sys.argv[1:].

    Returns:
        Integer exit code.
    """
    if argv is None:
        argv = sys.argv[1:]
    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
