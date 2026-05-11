#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Tests for dropdown filter_mode configuration (prefix, substring, fuzzy).
"""

import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent))

from spreadsheet_column_config import ColumnConfigBuilder


class TestDropdownFilterMode:
    """Tests for filter_mode propagation in dropdown column configs."""

    def test_default_filter_mode_is_prefix(self):
        """Dropdown columns get filter_mode='prefix' by default."""
        dropdown_sources = {
            "instrument": [
                {"label": "Q-TOF", "value": "Q-TOF"},
                {"label": "Orbitrap", "value": "Orbitrap"},
            ]
        }

        builder = ColumnConfigBuilder()
        config = builder.build_column_config(
            headers=["instrument"],
            dropdown_sources=dropdown_sources,
        )

        assert config["instrument"]["type"] == "dropdown"
        assert config["instrument"]["filter_mode"] == "prefix"

    def test_filter_mode_overridden_via_constructor(self):
        """filter_modes dict in constructor overrides the default."""
        dropdown_sources = {
            "instrument": [
                {"label": "Q-TOF", "value": "Q-TOF"},
            ]
        }

        builder = ColumnConfigBuilder(filter_modes={"instrument": "substring"})
        config = builder.build_column_config(
            headers=["instrument"],
            dropdown_sources=dropdown_sources,
        )

        assert config["instrument"]["filter_mode"] == "substring"

    def test_fuzzy_filter_mode(self):
        """Fuzzy filter mode can be set per column."""
        dropdown_sources = {
            "organism": [
                {"label": "Homo sapiens", "value": "homo_sapiens"},
            ]
        }

        builder = ColumnConfigBuilder(filter_modes={"organism": "fuzzy"})
        config = builder.build_column_config(
            headers=["organism"],
            dropdown_sources=dropdown_sources,
        )

        assert config["organism"]["filter_mode"] == "fuzzy"

    def test_non_dropdown_columns_have_no_filter_mode(self):
        """Non-dropdown columns should not get a filter_mode key."""
        builder = ColumnConfigBuilder()
        config = builder.build_column_config(
            headers=["file", "fraction"],
            field_info_getter=lambda f: {"type": "str", "required": False},
        )

        assert "filter_mode" not in config["file"]
        assert "filter_mode" not in config["fraction"]

    def test_ontology_backed_dropdown_gets_filter_mode(self):
        """Ontology-backed dropdowns (e.g., instrument) also get filter_mode."""
        builder = ColumnConfigBuilder()
        config = builder.build_column_config(
            headers=["instrument"],
            field_info_getter=lambda f: {"type": "str", "required": False},
        )

        # instrument is in DROPDOWN_FIELD_MAPPING, so it becomes a dropdown
        if config["instrument"].get("type") == "dropdown":
            assert "filter_mode" in config["instrument"]
            assert config["instrument"]["filter_mode"] == "prefix"

    def test_multiple_columns_different_modes(self):
        """Different columns can have different filter modes."""
        dropdown_sources = {
            "instrument": [{"label": "Q-TOF", "value": "Q-TOF"}],
            "organism": [{"label": "Homo sapiens", "value": "homo_sapiens"}],
            "tissue": [{"label": "Brain", "value": "brain"}],
        }

        builder = ColumnConfigBuilder(
            filter_modes={
                "instrument": "prefix",
                "organism": "fuzzy",
                "tissue": "substring",
            }
        )
        config = builder.build_column_config(
            headers=["instrument", "organism", "tissue"],
            dropdown_sources=dropdown_sources,
        )

        assert config["instrument"]["filter_mode"] == "prefix"
        assert config["organism"]["filter_mode"] == "fuzzy"
        assert config["tissue"]["filter_mode"] == "substring"

    def test_class_level_dropdown_filter_mode_used_as_default(self):
        """DROPDOWN_FILTER_MODE class attribute provides defaults."""

        class CustomBuilder(ColumnConfigBuilder):
            DROPDOWN_FILTER_MODE = {"instrument": "substring"}

        dropdown_sources = {
            "instrument": [{"label": "Q-TOF", "value": "Q-TOF"}],
        }

        builder = CustomBuilder()
        config = builder.build_column_config(
            headers=["instrument"],
            dropdown_sources=dropdown_sources,
        )

        assert config["instrument"]["filter_mode"] == "substring"

    def test_constructor_filter_modes_override_class_level(self):
        """Constructor filter_modes take priority over class-level defaults."""

        class CustomBuilder(ColumnConfigBuilder):
            DROPDOWN_FILTER_MODE = {"instrument": "substring"}

        dropdown_sources = {
            "instrument": [{"label": "Q-TOF", "value": "Q-TOF"}],
        }

        builder = CustomBuilder(filter_modes={"instrument": "fuzzy"})
        config = builder.build_column_config(
            headers=["instrument"],
            dropdown_sources=dropdown_sources,
        )

        assert config["instrument"]["filter_mode"] == "fuzzy"
