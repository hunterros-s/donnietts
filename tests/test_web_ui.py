def test_index_served(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "DonnieTTS" in response.text
    assert 'src="/app.js"' in response.text


def test_static_assets_served(client) -> None:
    assert client.get("/style.css").status_code == 200
    assert client.get("/app.js").status_code == 200


def test_api_routes_take_precedence_over_static_mount(client) -> None:
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    assert "announcements_enabled" in response.json()

    response = client.get("/api/v1/announcements")
    assert response.status_code == 200
    assert response.json() == []


def test_vendored_web_component_assets_served(client) -> None:
    assert client.get("/vendor/wa/styles/themes/default.css").status_code == 200
    for component in ("switch", "card", "badge", "callout", "divider"):
        response = client.get(f"/vendor/wa/components/{component}/{component}.js")
        assert response.status_code == 200, component
