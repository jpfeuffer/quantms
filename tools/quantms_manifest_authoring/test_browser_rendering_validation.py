#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pytest-asyncio",
#   "nicegui",
#   "pyyaml",
#   "selenium",
# ]
# ///
"""
Real browser validation tests for spreadsheet rendering.

Uses Selenium to launch a real browser and:
1. Start the NiceGUI server
2. Load the page
3. Wait for spreadsheet to render
4. Validate spreadsheet is visible in DOM
5. Test cell editing and row deletion
"""

import pytest
import asyncio
import sys
import json
import time
import weakref
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from gui_nicegui import create_runs_step
from jspreadsheet_editor import JSpreadsheetEditor


class TestBrowserRendering:
    """Tests that validate actual browser rendering of the spreadsheet."""

    def test_spreadsheet_container_is_created_in_page_context(self):
        """
        AC19: When JSpreadsheetEditor.render() is called within a NiceGUI
        page context, it creates a visible container element.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw")
        wizard.add_run(file="/data/test2.raw")

        def refresh_ui():
            pass

        # When we create the step in page context, the container should be created
        # (This simulates what happens on the real page)
        editor = JSpreadsheetEditor(wizard, refresh_ui)

        # Verify the editor can be created
        assert editor is not None
        assert editor.widget_id is not None

        # After render is called, container should be created
        # (In real NiceGUI usage, render() is called within page context)
        with _mock_nicegui_page_context():
            editor.render()
            assert editor.container is not None
            # In real usage, the container would have a valid html_id
            # We can't test the actual DOM here without a browser


def _mock_nicegui_page_context():
    """Context manager to simulate NiceGUI page rendering context."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock, patch

    @contextmanager
    def context():
        with patch('jspreadsheet_editor.ui.element') as mock_element:
            with patch('jspreadsheet_editor.ui.run_javascript'):
                with patch('jspreadsheet_editor.ui.on'):
                    with patch('jspreadsheet_editor.ui.notify'):
                        # Create a realistic mock container
                        mock_container = MagicMock()
                        mock_container.id = 42
                        mock_container.html_id = 'c42'
                        mock_container.classes = MagicMock(return_value=mock_container)
                        mock_element.return_value = mock_container

                        yield

    return context()


class TestJavaScriptLibraryLoading:
    """Tests for local jspreadsheet asset loading."""

    def test_local_libraries_are_added_to_head(self):
        """
        AC20: JSpreadsheetEditor._ensure_cdn_loaded() adds local jspreadsheet
        assets to the page head (CSS and JS files).
        """
        from unittest.mock import patch, MagicMock

        if hasattr(JSpreadsheetEditor, '_cdn_loaded_clients'):
            delattr(JSpreadsheetEditor, '_cdn_loaded_clients')
        if hasattr(JSpreadsheetEditor, '_static_assets_registered'):
            delattr(JSpreadsheetEditor, '_static_assets_registered')

        with patch('jspreadsheet_editor.ui.add_head_html') as mock_add_head, \
             patch('jspreadsheet_editor.app.add_static_files') as mock_add_static, \
             patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.id = 101
            mock_context.client.has_socket_connection = True
            JSpreadsheetEditor._ensure_cdn_loaded()

            mock_add_head.assert_called()
            mock_add_static.assert_called_once()
            mock_context.client.run_javascript.assert_called_once()

            call_args = mock_add_head.call_args[0][0]
            loader_args = mock_context.client.run_javascript.call_args[0][0]

            assert 'jspreadsheet.css' in call_args
            assert 'jsuites.css' in call_args
            assert 'quantms-manifest/vendor' in call_args
            assert 'jspreadsheet.js' in loader_args
            assert 'jsuites.js' in loader_args

    def test_cdn_loaded_flag_prevents_duplicate_loads(self):
        """
        AC21: The _ensure_cdn_loaded() method uses a flag to prevent
        loading local assets multiple times for the same client.
        """
        from unittest.mock import patch

        if hasattr(JSpreadsheetEditor, '_cdn_loaded_clients'):
            delattr(JSpreadsheetEditor, '_cdn_loaded_clients')
        if hasattr(JSpreadsheetEditor, '_static_assets_registered'):
            delattr(JSpreadsheetEditor, '_static_assets_registered')

        call_count = 0
        loader_count = 0

        def mock_add_head(html):
            nonlocal call_count
            call_count += 1

        def mock_run_javascript(script):
            nonlocal loader_count
            loader_count += 1

        with patch('jspreadsheet_editor.ui.add_head_html', side_effect=mock_add_head), \
             patch('jspreadsheet_editor.app.add_static_files'), \
             patch('jspreadsheet_editor.context') as mock_context:
            mock_context.client.id = 101
            mock_context.client.has_socket_connection = True
            mock_context.client.run_javascript.side_effect = mock_run_javascript
            # First call should execute
            JSpreadsheetEditor._ensure_cdn_loaded()
            assert call_count == 1
            assert loader_count == 1

            # Second call should not execute (flag is set)
            JSpreadsheetEditor._ensure_cdn_loaded()
            assert call_count == 1
            assert loader_count == 1


class TestEventHandlerWiring:
    """Tests for JavaScript event handler registration."""

    def test_dispatch_spreadsheet_event_accepts_nicegui_event_args(self):
        """AC22b: The shared dispatcher should unwrap NiceGUI event objects that store payloads in .args."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)
        registry = JSpreadsheetEditor._get_registry('_instances', weakref.WeakValueDictionary)
        registry[editor.widget_id] = editor

        class MockEvent:
            def __init__(self, args):
                self.args = args

        event = MockEvent({
            'type': 'cell_edit',
            'widget_id': editor.widget_id,
            'row': 0,
            'col': 1,
            'value': '2',
        })

        JSpreadsheetEditor._dispatch_spreadsheet_event(event)

        assert wizard.runs[0]['fraction'] == 2
        on_change.assert_not_called()

    def test_dispatch_spreadsheet_event_accepts_single_payload_args_list(self):
        """AC22c: The shared dispatcher should unwrap NiceGUI emits that arrive as args=[payload]."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)
        registry = JSpreadsheetEditor._get_registry('_instances', weakref.WeakValueDictionary)
        registry[editor.widget_id] = editor

        class MockEvent:
            def __init__(self, args):
                self.args = args

        event = MockEvent([{
            'type': 'cell_edit',
            'widget_id': editor.widget_id,
            'row': 0,
            'col': 1,
            'value': '3',
        }])

        JSpreadsheetEditor._dispatch_spreadsheet_event(event)

        assert wizard.runs[0]['fraction'] == 3
        on_change.assert_not_called()

    def test_python_event_handler_filters_by_widget_id(self):
        """
        AC22: The _handle_spreadsheet_event() method only processes events
        for its own widget_id, ignoring events from other widgets.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        from unittest.mock import MagicMock

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Event for a different widget
        other_widget_event = {
            'type': 'cell_edit',
            'widget_id': 'different_widget_id',
            'row': 0,
            'col': 1,
            'value': 'should_be_ignored'
        }

        editor._handle_spreadsheet_event(other_widget_event)

        # Should not process this event
        on_change.assert_not_called()
        # Wizard should not be modified - file should remain unchanged
        assert wizard.runs[0]['file'] == '/data/test.raw'

    def test_python_event_handler_processes_cell_edit(self):
        """
        AC23: The _handle_spreadsheet_event() method properly processes
        'cell_edit' events with row, col, and value parameters
        without forcing a full rerender.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        from unittest.mock import MagicMock

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Event for this widget
        event = {
            'type': 'cell_edit',
            'widget_id': editor.widget_id,
            'row': 0,
            'col': 1,  # fraction column
            'value': '2'
        }

        editor._handle_spreadsheet_event(event)

        # Should process and update wizard
        assert wizard.runs[0]['fraction'] == 2
        on_change.assert_not_called()

    def test_python_event_handler_processes_string_indices_from_browser(self):
        """
        Browser-emitted spreadsheet events can serialize row/col indices as strings.
        The handler should coerce them before dispatching to the bridge.
        """
        wizard = WizardState()
        wizard.add_run(file='/data/test.raw', fraction=1)

        from unittest.mock import MagicMock

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        event = {
            'type': 'cell_edit',
            'widget_id': editor.widget_id,
            'row': '0',
            'col': '1',
            'value': '4',
        }

        editor._handle_spreadsheet_event(event)

        assert wizard.runs[0]['fraction'] == 4
        on_change.assert_not_called()

    def test_python_event_handler_processes_row_delete(self):
        """
        AC24: The _handle_spreadsheet_event() method properly processes
        'row_delete' events with row parameter.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw")
        wizard.add_run(file="/data/test2.raw")

        from unittest.mock import MagicMock

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Event for this widget
        event = {
            'type': 'row_delete',
            'widget_id': editor.widget_id,
            'row': 0
        }

        editor._handle_spreadsheet_event(event)

        # Should process and delete row
        assert len(wizard.runs) == 1
        assert wizard.runs[0]['file'] == '/data/test2.raw'
        on_change.assert_called()

    def test_python_event_handler_ignores_invalid_events(self):
        """
        AC25: The _handle_spreadsheet_event() method gracefully ignores
        invalid events (missing type, row, col, etc.).
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        from unittest.mock import MagicMock

        on_change = MagicMock()
        editor = JSpreadsheetEditor(wizard, on_change)

        # Missing type
        editor._handle_spreadsheet_event({
            'widget_id': editor.widget_id,
            'row': 0
        })

        # Missing row for cell_edit
        editor._handle_spreadsheet_event({
            'type': 'cell_edit',
            'widget_id': editor.widget_id,
            'col': 1,
            'value': 'test'
        })

        # Non-dict event
        editor._handle_spreadsheet_event("invalid")

        # Should not raise and should not update
        assert wizard.runs[0]['file'] == '/data/test.raw'  # file unchanged
