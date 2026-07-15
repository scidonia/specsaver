"""Gherkin parsing — wraps the official Cucumber parser (gherkin-official).

Scenario Outlines describe behaviour abstractly using <placeholder> variables.
Examples tables provide the concrete instances.  This module parses .feature
files using the same algorithm as real Cucumber implementations (the
official `gherkin` package's tokenizer/AST-builder plus its pickle
compiler), so <placeholder> substitution is standards-compliant rather than
hand-rolled.

Two complementary views are exposed:

- `parse_feature` / `parse_feature_file` produce fully-resolved concrete
  scenarios ("pickles") — the exact text a human would read for one row of
  an Examples table.  Useful for documentation, traceability reports, and
  sanity-checking that no `<placeholder>` survives substitution.

- `parse_examples_tables` / `examples_for` return the *structured* rows of
  an Examples table (column name -> value) directly from the Gherkin AST.
  This is what generated tests should consume to build concrete inputs —
  there is no regex/text parsing of natural-language step sentences
  anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gherkin.parser import Parser as _GherkinParser
from gherkin.pickles.compiler import Compiler as _PickleCompiler

# ---------------------------------------------------------------------------
# Resolved concrete scenarios ("pickles")
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GherkinStep:
    """A single step of a fully-resolved concrete scenario.

    keyword_type is one of "Context" (Given), "Action" (When), or
    "Outcome" (Then) — the classification the official compiler assigns.
    """

    keyword_type: str
    text: str


@dataclass(frozen=True)
class GherkinScenario:
    """A fully-resolved concrete scenario: one row of an Examples table
    substituted into its Scenario Outline, or a plain Scenario."""

    name: str
    steps: tuple[GherkinStep, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)
    examples_table: str | None = None


def _parse_document(feature_text: str, uri: str) -> dict[str, Any]:
    parser = _GherkinParser()
    doc = parser.parse(feature_text)
    doc["uri"] = uri
    return doc


def _row_id_to_table_name(feature_node: dict[str, Any]) -> dict[str, str]:
    """Build a lookup from Examples-table-row id -> table name."""
    lookup: dict[str, str] = {}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "tableHeader" in node and "tableBody" in node:
                name = node.get("name") or "Examples"
                for row in node["tableBody"]:
                    lookup[row["id"]] = name
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(feature_node)
    return lookup


def parse_feature(feature_text: str, uri: str = "<feature>") -> list[GherkinScenario]:
    """Parse Gherkin feature text into concrete, fully-resolved scenarios.

    Uses the official Cucumber Gherkin parser and pickle compiler, so
    Scenario Outline <placeholder> substitution is handled exactly as real
    Cucumber does it — not by hand-rolled string replacement.
    """
    doc = _parse_document(feature_text, uri)
    row_to_table = _row_id_to_table_name(doc["feature"])

    pickles = _PickleCompiler().compile(doc)

    scenarios: list[GherkinScenario] = []
    for pickle in pickles:
        steps = tuple(
            GherkinStep(keyword_type=s["type"], text=s["text"]) for s in pickle["steps"]
        )
        tags = tuple(t["name"] for t in pickle.get("tags", []))

        # astNodeIds[-1] is the Examples-table-row id for outline-derived
        # pickles; plain scenarios have a single astNodeId (the scenario
        # itself) and no corresponding table.
        examples_table = None
        for node_id in reversed(pickle.get("astNodeIds", [])):
            if node_id in row_to_table:
                examples_table = row_to_table[node_id]
                break

        scenarios.append(
            GherkinScenario(
                name=pickle["name"],
                steps=steps,
                tags=tags,
                examples_table=examples_table,
            )
        )
    return scenarios


def parse_feature_file(path: str | Path) -> list[GherkinScenario]:
    """Parse a .feature file from disk into concrete, resolved scenarios."""
    p = Path(path)
    return parse_feature(p.read_text(), uri=str(p))


# ---------------------------------------------------------------------------
# Structured Examples tables — for driving generated tests
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExamplesTable:
    """One 'Examples:' table belonging to a Scenario Outline."""

    outline_name: str
    table_name: str
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]


def parse_examples_tables(feature_text: str) -> list[ExamplesTable]:
    """Extract every Examples table as structured rows (column -> value).

    No text/regex parsing of step sentences is performed; this reads the
    Gherkin table AST directly (tableHeader / tableBody).
    """
    doc = _parse_document(feature_text, uri="<feature>")
    tables: list[ExamplesTable] = []

    def walk(node: Any, outline_name: str | None) -> None:
        if isinstance(node, dict):
            if node.get("keyword", "").strip().lower().startswith("scenario outline"):
                outline_name = node.get("name")
            if "tableHeader" in node and "tableBody" in node and outline_name:
                header = tuple(c["value"] for c in node["tableHeader"]["cells"])
                rows = tuple(
                    dict(
                        zip(
                            header,
                            (c["value"] for c in row["cells"]),
                            strict=True,
                        )
                    )
                    for row in node["tableBody"]
                )
                tables.append(
                    ExamplesTable(
                        outline_name=outline_name,
                        table_name=node.get("name") or "Examples",
                        columns=header,
                        rows=rows,
                    )
                )
            for v in node.values():
                walk(v, outline_name)
        elif isinstance(node, list):
            for item in node:
                walk(item, outline_name)

    walk(doc["feature"], None)
    return tables


def parse_examples_tables_file(path: str | Path) -> list[ExamplesTable]:
    p = Path(path)
    return parse_examples_tables(p.read_text())


def examples_for(
    tables: list[ExamplesTable],
    outline_name: str,
    table_name: str | None = None,
) -> list[dict[str, str]]:
    """Return concrete example rows for a given Scenario Outline.

    If table_name is given, only rows from that specific Examples table
    are returned; otherwise rows from every Examples table under the
    outline are concatenated.
    """
    rows: list[dict[str, str]] = []
    for t in tables:
        if t.outline_name != outline_name:
            continue
        if table_name is not None and t.table_name != table_name:
            continue
        rows.extend(t.rows)
    return rows
