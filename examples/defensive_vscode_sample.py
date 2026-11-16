"""AwaitLab 上手示例：黄色提示可预览修复，蓝色提示需人工判断。"""


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


def optional(loader):
    try:
        return loader()
    except Exception:
        return None
