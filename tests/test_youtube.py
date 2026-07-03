"""Tests for YouTube OAuth credential handling."""
from unittest.mock import MagicMock, patch

import pytest

from publisher.platforms.youtube import _get_credentials, _is_interactive


class TestIsInteractive:
    def test_tty_without_ci_is_interactive(self):
        with patch("sys.stdin.isatty", return_value=True), \
             patch.dict("os.environ", {}, clear=True):
            assert _is_interactive() is True

    def test_ci_env_var_forces_non_interactive(self):
        with patch("sys.stdin.isatty", return_value=True), \
             patch.dict("os.environ", {"CI": "true"}):
            assert _is_interactive() is False

    def test_no_tty_is_non_interactive(self):
        with patch("sys.stdin.isatty", return_value=False), \
             patch.dict("os.environ", {}, clear=True):
            assert _is_interactive() is False


class TestGetCredentialsFastFail:
    def test_missing_token_raises_immediately_in_ci(self, tmp_path):
        token_path = tmp_path / "token.json"
        with patch.dict("os.environ", {"CI": "true"}):
            with pytest.raises(RuntimeError, match="no interactive terminal"):
                _get_credentials("secrets.json", str(token_path))
        assert not token_path.exists()

    def test_expired_token_with_failed_refresh_raises_in_ci(self, tmp_path):
        token_path = tmp_path / "token.json"
        token_path.write_text("{}")

        creds = MagicMock()
        creds.scopes = [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
        ]
        creds.valid = False
        creds.expired = True
        creds.refresh_token = "refresh-tok"
        creds.refresh.side_effect = Exception("token revoked")

        with patch(
            "google.oauth2.credentials.Credentials.from_authorized_user_file",
            return_value=creds,
        ), patch.dict("os.environ", {"CI": "true"}):
            with pytest.raises(RuntimeError, match="no interactive terminal"):
                _get_credentials("secrets.json", str(token_path))

    def test_interactive_flow_runs_locally_when_not_ci(self, tmp_path):
        token_path = tmp_path / "token.json"

        new_creds = MagicMock()
        new_creds.to_json.return_value = "{}"

        flow = MagicMock()
        flow.run_local_server.return_value = new_creds

        with patch(
            "google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file",
            return_value=flow,
        ), patch("sys.stdin.isatty", return_value=True), \
             patch.dict("os.environ", {}, clear=True):
            creds = _get_credentials("secrets.json", str(token_path))

        assert creds is new_creds
        flow.run_local_server.assert_called_once_with(port=0)
        assert token_path.exists()
