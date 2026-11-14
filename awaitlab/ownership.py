"""Track only tasks created in this workload's context, never unrelated tasks."""
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
import weakref

_owner=ContextVar('awaitlab_owned_tasks',default=None)


@contextmanager
def owned_tasks():
    loop=asyncio.get_running_loop()
    tasks=weakref.WeakSet()
    previous=loop.get_task_factory()
    token=_owner.set(tasks)
    def factory(loop,coro,**kwargs):
        context=kwargs.get('context')
        owner=context.get(_owner) if context is not None else _owner.get()
        task=previous(loop,coro,**kwargs) if previous else asyncio.Task(coro,loop=loop,**kwargs)
        if owner is tasks:tasks.add(task)
        return task
    loop.set_task_factory(factory)
    try:yield tasks
    finally:
        if loop.get_task_factory() is factory:loop.set_task_factory(previous)
        _owner.reset(token)
