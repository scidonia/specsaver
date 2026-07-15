from specsaver.quantifiers import exists, forall


def test_forall_finite():
    assert forall([1, 2, 3], lambda x: x > 0)
    assert not forall([1, -2, 3], lambda x: x > 0)
    assert forall([], lambda x: False)  # vacuous truth


def test_exists_finite():
    assert exists([1, -2, 3], lambda x: x < 0)
    assert not exists([1, 2, 3], lambda x: x < 0)
    assert not exists([], lambda x: True)


def test_forall_generator():
    assert forall((x for x in range(1, 1000)), lambda x: x > 0)


def test_forall_list_of_lists():
    xs = [[1, 2], [3, 4]]
    assert forall(xs, lambda inner: forall(inner, lambda y: y > 0))


def test_exists_generator():
    assert exists((x for x in range(100, 200)), lambda x: x == 150)
