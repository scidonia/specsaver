from specsaver.types import EffectSpec, Event, Field, Frame


class TestField:
    def test_basic_path(self):
        f = Field("source.balance")
        assert str(f) == "source.balance"
        assert f.path == "source.balance"

    def test_parent(self):
        f = Field("a.b.c")
        p = f.parent()
        assert p is not None
        assert p.path == "a.b"
        pp = p.parent()
        assert pp is not None
        assert pp.path == "a"
        assert pp.parent() is None

    def test_is_prefix_of(self):
        f = Field("source")
        assert f.is_prefix_of(Field("source.balance"))
        assert f.is_prefix_of(Field("source"))
        assert not f.is_prefix_of(Field("target"))

    def test_empty_path_raises(self):
        import pytest

        with pytest.raises(ValueError):
            Field("")

    def test_double_dot_raises(self):
        import pytest

        with pytest.raises(ValueError):
            Field("a..b")


class TestFrame:
    def test_default_empty(self):
        f = Frame()
        assert len(f.writes) == 0
        assert len(f.reads) == 0

    def test_accepts_set(self):
        f = Frame(writes={Field("a")}, reads={Field("b"), Field("c")})
        assert isinstance(f.writes, frozenset)
        assert isinstance(f.reads, frozenset)
        assert Field("a") in f.writes
        assert Field("b") in f.reads

    def test_union(self):
        f1 = Frame(writes={Field("a")})
        f2 = Frame(writes={Field("b")}, reads={Field("x")})
        f3 = f1 | f2
        assert Field("a") in f3.writes
        assert Field("b") in f3.writes
        assert Field("x") in f3.reads


class TestEffectSpec:
    def test_default_empty(self):
        e = EffectSpec()
        assert len(e.opens) == 0
        assert len(e.uses) == 0

    def test_accepts_set(self):
        e = EffectSpec(uses={"database"}, emits={Event("ev")})
        assert isinstance(e.uses, frozenset)
        assert "database" in e.uses
        assert Event("ev") in e.emits

    def test_union(self):
        e1 = EffectSpec(uses={"db"})
        e2 = EffectSpec(emits={Event("ev")})
        e3 = e1 | e2
        assert "db" in e3.uses
        assert Event("ev") in e3.emits
