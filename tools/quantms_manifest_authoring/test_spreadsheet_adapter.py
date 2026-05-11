#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Test suite for the spreadsheet adapter contract.

Tests the translation between WizardState run rows and spreadsheet rows,
and synchronization of edits back to wizard state.
"""

import pytest
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from spreadsheet_adapter import (
    SpreadsheetAdapter,
    SpreadsheetRow,
    RunFieldInfo,
)


class TestRunFieldInfo:
    """Tests for RunFieldInfo metadata about columns."""

    def test_run_field_info_has_all_standard_fields(self):
        """Test that RunFieldInfo provides all standard run fields for the spreadsheet."""
        fields = RunFieldInfo.get_all_fields()
        assert "file" in fields
        assert "fraction" in fields
        assert "instrument" in fields
        # Sample and mixture are not in spreadsheet schema

    def test_run_field_info_file_is_required(self):
        """Test that file field is marked as required."""
        field_info = RunFieldInfo.get_field_info("file")
        assert field_info["required"] is True

    def test_run_field_info_optional_fields_not_required(self):
        """Test that optional run fields are not required in spreadsheet."""
        for field in ["fraction", "instrument"]:
            field_info = RunFieldInfo.get_field_info(field)
            assert field_info["required"] is False

    def test_run_field_info_fraction_is_integer_type(self):
        """Test that fraction field has integer type."""
        field_info = RunFieldInfo.get_field_info("fraction")
        assert field_info["type"] == "int"

    def test_run_field_info_file_is_string_type(self):
        """Test that file field has string type."""
        field_info = RunFieldInfo.get_field_info("file")
        assert field_info["type"] == "str"


class TestSpreadsheetRow:
    """Tests for SpreadsheetRow data structure."""

    def test_spreadsheet_row_creation_from_wizard_run(self):
        """Test creating a spreadsheet row from a wizard run dict."""
        run = {
            "file": "/data/sample1.raw",
            "fraction": 1,
        }
        row = SpreadsheetRow.from_wizard_run(run, row_index=0)
        assert row.file == "/data/sample1.raw"
        assert row.fraction == 1
        assert row.instrument is None

    def test_spreadsheet_row_with_all_fields(self):
        """Test spreadsheet row with all fields filled."""
        run = {
            "file": "/data/sample1.raw",
            "fraction": 2,
            "instrument": "Q Exactive",
        }
        row = SpreadsheetRow.from_wizard_run(run, row_index=0)
        assert row.file == "/data/sample1.raw"
        assert row.fraction == 2
        assert row.instrument == "Q Exactive"

    def test_spreadsheet_row_to_dict(self):
        """Test converting spreadsheet row back to dict."""
        original = {
            "file": "test.raw",
            "fraction": 1,
        }
        row = SpreadsheetRow.from_wizard_run(original, row_index=0)
        result = row.to_dict()
        assert result["file"] == "test.raw"
        assert result["fraction"] == 1

    def test_spreadsheet_row_to_dict_excludes_none_values(self):
        """Test that to_dict strictly excludes None values."""
        run = {
            "file": "test.raw",
            "fraction": None,
            "instrument": None,
        }
        row = SpreadsheetRow.from_wizard_run(run, row_index=0)
        result = row.to_dict()
        assert "file" in result
        assert result["file"] == "test.raw"
        # Must not have these keys at all
        assert "fraction" not in result
        assert "instrument" not in result

    def test_spreadsheet_row_update(self):
        """Test updating spreadsheet row fields."""
        row = SpreadsheetRow.from_wizard_run({"file": "test.raw"}, row_index=0)
        row.update(file="new.raw", fraction=2)
        assert row.file == "new.raw"
        assert row.fraction == 2


class TestSpreadsheetAdapterBasics:
    """Tests for basic spreadsheet adapter functionality."""

    def test_adapter_initialization(self):
        """Test creating a spreadsheet adapter."""
        wizard = WizardState()
        adapter = SpreadsheetAdapter(wizard)
        assert adapter.wizard is wizard

    def test_adapter_convert_empty_wizard_to_rows(self):
        """Test converting empty wizard to spreadsheet rows."""
        wizard = WizardState()
        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()
        assert rows == []

    def test_adapter_convert_single_run_to_row(self):
        """Test converting single wizard run to spreadsheet row."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        assert len(rows) == 1
        assert rows[0].file == "/data/sample1.raw"
        assert rows[0].fraction == 1

    def test_adapter_convert_multiple_runs_to_rows(self):
        """Test converting multiple wizard runs to spreadsheet rows."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)
        wizard.add_run(file="/data/sample2.raw", fraction=2, instrument="Orbitrap")
        wizard.add_run(file="/data/sample3.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        assert len(rows) == 3
        assert rows[0].file == "/data/sample1.raw"
        assert rows[0].fraction == 1
        assert rows[1].file == "/data/sample2.raw"
        assert rows[1].fraction == 2
        assert rows[1].instrument == "Orbitrap"
        assert rows[2].file == "/data/sample3.raw"
        assert rows[2].fraction is None

    def test_adapter_convert_row_to_wizard_run(self):
        """Test converting single spreadsheet row to wizard run dict."""
        adapter = SpreadsheetAdapter(WizardState())
        row = SpreadsheetRow(
            file="/data/sample1.raw",
            fraction=1,
            instrument=None,
            row_index=0,
        )
        result = adapter.spreadsheet_row_to_wizard_run(row)
        assert result["file"] == "/data/sample1.raw"
        assert result["fraction"] == 1
        assert "instrument" not in result


class TestSpreadsheetAdapterSyncEdits:
    """Tests for syncing spreadsheet edits back to wizard state."""

    def test_adapter_update_single_run(self):
        """Test updating a single run via adapter."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)

        adapter = SpreadsheetAdapter(wizard)

        # Modify the spreadsheet row
        rows = adapter.wizard_to_spreadsheet()
        rows[0].file = "/data/new_file.raw"
        rows[0].fraction = 2

        # Sync back to wizard
        adapter.spreadsheet_to_wizard(rows)

        # Verify wizard was updated
        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "/data/new_file.raw"
        assert wizard.runs[0]["fraction"] == 2

    def test_adapter_add_field_to_existing_run(self):
        """Test adding a field to an existing run."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)

        # Get rows and add fraction and instrument
        rows = adapter.wizard_to_spreadsheet()
        rows[0].instrument = "Q Exactive"
        rows[0].fraction = 1

        # Sync back
        adapter.spreadsheet_to_wizard(rows)

        # Verify
        assert wizard.runs[0]["instrument"] == "Q Exactive"
        assert wizard.runs[0]["fraction"] == 1

    def test_adapter_remove_field_from_run(self):
        """Test removing a field from a run."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", instrument="Q Exactive", fraction=1)

        adapter = SpreadsheetAdapter(wizard)

        # Get rows and clear the instrument field
        rows = adapter.wizard_to_spreadsheet()
        rows[0].instrument = None

        # Sync back
        adapter.spreadsheet_to_wizard(rows)

        # Verify
        assert "instrument" not in wizard.runs[0]
        assert wizard.runs[0]["fraction"] == 1  # Not affected

    def test_adapter_update_multiple_runs(self):
        """Test updating multiple runs simultaneously."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)
        wizard.add_run(file="/data/sample2.raw", fraction=2)
        wizard.add_run(file="/data/sample3.raw", fraction=3)

        adapter = SpreadsheetAdapter(wizard)

        # Modify multiple rows
        rows = adapter.wizard_to_spreadsheet()
        rows[0].instrument = "Q Exactive"
        rows[1].instrument = "Orbitrap"
        rows[2].fraction = 5

        # Sync back
        adapter.spreadsheet_to_wizard(rows)

        # Verify
        assert wizard.runs[0]["instrument"] == "Q Exactive"
        assert wizard.runs[1]["instrument"] == "Orbitrap"
        assert wizard.runs[2]["fraction"] == 5

    def test_adapter_sync_with_row_deletion_raises_error(self):
        """Test that syncing with fewer rows raises an error (prevent accidental deletions)."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")
        wizard.add_run(file="/data/sample2.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        # Remove a row in the spreadsheet
        rows = rows[:1]

        # Attempt to sync should raise an error
        with pytest.raises(ValueError, match="row count"):
            adapter.spreadsheet_to_wizard(rows)

    def test_adapter_sync_missing_required_field_raises_error(self):
        """Test that syncing a row missing required field raises error."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        # Remove the required file field
        rows[0].file = None

        # Should raise validation error
        with pytest.raises(ValueError, match="file|required"):
            adapter.spreadsheet_to_wizard(rows)

    def test_adapter_maintains_wizard_as_source_of_truth(self):
        """Test that wizard state remains authoritative on sync."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)

        # Convert to spreadsheet
        rows = adapter.wizard_to_spreadsheet()
        assert rows[0].file == "/data/sample1.raw"

        # Change wizard directly
        wizard.update_run(0, file="/data/new.raw")

        # Convert again - should reflect the wizard's state
        rows2 = adapter.wizard_to_spreadsheet()
        assert rows2[0].file == "/data/new.raw"

    def test_adapter_sync_preserves_unmodified_fields(self):
        """Test that syncing preserves fields not explicitly set."""
        wizard = WizardState()
        wizard.add_run(
            file="/data/sample1.raw",
            sample="s1",
            instrument="Q Exactive",
            fraction=1,
        )

        adapter = SpreadsheetAdapter(wizard)

        # Get rows and modify only the fraction
        rows = adapter.wizard_to_spreadsheet()
        rows[0].fraction = 2

        # Sync back
        adapter.spreadsheet_to_wizard(rows)

        # Verify that unmodified fields are still there
        assert wizard.runs[0]["file"] == "/data/sample1.raw"
        assert wizard.runs[0]["sample"] == "s1"
        assert wizard.runs[0]["instrument"] == "Q Exactive"
        assert wizard.runs[0]["fraction"] == 2

    def test_adapter_column_order_is_predictable(self):
        """Test that spreadsheet columns have a consistent, predictable order."""
        adapter = SpreadsheetAdapter(WizardState())
        columns = adapter.get_column_headers()

        # Should be ordered logically (run-level fields only)
        assert columns[0] == "file"
        assert "fraction" in columns
        assert "instrument" in columns
        # file must be first, order of others should be consistent
        assert columns.index("file") == 0
        assert columns == ["file", "fraction", "instrument"]


class TestSpreadsheetAdapterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_adapter_handles_row_with_only_file(self):
        """Test that adapter handles row with only required file field."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        # Should have exactly 1 row with only file set
        assert len(rows) == 1
        assert rows[0].file == "/data/sample1.raw"
        assert rows[0].fraction is None
        assert rows[0].instrument is None

    def test_adapter_handles_empty_string_as_none(self):
        """Test that empty strings are treated as None for optional fields."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        # Set empty strings
        rows[0].fraction = ""
        rows[0].instrument = ""

        # Sync
        adapter.spreadsheet_to_wizard(rows)

        # Empty strings should not be added to wizard - keys should not exist
        result = wizard.runs[0]
        assert "fraction" not in result
        assert "instrument" not in result

    def test_adapter_coerces_fraction_to_int(self):
        """Test that fraction is coerced to int."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        # Set fraction as string (from CSV/spreadsheet)
        rows[0].fraction = "2"

        # Sync
        adapter.spreadsheet_to_wizard(rows)

        # Should be converted to int
        assert wizard.runs[0]["fraction"] == 2
        assert isinstance(wizard.runs[0]["fraction"], int)

    def test_adapter_handles_s3_paths(self):
        """Test that adapter handles S3 paths correctly."""
        wizard = WizardState()
        wizard.add_run(file="s3://bucket/sample1.raw")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_to_spreadsheet()

        assert rows[0].file == "s3://bucket/sample1.raw"

        # Modify
        rows[0].fraction = 1

        # Sync
        adapter.spreadsheet_to_wizard(rows)

        assert wizard.runs[0]["file"] == "s3://bucket/sample1.raw"
        assert wizard.runs[0]["fraction"] == 1


class TestDragCopyFillDown:
    """Tests for copy_field_down (spreadsheet drag-copy groundwork)."""

    def test_copy_field_down_basic(self):
        """Test copying a field value down from one row to subsequent rows."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1)
        wizard.add_run(file="/data/s2.raw", fraction=2)
        wizard.add_run(file="/data/s3.raw", fraction=3)

        adapter = SpreadsheetAdapter(wizard)

        # Copy fraction from row 0 to rows 1 and 2
        adapter.copy_field_down("fraction", from_row_index=0, to_row_index=2)

        # Verify
        assert wizard.runs[0]["fraction"] == 1
        assert wizard.runs[1]["fraction"] == 1
        assert wizard.runs[2]["fraction"] == 1

    def test_copy_field_down_partial_range(self):
        """Test copying field to a specific range."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", instrument="Q Exactive")
        wizard.add_run(file="/data/s2.raw")
        wizard.add_run(file="/data/s3.raw")
        wizard.add_run(file="/data/s4.raw")

        adapter = SpreadsheetAdapter(wizard)

        # Copy instrument from row 0 to rows 1-2 only
        adapter.copy_field_down("instrument", from_row_index=0, to_row_index=2)

        # Verify
        assert wizard.runs[0]["instrument"] == "Q Exactive"
        assert wizard.runs[1]["instrument"] == "Q Exactive"
        assert wizard.runs[2]["instrument"] == "Q Exactive"
        assert "instrument" not in wizard.runs[3]  # Row 3 untouched

    def test_copy_field_down_to_end_implicit(self):
        """Test that to_row_index=None copies to end of rows."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", instrument="Q Exactive")
        wizard.add_run(file="/data/s2.raw")
        wizard.add_run(file="/data/s3.raw")

        adapter = SpreadsheetAdapter(wizard)

        # Copy instrument from row 0 to end (None = last row)
        adapter.copy_field_down("instrument", from_row_index=0, to_row_index=None)

        # Verify
        assert wizard.runs[0]["instrument"] == "Q Exactive"
        assert wizard.runs[1]["instrument"] == "Q Exactive"
        assert wizard.runs[2]["instrument"] == "Q Exactive"

    def test_copy_field_down_with_none_value_clears_target(self):
        """Test that copying None value clears field in target rows."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw", fraction=2)
        wizard.add_run(file="/data/s3.raw", fraction=3)

        adapter = SpreadsheetAdapter(wizard)

        # Copy None fraction from row 0 to rows 1-2
        adapter.copy_field_down("fraction", from_row_index=0, to_row_index=2)

        # Verify that fraction was removed
        assert "fraction" not in wizard.runs[0]
        assert "fraction" not in wizard.runs[1]
        assert "fraction" not in wizard.runs[2]

    def test_copy_field_down_invalid_field_raises_error(self):
        """Test that copying invalid field raises ValueError."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw")

        adapter = SpreadsheetAdapter(wizard)

        with pytest.raises(ValueError, match="Unknown field"):
            adapter.copy_field_down("invalid_field", from_row_index=0, to_row_index=1)

    def test_copy_field_down_invalid_range_raises_error(self):
        """Test that invalid row ranges raise ValueError."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw")

        adapter = SpreadsheetAdapter(wizard)

        # to_row_index < from_row_index
        with pytest.raises(ValueError, match="must be >="):
            adapter.copy_field_down("fraction", from_row_index=1, to_row_index=0)

        # from_row_index out of range
        with pytest.raises(ValueError, match="out of range"):
            adapter.copy_field_down("fraction", from_row_index=5, to_row_index=1)

        # to_row_index out of range
        with pytest.raises(ValueError, match="out of range"):
            adapter.copy_field_down("fraction", from_row_index=0, to_row_index=5)

    def test_copy_field_down_single_row_no_op(self):
        """Test that copying within same row (no dest rows) doesn't fail."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1)
        wizard.add_run(file="/data/s2.raw")

        adapter = SpreadsheetAdapter(wizard)

        # Copy fraction from row 0 to row 0 (should be no-op, no rows after it)
        # Actually this is technically a no-op since from_row_index+1 > to_row_index
        adapter.copy_field_down("fraction", from_row_index=0, to_row_index=0)

        # Verify original row unchanged (and s2 unchanged)
        assert wizard.runs[0]["fraction"] == 1
        assert "fraction" not in wizard.runs[1]

    def test_copy_field_down_respects_wizard_authority(self):
        """Test that copy_field_down updates wizard state only."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1)
        wizard.add_run(file="/data/s2.raw", fraction=2)

        adapter = SpreadsheetAdapter(wizard)

        # Copy fraction from row 0 to row 1
        adapter.copy_field_down("fraction", from_row_index=0, to_row_index=1)

        # Verify in wizard
        assert wizard.runs[0]["fraction"] == 1
        assert wizard.runs[1]["fraction"] == 1

        # Verify adapter reflects wizard state
        rows = adapter.wizard_to_spreadsheet()
        assert rows[0].fraction == 1
        assert rows[1].fraction == 1


class TestWizardStateClearField:
    """Tests for the new clear_run_field API on WizardState."""

    def test_clear_run_field_removes_field(self):
        """Test that clear_run_field removes a field from a run."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", sample="s1", fraction=1)

        # Clear the sample field
        wizard.clear_run_field(0, "sample")

        # Verify
        assert "sample" not in wizard.runs[0]
        assert wizard.runs[0]["file"] == "/data/s1.raw"
        assert wizard.runs[0]["fraction"] == 1

    def test_clear_run_field_idempotent(self):
        """Test that clearing non-existent field is safe (idempotent)."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")

        # Clear a field that doesn't exist - should not raise
        wizard.clear_run_field(0, "sample")

        # Verify no change
        assert "sample" not in wizard.runs[0]
        assert wizard.runs[0]["file"] == "/data/s1.raw"

    def test_clear_run_field_cannot_remove_file(self):
        """Test that file field cannot be removed."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")

        # Attempting to clear required field should raise
        with pytest.raises(ValueError, match="Cannot remove required field"):
            wizard.clear_run_field(0, "file")

    def test_clear_run_field_invalid_run_index(self):
        """Test that invalid run index raises error."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")

        with pytest.raises(IndexError, match="out of range"):
            wizard.clear_run_field(5, "sample")

        with pytest.raises(IndexError, match="out of range"):
            wizard.clear_run_field(-1, "sample")

    def test_clear_run_field_affects_spreadsheet_view(self):
        """Test that clearing field is reflected in spreadsheet view."""
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1, instrument="Q Exactive")

        adapter = SpreadsheetAdapter(wizard)

        # Clear via wizard API
        wizard.clear_run_field(0, "instrument")

        # Verify in spreadsheet view
        rows = adapter.wizard_to_spreadsheet()
        assert rows[0].file == "/data/s1.raw"
        assert rows[0].fraction == 1
        assert rows[0].instrument is None
