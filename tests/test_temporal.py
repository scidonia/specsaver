from specsaver.temporal import old, unchanged


def test_old_is_noop():
    x = 5
    assert old(x) == 5


def test_old_with_complex_expression():
    xs = [1, 2, 3]
    assert old(xs[0]) == 1


def test_unchanged_equal():
    assert unchanged({"a": 1}, {"a": 1})


def test_unchanged_not_equal():
    assert not unchanged({"a": 1}, {"a": 2})


def test_unchanged_with_except_is_still_equality():
    # At runtime, unchanged ignores except_ and just does ==
    assert not unchanged({"a": 1}, {"a": 2}, except_=frozenset())
