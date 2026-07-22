"""Compile generated obligation files and produce the scoreboard.

Whole-file compile first; on failure, bisect per obligation (target
lemma live with its portfolio, everything else Admitted) and recompile
each — yielding a per-obligation PROVED / UNKNOWN scoreboard.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_OBLIGATION_RE = re.compile(r"^Lemma (o\d_[a-z0-9_]+)", re.MULTILINE)


@dataclass(frozen=True)
class Scoreboard:
    results: dict[str, str]   # obligation name → "PROVED" | "UNKNOWN"

    def report(self) -> str:
        lines = [f"  {name:<32} {status}" for name, status in self.results.items()]
        return "scoreboard:\n" + "\n".join(lines)


def _compile(path: Path, coqdir: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["coqc", "-R", coqdir, "", str(path)],
        capture_output=True, text=True, timeout=300,
    )


def _bisect(src: str, target: str) -> str:
    """Admit every Lemma except *target*."""
    out = re.sub(
        r"^Lemma (o\d_[a-z_]+)([\s\S]*?)Qed\.",
        lambda m: (
            m.group(0) if m.group(1) == target
            else f"Lemma {m.group(1)}{m.group(2).split('Proof.')[0]}Proof. Admitted."
        ),
        src,
        flags=re.MULTILINE,
    )
    return out


def score(path: Path, coqdir: str = "coq") -> Scoreboard:
    """Compile *path* and return the per-obligation scoreboard.

    Obligations that don't close are UNKNOWN: well-formed statements
    awaiting the LLM proof oracle — the queue, not a failure.
    """
    proc = _compile(path, coqdir)
    obligations = _OBLIGATION_RE.findall(path.read_text())
    if proc.returncode == 0:
        return Scoreboard(dict.fromkeys(obligations, "PROVED"))

    src = path.read_text()
    results: dict[str, str] = {}
    for target in obligations:
        variant = path.with_name(path.stem + f".{target}.v")
        variant.write_text(_bisect(src, target))
        p = _compile(variant, coqdir)
        results[target] = "PROVED" if p.returncode == 0 else "UNKNOWN"
        variant.unlink()
    return Scoreboard(results)


def queue(path: Path, coqdir: str = "coq") -> list[str]:
    """The LLM queue: self-contained files for each UNKNOWN obligation —
    the target lemma live, every other obligation Admitted, all
    supporting definitions in place.  Feed to the proof oracle."""
    board = score(path, coqdir)
    src = path.read_text()
    entries = []
    for name, status in board.results.items():
        if status != "UNKNOWN":
            continue
        variant = path.with_name(path.stem + f".{name}.v")
        variant.write_text(_bisect(src, name))
        entries.append(str(variant))
    return entries
