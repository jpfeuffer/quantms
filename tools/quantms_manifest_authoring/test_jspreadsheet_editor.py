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
