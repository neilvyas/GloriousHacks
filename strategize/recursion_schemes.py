import hypothesis.strategies as st
from voluptuous import Schema


def strategize(obj):
    # More elegant than the decorator-registration scheme we undertook in the first version.
    if hasattr(obj, '__strategize__'):
        return obj.__strategize__()
    elif isinstance(obj, Schema):
        return strategize(obj.schema)
    elif isinstance(obj, (int, str)):
        return st.just(obj)
    elif obj is int:
        return st.integers()
    elif obj is float:
        return st.floats()
    elif obj is str:
        return st.text()
    elif obj is bool:
        return st.booleans()
    elif isinstance(obj, dict):
        strat_pairs = [st.tuples(strategize(k), strategize(v)) for k, v in obj.items()]
        return st.builds(
            # This comment is left-over from Affirm.strategize.
            #
            # This filtering is to handle voluptuous Optional keys.
            # If we weren't using decorator registration this might be cleaner,
            # because we could leave it off here and simply do
            #    super(...).filter(lambda d: k is not None for k in d)
            # in VoluptuousStrategizer or something.
            # This means None is not an acceptable key (which is fine, maybe?).
            lambda *tuples: dict((k, v) for k, v in tuples if k is not None),
            *strat_pairs
        )
    elif isinstance(obj, list):
        return st.lists(elements=st.one_of(strategize(x) for x in obj))


# Because all good software starts with fmap.
def fmap(f, obj):
    if hasattr(obj, '__fmap__'):
        return obj.__fmap__(f)
    elif isinstance(obj, list):
        return [fmap(f, x) for x in obj]
    elif isinstance(obj, dict):
        return {fmap(f, k): fmap(f, v) for k, v in obj.items()}
    else:
        return f(obj)
