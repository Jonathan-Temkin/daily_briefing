"""
Renders a local HTML report file to a polished PDF using headless Chromium
(via Playwright). Unlike the old email-safe HTML, this report can use real
CSS (flexbox/grid, @media print, box-shadow, etc.) since it's rendered by an
actual browser engine, not an email client.

Usage:
  python render_pdf.py <input.html> <output.pdf>
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def render(input_html: Path, output_pdf: Path):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(input_html.resolve().as_uri())
        page.wait_for_timeout(200)
        page.pdf(
            path=str(output_pdf),
            format="Letter",
            print_background=True,
            margin={"top": "0.55in", "bottom": "0.55in", "left": "0.4in", "right": "0.4in"},
        )
        browser.close()


def main():
    if len(sys.argv) != 3:
        print("Usage: python render_pdf.py <input.html> <output.pdf>", file=sys.stderr)
        return 1
    input_html = Path(sys.argv[1])
    output_pdf = Path(sys.argv[2])
    if not input_html.exists():
        print(f"ERROR: {input_html} does not exist", file=sys.stderr)
        return 1
    render(input_html, output_pdf)
    print(f"Wrote {output_pdf} ({output_pdf.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
