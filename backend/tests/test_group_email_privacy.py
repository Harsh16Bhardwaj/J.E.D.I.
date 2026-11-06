# ruff: noqa: F401, F811

from backend.tests.test_product_api import login, product_client


def test_group_names_and_email_owner_boundary(product_client):
    assert product_client.get("/api/group").status_code == 401
    assert product_client.get("/api/email/recipients").status_code == 401
    login(product_client)
    assert product_client.patch(
        "/api/group/display-name", json={"displayName": "  Group Owner  "}
    ).json() == {"displayName": "Group Owner"}
    assert (
        product_client.patch(
            "/api/group/display-name", json={"displayName": "owner@example.com"}
        ).status_code
        == 422
    )
    assert product_client.get("/api/email/recipients").status_code == 200
    owner_roster = product_client.get("/api/group").json()
    assert owner_roster["myDisplayName"] == "Group Owner"
    assert all("email" not in row for row in owner_roster["members"])

    response = product_client.post(
        "/api/auth/login",
        json={"email": "friend@example.com", "password": "friend password"},
    )
    assert response.status_code == 200
    roster = product_client.get("/api/group").json()
    assert roster["myDisplayName"] is None
    assert {row["displayName"] for row in roster["members"]} == {"Group Owner", None}
    assert all("email" not in row for row in roster["members"])
    assert (
        product_client.patch(
            "/api/group/display-name", json={"displayName": "A Member"}
        ).status_code
        == 200
    )
    assert (
        product_client.get("/api/auth/session").json()["email"] == "friend@example.com"
    )
    for method, path in [
        ("GET", "/api/email/settings"),
        ("PATCH", "/api/email/settings"),
        ("GET", "/api/email/recipients"),
        ("GET", "/api/email/recipients/unknown"),
        ("POST", "/api/email/recipients"),
        ("PATCH", "/api/email/recipients/unknown"),
        ("DELETE", "/api/email/recipients/unknown"),
        ("GET", "/api/email/events"),
        ("POST", "/api/email/manual-dispatch"),
        ("POST", "/api/batches/unknown/email-digest"),
        ("GET", "/api/batches/unknown/email-deliveries"),
    ]:
        assert product_client.request(method, path, json={}).status_code == 403, path
