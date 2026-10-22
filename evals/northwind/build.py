"""Builds the Northwind Air PDFs from the Markdown policies.

Run:  python build.py
Steps: draw the two figures, turn each Markdown file into HTML, print the HTML to PDF with a
headless browser (Edge or Chrome). Output goes to build/pdf/. Set BROWSER to use another browser.
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import date

import markdown
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from corpus import HERE, POLICIES, load_doc  # noqa: E402

BUILD = HERE / "build"
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/usr/bin/chromium",
    "/usr/bin/google-chrome",
]

CSS = """
@page { size: Letter; margin: 22mm 20mm; @bottom-center { content: counter(page); font: 9pt sans-serif; color: #555; } }
body { font: 11pt/1.5 'Segoe UI', Arial, sans-serif; color: #111; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 13pt; margin: 18pt 0 6pt; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; }
p { margin: 0 0 7pt; }
.meta { color: #555; font-size: 9.5pt; border-bottom: 1px solid #bbb; padding-bottom: 8pt; margin-bottom: 8pt; }
table { border-collapse: collapse; margin: 6pt 0 10pt; }
th, td { border: 1px solid #999; padding: 3pt 10pt; text-align: left; }
th { background: #eee; }
img { max-width: 70%; display: block; margin: 8pt 0 2pt; }
"""


def draw_figures() -> None:
    out = HERE / "figures"  # committed: the app shows these images next to the Markdown policies
    out.mkdir(parents=True, exist_ok=True)
    specs = json.loads((HERE / "figures.json").read_text(encoding="utf-8"))

    bars = specs["crew_duty_hours"]
    fig, ax = plt.subplots(figsize=(7, 3.2), dpi=150)
    labels, values = list(bars["data"]), list(bars["data"].values())
    ax.barh(labels, values, color="#3b6ea5")
    for y, v in enumerate(values):
        ax.text(v + 0.2, y, f"{v} hours", va="center", fontsize=10)
    ax.set_xlim(0, max(values) + 3)
    ax.set_xlabel("Hours")
    ax.set_title(bars["title"])
    ax.invert_yaxis()
    fig.tight_layout()
    fig.savefig(out / "crew_duty_hours.png")
    plt.close(fig)

    d = specs["cabin_bag_dimensions"]["data"]
    fig, ax = plt.subplots(figsize=(5.5, 4), dpi=150)
    w, h, dep = d["Length"] / 10, d["Width"] / 10, d["Depth"] / 10  # scale cm to drawing units
    dx, dy = dep * 0.6, dep * 0.4  # oblique offset that shows depth
    front = plt.Rectangle((0, 0), w, h, fill=False, lw=2, color="#222")
    ax.add_patch(front)
    ax.plot([w, w + dx, w + dx, w], [0, dy, h + dy, h], color="#222", lw=2)
    ax.plot([0, dx, w + dx], [h, h + dy, h + dy], color="#222", lw=2)
    ax.text(w / 2, -0.6, f"{d['Length']} cm", ha="center", fontsize=12)
    ax.text(-0.3, h / 2, f"{d['Width']} cm", ha="right", va="center", fontsize=12)
    ax.text(w + dx + 0.2, h + dy / 2, f"{d['Depth']} cm", ha="left", va="center", fontsize=12)
    ax.set_xlim(-3, w + dx + 3)
    ax.set_ylim(-1.5, h + dy + 1)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(specs["cabin_bag_dimensions"]["title"])
    fig.tight_layout()
    fig.savefig(out / "cabin_bag_dimensions.png")
    plt.close(fig)


def to_html(md_path) -> tuple[str, str]:
    doc = load_doc(md_path)
    body = md_path.read_text(encoding="utf-8").split("---", 2)[2]
    html = markdown.markdown(body, extensions=["tables"])
    html = html.replace('src="figures/', f'src="{(HERE / "figures").as_uri()}/')  # figures live next to the policies
    m = doc.meta
    eff = m["effective"] if isinstance(m["effective"], date) else date.fromisoformat(str(m["effective"]))
    meta = (
        f'<p class="meta">Document {m["doc_id"]} &middot; Version {m["version"]} &middot; '
        f'Effective {eff.strftime("%d %B %Y").lstrip("0")} &middot; Owner: {m["owner"]} &middot; '
        f'Northwind Air</p>'
    )
    html = re.sub(r"(</h1>)", r"\1" + meta, html, count=1)
    page = (
        f'<!doctype html><html><head><meta charset="utf-8"><title>{m["title"]}</title>'
        f"<style>{CSS}</style></head><body>{html}</body></html>"
    )
    return m["doc_id"], page


def find_browser() -> str:
    for path in [os.environ.get("BROWSER", ""), *BROWSERS]:
        if path and os.path.exists(path):
            return path
    sys.exit("No Edge or Chrome found. Set the BROWSER environment variable to its path.")


def main() -> None:
    draw_figures()
    pdf_dir = BUILD / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    browser = find_browser()
    total_pages = 0
    for md_path in sorted(POLICIES.glob("*.md")):
        doc_id, page = to_html(md_path)
        html_path = BUILD / f"{doc_id}.html"
        html_path.write_text(page, encoding="utf-8")
        pdf_path = pdf_dir / f"{doc_id}.pdf"
        run = subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--user-data-dir={BUILD / 'browser-profile'}",  # own profile, so a running browser is not reused
                f"--print-to-pdf={pdf_path}",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        for _ in range(40):  # the browser can exit before the file is fully written
            if pdf_path.exists() and pdf_path.stat().st_size > 0:
                break
            time.sleep(0.5)
        else:
            sys.exit(f"{browser} did not write {pdf_path}: {run.stderr.decode(errors='replace')[:300]}")
        pages = len(re.findall(rb"/Type\s*/Page\b", pdf_path.read_bytes()))
        total_pages += pages
        print(f"{doc_id}: {pages} pages")
    print(f"Total: {total_pages} pages in {pdf_dir}")


if __name__ == "__main__":
    main()
