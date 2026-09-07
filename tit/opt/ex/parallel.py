"""Ordered, fork-based candidate evaluation for the exhaustive searches.

Both exhaustive searches (:mod:`tit.opt.ex`, :mod:`tit.opt.mex`) score
independent candidates against one large in-memory leadfield. Workers
are forked *after* the engine has loaded it, so every worker reads the
parent's arrays copy-on-write -- nothing is pickled per task except the
small electrode tuples and metric dicts. Results are yielded in task
order, so CSV ordering and per-candidate progress logging are unchanged.

``n_jobs == 1`` (or a platform without ``fork``) evaluates in-process.
"""

import multiprocessing
import os
import signal
from typing import Any, Callable, Iterable, Iterator

# The engine the forked workers evaluate with. Set by the parent right
# before the pool forks and cleared when it is torn down.
_ENGINE: Any = None


def resolve_n_jobs(n_jobs: int | None) -> int:
    """Worker count: ``n_jobs < 1`` (or ``None``) means all cores minus one."""
    cpu = os.cpu_count() or 1
    if n_jobs is None or n_jobs < 1:
        return max(1, cpu - 1)
    return int(n_jobs)


def _worker_init(numba_threads: int) -> None:
    """Give each worker a share of the numba threads and default signals.

    The parent installs its own flag-setting SIGINT/SIGTERM handlers
    before forking, and a worker that inherited them would ignore
    ``Pool.terminate()`` (SIGTERM). SIGINT is ignored so a terminal
    Ctrl-C reaches the parent, which stops cleanly and terminates the
    workers itself.

    BLAS/OpenMP thread limits are deliberately NOT applied here: the
    parent applies them before forking (see :func:`evaluate_ordered`).
    Calling ``threadpoolctl`` inside a forked child initialises the
    OpenMP runtimes SimNIBS loads (``libomp``) and aborts the child.
    """
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        import numba

        # The default OpenMP/TBB layers are not safe to start inside a
        # forked child (Intel OpenMP aborts on affinity init); workqueue is.
        numba.config.THREADING_LAYER = "workqueue"
        numba.set_num_threads(max(1, numba_threads))
    except Exception:  # noqa: BLE001 - numba optional / not parallel-capable
        pass


def _worker_call(task: tuple[str, tuple]) -> Any:
    method, args = task
    return getattr(_ENGINE, method)(*args)


def evaluate_ordered(
    engine: Any,
    method: str,
    tasks: Iterable[tuple],
    n_jobs: int | None,
    chunksize: int = 1,
    n_tasks: int | None = None,
) -> Iterator[Any]:
    """Yield ``getattr(engine, method)(*args)`` for every ``args`` in ``tasks``.

    Results arrive in task order. With more than one worker the engine is
    shared with forked workers via copy-on-write; closing the generator
    early (e.g. ``break`` after a stop signal) terminates the pool. When
    ``n_tasks`` is known, no more workers than tasks are started and the
    numba threads are shared out among the workers actually used.
    """
    global _ENGINE

    n_jobs = resolve_n_jobs(n_jobs)
    if n_tasks is not None:
        n_jobs = max(1, min(n_jobs, int(n_tasks)))
    if n_jobs > 1:
        try:
            ctx = multiprocessing.get_context("fork")
        except ValueError:
            n_jobs = 1

    if n_jobs == 1:
        fn: Callable = getattr(engine, method)
        for args in tasks:
            yield fn(*args)
        return

    numba_threads = max(1, (os.cpu_count() or 1) // n_jobs)
    _ENGINE = engine
    # One BLAS/OpenMP thread per worker: limit in the parent (safe, the
    # runtimes are already initialised here) so the forked workers inherit
    # it; restored when the pool is torn down.
    limits = _thread_limits()
    pool = ctx.Pool(n_jobs, initializer=_worker_init, initargs=(numba_threads,))
    try:
        for result in pool.imap(
            _worker_call, ((method, args) for args in tasks), chunksize
        ):
            yield result
        pool.close()
    finally:
        pool.terminate()
        pool.join()
        _ENGINE = None
        if limits is not None:
            limits.unregister()


def _thread_limits():
    """``threadpoolctl.threadpool_limits(1)`` if available, else ``None``."""
    try:
        from threadpoolctl import threadpool_limits

        return threadpool_limits(1)
    except Exception:  # noqa: BLE001 - optional dependency
        return None
