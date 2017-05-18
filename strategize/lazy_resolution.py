"""
RecRecord
~~~~~~~~~

An implementation of self-referential records resolved by lazy evaluation.

Problems with this lazy resolution engine so far:

* Most of the `DeferredVal` classes assume they live inside a `RecRecord` and that's the only
  place they can be resolved from. This is at odds with giving __resolve__ a more consistent
  API; either I free this constraint or I, indeed, make `RecRecord` the only entry point.

* We're not being particularly smart about resolution, instead relying on just re-running
  __resolve__ a ton of times and hoping that all the kinks get worked out. I know how to handle
  resolution smartly on its own, but I'm punting on implementing that because...

* I don't know how this is supposed to interact with __strategize__. Actually, what I'm really
  not sure how to approach is multi-phase resolution, which is the more general problem, and
  integrating into strategize's flatmap chain is really just the grossest version of that.

  I think the natural approach to this problem is to introduce another class of `DeferredVal`s,
  `DependentDeferredVal`, which wait on their refs to be "fully resolved" i.e. an `int` not a
  `Range`, before resolving themsleves, then topo-sorting the `RecRecord` based on connections
  induced by `DependentDeferredVal`s, BFSing, and at each layer interrupting resolution for
  filling in the necessary refs with outside input, either by progressive schema validation
  or flatmap chains or whatever.

* There's no __schema__ implementations yet. D'oh!


Also, this whole thing is monadic. Eat your heart out, guys. I don't think it fits nicely into
an `mtl`-type interface on top of __strategize__ and __schema__  because it's probably deeply
non-commutative / order matters / it's gross.
"""
import hypothesis.strategies as st


from .util import get_deep
from .recursion_schemes import fmap, strategize
from .validators import Range  # This is a stupid dependency.


class DeferredVal(object):
    # TODO FIXME: Make strategize pass `hypothesis.strategies` or a similar object
    #             so that we don't have to depend upon it at definition time.
    def __strategize__(self):
        # Not implementing anything for now; you should do flatmapping to get all
        # draws first and then resolve.
        return st.just(self)
    

class Pure(DeferredVal):
    def __init__(self, val):
        self.val = val
        
    # TODO FIXME: I need to guve __resolve__ a consistent API.
    def __resolve__(self, _):
        return self.val
    

def pure(v):
    return v if isinstance(v, DeferredVal) else Pure(v)
    

class Ref(DeferredVal):
    def __init__(self, ref):
        self.ref = ref
    
    def __resolve__(self, d):
        return get_deep(d, self.ref)
    
    def __repr__(self):
        return "Ref({})".format(self.ref)
    

# TODO decide on whether to make `StrategizeDeferred(DeferredVal)` that defers on strategies.
#      alternatively, the more general case is something like `DependentDeferredVal` which waits
#      until the ref is of a target (say primitive) type before resolving; we need this to handle
#      runtime schema validation as well.
class DefRef(DeferredVal):
    """
    This is a variant of a Ref that won't resolve anything non-value level.
    The use of this is deferring resolution of a ref until it is touched by
    strategize (for now).
    """
    def __init__(self, ref):
        self.ref = ref
    
    def __resolve__(self, d):
        res = get_deep(d, self.ref)
        # TODO FIXME: replace this with something like `hasattr(res, 'strategize')`?
        if isinstance(res, (Range)):
            return self
        else:
            return res
        
    def __repr__(self):
        return "DefRef({})".format(self.ref)
    

class Add(DeferredVal):
    def __init__(self, *terms):
        self.terms = [pure(t) for t in terms]
    
    def __resolve__(self, d):
        try:
            return sum([t.__resolve__(d) for t in self.terms])
        except TypeError:
            return self
    
    def __repr__(self):
        return "Add({})".format(", ".join(str(e) for e in self.terms))
    

class Sub(DeferredVal):
    def __init__(self, to_sub_from, sub_amount):
        self.to_sub_from = pure(to_sub_from)
        self.sub_amount = pure(sub_amount)
    
    def __resolve__(self, d):
        try:
            res = self.to_sub_from.__resolve__(d) - self.sub_amount.__resolve__(d)
            return res
        except Exception:
            return self
        
    def __repr__(self):
        return "Sub({}, {})".format(self.to_sub_from, self.sub_amount)
    

class DefListAgg(DeferredVal):
    """Run a function over a list that will be resolved to a list by strategize.
    """
    def __init__(self, agg_func, item_dep_ref, predicate=None):
        self.agg_func = agg_func
        
        path = item_dep_ref.split('.', 1)
        if len(path) == 1:
            self.list_ref = Ref(item_dep_ref)
            self.item_resolver = lambda x: x
        else:
            self.list_ref = DefRef(path[0])
            self.item_resolver = lambda x: Ref(path[1]).__resolve__(x)
            
        self.predicate = predicate or (lambda _: True)
        
    def __resolve__(self, d):
        try:
            return self.agg_func(
                self.item_resolver(item)
                for item in self.list_ref.__resolve__(d)
                if self.predicate(item)
            )
        except Exception:
            return self
        

class LockedList(list):
    """This is a glorious hack to prevent repeated iterations of strategize-resolve from
    breaking any Refs that depend on lists. This is because the list is the only object
    that has a strategize instance that returns something other than `st.just(self)` that is
    also a list, so strategize isn't "idempotent" for a bare list value.
    """
    class Locked(list):
        def __fmap__(self, f):
            return LockedList.Locked([fmap(f, x) for x in self])
        
        def __resolve__(self, _):
            return self
        
        def __strategize__(self):
            return st.just(self)
        
    def __init__(self, the_list, *args, **kwargs):
        super(LockedList, self).__init__(the_list, *args, **kwargs)
        
        self._locked_draw = LockedList.Locked(st.lists(
            elements=st.one_of([strategize(x) for x in self])
        ).example())
        
    def __fmap__(self, f):
        res = self._locked_draw.__fmap__(f)
        self._locked_draw = res
        
        return res
        
    def __resolve__(self, _):
        return self._locked_draw
    
    def __strategize__(self):
        return st.just(self._locked_draw)


class RecRecord(dict):
    """Define a record whose fields can contain self-referential references, in the vein of
    Nix sets. This is awesome for encoding crazy amounts of schema validation information.
    Also compatible with strategize. For example:

        >>> RecRecord(**{'container': {'value': 4}, 'deferred': Ref('container.value')}).__resolve__()
        {'container': {'value': 4}, 'deferred': 4}

        >>> strategize(RecRecord(**{'a': Range(2, 4), 'b': Range(DefRef('a'), 10)})).example()
        {'a': 3, 'b': 3}
    """
    def __strategize__(self):
        # TODO FIXME: THIS IS A DIRTY HACK
        # I don't want to figure out how to make resolution and strategize trampoline properly.
        # Perhaps the right way is to make resolution understand partial-resolution with a
        # boolean flag, and handing off completion of such resolution to something else
        # (like strategize?).

        # These calls are non-recursive because we're strategizing a `dict` each time.
        return (
            strategize(self.__resolve__())
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
            .flatmap(lambda s: strategize(_resolve_rec_dict(s)))
        )

    def __resolve__(self):
        keys = set(self.keys())

        queue = list(keys)
        while queue:  # If there is a circular dependency, this will loop forever.
            node_to_resolve = queue.pop(0)
            value_to_resolve = self[node_to_resolve]
            
            self[node_to_resolve] = fmap(
                lambda v: pure(v).__resolve__(self),
                value_to_resolve,
            )

            # TODO FIXME: We should insert keys back on the queue if their values are not
            # fully resolved, and also insert a unique token in the queue to keep track of
            # the presence of circular dependencies.
            # This is also a good opportunity for topo-sorting Refs!
            # I haven't addressed this now because I run many strategize-resolve iterations
            # in __strategize__.

        # resolution is supposed to return a primitive / strict version of the object.
        return dict(**self)


def _resolve_rec_dict(d):
    return RecRecord(**d).__resolve__()
