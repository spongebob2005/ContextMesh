"""Export the FastAPI OpenAPI schema for static website hosting."""
from __future__ import annotations

import json
from pathlib import Path

from hydracontext.service import app


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "site" / "openapi.json"
    output.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {output}")


if __name__ == "__main__":
    main()
