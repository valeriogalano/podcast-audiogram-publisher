"""Tests for InstagramPlatform token expiry handling."""
from datetime import date, timedelta

import pytest

from publisher.platforms.instagram import _check_token_expiry


class TestCheckTokenExpiry:
    def test_accepts_iso_string(self):
        _check_token_expiry((date.today() + timedelta(days=30)).isoformat())

    def test_accepts_date_object(self):
        # YAML deserializza una data non quotata in datetime.date: prima
        # sollevava TypeError, che nessuno intercettava.
        _check_token_expiry(date.today() + timedelta(days=30))

    def test_raises_when_expired(self):
        expired = (date.today() - timedelta(days=1)).isoformat()
        with pytest.raises(RuntimeError, match="expired"):
            _check_token_expiry(expired)

    def test_raises_when_expired_as_date_object(self):
        with pytest.raises(RuntimeError, match="expired"):
            _check_token_expiry(date.today() - timedelta(days=1))

    def test_empty_value_is_skipped(self):
        _check_token_expiry("")

    def test_garbage_only_warns(self, caplog):
        _check_token_expiry("non-una-data")
        assert "not a valid ISO date" in caplog.text
