"""Render one explainer section (or the whole site) in headless Chromium and slice it into PNG tiles.

usage: <python-with-PIL> preview_section.py <site_dir> <section_id | ALL> [--dark] [--wait-ms N] [--out DIR]
Writes <out>/<id>_<desktop|phone>[_dark]_NN.png (desktop tiles 1400 px tall, phone 1800 px) and prints, per width,
the page height, scrollWidth (horizontal overflow is flagged) and any JS errors.
Default <out>: <site_dir>/../.preview_<site name>/ unless --out is given (use the session scratch dir).
"""

import glob
import html
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image

CHROME_GLOBS = [
    os.path.expanduser("~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"),
    os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome"),
]
HEADLESS_LIBS = "/data/yihuai/miniforge3/envs/headless-libs/lib"  # libnspr4 / libnss3 for the playwright build
PROBE = """<script>
window.__errs=[];window.addEventListener('error',e=>window.__errs.push(String(e.message)+' @'+(e.lineno||'')));
window.addEventListener('load',()=>setTimeout(()=>{const d=document.createElement('pre');d.id='__probe';
d.textContent='H='+document.documentElement.scrollHeight+' W='+document.documentElement.scrollWidth+' ERRS='+JSON.stringify(window.__errs);
document.body.appendChild(d);},WAIT));</script>"""


def find_chrome() -> str:
    for pattern in CHROME_GLOBS:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    raise SystemExit("No headless Chromium found under ~/.cache/ms-playwright (install: npx playwright install chromium-headless-shell).")


def build_page(site: str, section_id: str, dark: bool, wait_ms: int) -> str:
    if section_id == "ALL":
        page = open(os.path.join(site, "index.html")).read()
    else:
        shell = open(os.path.join(site, "shell.html")).read()
        frag = open(os.path.join(site, "sections", f"{section_id}.html")).read()
        page = (
            shell.replace("<!--TITLE-->", "preview")
            .replace("<!--BRAND-->", "preview")
            .replace("<!--NAV-->", f'  <a href="#{section_id}">{section_id}</a>')
            .replace("<!--FOOTER-->", "")
            .replace("<!--SECTIONS-->", frag)
        )
    if dark:
        page = re.sub(r"<html([^>]*)>", r'<html\1 data-theme="dark">', page, count=1)
    return page.replace("<head>", "<head>" + PROBE.replace("WAIT", str(wait_ms)), 1)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    site, section_id = os.path.abspath(args[0]), args[1]
    dark = "--dark" in args
    wait_ms = int(args[args.index("--wait-ms") + 1]) if "--wait-ms" in args else 1500
    out_dir = args[args.index("--out") + 1] if "--out" in args else os.path.join(os.path.dirname(site), f".preview_{os.path.basename(site)}")
    os.makedirs(out_dir, exist_ok=True)
    chrome = find_chrome()
    env = dict(os.environ)
    if os.path.isdir(HEADLESS_LIBS):
        env["LD_LIBRARY_PATH"] = HEADLESS_LIBS + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")

    def run(extra: list[str]) -> str:
        cmd = [chrome, "--no-sandbox", "--hide-scrollbars", "--disable-gpu", *extra]
        return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180).stdout

    with tempfile.NamedTemporaryFile("w", suffix=".html", dir=out_dir, delete=False) as f:
        f.write(build_page(site, section_id, dark, wait_ms))
        page_path = f.name
    budget = str(wait_ms + 1500)
    suffix = "_dark" if dark else ""
    try:
        for label, width in (("desktop", 1280), ("phone", 390)):
            dom = run(["--virtual-time-budget=" + budget, f"--window-size={width},900", "--dump-dom", "file://" + page_path])
            m = re.search(r'<pre id="__probe">(.*?)</pre>', dom, re.S)
            probe = html.unescape(m.group(1)) if m else "H=6000 W=0 ERRS=[probe missing: page did not finish loading]"
            height = min(int(re.search(r"H=(\d+)", probe).group(1)) + 20, 40000)
            scroll_w = int(re.search(r"W=(\d+)", probe).group(1))
            flag = f"  !! horizontal overflow: scrollWidth {scroll_w} > {width}" if scroll_w > width else ""
            print(f"[{label}{suffix}] {probe}{flag}")
            full = os.path.join(out_dir, f"_{section_id}_{label}.png")
            run(["--virtual-time-budget=" + budget, f"--window-size={width},{height}", "--screenshot=" + full, "file://" + page_path])
            img = Image.open(full)
            tile_h = 1400 if label == "desktop" else 1800
            for old in glob.glob(os.path.join(out_dir, f"{section_id}_{label}{suffix}_*.png")):
                os.remove(old)
            for n, top in enumerate(range(0, img.height, tile_h)):
                tile_path = os.path.join(out_dir, f"{section_id}_{label}{suffix}_{n:02d}.png")
                img.crop((0, top, img.width, min(top + tile_h, img.height))).save(tile_path)
                print("   ", tile_path)
            os.remove(full)
    finally:
        os.remove(page_path)


if __name__ == "__main__":
    main()
