import pytest

from app.callback import SSRFError, validate_callback_url


def test_ssrf_blocks_private_ips():
    """SSRF protection should block private/internal IPs when allow_private is False."""
    import os
    original = os.environ.get("CONSUMA_ALLOW_PRIVATE_CALLBACKS")
    os.environ["CONSUMA_ALLOW_PRIVATE_CALLBACKS"] = "false"

    # Reload settings to pick up new env
    from app.config import Settings
    settings = Settings()

    from unittest.mock import patch
    with patch("app.callback.settings", settings):
        with pytest.raises(SSRFError):
            validate_callback_url("http://127.0.0.1:8080/callback")

        with pytest.raises(SSRFError):
            validate_callback_url("http://10.0.0.1:8080/callback")

        with pytest.raises(SSRFError):
            validate_callback_url("http://192.168.1.1:8080/callback")

        with pytest.raises(SSRFError):
            validate_callback_url("http://172.16.0.1:8080/callback")

    # Restore
    if original is not None:
        os.environ["CONSUMA_ALLOW_PRIVATE_CALLBACKS"] = original
    else:
        os.environ.pop("CONSUMA_ALLOW_PRIVATE_CALLBACKS", None)


def test_ssrf_allows_private_when_configured():
    """With allow_private_callbacks=True, private IPs should be allowed."""
    # conftest sets CONSUMA_ALLOW_PRIVATE_CALLBACKS=true
    validate_callback_url("http://127.0.0.1:8080/callback")


def test_ssrf_rejects_invalid_scheme():
    with pytest.raises(SSRFError, match="Invalid scheme"):
        validate_callback_url("ftp://example.com/callback")

    with pytest.raises(SSRFError, match="Invalid scheme"):
        validate_callback_url("file:///etc/passwd")


def test_ssrf_rejects_no_hostname():
    with pytest.raises(SSRFError, match="No hostname"):
        validate_callback_url("http:///callback")
