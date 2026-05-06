"""Anchor-bounded glossary patcher for ``SCHEMA.md``.

Inserts new term rows between the markers
``<!-- glossary:auto:start -->`` and ``<!-- glossary:auto:end -->`` inside
the ``## Glossary`` section. Manual rows above/below the markers are
preserved byte-identical. First call inserts the markers at the bottom of
the table body; subsequent calls only edit between them.

Per M3 contract, criterion 9.
"""

from __future__ import annotations

import re

START = "<!-- glossary:auto:start -->"
END = "<!-- glossary:auto:end -->"

_GLOSSARY_HEADING = re.compile(r"^## +Glossary\s*$", re.MULTILINE)
_NEXT_H2 = re.compile(r"^## +", re.MULTILINE)


def existing_terms(schema_md: str) -> set[str]:
    """Return all term names already present in the glossary table."""
    return {term for term, _, _ in glossary_rows(schema_md)}


def glossary_rows(schema_md: str) -> list[tuple[str, str, str]]:
    """Return all glossary rows as ``(term, definition, aliases)``.

    Reads every non-header table row inside ``## Glossary``, including rows
    above and below the auto-managed marker block. Empty cells are returned
    as empty strings. HTML pipe entities ``&#124;`` are decoded back to
    ``|`` so callers see the human-readable definition.
    """
    section = _section(schema_md)
    if section is None:
        return []
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for line in section.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if not cols or not cols[0]:
            continue
        if cols[0].lower() == "term":
            continue
        if set(cols[0]) <= {"-", ":"}:
            continue
        term = cols[0].replace("&#124;", "|")
        definition = cols[1].replace("&#124;", "|") if len(cols) > 1 else ""
        aliases = cols[2].replace("&#124;", "|") if len(cols) > 2 else ""
        if term in seen:
            continue
        seen.add(term)
        rows.append((term, definition, aliases))
    return rows


def render_mirror(schema_md: str, today: str) -> str:
    """Return the markdown body for ``wiki/concepts/_glossary.md``.

    Per [ADR-0002](../../adr/ADR-0002-glossary-indexing.md): one H2 section
    per glossary row, alphabetically (case-insensitive), with frontmatter
    ``generated_by: glossary-mirror``.
    """
    rows = sorted(glossary_rows(schema_md), key=lambda r: r[0].lower())
    lines = [
        "---",
        "type: concept",
        "confidence: high",
        "sources: []",
        f"updated: {today}",
        "generated_by: glossary-mirror",
        "---",
        "",
        "# Glossary",
        "",
        "> Auto-generated from SCHEMA.md ## Glossary. Do not edit by hand.",
        "",
    ]
    for term, definition, aliases in rows:
        lines.append(f"## {term}")
        lines.append(definition or "_no definition recorded_")
        lines.append("")
        lines.append(f"**Aliases to avoid:** {aliases or 'none'}")
        lines.append("**Source:** [SCHEMA.md](../../SCHEMA.md#glossary)")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def patch(schema_md: str, new_terms: list[tuple[str, str]]) -> str:
    """Return new SCHEMA.md text with ``new_terms`` added between markers.

    Idempotent: terms already present (anywhere in the glossary) are
    skipped. If markers don't yet exist, they are inserted at the bottom
    of the glossary table body.
    """
    if not new_terms:
        return schema_md

    have = existing_terms(schema_md)
    fresh = [(t, d) for t, d in new_terms if t not in have]
    if not fresh:
        return schema_md

    m = _GLOSSARY_HEADING.search(schema_md)
    if m is None:
        # No glossary section; append one.
        block = (
            "\n## Glossary\n\n"
            "| Term | Definition | Aliases to avoid |\n"
            "|---|---|---|\n"
            f"{START}\n"
            + "".join(_row(t, d) for t, d in fresh)
            + f"{END}\n"
        )
        if not schema_md.endswith("\n"):
            schema_md += "\n"
        return schema_md + block

    sec_start = m.end()
    next_m = _NEXT_H2.search(schema_md, sec_start + 1)
    sec_end = next_m.start() if next_m else len(schema_md)
    section = schema_md[sec_start:sec_end]

    if START in section and END in section:
        # Insert fresh rows immediately before the END marker, preserving
        # everything else byte-for-byte.
        insert_at = section.index(END)
        injected = "".join(_row(t, d) for t, d in fresh)
        new_section = section[:insert_at] + injected + section[insert_at:]
    else:
        # First call: locate the bottom of the glossary table body and
        # append the markers + rows there. Manual rows above are kept.
        new_section = _insert_markers(section, fresh)

    return schema_md[:sec_start] + new_section + schema_md[sec_end:]


def _section(schema_md: str) -> str | None:
    m = _GLOSSARY_HEADING.search(schema_md)
    if m is None:
        return None
    sec_start = m.end()
    next_m = _NEXT_H2.search(schema_md, sec_start + 1)
    sec_end = next_m.start() if next_m else len(schema_md)
    return schema_md[sec_start:sec_end]


def _insert_markers(section: str, fresh: list[tuple[str, str]]) -> str:
    lines = section.splitlines(keepends=True)
    # Find the last contiguous run of table lines (lines starting with '|').
    last_table_idx = -1
    for i, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            last_table_idx = i
    injected = (
        f"{START}\n" + "".join(_row(t, d) for t, d in fresh) + f"{END}\n"
    )
    if last_table_idx == -1:
        # No table; append a fresh table + markers.
        body = (
            "\n| Term | Definition | Aliases to avoid |\n"
            "|---|---|---|\n" + injected
        )
        return section.rstrip("\n") + "\n" + body
    insert_pos = last_table_idx + 1
    return "".join(lines[:insert_pos]) + injected + "".join(lines[insert_pos:])


def _row(term: str, definition: str) -> str:
    # Replace literal '|' with the HTML entity so an LLM-emitted term or
    # definition cannot break out into a new table column. ``existing_terms``
    # parses by splitting on raw '|'; a stray pipe would corrupt the term
    # column on the next ingest and break idempotency permanently. The HTML
    # entity renders as '|' in any Markdown viewer.
    return f"| {_esc(term)} | {_esc(definition)} |  |\n"


def _esc(cell: str) -> str:
    return cell.replace("|", "&#124;")
