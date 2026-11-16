"""Known fixtures for loop guard review; audit never executes the target."""


def collect(values):
    result=[]
    for value in values:
        if value is None:
            continue
        if value is None:
            result.append('unreachable')
        result.append(value)
    return result


def prefix(values):
    result=[]
    for value in values:
        if value is None:
            break
        if value is not None:
            result.append(value)
    else:
        result.append('exhausted')
    return result
