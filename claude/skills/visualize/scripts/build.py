"""Assemble index.html from site.json + shell.html + sections/<id>.html, and build the nav.

Run from (or point at) the site directory:  python3 build.py [site_dir]
site.json: {"title": str, "brand": str, "footer_html": str, "sections": ["todo", "overview", "<id>", ...]}
Sections are numbered by position (the first, the todo / pending-decisions section, is 1); h2 badges must match.
Each section is <section class="sec" id="<id>" data-nav="<short nav label>"> ... </section>.
A missing section file renders a "still being built" placeholder, so the site can be served early.
"""

import html
import json
import os
import re
import sys

SITE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))


def load_section(section_id: str) -> str:
    path = os.path.join(SITE, "sections", f"{section_id}.html")
    if os.path.exists(path):
        return open(path).read()
    return (
        f'<section class="sec" id="{section_id}" data-nav="{section_id}"><h2>{section_id}</h2>'
        '<p class="muted">Still being built.</p></section>'
    )


def nav_label(section_html: str, section_id: str, index: int) -> str:
    m = re.search(r'data-nav="([^"]+)"', section_html)
    label = m.group(1) if m else section_id.replace("-", " ").capitalize()
    return f"{index} · {label}"  # every section is numbered by position; the h2 badges use the same numbers


def main() -> None:
    config = json.load(open(os.path.join(SITE, "site.json")))
    shell = open(os.path.join(SITE, "shell.html")).read()
    sections = [(sid, load_section(sid)) for sid in config["sections"]]
    nav = []
    for n, (sid, body) in enumerate(sections, start=1):
        nav.append(f'  <a href="#{sid}">{html.escape(nav_label(body, sid, n))}</a>')
    page = (
        shell.replace("<!--TITLE-->", html.escape(config["title"]))
        .replace("<!--BRAND-->", html.escape(config.get("brand", config["title"])))
        .replace("<!--NAV-->", "\n".join(nav))
        .replace("<!--FOOTER-->", config.get("footer_html", ""))
        .replace("<!--SECTIONS-->", "\n".join(body for _, body in sections))
    )
    open(os.path.join(SITE, "index.html"), "w").write(page)
    ids = re.findall(r'\bid="([^"]+)"', page)
    dups = sorted({i for i in ids if ids.count(i) > 1})
    print(f"index.html {len(page) / 1024:.0f} KiB, {len(sections)} sections" + (f"  !! duplicate ids: {dups}" if dups else ""))


if __name__ == "__main__":
    main()
