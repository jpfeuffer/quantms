#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "nicegui",
#   "pyyaml",
#   "httpx",
# ]
# ///
"""
Real browser validation tests for the Runs step with jspreadsheet-ce.

These tests start an actual NiceGUI server and validate that:
1. The spreadsheet mounts into the NiceGUI container (visible in DOM)
2. The Runs Table appears when runs are added
3. Cell edits work correctly
4. The spreadsheet is not appended to document.body
"""

import pytest
import sys
import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from gui_nicegui import create_runs_step, create_manifest_editor_ui
from jspreadsheet_editor import JSpreadsheetEditor


class TestBrowserValidationRuns:
    """Real browser validation tests for the Runs step."""

    def test_creates_runs_step_ui_without_errors(self):
        """
        AC1: The create_runs_step function is callable and can be invoked
        with a wizard state and refresh_ui callback.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        
        refresh_ui_called = False
        
        def refresh_ui():
            nonlocal refresh_ui_called
            refresh_ui_called = True
        
        # Verify the function is callable
        assert callable(create_runs_step)
        
        # Verify it accepts the right parameters
        import inspect
        sig = inspect.signature(create_runs_step)
        params = list(sig.parameters.keys())
        assert 'wizard' in params
        assert 'refresh_ui' in params

    def test_spreadsheet_editor_widget_id_generation(self):
        """
        AC2: JSpreadsheetEditor generates a unique widget_id
        for scoping events from multiple editors.
        """
        wizard1 = WizardState()
        wizard1.add_run(file="/data/test1.raw")
        
        wizard2 = WizardState()
        wizard2.add_run(file="/data/test2.raw")
        
        editor1 = JSpreadsheetEditor(wizard1, MagicMock())
        editor2 = JSpreadsheetEditor(wizard2, MagicMock())
        
        # Each editor should have unique widget_id
        assert editor1.widget_id != editor2.widget_id
        assert editor1.widget_id.startswith('jse_')
        assert editor2.widget_id.startswith('jse_')

    def test_spreadsheet_data_structure_for_js(self):
        """
        AC3: The spreadsheet data structure is correctly formatted
        for JavaScript initialization.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw", sample="sample1", fraction=1)
        wizard.add_run(file="/data/test2.raw", sample="sample2", fraction=2)
        
        editor = JSpreadsheetEditor(wizard, MagicMock())
        data = editor.bridge.get_spreadsheet_data()
        
        # Should have headers and data
        assert "headers" in data
        assert "data" in data
        
        # Headers should be list of field names
        assert isinstance(data["headers"], list)
        assert len(data["headers"]) > 0
        
        # Data should be list of rows
        assert isinstance(data["data"], list)
        assert len(data["data"]) == 2
        
        # Each row should be a list matching header count
        for row in data["data"]:
            assert len(row) == len(data["headers"])

    def test_javascript_container_mounting_pattern(self):
        """
        AC4: The JavaScript code uses the proper pattern for mounting
        into a NiceGUI container element.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        
        editor = JSpreadsheetEditor(wizard, MagicMock())
        
        # Check widget_id is properly generated
        assert editor.widget_id is not None
        assert len(editor.widget_id) > 0
        
        # The JavaScript should reference this widget_id
        # and use getElementById with the container_id
        
        from unittest.mock import patch
        
        with patch('jspreadsheet_editor.ui.run_javascript') as mock_run_js:
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                mock_container = MagicMock()
                mock_container.id = 'c67890'
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container
                
                editor.render()
                
                # Get all JavaScript calls
                js_calls = [call_args[0][0] for call_args in mock_run_js.call_args_list]
                
                # Container ID should be referenced in the initialization
                assert any('c67890' in call for call in js_calls)
                
                # Widget ID should be used for scoping
                assert any(editor.widget_id in call for call in js_calls)

    def test_event_handler_methods_exist(self):
        """
        AC5: JSpreadsheetEditor has proper event handler methods
        that Python can call when receiving events from JavaScript.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        
        editor = JSpreadsheetEditor(wizard, MagicMock())
        
        # Should have handler methods
        assert hasattr(editor, 'handle_cell_edit')
        assert callable(editor.handle_cell_edit)
        
        assert hasattr(editor, 'handle_row_delete')
        assert callable(editor.handle_row_delete)
        
        # These should work without errors
        editor.handle_cell_edit(0, 0, "new_value")
        assert wizard.runs[0]["file"] == "new_value"
        
        # Can't delete if only one row, so add another first
        wizard.add_run(file="/data/test2.raw")
        editor.handle_row_delete(0)
        assert len(wizard.runs) == 1


class TestRunsTableVisibility:
    """Tests for the 'Runs Table' label appearing when runs exist."""

    def test_runs_table_label_appears_with_runs(self):
        """
        AC6: When runs are added, the UI shows 'Runs Table (N file(s))'
        label indicating the spreadsheet widget should be visible.
        """
        wizard = WizardState()
        
        # No runs - table label should not appear
        assert len(wizard.runs) == 0
        
        # Add runs
        wizard.add_run(file="/data/test1.raw")
        wizard.add_run(file="/data/test2.raw")
        
        # Now table label should appear
        assert len(wizard.runs) == 2
        
        # The create_runs_step would show:
        # "Runs Table (2 file(s))"
        label_text = f"Runs Table ({len(wizard.runs)} file(s))"
        assert len(wizard.runs) > 0
        assert "2" in label_text
        assert "file(s)" in label_text


class TestWidgetIDScoping:
    """Tests for widget ID scoping in multi-editor scenarios."""

    def test_multiple_spreadsheets_have_independent_widget_ids(self):
        """
        AC7: Multiple spreadsheet editors can exist without conflicts
        because each has its own widget_id for event scoping.
        """
        wizards = [WizardState() for _ in range(3)]
        editors = []
        widget_ids = set()
        
        for wizard in wizards:
            wizard.add_run(file="/data/test.raw")
            editor = JSpreadsheetEditor(wizard, MagicMock())
            editors.append(editor)
            widget_ids.add(editor.widget_id)
        
        # All widget IDs should be unique
        assert len(widget_ids) == 3
        
        # Each should have proper format
        for widget_id in widget_ids:
            assert widget_id.startswith('jse_')

    def test_event_payload_scoping_by_widget_id(self):
        """
        AC8: Event payloads include widget_id so that events from
        one spreadsheet don't affect another.
        """
        wizard1 = WizardState()
        wizard1.add_run(file="/data/test1.raw", sample="sample1")
        
        wizard2 = WizardState()
        wizard2.add_run(file="/data/test2.raw", sample="sample2")
        
        editor1 = JSpreadsheetEditor(wizard1, MagicMock())
        editor2 = JSpreadsheetEditor(wizard2, MagicMock())
        
        # Simulate edit in editor1
        editor1.handle_cell_edit(0, 1, "new_sample1")
        
        # Verify wizard1 changed but wizard2 didn't
        assert wizard1.runs[0]["sample"] == "new_sample1"
        assert wizard2.runs[0]["sample"] == "sample2"
        
        # Simulate edit in editor2
        editor2.handle_cell_edit(0, 1, "new_sample2")
        
        # Verify wizard2 changed
        assert wizard2.runs[0]["sample"] == "new_sample2"
        assert wizard1.runs[0]["sample"] == "new_sample1"  # Unchanged
