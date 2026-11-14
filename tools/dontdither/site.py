"""Build the project's GitHub Pages site: a landing page and the articles,
as HTML, with each article also printed to PDF when Chrome is available.

    uv run --with "markdown>=3.5" dd-build-site    # -> build/site/

(markdown is not a project dependency, so the lock file is untouched.)

Sources:
- docs/site/index.md: the landing page;
- docs/articles/*.md: the articles;
- docs/images/: the images they use (only those are copied).

Pages link to each other and to images with relative paths to the .md
sources, as they would on GitHub; the build rewrites them for the site:
an article's .md becomes .html, and images are gathered into images/.
An image paragraph followed by an italic paragraph becomes a figure with
that caption, kept together when printed.

The PDFs are printed by headless Chrome (CHROME_FILEPATH, or found on the
PATH or in /Applications). Without it the site is built without them.
.github/workflows/pages.yml builds and deploys the site.
"""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
from pathlib import Path

from dontdither.inks import PROJECT_DIRPATH

DOCS_DIRPATH = PROJECT_DIRPATH / "docs"
INDEX_FILEPATH = DOCS_DIRPATH / "site" / "index.md"
ARTICLES_DIRPATH = DOCS_DIRPATH / "articles"
IMAGES_DIRPATH = DOCS_DIRPATH / "images"
SITE_DIRPATH = PROJECT_DIRPATH / "build" / "site"
SITE_TITLE = "Don't Dither!"
REPOSITORY_URL = "https://github.com/rob-smallshire/dont-dither"

CHROME_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)

CSS = """
:root { color-scheme: light; }
body { margin: 0; background: #fff; color: #111;
       font-family: Georgia, 'Times New Roman', serif; font-size: 18px; line-height: 1.55; }
header.site { background: #000; color: #fff; padding: 10px 16px; font-family: Helvetica, Arial, sans-serif; }
header.site a { color: #0ff; text-decoration: none; font-weight: bold; }
header.site span.inks { margin-left: 10px; letter-spacing: 2px; }
main { max-width: 46em; margin: 0 auto; padding: 8px 16px 48px; }
h1, h2, h3 { font-family: Helvetica, Arial, sans-serif; line-height: 1.2; }
h1 { font-size: 2em; margin: 0.8em 0 0.4em; }
h2 { font-size: 1.35em; margin: 1.6em 0 0.4em; }
h3 { font-size: 1.1em; margin: 1.2em 0 0.3em; }
a { color: #1a4d8f; }
figure { margin: 1.2em 0; text-align: center; }
figure img { max-width: 100%; height: auto; image-rendering: pixelated; }
figcaption { font-size: 0.85em; font-style: italic; color: #444; margin-top: 0.4em; text-align: left; }
table { border-collapse: collapse; margin: 1em auto; font-size: 0.9em; display: block; overflow-x: auto; }
th, td { border: 1px solid #bbb; padding: 4px 9px; }
th { background: #eee; }
blockquote { margin: 1em 1.5em; padding-left: 1em; border-left: 3px solid #999; font-style: italic; }
code { font-family: Menlo, Consolas, monospace; font-size: 0.85em; background: #f2f2f2; padding: 0 3px; }
p.download { font-family: Helvetica, Arial, sans-serif; font-size: 0.85em; }
footer { max-width: 46em; margin: 0 auto; padding: 16px; font-size: 0.8em; color: #666;
         font-family: Helvetica, Arial, sans-serif; border-top: 1px solid #ddd; }
@media print {
  @page { size: A4; margin: 18mm 18mm 20mm 18mm; }
  body { font-size: 10.5pt; line-height: 1.45; }
  header.site, footer, p.download { display: none; }
  main { max-width: none; padding: 0; }
  h1 { font-size: 22pt; margin-top: 0; }
  h2 { font-size: 14pt; break-after: avoid; }
  h3 { font-size: 11.5pt; break-after: avoid; }
  p, li { orphans: 3; widows: 3; }
  figure { break-inside: avoid; margin: 10pt 0 12pt; }
  figure img { max-height: 85mm; width: auto; }
  figcaption { font-size: 9pt; }
  table { display: table; break-inside: avoid; font-size: 9.5pt; }
}
"""


def render_markdown(text: str, source_filepath: Path, output_filepath: Path, images: set[Path]) -> tuple[str, str]:
    """(title, body HTML) for a Markdown page, its links rewritten for the
    site and the images it uses added to `images`."""
    import markdown

    body = markdown.markdown(text, extensions=["tables"])
    output_dirpath = output_filepath.parent

    def image(match: re.Match) -> str:
        image_filepath = (source_filepath.parent / html.unescape(match.group(1))).resolve()
        images.add(image_filepath)
        target = SITE_DIRPATH / "images" / image_filepath.name
        return f'src="{os.path.relpath(target, output_dirpath)}"'

    def link(match: re.Match) -> str:
        href = html.unescape(match.group(1))
        if re.match(r"[a-z]+:", href) or not href.endswith(".md"):
            return match.group(0)
        page = site_filepath((source_filepath.parent / href).resolve())
        return f'href="{os.path.relpath(page, output_dirpath)}"'

    body = re.sub(r'src="([^"]+)"', image, body)
    body = re.sub(r'href="([^"]+)"', link, body)
    body = re.sub(r'<p>(<img [^>]+>)</p>\s*<p><em>(.*?)</em></p>',
                  r'<figure>\1<figcaption>\2</figcaption></figure>', body, flags=re.S)
    body = re.sub(r'<p>(<img [^>]+>)</p>', r'<figure>\1</figure>', body)
    heading = re.search(r"<h1>(.*?)</h1>", body, flags=re.S)
    title = re.sub(r"<[^>]+>", "", heading.group(1)) if heading else SITE_TITLE
    return html.unescape(title), body


def site_filepath(source_filepath: Path) -> Path:
    """Where a Markdown source's page goes in the site."""
    if source_filepath == INDEX_FILEPATH:
        return SITE_DIRPATH / "index.html"
    return SITE_DIRPATH / "articles" / (source_filepath.stem + ".html")


def page(title: str, body: str, output_filepath: Path) -> str:
    home = os.path.relpath(SITE_DIRPATH / "index.html", output_filepath.parent)
    full_title = title if title == SITE_TITLE else f"{title} - {SITE_TITLE}"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(full_title)}</title>
<style>{CSS}</style>
</head>
<body>
<header class="site"><a href="{home}">{html.escape(SITE_TITLE)}</a><span class="inks"><span style="color:#0ff">&#9632;</span><span style="color:#f0f">&#9632;</span><span style="color:#ff0">&#9632;</span><span style="color:#888">&#9632;</span></span></header>
<main>
{body}
</main>
<footer>A BBC Micro game. Source on <a href="{REPOSITORY_URL}">GitHub</a>.</footer>
</body>
</html>
"""


def find_chrome() -> str | None:
    if os.environ.get("CHROME_FILEPATH"):
        return os.environ["CHROME_FILEPATH"]
    for candidate in CHROME_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if found:
            return found
    return None


def print_pdf(chrome: str, html_filepath: Path, pdf_filepath: Path) -> None:
    subprocess.run(
        [chrome, "--headless", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_filepath}", html_filepath.as_uri()],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def build() -> Path:
    if SITE_DIRPATH.exists():
        shutil.rmtree(SITE_DIRPATH)
    (SITE_DIRPATH / "articles").mkdir(parents=True)
    chrome = find_chrome()
    images: set[Path] = set()

    article_filepaths = sorted(ARTICLES_DIRPATH.glob("*.md"))
    rendered = []
    for source_filepath in [INDEX_FILEPATH, *article_filepaths]:
        output_filepath = site_filepath(source_filepath)
        title, body = render_markdown(source_filepath.read_text(), source_filepath, output_filepath, images)
        rendered.append((source_filepath, output_filepath, title, body))

    (SITE_DIRPATH / "images").mkdir()       # before printing: the PDFs need them
    for image_filepath in sorted(images):
        shutil.copy2(image_filepath, SITE_DIRPATH / "images" / image_filepath.name)

    for source_filepath, output_filepath, title, body in rendered:
        if source_filepath in article_filepaths and chrome:
            pdf_filename = source_filepath.stem + ".pdf"
            print_filepath = output_filepath.with_suffix(".print.html")
            print_filepath.write_text(page(title, body, output_filepath))
            print_pdf(chrome, print_filepath, output_filepath.with_name(pdf_filename))
            print_filepath.unlink()
            body = re.sub(r"(</h1>)", rf'\1\n<p class="download"><a href="{pdf_filename}">Download as PDF</a></p>',
                          body, count=1)
        output_filepath.write_text(page(title, body, output_filepath))
        print(f"Wrote {output_filepath.relative_to(PROJECT_DIRPATH)}")

    (SITE_DIRPATH / ".nojekyll").write_text("")   # serve the files as they are
    if not chrome:
        print("Chrome not found: no PDFs (set CHROME_FILEPATH)")
    return SITE_DIRPATH


def main() -> None:
    build()


if __name__ == "__main__":
    main()
