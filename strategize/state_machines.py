from voluptuous import Schema

from .lazy_resolution import RecRecord
from .recursion_schemes import strategize


class SMInputContract(object):
    def __init__(self, state_schema, event_schema=None):
        self.state_schema = state_schema
        self.event_schema = event_schema
        self.is_creator = event_schema is None
        
    def __strategize__(self):
        state_schema_strat = strategize(self.state_schema)
        
        if self.is_creator:
            return state_schema_strat
        else:
            return state_schema_strat.flatmap(
                    lambda s: strategize(RecRecord(init_state=s, event=self.event_schema))
                )

    def __call__(f):
        n_args = len(getargspec(f).args)
        if n_args == 1:
            def wrapper(creator_event):
                # Yeah the naming is weird. Deal with it. This is because of arity.
                creator_event = self.state_schema(creator_event)
                return f(creator_event)
            
        elif n_args == 2:
            def wrapper(init_state, event):
                init_state = self.state_schema(init_state)
                reified_event_schema = Schema(RecRecord(
                    init_state=init_state,
                    event=self.event_schema).__resolve__()['event'])
                
                reified_event_schema(event)
                return f(init_state, event)
                
        else:
            raise TypeError
            
        return wrapper   
