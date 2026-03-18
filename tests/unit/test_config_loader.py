"""Tests for utils.config.load_yaml."""

from __future__ import annotations

import pytest

from aiswarm.utils.config import load_yaml


class TestLoadYaml:
    """Tests for the load_yaml helper."""

    def test_loads_valid_yaml(self, tmp_path: object) -> None:
        f = tmp_path / "cfg.yaml"  # type: ignore[operator]
        f.write_text("key: value\nnested:\n  a: 1\n")
        result = load_yaml(f)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_empty_file_returns_empty_dict(self, tmp_path: object) -> None:
        f = tmp_path / "empty.yaml"  # type: ignore[operator]
        f.write_text("")
        assert load_yaml(f) == {}

    def test_non_dict_yaml_returns_empty_dict(self, tmp_path: object) -> None:
        f = tmp_path / "list.yaml"  # type: ignore[operator]
        f.write_text("- a\n- b\n")
        assert load_yaml(f) == {}

    def test_missing_file_raises(self, tmp_path: object) -> None:
        with pytest.raises(FileNotFoundError):
            load_yaml(tmp_path / "nope.yaml")  # type: ignore[operator]

    def test_accepts_string_path(self, tmp_path: object) -> None:
        f = tmp_path / "str.yaml"  # type: ignore[operator]
        f.write_text("x: 42\n")
        assert load_yaml(str(f)) == {"x": 42}
