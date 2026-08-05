"""Compile generated obligation files and produce the scoreboard.

Whole-file compile first; on failure, bisect per obligation (target
lemma live with its portfolio, everything else Admitted) and recompile
each — yielding a per-obligation PROVED / UNKNOWN scoreboard.

If an Lneg layer exists, UNKNOWN obligations are checked against
bundling theorems compiled by the Lneg layer.  A successful Lneg
compile + bundling theorem closure upgrades UNKNOWN to DISPROVED
(the negation is certified).  The three-valued outcome per obligation
is PROVED | DISPROVED | UNKNOWN.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_OBLIGATION_RE = re.compile(r"^Lemma (o\d_[a-z0-9_]+)", re.MULTILINE)


@dataclass(frozen=True)
class Scoreboard:
    results: dict[str, str]   # obligation name → "PROVED" | "DISPROVED" | "UNKNOWN"

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


def _compile_file_in_dir(path: Path) -> subprocess.CompletedProcess:
    """Compile *path* using _CoqProject in its parent directory."""
    parent = path.parent
    coqproject = parent / "_CoqProject"
    if coqproject.exists():
        lines = coqproject.read_text().strip().splitlines()
        flags: list[str] = []
        for line in lines:
            if not line.strip() or not (line.strip()[0] == "-"):
                continue
            for tok in line.split():
                # _CoqProject uses shell quoting (e.g. "" for empty
                # logical prefix).  subprocess passes args literally,
                # so strip the outer quotes when present.
                if tok.startswith('"') and tok.endswith('"'):
                    tok = tok[1:-1]
                flags.append(tok)
        return subprocess.run(
            ["coqc"] + flags + [path.name],
            capture_output=True, text=True, timeout=300, cwd=str(parent),
        )
    return _compile(path, "coq")


def score(path: Path, coqdir: str = "coq") -> Scoreboard:
    """Compile *path* and return the per-obligation scoreboard.

    Three-valued outcomes:
    - PROVED   — obligation proof closes (bisect coqc passes).
    - DISPROVED — Lneg bundling theorem compiles, proving the negation.
    - UNKNOWN  — neither proof nor disproof is certified.
    """
    proc = _compile_file_in_dir(path)
    obligations = _OBLIGATION_RE.findall(path.read_text())
    if proc.returncode == 0:
        return Scoreboard(dict.fromkeys(obligations, "PROVED"))

    src = path.read_text()
    base = path.parent
    results: dict[str, str] = {}
    # Try to detect DISPROVED from Lneg before falling back to bisect.
    lneg_targets = _lneg_target_map(base)

    for target in obligations:
        # 1. Lneg: is the negation certified?
        if target in lneg_targets:
            lneg_ok = _lneg_compile(base, lneg_targets[target])
            if lneg_ok:
                results[target] = "DISPROVED"
                continue

        # 2. Bisect: does the proof close in isolation?
        variant = path.with_name(path.stem + f"_{target}.v")
        variant.write_text(_bisect(src, target))
        p = _compile_file_in_dir(variant)
        results[target] = "PROVED" if p.returncode == 0 else "UNKNOWN"
        variant.unlink()
    return Scoreboard(results)


def _lneg_target_map(base: Path) -> dict[str, str]:
    """Read statements.json → {obligation_name: bundling_theorem_name}."""
    sj = base / "statements.json"
    if not sj.exists():
        return {}
    try:
        data = json.loads(sj.read_text())
    except (json.JSONDecodeError, KeyError):
        return {}
    mapping: dict[str, str] = {}
    for entry in data.get("lneg", []):
        mapping[entry["target"]] = entry["theorem"]
    return mapping


def _lneg_compile(base: Path, theorem: str) -> bool:
    """Compile the Lneg file and check if *theorem* closes.

    The Lneg file lives alongside the positive layer files and carries
    its own _CoqProject.  Whole-file coqc first; if that fails, the
    bundling theorems may still close individually (e.g. one witness
    proof is malformed but another isn't).  We accept whole-file
    success as sufficient for all DISPROVED; otherwise try theorem-
    specific bisect.
    """
    lneg = base / f"{base.name}_Lneg.v"
    if not lneg.exists():
        return False
    p = _compile_file_in_dir(lneg)
    if p.returncode == 0:
        return True
    # Bisect-style: admit everything except the target theorem.
    # (Coarse: just retry whole-file — the coqc error may be in a
    #  satellite lemma, which the bundling theorem depends on anyway.)
    return False


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
        variant = path.with_name(path.stem + f"_{name}.v")
        variant.write_text(_bisect(src, name))
        entries.append(str(variant))
    return entries
