"""Writes each product's typed API client from its FastAPI app's OpenAPI schema. CI runs it
and fails when a committed schema.ts is out of date."""

from __future__ import annotations

import json

from _cli import PNPM, ROOT, run


def _apps():
    from cuentas_claras_api.main import app as cuentas_claras
    from inmo24x7_api.main import app as inmo24x7

    return (
        (inmo24x7, "packages/api-client-inmo24x7/src/schema.ts"),
        (cuentas_claras, "packages/api-client-cuentas-claras/src/schema.ts"),
    )


def main() -> None:
    schema_path = ROOT / ".openapi.json"
    apps = _apps()
    try:
        for app, output in apps:
            schema_path.write_text(json.dumps(app.openapi()), encoding="utf-8")
            run([*PNPM, "exec", "openapi-typescript", str(schema_path), "-o", output])
    finally:
        schema_path.unlink(missing_ok=True)

    print(f"Generated {len(apps)} client schemas from {ROOT}", flush=True)


if __name__ == "__main__":
    main()
