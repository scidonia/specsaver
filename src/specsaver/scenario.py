"""Scenario assembler — the full contract for one Gherkin scenario.

`SpecScenario` cross-references a Scenario/Scenario Outline's Given/When/Then
step templates against the contract registry, answering "what is the
complete contract for this scenario?" in one structure:

    Given ... ->  preconditions
    When  ... ->  (text only — no implementation reference)
    Then  ... ->  postconditions
    Rule  ... ->  invariants (ambient, feature-wide)

Implementation is injected at test time, not contract time (see the
project's design discussion) — this module never imports or references a
concrete implementation.  It only assembles Gherkin structure + already
registered contracts.

Two views of "which contracts belong to this scenario" are combined:

  - Feature-wide: every precondition/postcondition/invariant registered
    with `feature=<this file>` is considered part of the scenario's
    contract.  This is deliberately *not* restricted to contracts whose
    `from_gherkin` matches one of the literal Given/Then step strings,
    because some preconditions legitimately originate from the When step
    (e.g. a validity check on a value introduced there), and because a
    feature file may (for now, or by design) contain contracts with no
    single-step Gherkin counterpart yet (a tracked specification gap, not
    a bug in this module — see specsaver/#8 in the demo repo).

  - Per-step completeness check: every literal Given step must resolve to
    at least one precondition, and every literal Then step must resolve to
    at least one postcondition.  This is the forward direction only — it
    catches "this Gherkin sentence has no formal meaning yet", not the
    reverse ("this contract has no matching Gherkin sentence").
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gherkin.parser import Parser as _GherkinParser

from specsaver.gherkin import ExamplesTable, parse_examples_tables
from specsaver.registry import ContractRecord, get_registry
from specsaver.types import ContractKind

_ROLE_BY_KEYWORD_TYPE = {
    "Context": "given",
    "Action": "when",
    "Outcome": "then",
}


class ScenarioSpecError(Exception):
    """The Gherkin structure for a scenario doesn't resolve to a complete,
    well-formed contract (a specification-completeness failure)."""


@dataclass(frozen=True)
class GherkinStepTemplate:
    """One step of a Scenario/Scenario Outline, placeholders intact.

    `role` is one of "given"/"when"/"then" — Conjunction ("And"/"But")
    steps inherit the role of the preceding non-conjunction step.
    """

    role: str
    text: str


def _step_templates(scenario_node: dict) -> list[GherkinStepTemplate]:
    templates: list[GherkinStepTemplate] = []
    current_role: str | None = None
    for step in scenario_node.get("steps", []):
        role = _ROLE_BY_KEYWORD_TYPE.get(step.get("keywordType"))
        if role is not None:
            current_role = role
        if current_role is None:
            raise ScenarioSpecError(
                f"Step {step.get('text')!r} has no preceding Given/When/Then "
                "step to inherit its role from (Background is not supported)"
            )
        templates.append(GherkinStepTemplate(role=current_role, text=step["text"]))
    return templates


def _find_scenario_node(feature_node: dict, name: str) -> dict:
    """Find a Scenario/Scenario Outline node by name, at the top level of
    the feature or nested one level under a Rule (Gherkin does not nest
    Rules within Rules)."""
    for child in feature_node.get("children", []):
        scenario = child.get("scenario")
        if scenario is not None and scenario.get("name") == name:
            return scenario
        rule = child.get("rule")
        if rule is not None:
            for rule_child in rule.get("children", []):
                nested = rule_child.get("scenario")
                if nested is not None and nested.get("name") == name:
                    return nested
    raise ScenarioSpecError(
        f"No Scenario/Scenario Outline named {name!r} found in feature"
    )


@dataclass(frozen=True)
class SpecScenario:
    """The assembled contract for one Gherkin scenario."""

    feature: str
    name: str
    given: tuple[ContractRecord, ...]
    given_steps: tuple[str, ...]
    when_text: str
    then: tuple[ContractRecord, ...]
    then_steps: tuple[str, ...]
    invariants: tuple[ContractRecord, ...]
    exceptionals: tuple[ContractRecord, ...]
    examples: tuple[ExamplesTable, ...]

    @classmethod
    def from_text(
        cls, feature_text: str, feature_id: str, scenario_name: str
    ) -> SpecScenario:
        doc = _GherkinParser().parse(feature_text)
        feature_node = doc.get("feature")
        if feature_node is None:
            raise ScenarioSpecError("Feature text has no Feature: block")

        scenario_node = _find_scenario_node(feature_node, scenario_name)
        templates = _step_templates(scenario_node)

        given_steps = tuple(t.text for t in templates if t.role == "given")
        when_steps = tuple(t.text for t in templates if t.role == "when")
        then_steps = tuple(t.text for t in templates if t.role == "then")

        if len(when_steps) != 1:
            raise ScenarioSpecError(
                f"Scenario {scenario_name!r} must have exactly one When "
                f"step, got {len(when_steps)}: {when_steps}"
            )
        when_text = when_steps[0]

        registry = get_registry()

        for step_text in given_steps:
            matches = [
                r
                for r in registry.list_by_gherkin(step_text)
                if r.kind == ContractKind.PRECONDITION
            ]
            if not matches:
                # A Given step with no matching precondition may be a
                # business-case condition (checked by the impl, not by
                # admissibility).  Not an error — just no admissibility
                # contract associated with this step.
                pass
        for step_text in then_steps:
            matches = [
                r
                for r in registry.list_by_gherkin(step_text)
                if r.kind == ContractKind.POSTCONDITION
            ]
            if not matches:
                raise ScenarioSpecError(
                    f"Then step {step_text!r} has no associated postcondition"
                )

        given = tuple(
            registry.list_by_feature_and_kind(feature_id, ContractKind.PRECONDITION)
        )
        then = tuple(
            registry.list_by_feature_and_kind(feature_id, ContractKind.POSTCONDITION)
        )
        invariants = tuple(
            registry.list_by_feature_and_kind(feature_id, ContractKind.INVARIANT)
        )
        exceptionals = tuple(
            registry.list_by_feature_and_kind(feature_id, ContractKind.EXCEPTIONAL)
        )

        tables = tuple(
            t
            for t in parse_examples_tables(feature_text)
            if t.outline_name == scenario_name
        )

        return cls(
            feature=feature_id,
            name=scenario_name,
            given=given,
            given_steps=given_steps,
            when_text=when_text,
            then=then,
            then_steps=then_steps,
            invariants=invariants,
            exceptionals=exceptionals,
            examples=tables,
        )

    @classmethod
    def from_feature(
        cls, feature_path: str | Path, scenario_name: str
    ) -> SpecScenario:
        p = Path(feature_path)
        return cls.from_text(p.read_text(), p.name, scenario_name)
