"""Contract tests: every adapter must expose a minimum valid configuration.

These tests verify that each adapter has non-empty selectors and strategies —
they don't need a real browser.  Catches regressions where a platform's selector
field is renamed or removed.
"""

import sys, os, inspect
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from adapters import ADAPTER_REGISTRY, BaseAdapter


# Which adapter classes to verify (exclude deprecated)
ACTIVE_ADAPTERS = ["chatgpt", "qianwen", "gemini", "kimi", "claude", "deepseek"]


def _get_adapter_cls(name: str):
    cls = ADAPTER_REGISTRY.get(name)
    if cls is None:
        raise pytest.skip(f"Adapter '{name}' not in registry")
    return cls


class TestAdapterContract:
    """Every active adapter must define the minimum interface."""

    def _check_required_attrs(self, cls, name: str):
        """Validate that *cls* has all required class-level attributes."""
        missing = []
        required = [
            "name", "URL", "EDITOR_SELECTOR", "SEND_SELECTOR",
            "STOP_SELECTOR", "RESPONSE_STRATEGIES",
        ]
        for attr in required:
            val = getattr(cls, attr, None)
            if not val and not isinstance(val, float):
                missing.append(attr)

        assert not missing, (
            f"Adapter '{name}' ({cls.__name__}) is missing required attributes: {missing}"
        )

    def _check_name_is_lowercase(self, cls, name: str):
        """P0 fix: adapter.name MUST be lowercase PlatformId."""
        adapter_name = cls.name
        assert adapter_name == adapter_name.lower(), (
            f"Adapter '{name}'.name='{adapter_name}' must be lowercase! "
            f"This was the P0 bug that broke tab rotation counters."
        )

    def _check_url_is_https(self, cls, name: str):
        """Adapters must use HTTPS URLs."""
        assert cls.URL.startswith("https://"), (
            f"Adapter '{name}' URL='{cls.URL}' must use HTTPS"
        )

    def _check_response_strategies_are_selectors(self, cls, name: str):
        """Response strategies must be non-empty CSS selectors."""
        assert len(cls.RESPONSE_STRATEGIES) > 0, (
            f"Adapter '{name}' has no RESPONSE_STRATEGIES"
        )
        for i, sel in enumerate(cls.RESPONSE_STRATEGIES):
            assert isinstance(sel, str) and len(sel) > 0, (
                f"Adapter '{name}' strategy #{i} is empty"
            )

    def test_all_active_adapters_have_minimum_contract(self):
        """Every adapter in ACTIVE_ADAPTERS passes all checks."""
        failures = []
        for name in ACTIVE_ADAPTERS:
            cls = _get_adapter_cls(name)
            try:
                self._check_required_attrs(cls, name)
                self._check_name_is_lowercase(cls, name)
                self._check_url_is_https(cls, name)
                self._check_response_strategies_are_selectors(cls, name)
            except AssertionError as e:
                failures.append(str(e))
        assert not failures, "\n".join(failures)

    def test_base_adapter_not_instantiable_as_worker(self):
        """BaseAdapter lacks selectors — shouldn't be used directly."""
        base = BaseAdapter()
        assert base.EDITOR_SELECTOR == ""
        assert base.RESPONSE_STRATEGIES == []


def test_registry_keys_are_lowercase():
    """P0 fix: ADAPTER_REGISTRY keys must be lowercase."""
    from common import PlatformId
    # doubao is deprecated — retained in registry for backward compat but
    # not an active platform.  Q3 AI review marked it for manual opt-in only.
    DEPRECATED = {"doubao"}
    for key in ADAPTER_REGISTRY:
        assert key == key.lower(), (
            f"ADAPTER_REGISTRY key '{key}' is not lowercase!"
        )
        if key not in DEPRECATED:
            assert PlatformId.is_valid(key), (
                f"ADAPTER_REGISTRY key '{key}' is not a valid PlatformId"
            )
