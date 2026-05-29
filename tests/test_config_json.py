"""Tests for config.json client loader."""

from app.config_json import load_clients, search_clients, suggest_clients_for_text


def test_load_clients():
    clients = load_clients()
    assert len(clients) > 0
    assert clients[0].client_name


def test_search_clients_by_abbrev():
    clients = load_clients()
    if not clients:
        return
    abbrev = clients[0].client_abbrev
    results = search_clients(abbrev)
    assert any(c.client_abbrev == abbrev for c in results)


def test_suggest_from_subject():
    results = suggest_clients_for_text("AAAIC schema approval STD705081")
    assert isinstance(results, list)
