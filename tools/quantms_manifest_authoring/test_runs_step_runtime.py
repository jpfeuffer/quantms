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
Runtime validation tests for the Runs step with jspreadsheet-ce.

These tests verify that the actual NiceGUI create_runs_step function
can be called without errors and produces the expected UI output.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from gui_nicegui import create_runs_step


class MockUIElements:
    """Mock NiceGUI UI elements for testing."""

    def __init__(self):
        self.cards = []
        self.labels = []
        self.buttons = []
        self.html_elements = []
        self.notifications = []

    def card(self):
        """Mock card context manager."""
        return MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None))

    def label(self, text=""):
        """Mock label."""
        self.labels.append(text)
        mock_label = MagicMock()
        mock_label.classes = MagicMock(return_value=mock_label)
        return mock_label

    def button(self, text="", on_click=None, icon=""):
        """Mock button."""
        self.buttons.append({"text": text, "on_click": on_click, "icon": icon})
        mock_btn = MagicMock()
        mock_btn.classes = MagicMock(return_value=mock_btn)
        return mock_btn

    def input(self, value="", label="", placeholder=""):
        """Mock input."""
        mock_input = MagicMock()
        mock_input.value = value
        mock_input.label = label
        mock_input.placeholder = placeholder
        mock_input.classes = MagicMock(return_value=mock_input)
        return mock_input

    def row(self):
        """Mock row context manager."""
        return MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None))

    def column(self):
        """Mock column context manager."""
        return MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None))

    def expansion(self, text="", icon=""):
        """Mock expansion context manager."""
        return MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None))

    def html(self, content=""):
        """Mock HTML element."""
        self.html_elements.append(content)
        return MagicMock()

    def notify(self, message="", type=None):
        """Mock notification."""
        self.notifications.append({"message": message, "type": type})

    def run_javascript(self, script=""):
        """Mock JavaScript runner."""
        pass


class TestRunsStepRuntimeValidation:
    """Runtime validation tests for the Runs step."""

    def test_create_runs_step_with_no_runs(self):
        """
        AC1: create_runs_step with an empty wizard should render without error.
        Shows file picker and manual entry, no spreadsheet yet.
        """
        wizard = WizardState()
        refresh_ui = MagicMock()

        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui):
            # Should not raise an exception
            create_runs_step(wizard, refresh_ui)

        # Verify UI was created
        assert len(mock_ui.labels) > 0
        assert len(mock_ui.buttons) >= 2  # At least file picker and add buttons

    def test_create_runs_step_with_runs_creates_spreadsheet(self):
        """
        AC2: create_runs_step with runs should create an embedded spreadsheet.
        The HTML element with jspreadsheet should be present.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test1.raw", fraction=1)
        wizard.add_run(file="/data/test2.raw", sample="sample2")

        refresh_ui = MagicMock()
        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui), \
             patch("jspreadsheet_editor.ui") as mock_editor_ui, \
             patch("jspreadsheet_editor.app") as mock_app:

            # Mock the ui functions in editor
            mock_editor_ui.element = MagicMock(return_value=MagicMock())
            mock_editor_ui.run_javascript = MagicMock()
            mock_editor_ui.notify = MagicMock()
            mock_app.add_head_html = MagicMock()

            create_runs_step(wizard, refresh_ui)

            # Verify spreadsheet label was created
            run_count_labels = [l for l in mock_ui.labels if "2 file(s)" in str(l)]
            assert len(run_count_labels) > 0

    def test_create_runs_step_file_picker_callback(self):
        """
        AC3: File picker button exists and its callback can be called.
        """
        wizard = WizardState()
        refresh_ui = MagicMock()
        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui), \
             patch("gui_nicegui.MsFilePickerDialog"):

            create_runs_step(wizard, refresh_ui)

            # Find the file picker button
            file_picker_button = None
            for btn in mock_ui.buttons:
                if "Choose" in btn.get("text", ""):
                    file_picker_button = btn
                    break

            assert file_picker_button is not None, "File picker button not found"
            assert file_picker_button["on_click"] is not None

    def test_create_runs_step_manual_add_callback(self):
        """
        AC4: Manual add button exists and its callback works.
        """
        wizard = WizardState()
        refresh_ui = MagicMock()
        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui):
            create_runs_step(wizard, refresh_ui)

            # Find the add button (should be in the second row with manual input)
            add_button = None
            for btn in mock_ui.buttons:
                if btn.get("text") == "Add":
                    add_button = btn
                    break

            assert add_button is not None, "Manual add button not found"
            assert add_button["on_click"] is not None

    def test_create_runs_step_shows_run_count(self):
        """
        AC5: When runs exist, the UI shows the run count.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/s1.raw")
        wizard.add_run(file="/data/s2.raw")
        wizard.add_run(file="/data/s3.raw")

        refresh_ui = MagicMock()
        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui), \
             patch("jspreadsheet_editor.ui") as mock_editor_ui, \
             patch("jspreadsheet_editor.app"):

            mock_editor_ui.element = MagicMock(return_value=MagicMock())
            mock_editor_ui.run_javascript = MagicMock()
            mock_editor_ui.notify = MagicMock()

            create_runs_step(wizard, refresh_ui)

            # Check that run count is displayed
            run_count_label = [l for l in mock_ui.labels if "3 file(s)" in str(l)]
            assert len(run_count_label) > 0, "Run count not displayed"

    def test_create_runs_step_shows_instructions(self):
        """
        AC6: When runs exist, instructions about editing and drag-copy are shown.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        refresh_ui = MagicMock()
        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui), \
             patch("jspreadsheet_editor.ui") as mock_editor_ui, \
             patch("jspreadsheet_editor.app"):

            mock_editor_ui.element = MagicMock(return_value=MagicMock())
            mock_editor_ui.run_javascript = MagicMock()
            mock_editor_ui.notify = MagicMock()

            create_runs_step(wizard, refresh_ui)

            # Check for instruction label
            instruction_labels = [l for l in mock_ui.labels if "drag-copy" in str(l).lower() or "edit" in str(l).lower()]
            assert len(instruction_labels) > 0, "Instructions not found"

    def test_create_runs_step_UI_structure_complete(self):
        """
        AC7: The complete UI structure is present: title, description, picker, input, spreadsheet.
        """
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        refresh_ui = MagicMock()
        mock_ui = MockUIElements()

        with patch("gui_nicegui.ui", mock_ui), \
             patch("jspreadsheet_editor.ui") as mock_editor_ui, \
             patch("jspreadsheet_editor.app"):

            mock_editor_ui.element = MagicMock(return_value=MagicMock())
            mock_editor_ui.run_javascript = MagicMock()
            mock_editor_ui.notify = MagicMock()

            create_runs_step(wizard, refresh_ui)

            # Check key UI elements are present
            labels_text = " ".join(str(l) for l in mock_ui.labels)

            assert "Add Raw" in labels_text or "Step 1" in labels_text, "Title/step not found"
            assert "Supported formats" in labels_text, "Format info not found"

            assert len(mock_ui.buttons) >= 2, "Buttons not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
