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


class MockUIButton:
    """Mock for ui.button with captured on_click callback."""
    
    def __init__(self, text="", on_click=None, icon=""):
        self.text = text
        self.on_click_callback = on_click
        self.icon = icon
    
    def classes(self, *args, **kwargs):
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
    
    def __init__(self):
        self.children = []
    
    def classes(self, *args, **kwargs):
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


class MockUICard:
    """Mock for ui.card context manager."""
    
    def __init__(self):
        self.children = []
    
    def classes(self, *args, **kwargs):
        return self
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        pass


class MockUIContext:
    """Captures UI structure and state during create_runs_step."""
    
    def __init__(self):
        self.buttons = []
        self.inputs = []
        self.labels = []
        self.notifications = []
    
    def notify(self, message, type=None):
        """Capture notifications (non-blocking)."""
        self.notifications.append({"message": message, "type": type})
    
    def button(self, text="", on_click=None, icon=""):
        """Create a mock button and capture callbacks."""
        btn = MockUIButton(text, on_click, icon)
        self.buttons.append(btn)
        return btn
    
    def input(self, value="", placeholder="", label="", type=None):
        """Create a mock input and capture state."""
        inp = MockUIInput(value, placeholder, label, type)
        self.inputs.append(inp)
        return inp
    
    def label(self, text=""):
        """Create a mock label."""
        lbl = MockUILabel(text)
        self.labels.append(lbl)
        return lbl
    
    def row(self):
        """Create a mock row."""
        return MockUIRow()
    
    def card(self):
        """Create a mock card."""
        return MockUICard()
    
    def column(self):
        """Create a mock column."""
        return MockUIRow()
    
    def expansion(self, text="", icon=""):
        """Create a mock expansion (deprecated in new design)."""
        return MockUICard()


class TestRunsStepCallbacks:
    """Tests that invoke real callback code in create_runs_step."""

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
             patch("gui_nicegui.MsFilePickerDialog", side_effect=mock_file_picker_dialog_class):
            
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
        with patch("gui_nicegui.ui", mock_ui_ctx):
            # Call create_runs_step with mocked UI
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
    
    def test_save_button_callback_clears_fraction_to_none(self):
        """
        AC6.2: Test that the Save button callback (save_row_edit) correctly
        handles empty fraction field as None, not "None" string.
        """
        wizard = WizardState()
        wizard.add_run(file="data.raw", fraction=5)
        
        refresh_ui_calls = []
        
        def mock_refresh_ui():
            refresh_ui_calls.append(True)
        
        # Monkeypatch ui to capture the UI structure
        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx):
            create_runs_step(wizard, refresh_ui=mock_refresh_ui)
        
        # Find the fraction input (should be created for the first run)
        # Find inputs that look like the fraction input (type="number")
        fraction_inputs = [inp for inp in mock_ui_ctx.inputs if inp.type == "number"]
        assert len(fraction_inputs) > 0, "No fraction inputs found"
        
        fraction_input = fraction_inputs[0]
        # Initial value should be "5"
        assert fraction_input.value == "5"
        
        # Find the Save button for the first row
        save_buttons = [btn for btn in mock_ui_ctx.buttons if btn.text == "Save"]
        assert len(save_buttons) > 0, "No Save button found"
        
        save_button = save_buttons[0]
        
        # Simulate user clearing the fraction field
        fraction_input.value = ""
        file_inputs = [inp for inp in mock_ui_ctx.inputs if inp.placeholder == "File path"]
        assert len(file_inputs) > 0
        file_input = file_inputs[0]
        file_input.value = "data.raw"
        
        # Trigger the Save button callback
        save_button.trigger_click()
        
        # Verify fraction was set to None, not "None"
        assert wizard.runs[0]["fraction"] is None
        assert wizard.runs[0]["fraction"] != "None"
        assert wizard.runs[0]["fraction"] != ""
    
    def test_delete_button_callback_removes_run_and_refreshes(self):
        """
        AC6.3: Test that the Delete button callback (delete_row) correctly
        removes the run from wizard and calls refresh_ui.
        """
        wizard = WizardState()
        wizard.add_run(file="file1.raw", fraction=1)
        wizard.add_run(file="file2.raw", fraction=2)
        
        refresh_ui_calls = []
        
        def mock_refresh_ui():
            refresh_ui_calls.append(True)
        
        # Monkeypatch ui to capture the UI structure
        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx):
            create_runs_step(wizard, refresh_ui=mock_refresh_ui)
        
        # Find the first Delete button
        delete_buttons = [btn for btn in mock_ui_ctx.buttons if btn.text == "Delete"]
        assert len(delete_buttons) > 0, "No Delete button found"
        
        delete_button = delete_buttons[0]
        
        # Trigger the first Delete button callback
        initial_runs = len(wizard.runs)
        delete_button.trigger_click()
        
        # Verify run was removed
        assert len(wizard.runs) == initial_runs - 1
        assert wizard.runs[0]["file"] == "file2.raw"
        
        # Verify refresh_ui was called
        assert len(refresh_ui_calls) > 0
    
    def test_fraction_input_initialization_renders_none_as_empty_string(self):
        """
        AC6.4: Test that the fraction input initializer renders None fraction
        as empty string, not "None" string (the fix in gui_nicegui.py).
        """
        wizard = WizardState()
        wizard.add_run(file="data.raw", fraction=None)
        
        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx):
            create_runs_step(wizard, refresh_ui=lambda: None)
        
        # Find the fraction input
        fraction_inputs = [inp for inp in mock_ui_ctx.inputs if inp.type == "number"]
        assert len(fraction_inputs) > 0
        
        fraction_input = fraction_inputs[0]
        
        # Verify it's initialized as empty string, not "None"
        assert fraction_input.value == ""
        assert fraction_input.value != "None"
    
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
    
    def test_multiple_runs_edit_independent_rows(self):
        """
        Test that editing one run doesn't affect other runs.
        """
        wizard = WizardState()
        wizard.add_run(file="file1.raw", fraction=1)
        wizard.add_run(file="file2.raw", fraction=2)
        wizard.add_run(file="file3.raw", fraction=3)
        
        mock_ui_ctx = MockUIContext()
        with patch("gui_nicegui.ui", mock_ui_ctx):
            create_runs_step(wizard, refresh_ui=lambda: None)
        
        # Find file inputs and fraction inputs
        file_inputs = [inp for inp in mock_ui_ctx.inputs if inp.placeholder == "File path"]
        fraction_inputs = [inp for inp in mock_ui_ctx.inputs if inp.type == "number"]
        save_buttons = [btn for btn in mock_ui_ctx.buttons if btn.text == "Save"]
        
        assert len(file_inputs) >= 3
        assert len(fraction_inputs) >= 3
        assert len(save_buttons) >= 3
        
        # Verify initial state
        assert wizard.runs[0]["fraction"] == 1
        assert wizard.runs[1]["fraction"] == 2
        assert wizard.runs[2]["fraction"] == 3
        
        # Edit second row: change fraction to None
        fraction_inputs[1].value = ""
        file_inputs[1].value = "file2_edited.raw"
        save_buttons[1].trigger_click()
        
        # Verify only second row changed
        assert wizard.runs[0]["fraction"] == 1
        assert wizard.runs[0]["file"] == "file1.raw"
        
        assert wizard.runs[1]["fraction"] is None
        assert wizard.runs[1]["file"] == "file2_edited.raw"
        
        assert wizard.runs[2]["fraction"] == 3
        assert wizard.runs[2]["file"] == "file3.raw"
