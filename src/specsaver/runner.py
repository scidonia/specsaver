"""Symmetric scenario runner — the generic test engine.

Implements the symmetric flow from the Symmetric Database State
architecture:

    witness → materialize → context
                          → snapshot → before (SpecState)
                          → check invariants + admissibility
                          → execute impl on context
                          → snapshot → after (SpecState)
                          → check transitions + frame + invariants

The runner depends only on Protocol interfaces (§19 of the Symmetric
document) and on ``SpecScenario`` (the Gherkin-assembled contract).
It never imports a concrete domain, database, or implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from specsaver.protocols import (
    FaultInjector,
    ImplementationAdapter,
    ScenarioMaterializer,
    ScenarioWitness,
    SpecificationProjection,
)
from specsaver.scenario import SpecScenario
from specsaver.verify import ContractCheck, run_checks


class ScenarioAssertionError(AssertionError):
    """The actual behaviour disagreed with the row's declared outcome."""


@dataclass
class ScenarioResult:
    scenario: str
    feature: str
    outcome: str
    before: Any = None
    after: Any = None
    result: Any = None
    invariant_checks_before: list[ContractCheck] = field(default_factory=list)
    invariant_checks_after: list[ContractCheck] = field(default_factory=list)
    admissibility_checks: list[ContractCheck] = field(default_factory=list)
    transition_checks: list[ContractCheck] = field(default_factory=list)
    skipped_call: bool = True

    @property
    def invariants_held(self) -> bool:
        return all(
            c.passed
            for c in self.invariant_checks_before + self.invariant_checks_after
        )

    @property
    def admissibility_held(self) -> bool:
        return all(c.passed for c in self.admissibility_checks)

    @property
    def transitions_held(self) -> bool:
        return all(c.passed for c in self.transition_checks)

    def describe_failures(self) -> str:
        lines = []
        for phase, checks in [
            ("invariant(before)", self.invariant_checks_before),
            ("admissibility", self.admissibility_checks),
            ("transition", self.transition_checks),
            ("invariant(after)", self.invariant_checks_after),
        ]:
            for c in checks:
                if not c.passed:
                    detail = f": {c.error}" if c.error else ""
                    lines.append(f"[{phase}] {c.identifier}{detail}")
        return "; ".join(lines)


def run_scenario(
    scenario: SpecScenario,
    witness: ScenarioWitness,
    *,
    materializer: ScenarioMaterializer,
    projection: SpecificationProjection,
    impl: ImplementationAdapter | None = None,
    fault_injector: FaultInjector | None = None,
    fault_name: str | None = None,
    outcome: str | None = None,
) -> ScenarioResult:
    """Run the symmetric specification-driven test flow.

    Outcome dispatch:
      - ``"rejected"``    — admissibility fails; impl NOT called.
      - ``"success"``     — admissibility holds; impl called;
                            transitions/invariants checked.
      - ``"error:CODE"``  — admissibility holds; fault injected (if any); impl called;
                            result.code must match; transitions/invariants checked.
      - ``None``          — inferred: if admissibility fails, treat as rejection.
    """
    # --- Materialize the concrete execution world ----------------
    context = materializer.materialize(witness)

    # --- Project the ACTUAL execution world (not the witness) -----
    before = projection.snapshot(context)

    out = ScenarioResult(
        scenario=scenario.name,
        feature=scenario.feature,
        outcome=outcome or "",
        before=before,
    )

    # --- Check invariants on the projected pre-state --------------
    out.invariant_checks_before = run_checks(list(scenario.invariants), before)

    # --- Check admissibility (true caller preconditions) ----------
    out.admissibility_checks = run_checks(list(scenario.given), before, witness.args)

    admissibility_held = all(c.passed for c in out.admissibility_checks)

    # --- Dispatch on outcome -------------------------------------
    if outcome == "rejected" or (outcome is None and not admissibility_held):
        # Caller precondition violation — impl must not be called.
        if admissibility_held:
            raise ScenarioAssertionError(
                f"{scenario.name}: outcome='rejected' but all admissibility "
                f"checks passed — expected at least one to fail"
            )
        out.skipped_call = True
        return out

    if not admissibility_held:
        raise ScenarioAssertionError(
            f"{scenario.name}: outcome={outcome!r} requires admissibility "
            f"to hold, but it failed: {out.describe_failures()}"
        )

    # --- Execute the implementation on the real context -----------
    if impl is None:
        out.skipped_call = True
        return out

    # Inject fault before execution (if requested)
    if fault_name and fault_injector is not None:
        fault_injector.inject(fault_name)

    out.skipped_call = False
    try:
        result = impl.execute(context, witness.args)
    except Exception as exc:
        result = exc
    out.result = result

    # --- Project the SAME execution world after execution ---------
    after = projection.snapshot(context)
    out.after = after

    # --- Check transitions (postconditions) -----------------------
    out.transition_checks = run_checks(
        list(scenario.then), before, witness.args, result, after
    )

    # --- Check exception contracts (if exception was raised) -------
    if isinstance(result, Exception):
        exc_type_name = getattr(type(result), "code", type(result).__name__)
        matching = [
            r for r in scenario.exceptionals
            if getattr(r.func, "_specsaver_exc_type", None) == exc_type_name
        ]
        if matching:
            _ = run_checks(matching, before, witness.args)
        elif scenario.exceptionals:
            raise ScenarioAssertionError(
                f"{scenario.name}: unhandled exception "
                f"{type(result).__name__} — no matching @exceptional contract"
            )

    # --- Check invariants on the projected post-state -------------
    out.invariant_checks_after = run_checks(list(scenario.invariants), after)

    # --- Validate against declared outcome ------------------------
    if outcome == "success":
        if not out.transitions_held or not out.invariants_held:
            raise ScenarioAssertionError(
                f"{scenario.name}: outcome='success' but "
                f"transitions/invariants failed: {out.describe_failures()}"
            )
    elif outcome and outcome.startswith("error:"):
        expected_code = outcome.split(":", 1)[1]
        actual_code = getattr(result, "code", None)
        if actual_code != expected_code:
            raise ScenarioAssertionError(
                f"{scenario.name}: expected error code {expected_code!r}, "
                f"got {actual_code!r}"
            )
        if not out.transitions_held or not out.invariants_held:
            raise ScenarioAssertionError(
                f"{scenario.name}: outcome='error:{expected_code}' but "
                f"transitions/invariants failed: {out.describe_failures()}"
            )

    return out
