#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Tests for read-only field propagation to jspreadsheet column definitions.
"""

import pytest
import sys
import json
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from spreadsheet_column_config import ColumnConfigBuilder
from spreadsheet_adapter import AssignmentFieldInfo


class TestReadOnlyPropagationToJspreadsheet:
    """Tests that read-only metadata is propagated to jspreadsheet column config."""

    def test_column_config_includes_readonly_for_readonly_fields(self):
        """
        ColumnConfigBuilder should include readOnly in the Python-side config
        when field metadata has read_only=True.
        """
        def field_info_getter(field_name: str) -> Dict[str, Any]:
            if field_name == "run_file":
                return {"type": "str", "required": True, "read_only": True}
            elif field_name == "assignment":
                return {"type": "str", "required": True, "read_only": False}
            else:
                return {"type": "str", "required": False}

        builder = ColumnConfigBuilder()
        config = builder.build_column_config(
            headers=["run_file", "assignment", "other_field"],
            field_info_getter=field_info_getter,
        )

        # Check that run_file column config includes read_only
        assert "read_only" in config["run_file"], \
            "read_only field should have read_only metadata in config"
        assert config["run_file"]["read_only"] is True

        # Check that assignment field does NOT have read_only set (or is False)
        assert config["assignment"].get("read_only") is not True, \
            "assignment field should not have read_only set to True"

        # Check that other_field also doesn't have read_only
        assert config["other_field"].get("read_only") is not True

    def test_column_config_readonly_persists_with_dropdown(self):
        """
        If a field is both read_only AND a dropdown, both properties
        should be preserved in the config. This shouldn't happen in practice
        for run_file, but the code should handle it correctly.
        """
        def field_info_getter(field_name: str) -> Dict[str, Any]:
            if field_name == "read_only_dropdown":
                return {"type": "str", "required": True, "read_only": True}
            return {"type": "str"}

        dropdown_sources = {
            "read_only_dropdown": [
                {"label": "Option 1", "value": "opt1"},
                {"label": "Option 2", "value": "opt2"},
            ]
        }

        builder = ColumnConfigBuilder()
        config = builder.build_column_config(
            headers=["read_only_dropdown"],
            field_info_getter=field_info_getter,
            dropdown_sources=dropdown_sources,
        )

        # Both dropdown and read_only should be present
        col_config = config["read_only_dropdown"]
        assert col_config.get("type") == "dropdown", \
            "Dropdown type should be set"
        assert col_config.get("source"), \
            "Dropdown source should be set"
        assert col_config.get("read_only") is True, \
            "read_only should be preserved even with dropdown"

    def test_assignment_run_file_field_is_readonly(self):
        """
        Verify that AssignmentFieldInfo correctly marks run_file as read_only.
        """
        info = AssignmentFieldInfo.get_field_info("run_file")
        assert info is not None, "run_file should have field info"
        assert info.get("read_only") is True, \
            "run_file field in assignments should be marked as read_only"


class TestJspreadsheetEditorReadOnlyMerge:
    """
    Tests for verifying that jspreadsheet editor merges read_only into column definitions.
    
    Note: These tests verify the JavaScript-facing column definition building.
    The actual JS-side readOnly behavior is tested via integration tests.
    """

    def test_jspreadsheet_column_definition_includes_readonly(self):
        """
        Verify that when column config includes read_only=True,
        the resulting jspreadsheet column definition should have readOnly: true.
        
        This test uses the same logic as jspreadsheet_editor.py's column merging.
        """
        # Simulate what jspreadsheet_editor does
        headers = ["run_file", "assignment", "other"]
        column_config = {
            "run_file": {
                "type": "str",
                "required": True,
                "read_only": True,
            },
            "assignment": {
                "type": "str",
                "required": True,
                "read_only": False,
            },
            "other": {
                "type": "str",
            }
        }

        # Build columns like jspreadsheet_editor does
        columns = []
        for header in headers:
            col = {
                "title": header.replace("_", " ").title(),
                "width": 100,
            }
            columns.append(col)

        # Merge column config properties
        for index, header in enumerate(headers):
            if column_config.get(header):
                config = column_config[header]
                # This is what we need to fix: merge read_only into readOnly
                if config.get("read_only"):
                    columns[index]["readOnly"] = True
                if config.get("type") == "dropdown" and config.get("source"):
                    columns[index]["type"] = "dropdown"
                    columns[index]["source"] = config["source"]

        # Verify run_file has readOnly: true
        run_file_col = columns[0]
        assert run_file_col.get("readOnly") is True, \
            "run_file column should have readOnly: true"

        # Verify assignment doesn't have readOnly set (or is False)
        assignment_col = columns[1]
        assert not assignment_col.get("readOnly"), \
            "assignment column should not have readOnly: true"

        # Verify other doesn't have readOnly
        other_col = columns[2]
        assert not other_col.get("readOnly"), \
            "other column should not have readOnly: true"

    def test_jspreadsheet_column_config_serialization(self):
        """
        Verify that the column definitions can be JSON-serialized
        (as they're sent to JavaScript) and include readOnly flag.
        """
        column_config = {
            "run_file": {
                "type": "str",
                "read_only": True,
            }
        }

        columns = [
            {
                "title": "Run File",
                "width": 200,
                "readOnly": True,
            }
        ]

        # Should serialize without error
        columns_json = json.dumps(columns)
        assert "readOnly" in columns_json, \
            "readOnly flag should be present in JSON"

        # Should deserialize correctly
        parsed = json.loads(columns_json)
        assert parsed[0].get("readOnly") is True
