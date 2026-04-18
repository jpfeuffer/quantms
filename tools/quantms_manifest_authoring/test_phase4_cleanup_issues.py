#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Tests for Phase 4 cleanup issues:
1. Assignments row deletion safety
2. Assignments bulk sync ignores run_file edits
3. Assignment and Mixture validation requirements
4. Read-only field support in column config
"""

import pytest
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from spreadsheet_adapter import (
    SpreadsheetAdapter,
    AssignmentSpreadsheetRow,
    AssignmentFieldInfo,
    MixtureSpreadsheetRow,
    MixtureFieldInfo,
)
from jspreadsheet_bridge import JSpreadsheetBridge


class TestAssignmentRowDeletionSafety:
    """Tests for safe handling of assignment row deletion."""

    def test_handle_row_delete_assignments_is_safe_noop(self):
        """
        Assignment rows are a view over runs, so deletion should be a safe no-op
        or safe rejection without raising 'unknown entity type' error from bridge.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/run1.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")

        # Should not raise ValueError about unknown entity type
        # Should either do nothing or handle safely
        initial_run_count = len(wizard.runs)
        try:
            bridge.handle_row_delete(row_index=0)
        except ValueError as e:
            # If it raises, it should NOT be about unknown entity type
            assert "Unknown entity type" not in str(e), \
                f"Should safely reject/ignore deletion, not raise unknown entity error: {e}"

        # Verify runs are not deleted (safe no-op)
        assert len(wizard.runs) == initial_run_count, \
            "Assignment row deletion should not actually delete runs"

    def test_handle_row_delete_runs_actually_deletes(self):
        """Verify that runs entity type still actually deletes rows (for contrast)."""
        wizard = WizardState()
        wizard.add_run(file="/data/run1.raw")
        wizard.add_run(file="/data/run2.raw")

        bridge = JSpreadsheetBridge(wizard, entity_type="runs")

        assert len(wizard.runs) == 2
        bridge.handle_row_delete(row_index=0)
        assert len(wizard.runs) == 1


class TestAssignmentBulkSyncIgnoresRunFile:
    """Tests that bulk sync from spreadsheet ignores run_file edits."""

    def test_sync_from_spreadsheet_data_ignores_run_file_column_edits(self):
        """
        When syncing assignments from spreadsheet data, the run_file column
        edits from the browser should be completely ignored.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/original.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")

        # Simulate browser sending back spreadsheet data where run_file was "edited" to a different value
        # Column order is: run_file, sample
        edited_spreadsheet_data = [
            ["/data/MODIFIED.raw", "s2"],  # Browser user tried to change run_file and sample
        ]

        # Sync the data back
        bridge.sync_from_spreadsheet_data(edited_spreadsheet_data)

        # run_file should NOT have changed - it should still be the original
        assert wizard.runs[0]["file"] == "/data/original.raw", \
            "run_file should not be modified from browser data; should remain original"

        # But sample SHOULD have been updated
        assert wizard.runs[0].get("sample") == "s2", \
            "Sample should be updated from browser data"

    def test_sync_from_spreadsheet_data_assignments_updates_correct_column(self):
        """Verify that sample or mixture column is updated correctly based on quantification method."""
        wizard = WizardState()
        wizard.add_run(file="/data/run1.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")

        # For LFQ, headers are: run_file, sample
        spreadsheet_data = [
            ["/data/run1.raw", "s1"],
        ]

        bridge.sync_from_spreadsheet_data(spreadsheet_data)
        assert wizard.runs[0].get("sample") == "s1"


class TestAssignmentRowValidationRequiresRunFile:
    """Tests that assignment row validation requires run_file."""

    def test_assignment_spreadsheet_row_validate_requires_run_file(self):
        """AssignmentSpreadsheetRow.validate() must require run_file to be present."""
        # Create an assignment row without run_file
        row = AssignmentSpreadsheetRow(run_file=None, sample="s1", row_index=0)

        # Validate should raise ValueError because run_file is missing
        with pytest.raises(ValueError, match=".*run_file.*required|.*run_file.*missing"):
            row.validate()

    def test_assignment_spreadsheet_row_validate_accepts_valid_row(self):
        """AssignmentSpreadsheetRow.validate() should pass with run_file present."""
        row = AssignmentSpreadsheetRow(run_file="/data/test.raw", sample="s1", row_index=0)

        # Should not raise
        row.validate()

    def test_assignment_spreadsheet_row_validate_allows_none_sample_and_mixture(self):
        """AssignmentSpreadsheetRow.validate() should allow None for sample/mixture (optional)."""
        row = AssignmentSpreadsheetRow(run_file="/data/test.raw", sample=None, mixture=None, row_index=0)

        # Should not raise - sample and mixture are optional
        row.validate()

    def test_assignment_field_info_run_file_is_required(self):
        """AssignmentFieldInfo metadata should mark run_file as required."""
        info = AssignmentFieldInfo.get_field_info("run_file")
        assert info.get("required") is True, "run_file should be marked as required"


class TestMixtureRowValidationRequiresId:
    """Tests that mixture row validation requires id."""

    def test_mixture_spreadsheet_row_validate_requires_id(self):
        """MixtureSpreadsheetRow.validate() must require id to be present."""
        # Create a mixture row without id
        row = MixtureSpreadsheetRow(id=None, channels={"127N": "s1"}, row_index=0)

        # Validate should raise ValueError because id is missing
        with pytest.raises(ValueError, match="Mixture ID is required"):
            row.validate()

    def test_mixture_spreadsheet_row_validate_accepts_valid_row(self):
        """MixtureSpreadsheetRow.validate() should pass with id present."""
        row = MixtureSpreadsheetRow(id="mix1", channels={"127N": "s1"}, row_index=0)

        # Should not raise
        row.validate()

    def test_mixture_spreadsheet_row_validate_empty_id_fails(self):
        """MixtureSpreadsheetRow.validate() should reject empty string id."""
        row = MixtureSpreadsheetRow(id="", channels={"127N": "s1"}, row_index=0)

        with pytest.raises(ValueError, match="Mixture ID is required"):
            row.validate()

    def test_mixture_field_info_id_is_required(self):
        """MixtureFieldInfo metadata should mark id as required."""
        info = MixtureFieldInfo.get_field_info("id")
        assert info.get("required") is True, "id should be marked as required"


class TestReadOnlyFieldMetadata:
    """Tests for read-only field support in metadata and column config."""

    def test_assignment_field_info_run_file_is_readonly(self):
        """AssignmentFieldInfo should mark run_file as read-only."""
        info = AssignmentFieldInfo.get_field_info("run_file")
        assert info.get("read_only") is True, "run_file should be marked as read-only"

    def test_column_config_includes_readonly_metadata(self):
        """Column config builder should include read_only metadata from field info."""
        from spreadsheet_column_config import ColumnConfigBuilder

        builder = ColumnConfigBuilder()

        def field_info_getter(field):
            if field == "run_file":
                return {"type": "str", "required": True, "read_only": True}
            return {"type": "str", "required": False}

        config = builder.build_column_config(
            headers=["run_file", "sample"],
            field_info_getter=field_info_getter,
        )

        # Config for run_file should include read_only marker
        assert "read_only" in config.get("run_file", {}), \
            "Column config should include read_only metadata"
        assert config["run_file"]["read_only"] is True


class TestIntegrationAssignmentSyncAndValidation:
    """Integration tests for assignment sync with validation."""

    def test_sync_assignment_edits_validates_run_file(self):
        """When syncing assignment edits, validation must catch missing run_file."""
        wizard = WizardState()
        wizard.add_run(file="/data/run1.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        adapter = SpreadsheetAdapter(wizard)

        # Create a row with missing run_file (simulating some edge case)
        rows = [AssignmentSpreadsheetRow(run_file=None, sample="s1", row_index=0)]

        # Sync should fail during validation
        with pytest.raises(ValueError, match=".*run_file.*required|.*run_file.*missing"):
            adapter.sync_assignment_edits(rows, "LFQ")

    def test_sync_mixture_edits_validates_id(self):
        """When syncing mixture edits, validation must catch missing id."""
        wizard = WizardState()
        wizard.add_sample(id="s1")

        adapter = SpreadsheetAdapter(wizard)

        # Create a row with missing id
        rows = [MixtureSpreadsheetRow(id=None, channels={"127N": "s1"}, row_index=0)]

        # Sync should fail during validation
        with pytest.raises(ValueError, match="Mixture ID is required"):
            adapter.sync_mixture_edits(rows)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
