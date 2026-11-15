"""Patch-generation sample: comments, else branches and one manual-only finding."""


def with_else(value):
    if value is None:
        return None
    if value is None:  # repeated guard
        return 'unreachable'
    else:  # reachable branch
        # preserve the output shape
        return {'value':value}


def with_comments(value):
    if value is None:
        return None
    if value is not None:  # already checked
        # keep this business explanation
        return value
        # keep this trailing explanation


def manual_only(value):
    if value is not None:
        if value is None:
            return 1


def true_else(value):
    if value is None:
        return None
    if value is not None:
        return value
    else:
        return 'unreachable'


def optional_port(loader):
    try:
        return int(loader())
    except Exception:
        return None
