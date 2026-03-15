"""Tests for G-001: HMAC secret must not fall back to a default."""

from __future__ import annotations


import pytest


class TestHmacSecretFailClosed:
    def test_missing_hmac_secret_raises_runtime_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("AIS_RISK_HMAC_SECRET", raising=False)
        # Force module reload to clear any cached values
        from aiswarm.risk.limits import _hmac_secret

        with pytest.raises(RuntimeError, match="AIS_RISK_HMAC_SECRET"):
            _hmac_secret()

    def test_empty_hmac_secret_raises_runtime_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIS_RISK_HMAC_SECRET", "")
        from aiswarm.risk.limits import _hmac_secret

        with pytest.raises(RuntimeError, match="AIS_RISK_HMAC_SECRET"):
            _hmac_secret()

    def test_valid_hmac_secret_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AIS_RISK_HMAC_SECRET", "my-test-secret")
        from aiswarm.risk.limits import _hmac_secret

        assert _hmac_secret() == "my-test-secret"

    def test_sign_risk_token_requires_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AIS_RISK_HMAC_SECRET", raising=False)
        from aiswarm.risk.limits import sign_risk_token

        with pytest.raises(RuntimeError, match="AIS_RISK_HMAC_SECRET"):
            sign_risk_token("ord_test123")
