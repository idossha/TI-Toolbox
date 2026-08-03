#!/usr/bin/env simnibs_python
"""Parsing of spherical ROI specifications.

The GUI collects spheres as ``"x,y,z,r"`` rows. Parsing lives here rather than
in the tab so it is exercised without PyQt5, which is absent from the test
environment.

See Also
--------
tit.analyzer.analyzer.Analyzer.analyze_sphere : Consumes one parsed sphere.
"""


def parse_sphere_row(text: str) -> tuple[float, float, float, float]:
    """Parse a single ``"x,y,z,r"`` row.

    Parameters
    ----------
    text : str
        Comma-separated centre and radius.

    Returns
    -------
    tuple of float
        ``(x, y, z, r)``.

    Raises
    ------
    ValueError
        If *text* is empty, does not hold exactly four values, holds a
        non-numeric value, or gives a non-positive radius.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Please enter coordinates and radius as x,y,z,r.")
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4 or any(p == "" for p in parts):
        raise ValueError("Enter exactly 4 values: x,y,z,r.")
    try:
        x, y, z, r = (float(p) for p in parts)
    except ValueError:
        raise ValueError("All values must be numeric: x,y,z,r.")
    if r <= 0:
        raise ValueError("Radius must be positive.")
    return (x, y, z, r)


def parse_sphere_rows(texts) -> list[tuple[float, float, float, float]]:
    """Parse several ``"x,y,z,r"`` rows.

    A one-element sequence reproduces single-sphere behaviour exactly, including
    its error messages -- the row number is only prefixed when there is more
    than one row, so a single malformed sphere reads the way it always did.

    Parameters
    ----------
    texts : sequence of str
        One ``"x,y,z,r"`` string per sphere.

    Returns
    -------
    list of tuple of float
        One ``(x, y, z, r)`` per input row, in order.

    Raises
    ------
    ValueError
        If *texts* is empty or any row is malformed.
    """
    if not texts:
        raise ValueError("Please enter coordinates and radius as x,y,z,r.")
    spheres = []
    for i, text in enumerate(texts):
        try:
            spheres.append(parse_sphere_row(text))
        except ValueError as exc:
            if len(texts) == 1:
                raise
            raise ValueError(f"Row {i + 1}: {exc}")
    return spheres
