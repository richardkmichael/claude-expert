#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Regenerate the index tables in code/analysis/README.md and desktop/analysis/README.md.

Each analysis doc carries its own index entry as YAML frontmatter, so a doc's version stamp is
written in one place.  Fields:

    verified      product version the whole doc was checked against (required)
    verified_on   date of that check, YYYY-MM-DD (optional)
    scope         one line: what the doc answers (required)
    section       index section the row belongs in (code docs only, required there)
    style         landmark, legacy, generated or methodology (code docs only, required there)
    landmarks     version-stable strings to grep for when relocating the behavior (code docs;
                  optional for methodology docs)

Each README keeps its hand-written headings and prose.  The script rewrites only the tables between
`<!-- analysis-index: <section> -->` and `<!-- /analysis-index -->` markers (the Desktop README has
one unnamed marker), one row per doc, ordered by file name.

Usage:
    bin/analysis-index.py           rewrite both READMEs
    bin/analysis-index.py --check   change nothing; exit 1 if a README is out of date or a doc's
                                    frontmatter is missing or invalid

Both modes also list the findings docs (all but methodology) stamped behind the newest prepared
version in the product's work/ directory: the docs a question about that version should re-check
first.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
STYLES = {"landmark", "legacy", "generated", "methodology"}
VERSION = re.compile(r"\d+(\.\d+)+")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
MARKER = re.compile(
    r"(<!-- analysis-index(?:: (?P<section>[^>]*?))? -->\n)(.*?)(<!-- /analysis-index -->)",
    re.DOTALL,
)


@dataclass
class Product:
    name: str
    directory: Path
    has_sections: bool

    @property
    def analysis(self) -> Path:
        return self.directory / "analysis"

    @property
    def readme(self) -> Path:
        return self.analysis / "README.md"


PRODUCTS = [
    Product("code", REPO_ROOT / "code", has_sections=True),
    Product("desktop", REPO_ROOT / "desktop", has_sections=False),
]


@dataclass
class Doc:
    path: Path
    verified: str
    scope: str
    section: str | None
    style: str | None
    landmarks: list[str]


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest_prepared(product: Product) -> str | None:
    work = product.directory / "work"
    if not work.is_dir():
        return None
    versions = [p.name for p in work.iterdir() if p.is_dir() and VERSION.fullmatch(p.name)]
    return max(versions, key=version_key, default=None)


def read_doc(product: Product, path: Path, errors: list[str]) -> Doc | None:
    match = FRONTMATTER.match(path.read_text())
    where = path.relative_to(REPO_ROOT)
    if match is None:
        errors.append(f"{where}: no YAML frontmatter")
        return None
    try:
        fields = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as error:
        errors.append(f"{where}: frontmatter is not valid YAML: {error}")
        return None
    if not isinstance(fields, dict):
        errors.append(f"{where}: frontmatter is not a mapping")
        return None

    allowed = {"verified", "verified_on", "scope"}
    if product.has_sections:
        allowed |= {"section", "style", "landmarks"}
    for key in sorted(set(fields) - allowed):
        errors.append(f"{where}: unknown frontmatter key '{key}'")

    verified = str(fields.get("verified", ""))
    if not VERSION.fullmatch(verified):
        errors.append(f"{where}: 'verified' must be a version such as 2.1.317, not '{verified}'")
    verified_on = fields.get("verified_on")
    if verified_on is not None and not DATE.fullmatch(str(verified_on)):
        errors.append(f"{where}: 'verified_on' must be YYYY-MM-DD, not '{verified_on}'")
    scope = fields.get("scope")
    if not isinstance(scope, str) or not scope.strip():
        errors.append(f"{where}: 'scope' is required")
        scope = ""

    section = style = None
    landmarks: list[str] = []
    if product.has_sections:
        section = fields.get("section")
        if not isinstance(section, str) or not section.strip():
            errors.append(f"{where}: 'section' is required")
        style = fields.get("style")
        if style not in STYLES:
            errors.append(f"{where}: 'style' must be one of {sorted(STYLES)}, not '{style}'")
        landmarks = fields.get("landmarks") or []
        if not isinstance(landmarks, list) or not all(isinstance(x, str) for x in landmarks):
            errors.append(f"{where}: 'landmarks' must be a list of strings")
            landmarks = []
        elif not landmarks and style != "methodology":
            errors.append(f"{where}: 'landmarks' is required unless the style is methodology")
        for landmark in landmarks:
            if "`" in landmark:
                errors.append(f"{where}: landmark {landmark!r} contains a backtick")

    return Doc(path, verified, " ".join(scope.split()), section, style, landmarks)


def cell(text: str) -> str:
    return text.replace("|", "\\|")


def table(header: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table with aligned columns, as mdformat writes it."""
    rows = [[cell(c) for c in row] for row in rows]
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    widths = [max(w, 3) for w in widths]

    def line(row: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(row, widths)) + " |"

    rule = "| " + " | ".join("-" * w for w in widths) + " |"
    return "\n".join([line(header), rule, *(line(r) for r in rows)]) + "\n"


def code_table(docs: list[Doc]) -> str:
    with_landmarks = any(d.landmarks for d in docs)
    header = ["Doc", "Scope", "Verified", "Style"] + (["Key landmarks"] if with_landmarks else [])
    rows = []
    for doc in docs:
        row = [f"`{doc.path.name}`", doc.scope, doc.verified, doc.style or ""]
        if with_landmarks:
            row.append(", ".join(f"`{x}`" for x in doc.landmarks))
        rows.append(row)
    return table(header, rows)


def desktop_table(docs: list[Doc]) -> str:
    rows = [[f"[{d.path.stem}](./{d.path.name})", d.scope, d.verified] for d in docs]
    return table(["File", "Covers", "Verified"], rows)


def render(product: Product, docs: list[Doc], errors: list[str]) -> str:
    text = product.readme.read_text()
    where = product.readme.relative_to(REPO_ROOT)
    seen: set[str | None] = set()

    def replace(match: re.Match) -> str:
        section = match.group("section")
        seen.add(section)
        if product.has_sections:
            members = [d for d in docs if d.section == section]
            if not members:
                errors.append(f"{where}: no doc has section '{section}'")
            body = code_table(members)
        else:
            members = docs
            body = desktop_table(members)
        return f"{match.group(1)}\n{body}\n{match.group(4)}"

    rendered = MARKER.sub(replace, text)
    if not seen:
        errors.append(f"{where}: no <!-- analysis-index --> markers")
    if product.has_sections:
        for doc in docs:
            if doc.section is not None and doc.section not in seen:
                errors.append(
                    f"{doc.path.relative_to(REPO_ROOT)}: section '{doc.section}' has no marker"
                    f" in {where}"
                )
    return rendered


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report only; change nothing")
    args = parser.parse_args()

    errors: list[str] = []
    stale: list[str] = []
    outdated: dict[Path, str] = {}
    for product in PRODUCTS:
        paths = sorted(p for p in product.analysis.glob("*.md") if p.name != "README.md")
        docs = [d for d in (read_doc(product, p, errors) for p in paths) if d is not None]

        latest = latest_prepared(product)
        if latest is not None:
            for doc in docs:
                if doc.style == "methodology" or not VERSION.fullmatch(doc.verified):
                    continue
                if version_key(doc.verified) < version_key(latest):
                    stale.append(f"  {doc.path.relative_to(REPO_ROOT)}: {doc.verified} < {latest}")

        rendered = render(product, docs, errors)
        if rendered != product.readme.read_text():
            outdated[product.readme] = rendered

    # A README is rewritten only when every doc's frontmatter is valid, so an error never
    # drops rows from the index.
    rewrite = not args.check and not errors
    if rewrite:
        for readme, rendered in outdated.items():
            readme.write_text(rendered)

    if stale:
        print("Stamped behind the newest prepared version (re-check before relying on them):")
        print("\n".join(stale))
    for error in errors:
        print(f"error: {error}", file=sys.stderr)
    for readme in outdated:
        verb = "rewritten" if rewrite else "out of date"
        print(f"{readme.relative_to(REPO_ROOT)}: {verb}")
    return 1 if errors or (args.check and outdated) else 0


if __name__ == "__main__":
    sys.exit(main())
