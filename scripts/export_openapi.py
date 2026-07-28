"""Export the FastAPI schema used to generate the TypeScript client."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from youtube_clipper.api import create_app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="youtube-clipper-openapi-") as workspace:
        application = create_app(workspace_dir=workspace)
        schema = application.openapi()
        application.state.analysis_worker.shutdown()
        application.state.preview_worker.shutdown()
    output.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
