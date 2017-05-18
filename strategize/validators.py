"""
Nodes in the schematization tree that are compatible with strategize.
(And lazy resolution)
"""
import hypothesis.strategies as st
from voluptuous import Invalid

from .recursion_schemes import fmap


class Range(object):
    def __init__(self, min=None, max=None):
        self.min = min
        self.max = max
    
    def __call__(self, v):
        minres, maxres = (
            v <= self.min if self.min is not None else True,
            v >= self.max if self.max is not None else True,
        )
        
        if not minres and maxres:
            raise Invalid
        else:
            return v
    
    def __repr__(self):
        return 'Range(min={}, max={})'.format(self.min, self.max)
    
    def __fmap__(self, f):
        return Range(fmap(f, self.min), fmap(f, self.max))
    
    def __strategize__(self):
        # This is so bad. This stupid validator implicitly knows about `RecRecord` and
        # expects to be called with some fields as `Ref`s. Since python is strict
        # (call-by-value), there's no real way around this, though.
        if all(v is None or isinstance(v, (int, float)) for v in (self.min, self.max)):
            return st.integers(min_value=self.min, max_value=self.max)
        else:
            # This is a dirty hack to play nice with lazy resolution:
            # return the un-resolved validator, with its `Ref`s still contained, to be resolved
            # in a later round.
            return st.just(self)  
