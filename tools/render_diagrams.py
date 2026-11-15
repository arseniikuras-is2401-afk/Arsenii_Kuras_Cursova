"""Render .mmd files to PNG via local headless Chrome + Mermaid from CDN.

Usage: python render_mermaid.py <diagrams_dir> <work_dir> [name ...]
Pass 1: --dump-dom to get the rendered SVG size (and detect syntax errors).
Pass 2: --screenshot with the exact window size, 2x scale.
"""
import html
import json
import re
import subprocess
import sys
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;background:#fff}}
#out{{display:inline-block;padding:16px}}</style>
<script src="{mermaid}"></script></head><body><div id="out"></div>
<script>
mermaid.initialize({{startOnLoad:false, theme:'default',
  fontFamily:'Segoe UI, Arial, sans-serif', securityLevel:'loose',
  er:{{useMaxWidth:false}}, class:{{useMaxWidth:false}},
  sequence:{{useMaxWidth:false}}, flowchart:{{useMaxWidth:false}},
  state:{{useMaxWidth:false}}}});
const src = {source};
mermaid.render('d', src).then(r => {{
  document.getElementById('out').innerHTML = r.svg;
  const b = document.getElementById('out').getBoundingClientRect();
  const size = Math.ceil(b.width) + 'x' + Math.ceil(b.height);
  document.body.setAttribute('data-size', size);
}}).catch(e => {{
  document.body.setAttribute('data-error', String(e.message || e));
}});
</script></body></html>"""


def chrome(args, work):
    base = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
            f"--user-data-dir={work / 'chrome-profile'}",
            "--virtual-time-budget=20000"]
    return subprocess.run(base + args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)


def main():
    diagrams = Path(sys.argv[1]).resolve()
    work = Path(sys.argv[2]).resolve()
    work.mkdir(parents=True, exist_ok=True)
    names = sys.argv[3:]
    files = [diagrams / f"{n}.mmd" for n in names] if names else sorted(
        diagrams.glob("*.mmd"))
    for mmd in files:
        page = work / f"{mmd.stem}.html"
        page.write_text(PAGE.format(mermaid=MERMAID, source=json.dumps(
            mmd.read_text(encoding="utf-8"))), encoding="utf-8")
        dom = chrome(["--dump-dom", page.as_uri()], work).stdout
        err = re.search(r'data-error="([^"]*)"', dom)
        if err:
            print(f"ERROR {mmd.name}: {html.unescape(err.group(1))}")
            continue
        size = re.search(r'data-size="(\d+)x(\d+)"', dom)
        if not size:
            print(f"ERROR {mmd.name}: no render result")
            continue
        w, h = int(size.group(1)), int(size.group(2))
        png = mmd.with_suffix(".png")
        chrome([f"--screenshot={png}", f"--window-size={w},{h}",
                "--force-device-scale-factor=2", page.as_uri()], work)
        print(f"OK {mmd.name} -> {png.name} ({w}x{h})")


if __name__ == "__main__":
    main()
