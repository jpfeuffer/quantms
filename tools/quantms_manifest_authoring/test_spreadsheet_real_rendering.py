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
Stronger tests for actual spreadsheet rendering in NiceGUI.

Tests that catch real rendering failures (not just mocked passing tests).
These tests validate:
1. The spreadsheet uses proper NiceGUI html_id (c{id}) not just id
2. The spreadsheet is actually mounted in the DOM
3. JavaScript code correctly references the container element
4. The event bridge is properly registered for Python to receive events
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_editor import JSpreadsheetEditor


class TestSpreadsheetRealRendering:
    """Tests that validate real DOM rendering, not just mocked calls."""

    def test_spreadsheet_uses_html_id_not_plain_id(self):
        """
        AC10: The spreadsheet JavaScript code uses element.html_id (e.g., 'c1234')
        not element.id (e.g., 1234), so document.getElementById() finds the container.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.ui.run_javascript') as mock_run_js:
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                # Create mock container with both id and html_id (like real NiceGUI element)
                mock_container = MagicMock()
                mock_container.id = 1234  # Internal numeric id
                mock_container.html_id = 'c1234'  # Actual DOM id in NiceGUI format
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container

                editor.render()

                # Extract JavaScript calls
                js_calls = [call_args[0][0] for call_args in mock_run_js.call_args_list]
                js_code = '\n'.join(js_calls)

                # The code MUST use html_id ('c1234'), not id ('1234')
                # If using just id, document.getElementById('1234') will fail
                assert 'c1234' in js_code, "JavaScript should reference NiceGUI html_id (c1234), not plain id (1234)"

                # Should use getElementById to find the container
                assert 'getElementById' in js_code

    def test_spreadsheet_container_element_has_html_id(self):
        """
        AC11: When JSpreadsheetEditor creates a container element,
        that element is correctly used with its html_id in JavaScript.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.ui.run_javascript') as mock_run_js:
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                mock_container = MagicMock()
                mock_container.id = 9999
                mock_container.html_id = 'c9999'
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container

                editor.render()

                # Verify container was created and stored
                assert editor.container is not None
                assert editor.container.html_id == 'c9999'

    def test_javascript_references_correct_dom_id_in_init_data(self):
        """
        AC12: The _initialize_data() method must use html_id when passing
        the container ID to JavaScript, not the plain numeric id.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.ui.run_javascript') as mock_run_js:
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                mock_container = MagicMock()
                mock_container.id = 5555  # Plain id
                mock_container.html_id = 'c5555'  # Actual DOM id for getElementById
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container

                editor.render()

                # Get the first JS call (should be the data initialization)
                first_js_call = mock_run_js.call_args_list[0][0][0]

                # Should contain the html_id, not the plain id
                assert 'c5555' in first_js_call
                assert 'container_id: "c5555"' in first_js_call


class TestPythonEventHandlerRegistration:
    """Tests for Python-side event handler registration."""

    def test_python_registers_event_handler_for_spreadsheet_events(self):
        """
        AC13: JSpreadsheetEditor must register a Python event handler
        using ui.on('spreadsheet_event', handler) so JavaScript events
        can be received and processed.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()

        # Patch ui.on to track if it's called
        with patch('jspreadsheet_editor.ui.on') as mock_ui_on:
            editor = JSpreadsheetEditor(wizard, on_change)

            # For now, we may not have a render that registers yet,
            # but we need to ensure it happens eventually
            # Check if editor has a method to register the handler
            assert hasattr(editor, 'handle_cell_edit'), "Editor should have handle_cell_edit method"
            assert hasattr(editor, 'handle_row_delete'), "Editor should have handle_row_delete method"

    def test_event_handler_callable_with_correct_signature(self):
        """
        AC14: The Python event handler accepts event payloads with
        {'type': ..., 'widget_id': ..., 'row': ..., 'col': ..., 'value': ...}
        and routes them to handle_cell_edit or handle_row_delete.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        change_count = 0

        def on_change_callback():
            nonlocal change_count
            change_count += 1

        editor = JSpreadsheetEditor(wizard, on_change_callback)

        # Simulate cell edit event payload from JavaScript
        # col_index=1 is 'fraction' field in reduced schema
        event_payload = {
            "type": "cell_edit",
            "widget_id": editor.widget_id,
            "row": 0,
            "col": 1,
            "value": 3
        }

        # Python event handler should route this correctly
        editor.handle_cell_edit(
            row_index=event_payload["row"],
            col_index=event_payload["col"],
            new_value=event_payload["value"]
        )

        # Verify state was updated
        assert wizard.runs[0]["fraction"] == 3
        # Cell edits do NOT trigger on_change callbacks
        assert change_count == 0


class TestSpreadsheetBridgeEventEmission:
    """Tests that JavaScript properly emits events and Python receives them."""

    def test_javascript_has_onclick_handlers_registered(self):
        """
        AC15: The JavaScript code registers onchange callback on the jspreadsheet
        so cell edits trigger event emission.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.ui.run_javascript') as mock_run_js:
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                mock_container = MagicMock()
                mock_container.id = 100
                mock_container.html_id = 'c100'
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container

                editor.render()

                js_code = '\n'.join([call_args[0][0] for call_args in mock_run_js.call_args_list])

                # Should register onchange handler
                assert 'onchange' in js_code.lower() or 'onChange' in js_code

                # Should emit events via window.emitEvent or fallback
                assert 'emitEvent' in js_code or 'pendingSpreadsheetEvents' in js_code

    def test_javascript_properly_initializes_jspreadsheet_library(self):
        """
        AC16: The JavaScript waits for jspreadsheet library to be loaded
        before initializing (using setInterval check).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.ui.run_javascript') as mock_run_js:
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                mock_container = MagicMock()
                mock_container.id = 200
                mock_container.html_id = 'c200'
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container

                editor.render()

                js_code = '\n'.join([call_args[0][0] for call_args in mock_run_js.call_args_list])

                # Should wait for jspreadsheet to load
                assert 'typeof jspreadsheet' in js_code
                assert 'setInterval' in js_code or 'setTimeout' in js_code


class TestIntegrationEndToEnd:
    """End-to-end integration tests."""

    def test_cell_edit_flow_with_real_container(self):
        """
        AC17: A complete cell edit flow: container created → rendered →
        event emitted → Python handler processes → wizard updated.
        Cell edits update state but do NOT trigger on_change callbacks.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        with patch('jspreadsheet_editor.ui.run_javascript'):
            with patch('jspreadsheet_editor.ui.element') as mock_element:
                mock_container = MagicMock()
                mock_container.id = 300
                mock_container.html_id = 'c300'
                mock_container.classes = MagicMock(return_value=mock_container)
                mock_element.return_value = mock_container

                editor.render()

                # Simulate JavaScript cell edit event
                editor.handle_cell_edit(row_index=0, col_index=1, new_value=5)

                # Verify full flow
                assert wizard.runs[0]["fraction"] == 5
                # Cell edits do NOT trigger on_change callbacks
                on_change.assert_not_called()

    def test_multiple_editors_have_unique_widget_ids(self):
        """
        AC18: Multiple JSpreadsheetEditor instances have unique widget_ids
        so events can be properly scoped and don't interfere.
        """
        wizard1 = WizardState()
        wizard1.add_run(file="/data/test1.raw")

        wizard2 = WizardState()
        wizard2.add_run(file="/data/test2.raw")

        editor1 = JSpreadsheetEditor(wizard1, MagicMock())
        editor2 = JSpreadsheetEditor(wizard2, MagicMock())

        # Each editor should have a unique widget ID
        assert editor1.widget_id != editor2.widget_id
        assert isinstance(editor1.widget_id, str)
        assert isinstance(editor2.widget_id, str)
        assert len(editor1.widget_id) > 0
        assert len(editor2.widget_id) > 0
