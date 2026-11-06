"""docs/local-test-guide.md -> PDF, styled like the Days 1-6 guide (Chromium via Playwright).

    uv run --no-project --with markdown --with pymdown-extensions --with playwright \
      python scripts/make_guide_pdf.py docs/local-test-guide.md \
      "docs/local test guide (Days 1–8).pdf" /snap/bin/chromium

The last argument is a Chromium executable (Playwright's own works after
`playwright install chromium`).
"""

import re
import sys
from datetime import date
from pathlib import Path

# Not project dependencies: `uv run --with` provides them (see the docstring).
import markdown  # pyright: ignore[reportMissingModuleSource]
from playwright.sync_api import sync_playwright  # pyright: ignore[reportMissingImports]

source, target, chromium = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
text = source.read_text(encoding="utf-8")

# The H1 becomes the title block; the rest is the body.
heading = re.match(r"# (.+)\n", text)
assert heading is not None, "the guide starts with its H1"
title = heading.group(1)
body_md = text[text.index("\n") + 1 :]
# The link to the old PDF only works inside the repository.
body_md = re.sub(r"\[(Days 1–6 PDF)\]\([^)]*\)", r"*\1* (`docs/`)", body_md)


# Python-Markdown nests lists at 4 spaces; the guide uses 2 (bullets) and 3 (numbered items).
def renest(line: str) -> str:
    stripped = line.lstrip(" ")
    depth = len(line) - len(stripped)
    if depth == 0 or not stripped:
        return line
    level = (depth + 1) // 2 if depth % 3 else depth // 3
    return " " * (4 * level) + stripped


lines = [renest(line) for line in body_md.splitlines()]
# A list right after a paragraph line needs a blank line before it.
fixed: list[str] = []
for line in lines:
    starts_list = re.match(r"(- |\d+\. )", line)
    after_text = fixed and fixed[-1].strip() and not re.match(r"\s*(- |\d+\. |\||#|```)", fixed[-1])
    if starts_list and after_text:
        fixed.append("")
    fixed.append(line)
body_md = "\n".join(fixed)
html_body = markdown.markdown(body_md, extensions=["tables", "pymdownx.superfences", "sane_lists"])
# Task-list items: "- [ ] …" -> a checkbox.
html_body = re.sub(
    r"<li>(\s*<p>)?\[ \]\s*", r'<li class="task">\1<span class="box"></span>', html_body
)
html_body = html_body.replace('<ul>\n<li class="task">', '<ul class="tasks">\n<li class="task">')
# Six-column tables get a smaller font.
html_body = re.sub(
    r"<table>(\s*<thead>\s*<tr>(?:\s*<th[^>]*>(?:(?!</th>).)*</th>){6}\s*</tr>)",
    r'<table class="wide">\1',
    html_body,
    flags=re.S,
)

css = """
@page { size: A4; margin: 22mm 18mm 20mm 18mm; }
:root { --ink: #1f1f1d; --muted: #6b6b66; --line: #e3e1da; --head: #f4f3ee; --code: #f1f0eb; }
* { box-sizing: border-box; }
body { font-family: "Inter", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt;
  line-height: 1.5; color: var(--ink); margin: 0; }
h1, h2, h3 { font-family: "Source Serif 4", "Georgia", serif; font-weight: 500; color: var(--ink);
  break-after: avoid; }
h1 { font-size: 24pt; margin: 0 0 8pt; line-height: 1.15; }
h2 { font-size: 16pt; margin: 22pt 0 8pt; }
h3 { font-size: 12.5pt; margin: 16pt 0 6pt; }
.meta { display: inline-block; font-size: 8.5pt; color: var(--muted); border: 1px solid var(--line);
  border-radius: 4px; padding: 1pt 6pt; margin-bottom: 12pt; }
p { margin: 0 0 8pt; }
hr { border: 0; border-top: 1px solid var(--line); margin: 18pt 0; }
code { font-family: "JetBrains Mono", "DejaVu Sans Mono", monospace; font-size: 8.8pt;
  background: var(--code); border-radius: 3px; padding: 0 3px; }
pre { background: var(--code); border-radius: 4px; padding: 7pt 9pt; font-size: 8.5pt;
  white-space: pre-wrap; word-break: break-word; break-inside: avoid; }
pre code { padding: 0; background: none; }
td code { white-space: normal; overflow-wrap: anywhere; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 12pt; font-size: 9pt;
  break-inside: auto; }
th { background: var(--head); color: var(--muted); font-weight: 500; text-align: left; }
th, td { border: 1px solid var(--line); padding: 4pt 6pt; vertical-align: top; }
tr { break-inside: avoid; }
table.wide { font-size: 7.6pt; }
table.wide th, table.wide td { padding: 3pt 4pt; }
table.wide td:first-child { width: 17%; }
ul, ol { margin: 0 0 8pt; padding-left: 18pt; }
li { margin: 2pt 0; }
ul.tasks { list-style: none; padding-left: 2pt; }
li.task { position: relative; padding-left: 16pt; break-inside: avoid; }
li.task > ul { padding-left: 14pt; list-style: disc; }
.box { position: absolute; left: 0; top: 3pt; width: 8.5pt; height: 8.5pt;
  border: 1px solid #9a988f; border-radius: 2px; }
a { color: var(--ink); }
"""

html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>{css}</style></head><body>
<h1>{title}</h1><div class="meta">{date.today():%b %-d, %Y} · followup-agent-24x7</div>
{html_body}</body></html>"""

header = (
    f'<div style="font-size:7pt;color:#8a8a84;width:100%;padding:0 18mm;'
    f'font-family:Arial,sans-serif">{title}</div>'
)
footer = (
    '<div style="font-size:7pt;color:#8a8a84;width:100%;padding:0 18mm;text-align:right;'
    'font-family:Arial,sans-serif">Page <span class="pageNumber"></span> of '
    '<span class="totalPages"></span></div>'
)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=chromium)
    page = browser.new_page()
    page.set_content(html, wait_until="load")
    page.pdf(
        path=str(target),
        format="A4",
        print_background=True,
        display_header_footer=True,
        header_template=header,
        footer_template=footer,
        margin={"top": "22mm", "bottom": "20mm", "left": "18mm", "right": "18mm"},
    )
    browser.close()
print(target)
