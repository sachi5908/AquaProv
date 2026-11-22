"""Optional, thread-local progress reporting for desktop and headless jobs.

Percentages describe completed stages/work units, never elapsed-time estimates.
Scientific functions remain usable without Qt or a progress listener.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event


progress_listener = ContextVar('aquaprov_progress_listener', default=None)
_range = ContextVar('aquaprov_progress_range', default=(0., 100.))
active_cancellation = ContextVar('aquaprov_cancellation', default=None)


class JobCancelled(Exception):
    """A user stopped an unfinished calculation; this is not a plot error."""


class CancellationToken:
    def __init__(self):
        self.event = Event()

    def cancel(self):
        self.event.set()

    @property
    def cancelled(self):
        return self.event.is_set()


def check_cancelled():
    token = active_cancellation.get()
    if token is not None and token.cancelled:
        raise JobCancelled('Plot cancelled')


def report_progress(value, detail=''):
    check_cancelled()
    listener = progress_listener.get()
    if listener is not None:
        low, high = _range.get()
        listener(low + (high - low) * max(0., min(100., value)) / 100., detail)


@contextmanager
def progress_stage(start, end, detail):
    """Map a subtask's 0–100 progress onto a portion of its parent's range."""
    low, high = _range.get()
    token = _range.set((low + (high-low)*start/100., low + (high-low)*end/100.))
    try:
        report_progress(0, detail)
        yield
        report_progress(100)
    finally:
        _range.reset(token)
