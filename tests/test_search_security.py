from __future__ import annotations

from src.connectors.search import scrape_public_page


class _RedirectResponse:
    status_code = 301
    headers: dict[str, str] = {"location": "https://example.org/"}
    text = "<html><body>Moved</body></html>"

    def raise_for_status(self) -> None:
        return None


def test_scrape_public_page_blocks_localhost_url() -> None:
    result = scrape_public_page("http://127.0.0.1:8080/admin")

    assert result["status"] == "blocked_url"


def test_scrape_public_page_blocks_link_local_metadata_url() -> None:
    result = scrape_public_page("http://169.254.169.254/latest/meta-data")

    assert result["status"] == "blocked_url"


def test_scrape_public_page_blocks_non_http_scheme() -> None:
    result = scrape_public_page("file:///etc/passwd")

    assert result["status"] == "blocked_url"


def test_scrape_public_page_blocks_malformed_url() -> None:
    result = scrape_public_page("http://[::1")

    assert result["status"] == "blocked_url"


def test_scrape_public_page_classifies_redirect_as_non_success(monkeypatch) -> None:
    monkeypatch.setattr("src.connectors.search._safe_public_url", lambda url: True)
    monkeypatch.setattr("src.connectors.search.requests.get", lambda *args, **kwargs: _RedirectResponse())

    result = scrape_public_page("https://example.org/")

    assert result["status"] == "redirect_blocked"
    assert result["text_excerpt"] == ""
