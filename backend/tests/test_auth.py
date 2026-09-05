"""Phase 1 acceptance: register, log in, set language, stay logged in."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.security import create_access_token, hash_password, verify_password

SIGNUP = {
    "email": "Ana@Example.com",
    "password": "a-long-enough-password",
    "display_name": "Ana",
    "preferred_language": "Spanish",
    "goal": "Stop hanging pieces",
}


def test_password_hashing_roundtrip() -> None:
    digest = hash_password("a-long-enough-password")
    assert digest != "a-long-enough-password"
    assert verify_password("a-long-enough-password", digest)
    assert not verify_password("wrong", digest)


def test_signup_returns_token_and_normalises_email(client: TestClient) -> None:
    res = client.post("/api/auth/signup", json=SIGNUP)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "ana@example.com"
    assert body["user"]["preferred_language"] == "Spanish"
    assert body["user"]["current_rating_estimate"] == 1000
    assert body["user"]["assessment_completed"] is False


def test_duplicate_email_is_rejected(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    res = client.post("/api/auth/signup", json=SIGNUP)
    assert res.status_code == 409


def test_short_password_is_rejected(client: TestClient) -> None:
    res = client.post("/api/auth/signup", json={**SIGNUP, "password": "short"})
    assert res.status_code == 422


def test_login_and_stay_logged_in(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    res = client.post("/api/auth/login", json={"email": "ana@example.com", "password": SIGNUP["password"]})
    assert res.status_code == 200
    token = res.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["display_name"] == "Ana"


def test_login_with_wrong_password_is_401(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    res = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "nope-nope-nope"})
    assert res.status_code == 401
    assert "Incorrect email or password" in res.json()["detail"]


def test_me_requires_a_valid_token(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_expired_token_is_rejected(client: TestClient) -> None:
    client.post("/api/auth/signup", json=SIGNUP)
    expired = create_access_token(1, expires_minutes=-5)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_profile_update_changes_language_and_goal(auth_client: TestClient) -> None:
    res = auth_client.patch("/api/auth/me", json={"preferred_language": "Hindi", "goal": "Win the school event"})
    assert res.status_code == 200
    assert res.json()["preferred_language"] == "Hindi"
    assert res.json()["goal"] == "Win the school event"
    assert auth_client.get("/api/auth/me").json()["preferred_language"] == "Hindi"


def test_languages_endpoint_lists_options(client: TestClient) -> None:
    langs = client.get("/api/auth/languages").json()
    assert "English" in langs and "Tamil" in langs and len(langs) > 10


def test_rate_limiter_counts_and_expires() -> None:
    """The in-memory fallback must expire counters, or a Redis-less deploy locks users out."""
    import time

    from app.core.cache import Cache

    cache = Cache(url="redis://127.0.0.1:6399/0")  # unreachable: forces the memory backend
    assert cache.backend == "memory"
    assert cache.incr_with_ttl("k", 1) == 1
    assert cache.incr_with_ttl("k", 1) == 2
    time.sleep(1.1)
    assert cache.incr_with_ttl("k", 1) == 1


def test_signup_rate_limit_eventually_rejects(client: TestClient) -> None:
    for index in range(10):
        res = client.post("/api/auth/signup", json={**SIGNUP, "email": f"user{index}@example.com"})
        assert res.status_code == 201, res.text
    blocked = client.post("/api/auth/signup", json={**SIGNUP, "email": "one-too-many@example.com"})
    assert blocked.status_code == 429


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    """A failure the learner reports has to be findable in the logs."""
    res = client.get("/api/health")
    assert res.headers.get("X-Request-ID")


def test_an_unhandled_error_returns_a_traceable_message(client: TestClient) -> None:
    from app.main import app

    @app.get("/api/_boom_for_tests")
    def boom() -> None:  # pragma: no cover - exercised through the client
        raise RuntimeError("deliberate failure")

    with TestClient(app, raise_server_exceptions=False) as fresh:
        res = fresh.get("/api/_boom_for_tests")
    assert res.status_code == 500
    body = res.json()
    assert body["request_id"]
    assert "deliberate failure" not in body["detail"], "internal errors must not leak to the client"
