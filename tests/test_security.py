import pytest
from fastapi.testclient import TestClient

from app import main, security


@pytest.fixture(autouse=True)
def _reset_limiter(monkeypatch):
    security.reset()
    monkeypatch.setattr(main.asyncio, "sleep", lambda s: _noop())
    yield
    security.reset()


async def _noop():
    return None


def _login(c, password="test-password"):
    return c.post("/login", data={"password": password}, follow_redirects=False)


def test_lockout_after_five_wrong_passwords():
    c = TestClient(main.app)
    for _ in range(security.MAX_FAILURES):
        assert _login(c, "wrong").status_code == 401
    r = _login(c)  # even the right password waits until the lock ends
    assert r.status_code == 429
    assert "Too many wrong passwords" in r.text
    security.reset()
    assert _login(c).status_code == 303


def test_success_clears_failures():
    c = TestClient(main.app)
    for _ in range(security.MAX_FAILURES - 1):
        _login(c, "wrong")
    assert _login(c).status_code == 303
    for _ in range(security.MAX_FAILURES - 1):
        assert _login(c, "wrong").status_code == 401


def test_sign_out_everywhere_ends_other_sessions():
    a, b = TestClient(main.app), TestClient(main.app)
    assert _login(a).status_code == 303 and _login(b).status_code == 303
    assert b.get("/settings", follow_redirects=False).status_code == 200
    assert a.post("/logout-everywhere", follow_redirects=False).status_code == 303
    assert b.get("/settings", follow_redirects=False).headers["location"] == "/login"
    assert a.get("/settings", follow_redirects=False).headers["location"] == "/login"
    assert _login(b).status_code == 303
    assert b.get("/settings", follow_redirects=False).status_code == 200


def test_api_docs_are_off():
    c = TestClient(main.app)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(path).status_code == 404


def test_security_headers():
    r = TestClient(main.app).get("/login")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "same-origin"


def test_cross_site_post_is_refused(client):
    r = client.post("/logout-everywhere", headers={"Origin": "https://evil.example"}, follow_redirects=False)
    assert r.status_code == 403
    assert client.get("/settings", follow_redirects=False).status_code == 200
    r = client.post("/settings", data={"language": "en"}, headers={"Origin": "http://testserver"},
                    follow_redirects=False)
    assert r.status_code == 303


def test_same_origin_helper():
    assert security.same_origin(None, "a.example")
    assert security.same_origin("https://a.example", "a.example")
    assert not security.same_origin("https://b.example", "a.example")
    assert not security.same_origin("null", "a.example")
