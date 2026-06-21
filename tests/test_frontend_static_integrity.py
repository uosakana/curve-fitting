from __future__ import annotations

import re
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"
INDEX_HTML = STATIC_DIR / "index.html"
APP_JS = STATIC_DIR / "app.js"
STYLES_CSS = STATIC_DIR / "styles.css"
CSS_IMPORT_RE = re.compile(r"@import\s+url\([\"']?([^\"')]+)[\"']?\);")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _direct_js_id_refs(js: str) -> set[str]:
    refs = set(re.findall(r"\$\([\"']([^\"']+)[\"']\)", js))
    refs.update(re.findall(r"getElementById\([\"']([^\"']+)[\"']\)", js))
    return refs


def _static_path(ref: str) -> Path:
    parsed = urlparse(ref)
    path = parsed.path
    if path.startswith("/static/"):
        return STATIC_DIR / path.removeprefix("/static/")
    return STATIC_DIR / path


def _css_files_from_manifest(path: Path = STYLES_CSS) -> list[Path]:
    files = [path]
    seen = {path.resolve()}
    index = 0
    while index < len(files):
        current = files[index]
        index += 1
        for ref in CSS_IMPORT_RE.findall(_read(current)):
            imported = _static_path(ref)
            resolved = imported.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(imported)
    return files


def _js_files_from_html() -> list[Path]:
    html = _read(INDEX_HTML)
    files: list[Path] = []
    for ref in re.findall(r"<script\s+src=[\"'](/static/[^\"']+)[\"']", html):
        path = _static_path(ref)
        if path.suffix == ".js":
            files.append(path)
    return files


def _all_js_text() -> str:
    return "\n".join(_read(path) for path in _js_files_from_html())


def _all_css_text() -> str:
    return "\n".join(_read(path) for path in _css_files_from_manifest())


def _css_rules(css: str) -> list[tuple[str, str, int]]:
    rules: list[tuple[str, str, int]] = []
    line_starts = [0]
    for match in re.finditer(r"\n", css):
        line_starts.append(match.end())

    def line_no(position: int) -> int:
        lo = 0
        hi = len(line_starts)
        while lo < hi:
            mid = (lo + hi) // 2
            if line_starts[mid] <= position:
                lo = mid + 1
            else:
                hi = mid
        return lo

    index = 0
    while index < len(css):
        start = css.find("{", index)
        if start < 0:
            break
        selector = re.sub(r"/\*.*?\*/", "", css[index:start], flags=re.S).strip()
        depth = 1
        end = start + 1
        while end < len(css) and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        body = css[start + 1 : end - 1].strip()
        if selector and not selector.startswith("@"):
            normalized_selector = re.sub(r"\s+", " ", selector)
            normalized_body = re.sub(r"\s+", " ", body)
            rules.append((normalized_selector, normalized_body, line_no(index)))
        index = end
    return rules


class FrontendStaticIntegrityTest(unittest.TestCase):
    def test_html_ids_are_unique_and_direct_js_refs_exist(self) -> None:
        html = _read(INDEX_HTML)
        js = _all_js_text()
        ids = re.findall(r"\bid=[\"']([^\"']+)[\"']", html)
        counts = Counter(ids)
        duplicates = sorted(name for name, count in counts.items() if count > 1)
        missing = sorted(ref for ref in _direct_js_id_refs(js) if ref not in counts)

        self.assertEqual(duplicates, [])
        self.assertEqual(missing, [])

    def test_static_asset_references_exist(self) -> None:
        html = _read(INDEX_HTML)
        css = _all_css_text()
        references = re.findall(r"(?:href|src)=[\"'](/static/[^\"']+)[\"']", html)
        references.extend(re.findall(r"url\([\"']?(/static/[^\"')]+)[\"']?\)", css))
        missing: list[str] = []
        for ref in references:
            parsed = urlparse(ref)
            if parsed.scheme or parsed.netloc:
                continue
            if not _static_path(ref).exists():
                missing.append(ref)

        self.assertEqual(sorted(missing), [])

    def test_stylesheet_manifest_imports_existing_files(self) -> None:
        imports = CSS_IMPORT_RE.findall(_read(STYLES_CSS))
        self.assertGreaterEqual(len(imports), 1)
        missing = [ref for ref in imports if not _static_path(ref).exists()]
        self.assertEqual(missing, [])

    def test_static_cache_versions_match(self) -> None:
        html = _read(INDEX_HTML)
        versions = []
        for ref in re.findall(r"(?:href|src)=[\"'](/static/(?:app\.js|styles\.css|js/[^\"']+\.js)\?[^\"']+)[\"']", html):
            query = parse_qs(urlparse(ref).query)
            versions.extend(query.get("v", []))

        self.assertGreaterEqual(len(versions), 2)
        self.assertEqual(len(set(versions)), 1)

    def test_javascript_chunks_load_in_numeric_order(self) -> None:
        js_files = [path for path in _js_files_from_html() if path.parent.name == "js"]
        self.assertGreaterEqual(len(js_files), 1)
        names = [path.name for path in js_files]
        self.assertEqual(names, sorted(names))
        missing = [path.as_posix() for path in js_files if not path.exists()]
        self.assertEqual(missing, [])

    def test_css_braces_and_exact_duplicate_rules(self) -> None:
        css = _all_css_text()
        self.assertEqual(css.count("{"), css.count("}"))

        rule_counts = Counter((selector, body) for selector, body, _line in _css_rules(css))
        duplicates = [
            selector
            for (selector, _body), count in rule_counts.items()
            if count > 1
        ]
        self.assertEqual(sorted(duplicates), [])


if __name__ == "__main__":
    unittest.main()
