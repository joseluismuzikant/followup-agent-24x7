"""A fake Tokko Broker and a webhook receiver, for trying the integrations locally (no real
Tokko account, no Zapier). Standard library only.

    uv run python scripts/fake_integrations.py            # Tokko on :8090, receiver on :8091
    uv run python scripts/fake_integrations.py --secret whsec_...   # also checks signatures

Start the API with TOKKO_API_URL=http://localhost:8090/api/v1 (in .env), then in the panel:
- Configuración → Integraciones → Tokko: key `fake-tokko-key` → "Probar conexión";
- Webhook: http://localhost:8091/hook (http is accepted only while the panel runs on
  localhost) → "Enviar prueba".

The fake Tokko answers with the shapes integrations/tokko.py expects (the real ones are
"to verify with a real key", docs/integrations.md). Edit LISTINGS below and press
"Sincronizar ahora" to see updates and pauses. Received web contacts and webhook bodies are
printed.
"""

import argparse
import contextlib
import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

KEY = "fake-tokko-key"
LISTINGS: list[dict[str, Any]] = [
    {
        "id": 501001,
        "reference_code": "TKO501001",
        "publication_title": "2 ambientes luminoso con balcón",
        "address": "Gorriti 4800",
        "fake_address": "",
        "location": {"name": "Palermo", "full_location": "Argentina | Capital Federal | Palermo"},
        "room_amount": 2,
        "suite_amount": 1,
        "public_url": "https://www.inmobiliariasur.test/propiedad/501001-gorriti-4800",
        "operations": [
            {"operation_type": "Alquiler", "prices": [{"currency": "ARS", "price": 880000}]}
        ],
    },
    {
        "id": 501002,
        "reference_code": "TKO501002",
        "publication_title": "3 ambientes con cochera",
        "address": "Cabildo 2100",
        "fake_address": "",
        "location": {"name": "Belgrano"},
        "room_amount": 3,
        "suite_amount": 2,
        "public_url": "https://www.inmobiliariasur.test/propiedad/501002-cabildo-2100",
        "operations": [
            {"operation_type": "Venta", "prices": [{"currency": "USD", "price": 189000}]},
            {"operation_type": "Alquiler", "prices": [{"currency": "ARS", "price": 1250000}]},
        ],
    },
    {
        "id": 501003,
        "reference_code": "TKO501003",
        "publication_title": "Casa en Tigre (precio a consultar)",
        "address": "Av. Cazón 900",
        "location": {"name": "Tigre"},
        "room_amount": 4,
        "public_url": "https://www.inmobiliariasur.test/propiedad/501003-tigre",
        "operations": [{"operation_type": "Venta", "prices": []}],
    },
]


def _json(handler: BaseHTTPRequestHandler, status: int, body: Any) -> None:
    data = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class Tokko(BaseHTTPRequestHandler):
    def _key_ok(self) -> bool:
        params = parse_qs(urlsplit(self.path).query)
        if params.get("key", [""])[0] != KEY:
            _json(self, 401, {"error": "Unauthorized"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if parts.path != "/api/v1/property/" or not self._key_ok():
            if parts.path != "/api/v1/property/":
                _json(self, 404, {})
            return
        params = parse_qs(parts.query)
        limit = int(params.get("limit", ["20"])[0])
        offset = int(params.get("offset", ["0"])[0])
        objects = LISTINGS[offset : offset + limit]
        more = offset + limit < len(LISTINGS)
        _json(
            self,
            200,
            {
                "meta": {
                    "limit": limit,
                    "offset": offset,
                    "total_count": len(LISTINGS),
                    "next": f"/api/v1/property/?offset={offset + limit}" if more else None,
                },
                "objects": objects,
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if urlsplit(self.path).path != "/api/v1/webcontact/":
            _json(self, 404, {})
            return
        if not self._key_ok():
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        print("\n[tokko] web contact:", json.dumps(body, ensure_ascii=False, indent=2))
        _json(self, 201, {"id": 900001})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        print("[tokko]", format % args)


def receiver(secret: str | None) -> type[BaseHTTPRequestHandler]:
    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            signature = self.headers.get("X-Inmo24x7-Signature", "")
            verdict = "not checked (no --secret)"
            if secret:
                expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
                verdict = "OK" if hmac.compare_digest(expected, signature) else "WRONG"
            print(
                f"\n[webhook] {self.headers.get('X-Inmo24x7-Event')} "
                f"delivery={self.headers.get('X-Inmo24x7-Delivery')} signature {verdict}"
            )
            print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
            _json(self, 200 if verdict != "WRONG" else 401, {"ok": verdict != "WRONG"})

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            pass

    return Receiver


def main() -> None:
    parser = argparse.ArgumentParser(description="A fake Tokko Broker and a webhook receiver.")
    parser.add_argument("--tokko-port", type=int, default=8090)
    parser.add_argument("--webhook-port", type=int, default=8091)
    parser.add_argument("--secret", help="the webhook secret shown in the panel, to check it")
    args = parser.parse_args()
    servers = [
        ThreadingHTTPServer(("127.0.0.1", args.tokko_port), Tokko),
        ThreadingHTTPServer(("127.0.0.1", args.webhook_port), receiver(args.secret)),
    ]
    print(f"Fake Tokko: http://localhost:{args.tokko_port}/api/v1 (key: {KEY})")
    print(f"Webhook receiver: http://localhost:{args.webhook_port}/hook")
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    with contextlib.suppress(KeyboardInterrupt):
        servers[0].serve_forever()


if __name__ == "__main__":
    main()
