from pprint import pprint


from strategize.lazy_resolution import *
from strategize.recursion_schemes import strategize
from strategize.state_machines import SMInputContract
from strategize.validators import Range


test_credit_input_contract = SMInputContract(
    state_schema=RecRecord(**{
        'payments': LockedList([{'amount': Range(4, 5), 'payment_status': bool}]), 
        'charges': LockedList([{'amount': Range(10, 20), 'charge_status': bool,}]), 
        'balance': Sub(
            DefListAgg(sum, 'charges.amount', lambda c: c['charge_status']),
            DefListAgg(sum, 'payments.amount', lambda p: p['payment_status'])
        ),
    }),
    event_schema={'amount': Range(max=Ref('init_state.balance'))},
)

if __name__ == "__main__":
    pprint(strategize(test_credit_input_contract).example())
