"""Provider search: service category + ZIP code -> top-ranked nearby providers.

Distance is a filter, not part of the score. Providers within the radius are
ranked by a Bayesian-adjusted rating, which pulls ratings with few reviews toward
the category average.
"""

from dataclasses import dataclass

from dispatch_agent.config import MIN_REVIEWS, PRIOR_WEIGHT, RADIUS_MILES, TOP_N
from dispatch_agent.geo import bounding_box, haversine_miles, zip_to_coords


class UnknownZipError(ValueError):
    pass


class UnknownCategoryError(ValueError):
    pass


@dataclass(frozen=True)
class Provider:
    id: int
    name: str
    phone: str
    website: str | None
    address: str | None
    rating: float
    review_count: int
    distance_miles: float
    score: float


def bayesian_score(rating, review_count, prior_mean, prior_weight=PRIOR_WEIGHT):
    """Rating blended with `prior_weight` reviews at `prior_mean`."""
    return (review_count * rating + prior_weight * prior_mean) / (review_count + prior_weight)


def category_mean_rating(conn, category):
    """Average rating of eligible providers in a category, across the whole database."""
    row = conn.execute(
        """SELECT COUNT(c.id) AS found, AVG(p.rating) AS mean
           FROM service_categories c
           LEFT JOIN provider_services ps ON ps.category_id = c.id
           LEFT JOIN providers p ON p.id = ps.provider_id
                AND p.review_count >= ? AND p.rating IS NOT NULL
           WHERE c.name = ?""",
        (MIN_REVIEWS, category),
    ).fetchone()
    if not row["found"]:
        raise UnknownCategoryError(f"unknown service category: {category!r}")
    return row["mean"]


def search_providers(conn, category, zip_code, radius_miles=RADIUS_MILES, limit=TOP_N):
    """Top `limit` providers in `category` within `radius_miles` of `zip_code`, best first.

    Raises UnknownCategoryError or UnknownZipError. Returns an empty list when the
    ZIP is valid but no eligible provider is in range.
    """
    zip_code = zip_code.strip().split("-")[0]  # accept ZIP+4
    coords = zip_to_coords(conn, zip_code)
    if coords is None:
        raise UnknownZipError(f"unknown ZIP code: {zip_code!r}")
    prior_mean = category_mean_rating(conn, category)

    lat, lng = coords
    south, north, west, east = bounding_box(lat, lng, radius_miles)
    rows = conn.execute(
        """SELECT p.id, p.name, p.phone, p.website, p.address, p.latitude, p.longitude,
                  p.rating, p.review_count
           FROM providers p
           JOIN provider_services ps ON ps.provider_id = p.id
           JOIN service_categories c ON c.id = ps.category_id
           WHERE c.name = ?
             AND p.review_count >= ? AND p.rating IS NOT NULL
             AND p.latitude BETWEEN ? AND ?
             AND p.longitude BETWEEN ? AND ?""",
        (category, MIN_REVIEWS, south, north, west, east),
    ).fetchall()

    providers = []
    for r in rows:
        distance = haversine_miles(lat, lng, r["latitude"], r["longitude"])
        if distance > radius_miles:
            continue
        providers.append(
            Provider(
                id=r["id"],
                name=r["name"],
                phone=r["phone"],
                website=r["website"],
                address=r["address"],
                rating=r["rating"],
                review_count=r["review_count"],
                distance_miles=round(distance, 1),
                score=bayesian_score(r["rating"], r["review_count"], prior_mean),
            )
        )
    providers.sort(key=lambda p: (-p.score, -p.review_count, p.distance_miles))
    return providers[:limit]
