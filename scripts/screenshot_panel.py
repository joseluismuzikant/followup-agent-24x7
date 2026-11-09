"""Screenshots of the inmo24x7 panel (and the backoffice) at phone, tablet and desktop widths,
plus a horizontal-overflow report. For checking the responsive layout by eye; needs the dev
stack with the seed (`scripts/dev.py --seed`).

    uv run --no-project --with playwright python scripts/screenshot_panel.py \
      scratch/responsive/after /snap/bin/chromium
    uv run --no-project --with playwright python scripts/screenshot_panel.py \
      --check /snap/bin/chromium

The last argument is a Chromium executable (Playwright's own works after
`playwright install chromium`). Writes <out>/<width>x<height>/<page>.png (plus the
conversation at screen height, where the reply box is pinned) and prints one line per page
whose document is wider than the viewport. `--check` takes no screenshots: every page at
390 px, exit status 1 when any of them scrolls sideways.
"""

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]

PANEL = "http://localhost:5173"
BACKOFFICE = "http://localhost:5174"
API = "http://localhost:8001"
OWNER = "dueno@inmobiliariasur.test"
ONBOARDING_OWNER = "dueno@belgranohogar.test"
ADMIN = "admin@local.test"
SIZES = [(390, 844), (360, 740), (768, 1024), (1280, 800)]


def first_lead_with_visit() -> str:
    request = urllib.request.Request(
        f"{API}/leads?tab=all&include_test=true",
        headers={"Authorization": f"Bearer dev:{OWNER}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        items = json.load(response)["items"]
    return next((i["id"] for i in items if i["status"] == "visit_proposed"), items[0]["id"])


def pages() -> list[tuple[str, str, str | None]]:
    """(name, url, signed-in email or None)."""
    lead = first_lead_with_visit()
    return [
        ("ingreso", f"{PANEL}/ingreso", None),
        ("inicio", f"{PANEL}/", OWNER),
        ("consultas", f"{PANEL}/consultas?tab=all", OWNER),
        ("consultas-lead", f"{PANEL}/consultas?tab=all&lead={lead}", OWNER),
        ("propiedades", f"{PANEL}/propiedades", OWNER),
        ("probar", f"{PANEL}/probar", OWNER),
        ("agente", f"{PANEL}/agente", OWNER),
        ("configuracion", f"{PANEL}/configuracion", OWNER),
        ("onboarding", f"{PANEL}/onboarding", ONBOARDING_OWNER),
        ("backoffice", f"{BACKOFFICE}/", ADMIN),
    ]


def main() -> None:
    check = sys.argv[1] == "--check"
    out, chromium = Path(sys.argv[1]), sys.argv[2]
    sizes = [(390, 844)] if check else SIZES
    overflow: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium)
        for width, height in sizes:
            phone = width < 768
            folder = out / f"{width}x{height}"
            if not check:
                folder.mkdir(parents=True, exist_ok=True)
            for name, url, email in pages():
                context = browser.new_context(
                    viewport={"width": width, "height": height},
                    is_mobile=phone,
                    has_touch=phone,
                    locale="es-AR",
                )
                if email:
                    context.add_init_script(
                        "window.localStorage.setItem('followup.devSession', "
                        f"{json.dumps('dev:' + email)});"
                    )
                page = context.new_page()
                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(600)
                scroll, client = page.evaluate(
                    "[document.documentElement.scrollWidth, document.documentElement.clientWidth]"
                )
                if scroll > client:
                    overflow.append(f"{width}px {name}: scrollWidth {scroll} > {client}")
                if not check:
                    page.screenshot(path=str(folder / f"{name}.png"), full_page=True)
                    if name == "consultas-lead":
                        page.screenshot(path=str(folder / f"{name}-screen.png"))
                    if name == "inicio" and phone:
                        menu = page.get_by_role("button", name="Abrir el menú")
                        menu.click()
                        page.screenshot(path=str(folder / "menu.png"))
                context.close()
        browser.close()
    print("\n".join(overflow) if overflow else "no horizontal overflow")
    if check and overflow:
        sys.exit(1)


if __name__ == "__main__":
    main()
