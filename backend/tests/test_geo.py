import pytest

from dispatch_agent.geo import bounding_box, haversine_miles, zip_to_coords


def test_haversine_chicago_to_new_york():
    assert haversine_miles(41.8781, -87.6298, 40.7128, -74.0060) == pytest.approx(711, abs=2)


def test_haversine_same_point_is_zero():
    assert haversine_miles(41.88, -87.62, 41.88, -87.62) == 0


def test_bounding_box_contains_radius():
    south, north, west, east = bounding_box(41.88, -87.62, 25)
    assert haversine_miles(41.88, -87.62, north, -87.62) == pytest.approx(25, rel=0.01)
    assert haversine_miles(41.88, -87.62, south, -87.62) == pytest.approx(25, rel=0.01)
    assert haversine_miles(41.88, -87.62, 41.88, east) >= 25
    assert haversine_miles(41.88, -87.62, 41.88, west) >= 25


def test_zip_to_coords(conn):
    lat, lng = zip_to_coords(conn, "60601")
    assert lat == pytest.approx(41.885, abs=0.01)
    assert lng == pytest.approx(-87.622, abs=0.01)


def test_zip_to_coords_unknown(conn):
    assert zip_to_coords(conn, "00000") is None
