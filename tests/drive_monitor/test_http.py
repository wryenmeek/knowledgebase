"""Unit tests for scripts/drive_monitor/_http.py.

Google API client libraries (``google-auth``, ``google-api-python-client``,
``httplib2``) are optional dependencies not present in the default test
environment.  All tests inject lightweight stub modules via ``sys.modules``
before importing the code-under-test so that no real library is required.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from scripts.drive_monitor._types import DriveAPIRequestError


# ---------------------------------------------------------------------------
# Stub module injection — runs once per module import
# ---------------------------------------------------------------------------

def _ensure_google_stubs() -> tuple[type, MagicMock]:
    """Inject stub ``google.*``, ``googleapiclient.*``, ``httplib2``, and
    ``google_auth_httplib2`` into ``sys.modules`` if they are not already
    importable.  Returns ``(HttpError_class, mock_service_account_module)``.

    The ``HttpError`` stub mirrors the real class's constructor signature
    (``resp``, ``content``) so that ``_with_retry`` can catch and inspect it.
    """
    # --- HttpError stub ---------------------------------------------------
    class _HttpError(Exception):
        def __init__(self, resp=None, content=b"", uri=""):
            self.resp = resp
            self.content = content
            self.uri = uri
            # reason used by _with_retry error messages
            self.reason = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
            super().__init__(self.reason)

    # googleapiclient hierarchy
    if "googleapiclient" not in sys.modules:
        pkg = types.ModuleType("googleapiclient")
        pkg.__path__ = []
        sys.modules["googleapiclient"] = pkg
    if "googleapiclient.errors" not in sys.modules:
        errors_mod = types.ModuleType("googleapiclient.errors")
        errors_mod.HttpError = _HttpError  # type: ignore[attr-defined]
        sys.modules["googleapiclient.errors"] = errors_mod
    if "googleapiclient.discovery" not in sys.modules:
        disc_mod = types.ModuleType("googleapiclient.discovery")
        disc_mod.build = MagicMock()  # type: ignore[attr-defined]
        sys.modules["googleapiclient.discovery"] = disc_mod
    if "googleapiclient.http" not in sys.modules:
        http_mod = types.ModuleType("googleapiclient.http")
        http_mod.MediaIoBaseDownload = MagicMock()  # type: ignore[attr-defined]
        sys.modules["googleapiclient.http"] = http_mod

    # google / google.oauth2 / google.oauth2.service_account
    if "google" not in sys.modules:
        g = types.ModuleType("google")
        g.__path__ = []
        sys.modules["google"] = g
    if "google.oauth2" not in sys.modules:
        g_oauth2 = types.ModuleType("google.oauth2")
        g_oauth2.__path__ = []
        sys.modules["google.oauth2"] = g_oauth2
    mock_sa = MagicMock()
    sa_mod = types.ModuleType("google.oauth2.service_account")
    sa_mod.Credentials = mock_sa  # type: ignore[attr-defined]
    sys.modules["google.oauth2.service_account"] = sa_mod

    # httplib2
    if "httplib2" not in sys.modules:
        h = types.ModuleType("httplib2")
        h.Http = MagicMock()  # type: ignore[attr-defined]
        sys.modules["httplib2"] = h

    # google_auth_httplib2
    if "google_auth_httplib2" not in sys.modules:
        gah = types.ModuleType("google_auth_httplib2")
        gah.AuthorizedHttp = MagicMock()  # type: ignore[attr-defined]
        sys.modules["google_auth_httplib2"] = gah

    HttpError = sys.modules["googleapiclient.errors"].HttpError  # type: ignore[attr-defined]
    return HttpError, mock_sa


# Inject stubs at import time so every test in this module can import _http
_HttpError, _mock_sa = _ensure_google_stubs()

# Force re-import of _http so it picks up the stubs
if "scripts.drive_monitor._http" in sys.modules:
    importlib.reload(sys.modules["scripts.drive_monitor._http"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_http_error(status: int, reason: str = "error", retry_after: str | None = None):
    """Build a stub ``HttpError`` instance with the given status code."""
    resp = MagicMock()
    resp.status = status
    header_store: dict[str, str] = {}
    if retry_after is not None:
        header_store["retry-after"] = retry_after
    resp.get = lambda key, default=None: header_store.get(key, default)
    return _HttpError(resp=resp, content=reason.encode())


# ---------------------------------------------------------------------------
# _with_retry tests
# ---------------------------------------------------------------------------


class TestWithRetrySuccess:
    """Successful call on first attempt — no retry needed."""

    def test_returns_immediately_on_success(self):
        from scripts.drive_monitor._http import _with_retry

        fn = MagicMock(return_value="ok")
        result = _with_retry(fn)
        assert result == "ok"
        fn.assert_called_once()


class TestWithRetryTransientRecovery:
    """Call fails with a transient 5xx, then succeeds on retry."""

    @patch("scripts.drive_monitor._http.time.sleep")
    def test_retries_on_5xx_then_succeeds(self, mock_sleep):
        from scripts.drive_monitor._http import _with_retry

        exc = _make_http_error(503, "Service Unavailable")
        fn = MagicMock(side_effect=[exc, "recovered"])

        result = _with_retry(fn)
        assert result == "recovered"
        assert fn.call_count == 2
        mock_sleep.assert_called_once()

    @patch("scripts.drive_monitor._http.time.sleep")
    def test_retries_on_429_then_succeeds(self, mock_sleep):
        from scripts.drive_monitor._http import _with_retry

        exc = _make_http_error(429, "Rate Limit")
        fn = MagicMock(side_effect=[exc, "ok"])

        result = _with_retry(fn)
        assert result == "ok"
        assert fn.call_count == 2


class TestWithRetryExhausted:
    """All retries fail — raises DriveAPIRequestError."""

    @patch("scripts.drive_monitor._http.time.sleep")
    def test_raises_after_all_retries_exhausted(self, mock_sleep):
        from scripts.drive_monitor._http import _with_retry, _MAX_RETRIES

        exc = _make_http_error(500, "Internal Server Error")
        fn = MagicMock(side_effect=exc)

        with pytest.raises(DriveAPIRequestError):
            _with_retry(fn)

        assert fn.call_count == _MAX_RETRIES


class TestRetryDelayBounds:
    """_RETRY_DELAYS index never causes IndexError."""

    @patch("scripts.drive_monitor._http.time.sleep")
    def test_delay_index_stays_in_bounds(self, mock_sleep):
        from scripts.drive_monitor._http import _with_retry, _RETRY_DELAYS, _MAX_RETRIES

        exc = _make_http_error(502, "Bad Gateway")
        fn = MagicMock(side_effect=exc)

        # The tuple must cover every retry attempt
        assert len(_RETRY_DELAYS) >= _MAX_RETRIES

        with pytest.raises(DriveAPIRequestError):
            _with_retry(fn)

        # Every sleep used a valid delay from the tuple
        for call in mock_sleep.call_args_list:
            delay_arg = call[0][0]
            assert delay_arg in _RETRY_DELAYS


class TestWithRetryPermanentError:
    """Non-retryable 4xx error fails immediately without retry."""

    def test_raises_immediately_on_400(self):
        from scripts.drive_monitor._http import _with_retry

        exc = _make_http_error(400, "Bad Request")
        fn = MagicMock(side_effect=exc)

        with pytest.raises(DriveAPIRequestError) as exc_info:
            _with_retry(fn)

        assert exc_info.value.status_code == 400
        fn.assert_called_once()


# ---------------------------------------------------------------------------
# Credential loading tests
# ---------------------------------------------------------------------------


class TestLoadCredentialsValueError:
    """ValueError from from_service_account_info is caught and re-raised
    with ``from None`` to prevent credential leakage."""

    @patch.dict(os.environ, {"GDRIVE_SA_KEY": '{"type": "bad"}'})
    def test_value_error_becomes_drive_api_request_error(self):
        from scripts.drive_monitor._http import _load_credentials

        sa_mod = sys.modules["google.oauth2.service_account"]
        sa_mod.Credentials.from_service_account_info.side_effect = ValueError(
            "bad key format"
        )
        try:
            with pytest.raises(DriveAPIRequestError) as exc_info:
                _load_credentials()

            # from None ⇒ __cause__ is None (no chained traceback)
            assert exc_info.value.__cause__ is None
        finally:
            sa_mod.Credentials.from_service_account_info.side_effect = None


class TestLoadCredentialsKeyError:
    """KeyError from from_service_account_info is caught and re-raised
    with ``from None``."""

    @patch.dict(os.environ, {"GDRIVE_SA_KEY": '{"type": "service_account"}'})
    def test_key_error_becomes_drive_api_request_error(self):
        from scripts.drive_monitor._http import _load_credentials

        sa_mod = sys.modules["google.oauth2.service_account"]
        sa_mod.Credentials.from_service_account_info.side_effect = KeyError(
            "client_email"
        )
        try:
            with pytest.raises(DriveAPIRequestError) as exc_info:
                _load_credentials()

            assert exc_info.value.__cause__ is None
        finally:
            sa_mod.Credentials.from_service_account_info.side_effect = None


class TestLoadCredentialsMissingEnvVar:
    """Missing env var produces a clear error before any credential loading."""

    def test_missing_env_var_raises(self):
        from scripts.drive_monitor._http import _load_credentials

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(DriveAPIRequestError, match="not set"):
                _load_credentials()


# ---------------------------------------------------------------------------
# Transport timeout test
# ---------------------------------------------------------------------------


class TestBuildDriveClientTimeout:
    """httplib2.Http(timeout=30) is applied when building the client."""

    @patch.dict(os.environ, {"GDRIVE_SA_KEY": '{"type": "service_account"}'})
    def test_httplib2_timeout_is_30(self):
        from scripts.drive_monitor._http import build_drive_client

        mock_creds = MagicMock()
        sa_mod = sys.modules["google.oauth2.service_account"]
        sa_mod.Credentials.from_service_account_info.side_effect = None
        sa_mod.Credentials.from_service_account_info.return_value = mock_creds

        mock_http_instance = MagicMock()
        httplib2_mod = sys.modules["httplib2"]
        httplib2_mod.Http = MagicMock(return_value=mock_http_instance)

        mock_authorized = MagicMock()
        gah_mod = sys.modules["google_auth_httplib2"]
        gah_mod.AuthorizedHttp = MagicMock(return_value=mock_authorized)

        mock_service = MagicMock()
        disc_mod = sys.modules["googleapiclient.discovery"]
        disc_mod.build = MagicMock(return_value=mock_service)

        result = build_drive_client()

        httplib2_mod.Http.assert_called_once_with(timeout=30)
        assert result is mock_service
