from specsaver import (
    ContractKind,
    effect,
    get_registry,
    invariant,
    postcondition,
    precondition,
    predicate,
    reads,
    writes,
)
from specsaver.types import EffectSpec, Field, Frame


def test_registry_is_singleton():
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_precondition_registered():
    @precondition
    def my_pre(state: object, x: int) -> bool:
        return x > 0

    registry = get_registry()
    records = registry.list_by_kind(ContractKind.PRECONDITION)
    assert any(r.qualname.endswith("my_pre") for r in records)

    assert my_pre(None, 1) is True
    assert my_pre(None, 0) is False


def test_postcondition_registered():
    @postcondition
    def my_post(old_s: object, inp: int, result: str, new_s: object) -> bool:
        return len(result) > 0

    records = get_registry().list_by_kind(ContractKind.POSTCONDITION)
    assert any(r.qualname.endswith("my_post") for r in records)


def test_predicate_registered():
    @predicate
    def is_positive(x: int) -> bool:
        return x > 0

    records = get_registry().list_by_kind(ContractKind.PREDICATE)
    assert any(r.qualname.endswith("is_positive") for r in records)


def test_invariant_registered():
    @invariant
    def always_true(state: object) -> bool:
        return True

    records = get_registry().list_by_kind(ContractKind.INVARIANT)
    assert any(r.qualname.endswith("always_true") for r in records)


def test_writes_registered():
    @writes
    def my_writes() -> Frame:
        return Frame(writes={Field("x")})

    records = get_registry().list_by_kind(ContractKind.WRITES)
    assert any(r.qualname.endswith("my_writes") for r in records)


def test_reads_registered():
    @reads
    def my_reads() -> Frame:
        return Frame(reads={Field("x")})

    records = get_registry().list_by_kind(ContractKind.READS)
    assert any(r.qualname.endswith("my_reads") for r in records)


def test_effect_registered():
    @effect
    def my_effect() -> EffectSpec:
        return EffectSpec(uses={"db"})

    records = get_registry().list_by_kind(ContractKind.EFFECT)
    assert any(r.qualname.endswith("my_effect") for r in records)


def test_list_by_module():
    registry = get_registry()
    records = registry.list_by_module("tests.test_contracts")
    assert len(records) > 0
    assert all(r.module == "tests.test_contracts" for r in records)


def test_registry_clear():
    registry = get_registry()
    registry.clear()
    assert len(registry) == 0

    @predicate
    def after_clear(x: int) -> bool:
        return True

    assert len(registry) > 0
