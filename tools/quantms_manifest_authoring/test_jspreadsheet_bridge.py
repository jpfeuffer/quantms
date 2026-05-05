#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "nicegui",
#   "pyyaml",
# ]
# ///
"""
Tests for jspreadsheet bridge integration with the Runs step.

Tests the actual bridge behavior for:
- Initializing spreadsheet data from adapter rows
- Syncing cell edits back to wizard state
- Deleting rows from the spreadsheet
- Appending rows via file picker into the spreadsheet
"""

import pytest
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from spreadsheet_adapter import SpreadsheetAdapter, SpreadsheetRow
from jspreadsheet_bridge import JSpreadsheetBridge


class TestJSpreadsheetBridge:
    """Tests for the jspreadsheet bridge."""

    def test_bridge_initialization_converts_wizard_to_spreadsheet_format(self):
        """
        AC1: Bridge.get_spreadsheet_data() converts WizardState.runs to jspreadsheet format
        with headers and nested list data (run-level fields only).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1)
        wizard.add_run(file="/data/s2.raw", fraction=2, instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        # Verify structure
        assert "headers" in data
        assert "data" in data
        assert data["headers"] == ["file", "fraction", "instrument"]

        # Verify data rows
        assert len(data["data"]) == 2
        assert data["data"][0][0] == "/data/s1.raw"  # file column
        assert data["data"][0][1] == 1  # fraction column

        assert data["data"][1][0] == "/data/s2.raw"
        assert data["data"][1][1] == 2  # fraction column
        assert data["data"][1][2] == "Orbitrap"  # instrument column

    def test_bridge_handles_cell_edit_syncs_to_wizard(self):
        """
        AC2: Bridge.handle_cell_edit() updates wizard state via adapter when a cell is edited.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/original.raw", fraction=1)

        bridge = JSpreadsheetBridge(wizard)

        # Edit fraction in first row (column index 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value=5)

        # Verify wizard state updated
        assert wizard.runs[0]["fraction"] == 5

    def test_bridge_handles_cell_edit_validates_required_fields(self):
        """
        AC3: Bridge.handle_cell_edit() raises ValueError if required field (file) is cleared.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        # Try to clear the required file field
        with pytest.raises(ValueError, match="File path is required"):
            bridge.handle_cell_edit(row_index=0, col_index=0, new_value="")

    def test_bridge_handles_cell_edit_coerces_fraction_to_int(self):
        """
        AC4: Bridge.handle_cell_edit() coerces fraction to int or rejects invalid values.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        # Edit with string "3" in fraction column (index 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value="3")
        assert wizard.runs[0]["fraction"] == 3
        assert isinstance(wizard.runs[0]["fraction"], int)

        # Edit with invalid non-numeric string - should raise
        with pytest.raises(ValueError, match="Fraction must be an integer"):
            bridge.handle_cell_edit(row_index=0, col_index=1, new_value="not_a_number")

    def test_bridge_handles_row_delete(self):
        """
        AC5: Bridge.handle_row_delete() removes a row from the wizard.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw")

        assert len(wizard.runs) == 2

        bridge = JSpreadsheetBridge(wizard)
        bridge.handle_row_delete(row_index=0)

        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "/data/s2.raw"

    def test_bridge_handles_row_append(self):
        """
        AC6: Bridge.handle_row_append() adds a new run to the wizard.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/existing.raw")

        bridge = JSpreadsheetBridge(wizard)
        bridge.handle_row_append("/data/new.raw")

        assert len(wizard.runs) == 2
        assert wizard.runs[1]["file"] == "/data/new.raw"

    def test_bridge_handles_multiple_cell_edits_sequence(self):
        """
        AC7: Bridge handles a sequence of cell edits correctly (e.g., user fills in fraction, instrument).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        # Simulate user editing fraction column (index 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value=2)
        assert wizard.runs[0]["fraction"] == 2

        # Edit instrument column (index 2)
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="Orbitrap")
        assert wizard.runs[0]["instrument"] == "Orbitrap"

    def test_bridge_clear_optional_field_with_empty_string(self):
        """
        AC8: Bridge allows clearing optional fields by setting empty string.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard)

        # Clear instrument field (column 2)
        bridge.handle_cell_edit(row_index=0, col_index=2, new_value="")

        # Verify field was removed (not in the dict)
        assert "instrument" not in wizard.runs[0] or wizard.runs[0]["instrument"] is None

    def test_bridge_edge_case_row_index_out_of_range(self):
        """
        AC9: Bridge raises ValueError for out-of-range row indices.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        bridge = JSpreadsheetBridge(wizard)

        with pytest.raises(ValueError, match="out of range"):
            bridge.handle_cell_edit(row_index=10, col_index=0, new_value="new_value")

    def test_modification_bridge_handles_missing_term_specificity(self):
        """Bridge should tolerate modifications that do not define term_specificity."""
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="custom",
            name="Custom PTM",
            residues="C",
            profile="default",
        )

        bridge = JSpreadsheetBridge(wizard, entity_type="modifications")
        data = bridge.get_spreadsheet_data()

        assert "term_specificity" in data["headers"]
        assert data["data"][0][data["headers"].index("term_specificity")] is None

        bridge.sync_from_spreadsheet_data(data["data"])

        assert wizard.modifications[0].get("term_specificity") is None
