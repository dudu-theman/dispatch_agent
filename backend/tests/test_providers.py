import pytest

from dispatch_agent.config import MIN_REVIEWS, RADIUS_MILES, TOP_N
from dispatch_agent.providers import (
    UnknownCategoryError,
    UnknownZipError,
    bayesian_score,
    search_providers,
)


def test_bayesian_score_prefers_many_reviews():
    few = bayesian_score(4.9, 15, prior_mean=4.6)
    many = bayesian_score(4.7, 400, prior_mean=4.6)
    assert many > few


def test_bayesian_score_with_no_prior_weight_is_raw_rating():
    assert bayesian_score(4.2, 30, prior_mean=4.8, prior_weight=0) == 4.2


@pytest.mark.parametrize("category", ["plumbing", "hvac", "electrical", "roofing"])
def test_downtown_search_returns_top_n(conn, category):
    providers = search_providers(conn, category, "60601")
    assert len(providers) == TOP_N
    for p in providers:
        assert p.distance_miles <= RADIUS_MILES
        assert p.review_count >= MIN_REVIEWS
        assert p.phone
    scores = [p.score for p in providers]
    assert scores == sorted(scores, reverse=True)


def test_results_are_best_in_radius(conn):
    top = search_providers(conn, "plumbing", "60601")
    everyone = search_providers(conn, "plumbing", "60601", limit=1000)
    assert top == everyone[:TOP_N]
    assert all(p.score <= top[-1].score for p in everyone[TOP_N:])


def test_smaller_radius_is_subset(conn):
    near = search_providers(conn, "hvac", "60614", radius_miles=3, limit=1000)
    far = search_providers(conn, "hvac", "60614", radius_miles=25, limit=1000)
    assert near
    assert len(near) < len(far)
    assert {p.id for p in near} <= {p.id for p in far}
    assert all(p.distance_miles <= 3 for p in near)


def test_zip_plus_four(conn):
    assert search_providers(conn, "plumbing", "60601-1234") == search_providers(
        conn, "plumbing", "60601"
    )


def test_valid_zip_with_no_providers_nearby(conn):
    assert search_providers(conn, "plumbing", "90210") == []


def test_unknown_zip(conn):
    with pytest.raises(UnknownZipError):
        search_providers(conn, "plumbing", "00000")


def test_unknown_category(conn):
    with pytest.raises(UnknownCategoryError):
        search_providers(conn, "pool_cleaning", "60601")
