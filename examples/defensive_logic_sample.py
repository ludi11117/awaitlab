"""Intentionally repeated identity guards for the compound-path audit demo."""


def customer_result(customer,ready):
    if customer is None or ready is not True:
        return None
    if None is customer:
        return 'unreachable customer fallback'
    if not (ready is True):
        return 'unreachable readiness fallback'
    return {'customer':customer}


def enabled(flag):
    if flag is True:
        if True is flag:
            return 'enabled'
    return 'disabled'


def optional_port(loader):
    try:
        return int(loader())
    except Exception:
        return None
