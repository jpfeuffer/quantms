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
Tests for JSpreadsheetEditor NiceGUI integration.

Tests the editor wrapper functionality for initializing and managing
spreadsheet display and user interactions.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_editor import JSpreadsheetEditor


class TestJSpreadsheetEditor:
    """Tests for JSpreadsheetEditor."""

    def test_editor_initialization_with_wizard_state(self):
        """
        AC1: JSpreadsheetEditor initializes with a WizardState
        and creates a JSpreadsheetBridge internally.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Verify initialization
        assert editor.wizard is wizard
        assert editor.bridge is not None
        assert editor.on_change is on_change

    def test_editor_get_initialization_data(self):
        """
        AC2: JSpreadsheetEditor can provide initialization data
        in the format expected by jspreadsheet.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw", fraction=1)
        wizard.add_run(file="/data/s2.raw", fraction=2)

        editor = JSpreadsheetEditor(wizard, MagicMock())

        # Get initialization data
        data = editor.bridge.get_spreadsheet_data()

        assert "headers" in data
        assert "data" in data
        assert len(data["data"]) == 2

    def test_editor_handle_cell_edit_calls_on_change(self):
        """
        AC3: When a cell is edited, the editor syncs via bridge
        and does not force a full UI rerender.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Simulate cell edit: change fraction from 1 to 5
        editor.handle_cell_edit(row_index=0, col_index=1, new_value="5")

        # Verify wizard was updated
        assert wizard.runs[0]["fraction"] == 5

        # Spreadsheet edits should not rerender the full page
        on_change.assert_not_called()

    def test_editor_handle_cell_edit_error_notification(self):
        """
        AC4: Cell edit errors result in a notification and no state change.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Try to edit with invalid value (empty required field)
        with patch("jspreadsheet_editor.ui.notify") as mock_notify:
            editor.handle_cell_edit(row_index=0, col_index=0, new_value="")

            # Verify error notification
            mock_notify.assert_called()
            assert "Error" in str(mock_notify.call_args)

    def test_editor_handle_row_delete(self):
        """
        AC5: Row delete through editor removes the run and calls on_change.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Delete first row
        editor.handle_row_delete(row_index=0)

        # Verify deletion
        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "/data/s2.raw"

        # Verify callback
        on_change.assert_called_once()

    def test_editor_append_row(self):
        """
        AC6: Appending a row adds a new run and refreshes.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/existing.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Append new file
        with patch.object(editor, "refresh"):
            editor.append_row("/data/new.raw")

        # Verify addition
        assert len(wizard.runs) == 2
        assert wizard.runs[1]["file"] == "/data/new.raw"

        # Verify callbacks
        on_change.assert_called_once()

    def test_editor_asset_path_exists(self):
        """
        AC7: Editor can locate the jspreadsheet HTML asset template.
        """
        wizard = WizardState()
        editor = JSpreadsheetEditor(wizard, MagicMock())

        vendor_root = Path(__file__).parent / "assets" / "vendor"

        assert editor is not None
        assert editor.bridge is not None
        assert (vendor_root / "jspreadsheet-ce" / "jspreadsheet.js").exists()
        assert (vendor_root / "jspreadsheet-ce" / "jspreadsheet.css").exists()
        assert (vendor_root / "jsuites" / "jsuites.js").exists()
        assert (vendor_root / "jsuites" / "jsuites.css").exists()


class TestJSpreadsheetEditorEditPersistenceRegression:
    """Regression tests for JSpreadsheet edit persistence.
    
    Tests that ensure pending spreadsheet cell edits are properly committed
    to WizardState before the editor is torn down and rebuilt during
    navigation.
    """

    def test_pending_cell_edit_is_committed_before_editor_teardown(self):
        """
        Regression: Pending cell edits should be flushed to WizardState
        before JSpreadsheetEditor is torn down (when user navigates to
        next step, then back).
        
        Scenario:
        1. Create a spreadsheet editor with a run
        2. Simulate a user editing a cell (fraction field)
        3. Simulate editor teardown (user navigates away)
        4. Create a new editor for the same wizard state
        5. Verify the edited value persists in the new editor
        
        This regression test confirms that no pending edits are lost
        when the editor UI is recreated.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", fraction=1)
        
        # Create first editor instance
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Simulate cell edit: user changes fraction from 1 to 3
        editor1.handle_cell_edit(row_index=0, col_index=1, new_value="3")
        
        # Verify the edit was applied to the wizard state
        assert wizard.runs[0]["fraction"] == 3, \
            "Edit should be immediately applied to wizard state"
        
        # Simulate editor teardown (navigate flow recreates the editor)
        del editor1
        
        # Create a fresh editor from the same wizard state
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        # Get the data from the new editor
        data = editor2.bridge.get_spreadsheet_data()
        
        # Verify the edited value persists in the new editor
        # The fraction field should still be 3 in the spreadsheet data
        assert len(data["data"]) == 1, "Should have one run row"
        fraction_col_idx = 1  # Assuming fraction is second column
        row_data = data["data"][0]
        assert row_data[fraction_col_idx] == 3, \
            f"Fraction value should persist as 3 in new editor, but got {row_data[fraction_col_idx]} (regression: edit was lost)"

    def test_multiple_pending_edits_persisted_across_editor_recreation(self):
        """
        Regression: Multiple pending edits in a single run should all
        persist when the editor is torn down and recreated.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", fraction=1, instrument="Orbitrap")
        
        # Create first editor and make multiple edits
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Edit fraction
        editor1.handle_cell_edit(row_index=0, col_index=1, new_value="2")
        assert wizard.runs[0]["fraction"] == 2
        
        # Edit instrument (use a valid ontology value)
        editor1.handle_cell_edit(row_index=0, col_index=2, new_value="Orbitrap Fusion Lumos")
        assert wizard.runs[0]["instrument"] == "Orbitrap Fusion Lumos"
        
        # Simulate editor teardown and recreation
        del editor1
        
        # Create new editor
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        # Verify both edits persist
        data = editor2.bridge.get_spreadsheet_data()
        row_data = data["data"][0]
        assert row_data[1] == 2, "Fraction edit should persist"
        assert row_data[2] == "Orbitrap Fusion Lumos", "Instrument edit should persist"

    def test_cell_edit_consistency_with_multiple_rows(self):
        """
        Regression: When multiple runs exist and one is edited, ensure
        the edit is applied to the correct row and persists across
        editor recreation.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)
        wizard.add_run(file="/data/sample2.raw", fraction=1)
        wizard.add_run(file="/data/sample3.raw", fraction=1)
        
        # Create editor and edit only the second row
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Edit fraction in row 1 (second run)
        editor1.handle_cell_edit(row_index=1, col_index=1, new_value="5")
        
        # Verify only the second run was modified
        assert wizard.runs[0]["fraction"] == 1, "First run should be unchanged"
        assert wizard.runs[1]["fraction"] == 5, "Second run should be edited"
        assert wizard.runs[2]["fraction"] == 1, "Third run should be unchanged"
        
        # Simulate teardown and recreation
        del editor1
        
        # Create new editor
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        # Verify the edit persists to the correct row
        data = editor2.bridge.get_spreadsheet_data()
        assert data["data"][0][1] == 1, "First row fraction should be 1"
        assert data["data"][1][1] == 5, "Second row fraction should be 5"
        assert data["data"][2][1] == 1, "Third row fraction should be 1"
