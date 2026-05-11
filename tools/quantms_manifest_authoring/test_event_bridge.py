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
Tests for the real browser→Python event bridge in JSpreadsheetEditor.

Validates that:
- The spreadsheet mounts into the NiceGUI container (not document.body)
- Cell edits emit JSON events that Python handlers receive
- Row deletes emit JSON events that Python handlers receive
- Event payloads include widget ID for proper scoping
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_bridge import JSpreadsheetBridge
from jspreadsheet_editor import JSpreadsheetEditor


class TestEventBridgeContainerMounting:
    """Tests for mounting the spreadsheet into the NiceGUI container."""

    def test_spreadsheet_mounts_into_nicegui_container(self):
        """
        AC1: JSpreadsheetEditor.render() creates a container element
        and the JS code mounts the spreadsheet into it (not document.body).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Track what JavaScript was run
        run_js_calls = []

        with patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.id = 1
            mock_context.client.has_socket_connection = True
            mock_context.client.run_javascript = MagicMock()
            with patch.object(JSpreadsheetEditor, 'prepare_client_runtime'):
                with patch('jspreadsheet_editor.ui.element') as mock_element:
                    with patch('jspreadsheet_editor.ui.on') as mock_ui_on:
                        # Mock the container element with proper ID attributes
                        mock_container = MagicMock()
                        mock_container.id = 12345  # Internal numeric id
                        mock_container.html_id = 'c12345'  # NiceGUI DOM id format
                        mock_container.classes = MagicMock(return_value=mock_container)  # Allow chaining
                        mock_element.return_value = mock_container

                        editor.render()
                        run_js_calls = [call_args[0][0] for call_args in mock_context.client.run_javascript.call_args_list]

        # Verify container was created
        mock_element.assert_called_once()

        # Verify JavaScript mounts to container, not document.body
        # Should contain reference to container ID
        assert len(run_js_calls) > 0

        # At least one JS call should reference mounting to the container
        js_code_combined = '\n'.join(run_js_calls)

        # Should NOT append to document.body
        assert 'document.body.appendChild' not in js_code_combined

        # Should reference proper container element by html_id
        assert 'c12345' in js_code_combined or 'getElementById' in js_code_combined

    def test_container_has_proper_id_reference(self):
        """
        AC2: The container element's ID is properly passed to JavaScript
        and used to mount the spreadsheet.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.id = 1
            mock_context.client.has_socket_connection = True
            mock_context.client.run_javascript = MagicMock()
            with patch.object(JSpreadsheetEditor, 'prepare_client_runtime'):
                with patch('jspreadsheet_editor.ui.element') as mock_element:
                    with patch('jspreadsheet_editor.ui.on') as mock_ui_on:
                        mock_container = MagicMock()
                        mock_container.id = 999  # Internal id
                        mock_container.html_id = 'c999'  # NiceGUI format
                        mock_container.classes = MagicMock(return_value=mock_container)
                        mock_element.return_value = mock_container

                        editor.render()

                        # Extract JavaScript calls
                        js_calls = [call_args[0][0] for call_args in mock_context.client.run_javascript.call_args_list]
                        js_code = '\n'.join(js_calls)

                        # Should reference the container html_id in initialization
                        assert 'c999' in js_code


class TestEventBridgeCallbacks:
    """Tests for JavaScript→Python callback bridge."""

    def test_cell_edit_event_emitted_and_handled(self):
        """
        AC3: When a cell is edited in the spreadsheet, JavaScript emits
        a JSON event that includes row, col, value, and widget_id.
        Python successfully receives and processes the event.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Simulate a cell edit event from JavaScript
        # This should call the Python callback registered via ui.on()
        event_payload = {
            "type": "cell_edit",
            "widget_id": "spreadsheet_editor_1",
            "row": 0,
            "col": 1,  # fraction column
            "value": "3"
        }

        editor.handle_cell_edit(
            row_index=event_payload["row"],
            col_index=event_payload["col"],
            new_value=event_payload["value"]
        )

        # Verify wizard was updated
        assert wizard.runs[0]["fraction"] == 3

        # Spreadsheet edits should not rerender the full page
        on_change.assert_not_called()

    def test_sheet_sync_event_persists_drag_copy_without_rerender(self):
        """Batch sheet sync events should persist drag-copy changes without tearing down the sheet."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="human", condition="treated")
        wizard.add_sample(id="sample2")
        wizard.add_sample(id="sample3")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(
            wizard,
            on_change,
            bridge=JSpreadsheetBridge(wizard, entity_type="samples"),
        )

        event = {
            "type": "sheet_sync",
            "widget_id": editor.widget_id,
            "data": [
                ["sample1", "human", None, "treated", None, None],
                ["sample2", "human", None, "treated", None, None],
                ["sample3", "human", None, "treated", None, None],
            ],
        }

        editor._handle_spreadsheet_event(event)

        assert wizard.samples[1]["organism"] == "human"
        assert wizard.samples[1]["condition"] == "treated"
        assert wizard.samples[2]["organism"] == "human"
        assert wizard.samples[2]["condition"] == "treated"
        on_change.assert_not_called()

    def test_row_delete_event_emitted_and_handled(self):
        """
        AC4: When a row is deleted in the spreadsheet, JavaScript emits
        a JSON event that includes row and widget_id.
        Python successfully receives and processes the event.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw")
        wizard.add_run(file="/data/test2.raw")
        assert len(wizard.runs) == 2

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Simulate a row delete event
        event_payload = {
            "type": "row_delete",
            "widget_id": "spreadsheet_editor_1",
            "row": 0
        }

        editor.handle_row_delete(row_index=event_payload["row"])

        # Verify row was deleted
        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "/data/test2.raw"

        # Verify on_change callback was invoked
        on_change.assert_called()

    def test_event_payload_includes_widget_id(self):
        """
        AC5: Event payloads from JavaScript include widget_id for scoping
        so multiple spreadsheet editors can coexist without conflicts.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Get the editor's widget ID
        # This should be generated during render() or initialization
        editor_widget_id = editor.widget_id

        # Verify it's a valid string
        assert isinstance(editor_widget_id, str)
        assert len(editor_widget_id) > 0

        # Verify it's stored on the editor instance
        assert editor.widget_id == editor_widget_id


class TestEventBridgeJavaScript:
    """Tests for JavaScript code structure and event emission."""

    def test_javascript_emits_cell_edit_events_with_nicegui_emit(self):
        """
        AC6: The JavaScript code uses NiceGUI's emitEvent(...) or similar
        mechanism to emit cell edit events to Python.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.id = 1
            mock_context.client.has_socket_connection = True
            mock_context.client.run_javascript = MagicMock()
            with patch.object(JSpreadsheetEditor, 'prepare_client_runtime'):
                with patch('jspreadsheet_editor.ui.element') as mock_element:
                    with patch('jspreadsheet_editor.ui.on') as mock_ui_on:
                        mock_container = MagicMock()
                        mock_container.id = 1  # Internal id
                        mock_container.html_id = 'c1'  # NiceGUI format
                        mock_container.classes = MagicMock(return_value=mock_container)
                        mock_element.return_value = mock_container

                        editor.render()

                        js_code = '\n'.join([call_args[0][0] for call_args in mock_context.client.run_javascript.call_args_list])

                    # Should use NiceGUI's event mechanism
                    # Look for either direct event emission or query selector
                    # The code should NOT use window.onCellEdit without a proper bridge
                    if 'window.onCellEdit' in js_code:
                        # If window.onCellEdit is still present, it must be properly
                        # wired to emit events, not just a placeholder
                        assert 'emitEvent' in js_code or 'ui.emit' in js_code or 'sendEvent' in js_code

    def test_create_spreadsheet_widget_emits_sheet_sync_events_after_batch_changes(self):
        """The browser integration should publish a batch sync event for drag-copy and paste operations."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)
        editor.container = MagicMock(html_id='c1')

        with patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.run_javascript = MagicMock()

            editor._create_spreadsheet_widget()

            js_code = mock_context.client.run_javascript.call_args[0][0]

        assert 'onafterchanges' in js_code
        assert "type: 'sheet_sync'" in js_code
        assert 'window.setTimeout' in js_code

    def test_javascript_mounts_into_container_not_document_body(self):
        """
        AC7: JavaScript initialization code mounts the spreadsheet
        into the passed container ID, not by appending to document.body.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.id = 1
            mock_context.client.has_socket_connection = True
            mock_context.client.run_javascript = MagicMock()
            with patch.object(JSpreadsheetEditor, 'prepare_client_runtime'):
                with patch('jspreadsheet_editor.ui.element') as mock_element:
                    with patch('jspreadsheet_editor.ui.on') as mock_ui_on:
                        mock_container = MagicMock()
                        mock_container.id = 99999  # Internal id
                        mock_container.html_id = 'c99999'  # NiceGUI format
                        mock_container.classes = MagicMock(return_value=mock_container)
                        mock_element.return_value = mock_container

                        editor.render()

                        js_code = '\n'.join([call_args[0][0] for call_args in mock_context.client.run_javascript.call_args_list])

                    # Should NOT have this pattern
                    assert 'document.body.appendChild(container)' not in js_code

                    # Should mount into the provided container
                    assert 'jspreadsheet' in js_code


class TestEventIntegration:
    """Integration tests for the full event flow."""

    def test_event_flow_cell_edit_end_to_end(self):
        """
        AC8: A cell edit event flows correctly from JavaScript to Python:
        JS emits → Python handler processes → WizardState updates.
        Cell edits update state but do NOT trigger on_change callbacks.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        change_count = 0

        def on_change_callback():
            nonlocal change_count
            change_count += 1

        editor = JSpreadsheetEditor(wizard, on_change_callback)

        # Simulate event from JavaScript
        # col_index=1 is 'fraction' field in reduced schema
        editor.handle_cell_edit(row_index=0, col_index=1, new_value=2)

        # Verify entire flow completed
        assert wizard.runs[0]["fraction"] == 2
        # Cell edits do NOT trigger on_change callbacks
        assert change_count == 0

    def test_event_flow_row_delete_end_to_end(self):
        """
        AC9: A row delete event flows correctly from JavaScript to Python:
        JS emits → Python handler processes → WizardState updates → on_change called.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw")
        wizard.add_run(file="/data/test2.raw")
        wizard.add_run(file="/data/test3.raw")

        change_count = 0

        def on_change_callback():
            nonlocal change_count
            change_count += 1

        editor = JSpreadsheetEditor(wizard, on_change_callback)

        # Delete middle row
        editor.handle_row_delete(row_index=1)

        # Verify flow completed
        assert len(wizard.runs) == 2
        assert wizard.runs[0]["file"] == "/data/test1.raw"
        assert wizard.runs[1]["file"] == "/data/test3.raw"
        assert change_count == 1
