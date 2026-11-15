"""Intentionally redundant sample for `awaitlab audit`; not production advice."""


def customer_result(customer):
    if customer is None:
        return {'customer':None}
    if customer is None:
        return {'customer':'unreachable fallback'}
    if customer is not None:
        return {'customer':customer}


def optional_port(loader):
    try:
        return int(loader())
    except Exception:
        return None
