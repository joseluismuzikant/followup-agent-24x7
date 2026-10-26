from __future__ import annotations

import json

from _cli import PNPM, ROOT, run
from inmo24x7_api.main import app

OUTPUTS = (
    "apps/inmo24x7/web/src/api/schema.ts",
    "apps/inmo24x7/backoffice/src/api/schema.ts",
)


def main() -> None:
    schema_path = ROOT / ".openapi.json"

    try:
        schema_path.write_text(json.dumps(app.openapi()), encoding="utf-8")

        for output in OUTPUTS:
            run(
                [
                    *PNPM,
                    "exec",
                    "openapi-typescript",
                    str(schema_path),
                    "-o",
                    output,
                ]
            )
    finally:
        schema_path.unlink(missing_ok=True)

    print(f"Generated {len(OUTPUTS)} client schemas from {ROOT}", flush=True)


if __name__ == "__main__":
    main()
