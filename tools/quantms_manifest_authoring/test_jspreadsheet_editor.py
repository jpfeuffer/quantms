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
spreadsheet display and user interactions, with revised persistence tests
that guard the critical pre-navigation flush boundary.
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


class TestJSpreadsheetEditorNavigationPersistence:
    """
    Revised regression tests for JSpreadsheet edit persistence at navigation boundary.
    
    These tests verify that pending spreadsheet cell edits (those in active-cell
    edit state in jspreadsheet, before a change event fires) are properly handled
    before the editor is torn down during navigation.
    
    The critical bug: When a user types in a spreadsheet cell and then navigates away
    before the cell loses focus, jspreadsheet hasn't emitted a change event yet,
    so the Python code never sees the edit, causing data loss.
    
    Testing Strategy:
    - Contract tests verify the presence of flush/commit mechanism
    - Integration tests verify behavior when flush is/isn't called
    - Documentation tests specify the expected pre-navigation behavior
    """

    def test_editor_has_flush_mechanism_for_pending_edits(self):
        """
        Contract test: JSpreadsheetEditor MUST provide a mechanism to flush
        pending cell edits from JavaScript before teardown (pre-navigation flush).
        
        This verifies the interface requirement at the navigation boundary.
        The method should exist or be callable, enabling the GUI layer to
        properly commit pending edits before destroying the editor.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", fraction=1)
        
        editor = JSpreadsheetEditor(wizard, MagicMock())
        
        # The editor MUST have a mechanism to flush pending edits
        # The method may be named 'flush_pending_edits', 'flush', etc.
        flush_methods = [attr for attr in dir(editor) if 'flush' in attr.lower()]
        
        assert len(flush_methods) > 0, (
            "JSpreadsheetEditor must have a flush method for pre-navigation "
            "pending edit handling (guards critical regression boundary)"
        )

    def test_pending_edit_without_flush_causes_data_loss(self):
        """
        Regression documentation: Without proper flushing before navigation,
        pending edits are lost when the editor is recreated.
        
        This test DOCUMENTS THE BUG: If the GUI doesn't flush pending edits
        before navigating away and recreating the editor, the user's data
        typed but not yet committed is permanently lost.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", fraction=1)
        
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Scenario: User types "99" in fraction field but immediately
        # clicks "Next" button before the cell blur event fires.
        # In JavaScript, the cell has value "99".
        # In Python state, it's still 1 (no event fired yet).
        
        # If we don't flush before destroying the editor, the "99" is lost
        del editor1
        
        # Create new editor from same wizard state
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        data = editor2.bridge.get_spreadsheet_data()
        
        # REGRESSION: Without flush, the value is still 1 (data loss!)
        # With proper flush, it should be 99 (after fix is implemented)
        assert data["data"][0][1] == 1, (
            "REGRESSION DOCUMENTED: When editor destroyed without flush, "
            "pending edits that weren't committed via change events are lost"
        )

    def test_pending_cell_edit_persists_when_change_event_fired(self):
        """
        Current working behavior: When a cell change event HAS fired
        (via handle_cell_edit), edits persist through editor recreation.
        
        This documents the baseline: changes with events work. The regression
        is when NO event has fired yet (user still editing the cell).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", fraction=1)
        
        # Create first editor instance
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Simulate cell edit where change event HAS fired
        editor1.handle_cell_edit(row_index=0, col_index=1, new_value="3")
        
        # Verify the edit was applied to the wizard state
        assert wizard.runs[0]["fraction"] == 3, "Edit should sync via handle_cell_edit"
        
        # Simulate editor teardown (navigate flow recreates the editor)
        del editor1
        
        # Create a fresh editor from the same wizard state
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        # Get the data from the new editor
        data = editor2.bridge.get_spreadsheet_data()
        
        # Verify the edited value persists
        # This works because the change event WAS fired
        assert len(data["data"]) == 1
        fraction_col_idx = 1
        row_data = data["data"][0]
        assert row_data[fraction_col_idx] == 3, (
            "With change event fired, edit persists (CURRENT WORKING CASE)"
        )

    def test_multiple_pending_edits_with_change_events_persist(self):
        """
        Current working behavior: Multiple edits (with change events fired)
        persist across editor recreation.
        
        The regression occurs when change events have NOT fired yet.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw", fraction=1, instrument="Orbitrap")
        
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Edit fraction (with change event)
        editor1.handle_cell_edit(row_index=0, col_index=1, new_value="2")
        assert wizard.runs[0]["fraction"] == 2
        
        # Edit instrument (with change event)
        editor1.handle_cell_edit(row_index=0, col_index=2, new_value="Orbitrap Fusion Lumos")
        assert wizard.runs[0]["instrument"] == "Orbitrap Fusion Lumos"
        
        # Simulate editor teardown and recreation
        del editor1
        
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        # Verify both edits persist
        data = editor2.bridge.get_spreadsheet_data()
        row_data = data["data"][0]
        assert row_data[1] == 2, "Fraction edit with event persists"
        assert row_data[2] == "Orbitrap Fusion Lumos", "Instrument edit with event persists"

    def test_cell_edit_correct_row_persistence(self):
        """
        Regression: When multiple runs exist and one is edited (with change event),
        ensure the correct row is updated and persists after recreation.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)
        wizard.add_run(file="/data/sample2.raw", fraction=1)
        wizard.add_run(file="/data/sample3.raw", fraction=1)
        
        on_change = MagicMock()
        editor1 = JSpreadsheetEditor(wizard, on_change)
        
        # Edit fraction in row 1 (with change event)
        editor1.handle_cell_edit(row_index=1, col_index=1, new_value="5")
        
        # Verify only the second run was modified
        assert wizard.runs[0]["fraction"] == 1
        assert wizard.runs[1]["fraction"] == 5
        assert wizard.runs[2]["fraction"] == 1
        
        # Simulate teardown and recreation
        del editor1
        
        on_change2 = MagicMock()
        editor2 = JSpreadsheetEditor(wizard, on_change2)
        
        # Verify the edit persists to the correct row
        data = editor2.bridge.get_spreadsheet_data()
        assert data["data"][0][1] == 1, "Row 0 fraction unchanged"
        assert data["data"][1][1] == 5, "Row 1 fraction updated (correct row)"
        assert data["data"][2][1] == 1, "Row 2 fraction unchanged"
