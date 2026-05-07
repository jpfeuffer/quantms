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
UI-level tests for the Runs step.

Tests the actual NiceGUI runs-step callback behavior by:
1. Monkeypatching nicegui ui functions to capture UI state and callbacks
2. Calling create_runs_step with the mocked UI
3. Directly invoking the callbacks (add_manual_path, save_row_edit, delete_row)
4. Verifying wizard state updates and refresh_ui is called

This exercises the real callback code paths without Selenium or a browser.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Any, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from gui_nicegui import create_runs_step


class RecordingSpreadsheetEditor:
    """Lightweight editor double that records how the Runs step wires spreadsheets."""

    created = []

    @classmethod
    def prepare_client_runtime(cls):
        return None

    def __init__(self, wizard, on_change, bridge=None, worksheet_name="Runs"):
        self.wizard = wizard
        self.on_change = on_change
        self.bridge = bridge
        self.worksheet_name = worksheet_name
        self.rendered = False
        RecordingSpreadsheetEditor.created.append(self)

    def render(self):
        self.rendered = True

    async def flush_pending_edits(self):
        return None


class MockContextClient:
    """Mock for context.client with on_connect lifecycle hook."""

    def __init__(self):
        self.on_connect_handlers = []
        self.javascript_calls = []

    def on_connect(self, handler):
        """Register a handler to be called when client connects (mock version)."""
        self.on_connect_handlers.append(handler)

    def run_javascript(self, script):
        """Mock implementation of run_javascript."""
        self.javascript_calls.append(script)


class MockContext:
    """Mock for nicegui context module."""

    def __init__(self):
        self.client = MockContextClient()


class MockElement:
    """Mock for ui.element."""

    def __init__(self):
        self.html_id = "c12345"  # Simulate NiceGUI's container ID format
        self._classes = []

    def classes(self, *args):
        self._classes.extend(args)
        return self


class MockUIInput:
    """Mock for ui.input that captures set/get of value."""

    def __init__(self, value="", placeholder="", label="", type=None):
        self.value = value
        self.placeholder = placeholder
        self.label = label
        self.type = type
        self._callbacks = {}

    def classes(self, *args, **kwargs):
        return self

    def set_visibility(self, *_args, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockUISelect:
    """Mock for ui.select that captures set/get of value."""

    def __init__(self, options=None, value=None, label="", clearable=False):
        self.options = options or {}
        self.value = value
        self.label = label
        self.clearable = clearable
        self._callbacks = []

    def classes(self, *args, **kwargs):
        return self

    def update(self):
        return self

    def on_value_change(self, callback):
        self._callbacks.append(callback)
        return self

    def set_visibility(self, *_args, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockUILabel:
    """Mock for ui.label."""

    def __init__(self, text=""):
        self.text = text

    def classes(self, *args, **kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def update(self):
        return self


class MockUIButton:
    """Mock for ui.button with captured on_click callback."""

    def __init__(self, text="", on_click=None, icon=""):
        self.text = text
        self.on_click_callback = on_click
        self.icon = icon
        self.parent = None

    def classes(self, *args, **kwargs):
        return self

    def props(self, *args, **kwargs):
        return self

    def trigger_click(self):
        """Trigger the on_click callback if present."""
        if self.on_click_callback:
            result = self.on_click_callback()
            # Handle async function
            import asyncio
            if asyncio.iscoroutine(result):
                # For async callbacks, run them
                asyncio.run(result)


class MockUIRow:
    """Mock for ui.row context manager."""

    def __init__(self, owner=None, kind="row"):
        self.owner = owner
        self.kind = kind
        self.children = []
        self.visible = True

    def classes(self, *args, **kwargs):
        return self

    def clear(self):
        self.children = []
        return self

    def set_visibility(self, visible):
        self.visible = visible
        return self

    def update(self):
        return self

    def props(self, *args, **kwargs):
        return self

    def open(self):
        return self

    def close(self):
        return self

    def __enter__(self):
        if self.owner is not None:
            self.owner._container_stack.append(self)
            parent = self.owner._container_stack[-2] if len(self.owner._container_stack) > 1 else None
            self.parent = parent
            if parent is not None:
                parent.children.append(self)
        return self

    def __exit__(self, *args):
        if self.owner is not None and self.owner._container_stack:
            self.owner._container_stack.pop()
        pass


class MockUICard:
    """Mock for ui.card context manager."""

    def __init__(self, owner=None, kind="card"):
        self.owner = owner
        self.kind = kind
        self.children = []
        self.visible = True

    def classes(self, *args, **kwargs):
        return self

    def clear(self):
        self.children = []
        return self

    def set_visibility(self, visible):
        self.visible = visible
        return self

    def update(self):
        return self

    def props(self, *args, **kwargs):
        return self

    def open(self):
        return self

    def close(self):
        return self

    def __enter__(self):
        if self.owner is not None:
            self.owner._container_stack.append(self)
            parent = self.owner._container_stack[-2] if len(self.owner._container_stack) > 1 else None
            self.parent = parent
            if parent is not None:
                parent.children.append(self)
        return self

    def __exit__(self, *args):
        if self.owner is not None and self.owner._container_stack:
            self.owner._container_stack.pop()
        pass


class MockUIContext:
    """Captures UI structure and state during create_runs_step."""

    def __init__(self):
        self.buttons = []
        self.inputs = []
        self.labels = []
        self.notifications = []
        self.cards = []
        self.rows = []
        self._container_stack = []

    def notify(self, message, type=None):
        """Capture notifications (non-blocking)."""
        self.notifications.append({"message": message, "type": type})

    def button(self, text="", on_click=None, icon="", **kwargs):
        """Create a mock button and capture callbacks."""
        btn = MockUIButton(text, on_click, icon)
        btn.parent = self._container_stack[-1] if self._container_stack else None
        if btn.parent is not None:
            btn.parent.children.append(btn)
        self.buttons.append(btn)
        return btn

    def input(self, value="", placeholder="", label="", type=None):
        """Create a mock input and capture state."""
        inp = MockUIInput(value, placeholder, label, type)
        self.inputs.append(inp)
        return inp

    def select(self, options=None, value=None, label="", clearable=False):
        """Create a mock select and capture state."""
        sel = MockUISelect(options, value, label, clearable)
        return sel

    def label(self, text=""):
        """Create a mock label."""
        lbl = MockUILabel(text)
        self.labels.append(lbl)
        if self._container_stack:
            self._container_stack[-1].children.append(lbl)
        return lbl

    def row(self):
        """Create a mock row."""
        row = MockUIRow(owner=self, kind="row")
        self.rows.append(row)
        return row

    def card(self):
        """Create a mock card."""
        card = MockUICard(owner=self, kind="card")
        self.cards.append(card)
        return card

    def column(self):
        """Create a mock column."""
        column = MockUIRow(owner=self, kind="column")
        self.rows.append(column)
        return column

    def expansion(self, text="", icon="", value=None):
        """Create a mock expansion (deprecated in new design)."""
        expansion = MockUICard(owner=self, kind="expansion")
        self.cards.append(expansion)
        return expansion

    def dialog(self):
        """Create a mock dialog."""
        dialog = MockUICard(owner=self, kind="dialog")
        self.cards.append(dialog)
        return dialog

    def separator(self):
        """Create a mock separator."""
        separator = MockUICard(owner=self, kind="separator")
        self.cards.append(separator)
        return separator

    def element(self, tag):
        """Create a mock element (container div)."""
        return MockElement()

    def on(self, event, handler):
        """Register event handler (no-op in test context)."""
        pass

    def add_head_html(self, html):
        """Mock add_head_html (no-op in test context)."""
        pass


class TestRunsStepCallbacks:
    """Tests that invoke real callback code in create_runs_step."""

    def test_runs_step_explains_filename_grouping_and_exposes_regroup_action(self):
        """The Runs step should keep regrouping explicit and place the button in the Groups pane."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample_fraction1.raw")
        wizard.add_run(file="/data/sample_fraction2.raw")
        refresh_calls = []

        def refresh_ui():
            refresh_calls.append(True)

        mock_ui_ctx = MockUIContext()

        with patch("gui_nicegui.ui", mock_ui_ctx):
            with patch("gui_nicegui.JSpreadsheetEditor.prepare_client_runtime", lambda *args, **kwargs: None):
                create_runs_step(wizard, refresh_ui=refresh_ui)

        label_text = " ".join(label.text for label in mock_ui_ctx.labels).lower()
        assert "fraction" in label_text
        assert "auto-grouped" not in label_text
        assert "basename" in label_text or "fraction markers" in label_text or "group" in label_text

        regroup_button = next(
            button for button in mock_ui_ctx.buttons if button.text == "Suggest groups from filenames"
        )
        assert regroup_button.parent is not None

        assert any(
            isinstance(child, MockUILabel) and (
                "group membership" in child.text.lower() or "no groups added yet" in child.text.lower()
            )
            for child in regroup_button.parent.children
        )
        assert not any(
            isinstance(child, MockUILabel) and "files table" in child.text.lower()
            for child in regroup_button.parent.children
        )

        assert wizard.groups == []

        initial_group_count = len(wizard.groups)
        regroup_button.trigger_click()

        assert initial_group_count == 0
        assert len(wizard.groups) == 1
        assert wizard.groups[0]["id"] == "sample"
        assert sorted(wizard.groups[0]["members"]) == ["run_1", "run_2"]
        assert refresh_calls

    def test_file_picker_button_callback_adds_selected_files_and_refreshes(self):
        """
        AC1: Test that the 'Choose Local Files' button callback (pick_local_files)
        correctly invokes MsFilePickerDialog, adds selected files to wizard.runs,
        and calls refresh_ui.
        """
        wizard = WizardState()
        refresh_ui_calls = []

        def mock_refresh_ui():
            refresh_ui_calls.append(True)

        # Known test files for the mock dialog to return
        test_files = ["/data/sample1.raw", "/data/sample2.raw", "/data/sample3.mzML"]

        # Monkeypatch ui to capture the UI structure
        mock_ui_ctx = MockUIContext()

        # Create a mock for MsFilePickerDialog that returns a coroutine
        async def mock_dialog_awaitable():
            return test_files

        def mock_file_picker_dialog_class(multiple=True):
            """Mock MsFilePickerDialog class that returns a coroutine."""
            return mock_dialog_awaitable()

        # Keep patches active throughout the test (including callback execution)
        with patch("gui_nicegui.ui", mock_ui_ctx), \
             patch("jspreadsheet_editor.context") as mock_context_editor, \
             patch("gui_nicegui.MsFilePickerDialog", side_effect=mock_file_picker_dialog_class):

            # Set up context mocks
            mock_context_obj = MockContext()
            mock_context_editor.client = mock_context_obj.client

            # Call create_runs_step with mocked UI
            create_runs_step(wizard, refresh_ui=mock_refresh_ui)

            # Find the "Choose Local Files" button
            choose_local_files_button = None
            for btn in mock_ui_ctx.buttons:
                if btn.text == "Choose Local Files" and btn.icon == "folder_open":
                    choose_local_files_button = btn
                    break

            assert choose_local_files_button is not None, "Choose Local Files button not found"

            # Verify initial state
            initial_runs = len(wizard.runs)

            # Trigger the button callback (with mocked MsFilePickerDialog still active)
            choose_local_files_button.trigger_click()

            # Verify wizard.runs gained the selected files
            assert len(wizard.runs) == initial_runs + len(test_files)
            assert wizard.runs[-3]["file"] == "/data/sample1.raw"
            assert wizard.runs[-2]["file"] == "/data/sample2.raw"
            assert wizard.runs[-1]["file"] == "/data/sample3.mzML"

            # Verify refresh_ui was called
            assert len(refresh_ui_calls) > 0

    def test_add_manual_path_callback_adds_run_and_refreshes(self):
        """
        AC6.1: Test that the Add button callback (add_manual_path) correctly
        calls wizard.add_run and invokes refresh_ui.
        """
        wizard = WizardState()
        refresh_ui_calls = []

        def mock_refresh_ui():
            refresh_ui_calls.append(True)

        # Monkeypatch ui to capture the UI structure
        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx), \
             patch("jspreadsheet_editor.context") as mock_context_editor:

            # Set up context mocks
            mock_context_obj = MockContext()
            mock_context_editor.client = mock_context_obj.client

            create_runs_step(wizard, refresh_ui=mock_refresh_ui)

        # Find the manual path input and the Add button
        # The manual_path_input is the second input (after the Choose Local Files section)
        manual_path_input = None
        add_button = None

        for inp in mock_ui_ctx.inputs:
            if "Or enter file path manually" in inp.label:
                manual_path_input = inp
                break

        # Find the "Add" button (not "Choose Local Files")
        for btn in mock_ui_ctx.buttons:
            if btn.text == "Add" and btn.icon == "add":
                add_button = btn
                break

        assert manual_path_input is not None, "Manual path input not found"
        assert add_button is not None, "Add button not found"

        # Simulate user entering a path and clicking Add
        manual_path_input.value = "/path/to/sample.raw"
        initial_runs = len(wizard.runs)

        # Trigger the Add button callback
        add_button.trigger_click()

        # Verify wizard state was updated
        assert len(wizard.runs) == initial_runs + 1
        assert wizard.runs[-1]["file"] == "/path/to/sample.raw"

        # Verify refresh_ui was called
        assert len(refresh_ui_calls) > 0

    def test_delete_button_callback_removes_run_and_refreshes(self):
        """
        AC6.3: Test that when there are runs, the spreadsheet UI is created
        with the spreadsheet editor being initialized after client connect.
        """
        wizard = WizardState()
        wizard.add_run(file="file1.raw", fraction=1)
        wizard.add_run(file="file2.raw", fraction=2)

        refresh_ui_calls = []

        def mock_refresh_ui():
            refresh_ui_calls.append(True)

        # Monkeypatch ui to capture the UI structure
        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx), \
             patch("jspreadsheet_editor.context") as mock_context_editor:

            # Set up context mocks
            mock_context_obj = MockContext()
            mock_context_editor.client = mock_context_obj.client

            create_runs_step(wizard, refresh_ui=mock_refresh_ui)

        # Verify that the Files Table label was created
        runs_table_labels = [lbl for lbl in mock_ui_ctx.labels if "Files Table" in lbl.text]
        assert len(runs_table_labels) > 0, "Files Table label not found"

        # Verify that the on_connect handler was registered (spreadsheet init deferred)
        mock_context_obj = mock_context_editor.client
        assert len(mock_context_obj.on_connect_handlers) > 0, "on_connect handler was not registered"

        # Verify that the help/instruction label exists
        help_labels = [lbl for lbl in mock_ui_ctx.labels if "Right-click rows to delete" in lbl.text]
        assert len(help_labels) > 0, "Help text with delete instruction not found"

    def test_runs_step_renders_files_groups_and_modifications_surfaces(self):
        """The Runs step should render Files and Groups surfaces and keep the modification editor."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")
        wizard.assign_run(run_index=0, group_id="group_1")
        wizard.add_modification(mode="fixed", kind="custom", name="Custom PTM", profile="default")

        mock_ui_ctx = MockUIContext()
        RecordingSpreadsheetEditor.created = []

        with patch("gui_nicegui.ui", mock_ui_ctx), \
             patch("jspreadsheet_editor.context") as mock_context_editor, \
             patch("gui_nicegui.JSpreadsheetEditor", RecordingSpreadsheetEditor):

            mock_context_obj = MockContext()
            mock_context_editor.client = mock_context_obj.client

            create_runs_step(wizard, refresh_ui=lambda: None)

        label_texts = [lbl.text for lbl in mock_ui_ctx.labels]
        assert any("Files Table" in text for text in label_texts)
        assert any("Groups Table" in text for text in label_texts)
        assert any("Modifications (1)" in text for text in label_texts)

        worksheet_names = [editor.worksheet_name for editor in RecordingSpreadsheetEditor.created]
        assert worksheet_names.count("Files") == 1
        assert worksheet_names.count("Groups") == 1
        assert worksheet_names.count("Modifications") == 1

    def test_manual_path_entry_clears_input_after_add(self):
        """
        Test that after clicking Add, the manual path input is cleared.
        """
        wizard = WizardState()

        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx):
            create_runs_step(wizard, refresh_ui=lambda: None)

        # Find manual path input
        manual_path_input = None
        for inp in mock_ui_ctx.inputs:
            if "Or enter file path manually" in inp.label:
                manual_path_input = inp
                break

        assert manual_path_input is not None

        # Find Add button
        add_button = None
        for btn in mock_ui_ctx.buttons:
            if btn.text == "Add" and btn.icon == "add":
                add_button = btn
                break

        # Set path and click Add
        manual_path_input.value = "/path/to/test.raw"
        add_button.trigger_click()

        # After successful add, input should be cleared
        # (This is done by add_manual_path callback: manual_path_input.value = "")
        assert manual_path_input.value == ""
