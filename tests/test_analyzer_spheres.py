#!/usr/bin/env simnibs_python
"""Unit tests for tit.analyzer.spheres -- 'x,y,z,r' sphere parsing.

These live outside the GUI tests deliberately: the parsers are pure, and the
analyzer tab imports PyQt5, which is absent from this environment. Kept here
they run everywhere.
"""

import pytest

from tit.analyzer.spheres import parse_sphere_row, parse_sphere_rows


@pytest.mark.unit
class TestParseSphereRow:
    def test_parses_a_row(self):
        assert parse_sphere_row("10,-20,30,5") == (10.0, -20.0, 30.0, 5.0)

    def test_tolerates_whitespace_and_floats(self):
        assert parse_sphere_row("  1.5 , -2.25 ,3 , 4.5 ") == (1.5, -2.25, 3.0, 4.5)

    def test_rejects_empty(self):
        for bad in ("", "   ", None):
            with pytest.raises(ValueError, match="Please enter coordinates"):
                parse_sphere_row(bad)

    def test_rejects_wrong_field_count(self):
        for bad in ("1,2,3", "1,2,3,4,5", "1,2,3,"):
            with pytest.raises(ValueError, match="exactly 4 values"):
                parse_sphere_row(bad)

    def test_rejects_non_numeric(self):
        with pytest.raises(ValueError, match="must be numeric"):
            parse_sphere_row("1,2,three,4")

    def test_rejects_non_positive_radius(self):
        for bad in ("1,2,3,0", "1,2,3,-5"):
            with pytest.raises(ValueError, match="Radius must be positive"):
                parse_sphere_row(bad)


@pytest.mark.unit
class TestParseSphereRows:
    def test_single_row_matches_single_sphere_behaviour(self):
        assert parse_sphere_rows(["10,-20,30,5"]) == [(10.0, -20.0, 30.0, 5.0)]

    def test_preserves_order(self):
        rows = ["1,1,1,1", "2,2,2,2", "3,3,3,3"]
        assert parse_sphere_rows(rows) == [
            (1.0, 1.0, 1.0, 1.0),
            (2.0, 2.0, 2.0, 2.0),
            (3.0, 3.0, 3.0, 3.0),
        ]

    def test_empty_sequence_rejected(self):
        with pytest.raises(ValueError, match="Please enter coordinates"):
            parse_sphere_rows([])

    def test_single_bad_row_keeps_the_plain_message(self):
        """N=1 must read exactly as it always did -- no row prefix."""
        with pytest.raises(ValueError, match="^Radius must be positive"):
            parse_sphere_rows(["1,2,3,-1"])

    def test_bad_row_among_several_is_numbered(self):
        with pytest.raises(ValueError, match="^Row 2: "):
            parse_sphere_rows(["1,2,3,4", "1,2,3,-1", "5,5,5,5"])
