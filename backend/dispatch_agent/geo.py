import math

EARTH_RADIUS_MILES = 3958.8
MILES_PER_DEGREE_LAT = 69.0


def zip_to_coords(conn, zip_code):
    """Return (latitude, longitude) of a ZIP's center point, or None if unknown."""
    row = conn.execute(
        "SELECT latitude, longitude FROM zip_centroids WHERE zip = ?", (zip_code,)
    ).fetchone()
    return (row["latitude"], row["longitude"]) if row else None


def haversine_miles(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points, in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def bounding_box(lat, lng, radius_miles):
    """(south, north, west, east) of a box that contains the circle around a point."""
    dlat = radius_miles / MILES_PER_DEGREE_LAT
    dlng = radius_miles / (MILES_PER_DEGREE_LAT * math.cos(math.radians(lat)))
    return lat - dlat, lat + dlat, lng - dlng, lng + dlng
