"""Real scipy for one test at a time, for the group-statistics tests (p16, 2026-10-22).

``tests/conftest.py`` replaces ``scipy`` with ``MagicMock`` so the host suite imports ``tit``
without the science stack. The group-statistics claims (cluster masses, peaks, p-values) need
the real library, which the host venv has. Some older stats test modules swap real scipy in at
import time and never put the mocks back, so at fixture time ``sys.modules`` may hold the mock
or a real scipy. This fixture:

* uses the real scipy already in ``sys.modules`` when there is one; otherwise removes the
  mock entries, imports the real package, and on teardown removes it and restores the mocks;
* points ``tit.stats.engine``'s module-level scipy bindings (``sp_stats``, ``label``,
  ``ndimage_sum``, ``rankdata``) at that real scipy for the test, through ``monkeypatch``.

It never re-imports a real scipy that is already loaded: popping and re-importing scipy leaves
its compiled ``csgraph`` extensions bound to the first copy's classes (``connected_components``
then rejects every sparse matrix). For the same reason tests that cluster on a graph use
:func:`bfs_components` -- an independent breadth-first connected-components -- instead of
whichever ``scipy.sparse.csgraph`` copy the session happens to hold.

Run: ``.venv/bin/python -m pytest tests/test_stats_*.py -q -p no:cacheprovider``.
"""

from __future__ import annotations

import sys
from collections import deque

import numpy as np
import pytest


def _is_real(module) -> bool:
    return getattr(module, "__file__", None) is not None


@pytest.fixture
def real_scipy(monkeypatch):
    """Yield the real ``scipy.stats`` module with ``tit.stats.engine`` bound to real scipy."""
    swapped = None
    if not _is_real(sys.modules.get("scipy")):
        swapped = {
            k: sys.modules.pop(k)
            for k in list(sys.modules)
            if k.split(".")[0] == "scipy"
        }
    try:
        import scipy.ndimage
        import scipy.sparse
        import scipy.stats
    except ImportError as exc:  # pragma: no cover - host venv always has scipy
        if swapped is not None:
            sys.modules.update(swapped)
        pytest.skip(f"skipping: real scipy is not importable here ({exc})")

    from tit.stats import engine

    monkeypatch.setattr(engine, "sp_stats", scipy.stats)
    monkeypatch.setattr(engine, "label", scipy.ndimage.label)
    monkeypatch.setattr(engine, "ndimage_sum", scipy.ndimage.sum)
    monkeypatch.setattr(engine, "rankdata", scipy.stats.rankdata)
    try:
        yield scipy.stats
    finally:
        if swapped is not None:
            for key in [k for k in sys.modules if k.split(".")[0] == "scipy"]:
                del sys.modules[key]
            sys.modules.update(swapped)


@pytest.fixture
def seeded_permutations(monkeypatch):
    """Make every permutation draw reproducible, and put the global state back afterwards.

    The volume engine draws per-permutation seeds from the global ``np.random``; the surface
    path calls ``np.random.default_rng()`` with no seed. A test about what a significant cluster
    reports must not depend on whether this run's random relabellings happened to reach it.
    """
    state = np.random.get_state()
    np.random.seed(20261022)
    real_default_rng = np.random.default_rng
    monkeypatch.setattr(
        np.random,
        "default_rng",
        lambda seed=None: real_default_rng(20261022 if seed is None else seed),
    )
    try:
        yield
    finally:
        np.random.set_state(state)


def bfs_components(graph, directed=False):
    """Connected components of a symmetric 0/1 graph: ``(n_components, labels)``.

    Same contract as ``scipy.sparse.csgraph.connected_components(graph, directed=False)``
    (0-based labels, numbered in order of the first vertex reached), written out so a graph
    test does not depend on which scipy copy the session holds.
    """
    csr = graph.tocsr() if hasattr(graph, "tocsr") else None
    n = graph.shape[0]
    labels = np.full(n, -1, dtype=int)
    current = 0
    for start in range(n):
        if labels[start] >= 0:
            continue
        labels[start] = current
        queue = deque([start])
        while queue:
            v = queue.popleft()
            if csr is not None:
                neighbours = csr.indices[csr.indptr[v] : csr.indptr[v + 1]]
            else:
                neighbours = np.flatnonzero(np.asarray(graph)[v])
            for w in neighbours:
                if labels[w] < 0:
                    labels[w] = current
                    queue.append(w)
        current += 1
    return current, labels


def chain_adjacency(n):
    """Symmetric adjacency of the path graph 0-1-2-...-(n-1), as a real scipy CSR matrix."""
    from scipy import sparse

    i = np.arange(n - 1)
    return sparse.coo_matrix(
        (np.ones(2 * (n - 1)), (np.r_[i, i + 1], np.r_[i + 1, i])), shape=(n, n)
    ).tocsr()


@pytest.fixture
def graph_components(real_scipy, monkeypatch):
    """Route ``tit.stats.surface``'s ``connected_components`` to :func:`bfs_components`."""
    import scipy.sparse.csgraph as csgraph

    monkeypatch.setattr(csgraph, "connected_components", bfs_components)
    return bfs_components
