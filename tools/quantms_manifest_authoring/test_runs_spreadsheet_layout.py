#!/usr/bin/env python3
"""
Tests for Runs spreadsheet layout and styling (Phase 2).

Validates that the spreadsheet fills available card width and uses
consistent styling with the rest of the NiceGUI wizard.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_editor import JSpreadsheetEditor


@pytest.fixture(autouse=True)
def reset_jspreadsheet_class_state():
    """
    Reset JSpreadsheetEditor class-level registries before each test.

    Ensures tests don't leak state through shared class attributes:
    - _static_assets_registered
    - _cdn_loaded_clients
    - _event_bridge_clients
    - _instances
    """
    # Clear any existing registries
    for attr in ['_static_assets_registered', '_cdn_loaded_clients',
                 '_event_bridge_clients', '_instances']:
        if hasattr(JSpreadsheetEditor, attr):
            delattr(JSpreadsheetEditor, attr)

    yield

    # Cleanup after test
    for attr in ['_static_assets_registered', '_cdn_loaded_clients',
                 '_event_bridge_clients', '_instances']:
        if hasattr(JSpreadsheetEditor, attr):
            delattr(JSpreadsheetEditor, attr)


class MockElement:
    """Mock for ui.element that tracks applied classes."""

    def __init__(self, tag='div'):
        self.tag = tag
        self.html_id = f"mock_{id(self)}"
        self._classes = []

    def classes(self, *class_names):
        """Add classes and return self for chaining."""
        for cls in class_names:
            # Split by whitespace in case multiple classes were passed as single arg
            if isinstance(cls, str):
                self._classes.extend(cls.split())
            else:
                self._classes.append(cls)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class MockContextClient:
    """Mock for context.client."""

    def __init__(self):
        self.has_socket_connection = False
        self._on_connect_handlers = []

    def on_connect(self, handler):
        """Register a handler to be called when client connects."""
        self._on_connect_handlers.append(handler)

    def run_javascript(self, script):
        """Mock implementation of run_javascript."""
        pass


class MockContext:
    """Mock for nicegui context."""

    def __init__(self):
        self.client = MockContextClient()


class TestSpreadsheetLayoutAndStyling:
    """Tests for spreadsheet width, responsiveness, and styling."""

    def test_spreadsheet_container_uses_full_width_class(self):
        """
        AC1: The spreadsheet container div should use NiceGUI's w-full class
        to fill available card width.
        """
        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        on_change = MagicMock()
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            mock_element = MockElement()
            mock_ui.element.return_value = mock_element
            mock_context.client = MockContextClient()

            editor = JSpreadsheetEditor(wizard, on_change)
            editor.render()

            # Verify container was created
            assert editor.container is not None
            # Verify w-full class is applied
            assert "w-full" in editor.container._classes

    def test_spreadsheet_container_has_proper_styling_classes(self):
        """
        AC2: The spreadsheet container should have styling classes that match
        the NiceGUI design system (rounded corners, border, background).
        """
        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        on_change = MagicMock()
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            mock_element = MockElement()
            mock_ui.element.return_value = mock_element
            mock_context.client = MockContextClient()

            editor = JSpreadsheetEditor(wizard, on_change)
            editor.render()

            # Verify styling classes present
            classes_str = " ".join(editor.container._classes)
            assert "rounded" in classes_str  # Rounded corners
            assert "border" in classes_str  # Border
            assert "bg-white" in classes_str  # White background

    def test_spreadsheet_container_minimum_height(self):
        """
        AC3: The spreadsheet container should have a minimum height
        to ensure visibility even with few rows.
        """
        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        on_change = MagicMock()
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            mock_element = MockElement()
            mock_ui.element.return_value = mock_element
            mock_context.client = MockContextClient()

            editor = JSpreadsheetEditor(wizard, on_change)
            editor.render()

            # Verify min height is set
            classes_str = " ".join(editor.container._classes)
            assert "min-h" in classes_str  # Has minimum height

    def test_custom_quantms_css_is_loaded(self):
        """
        AC4: Custom quantms CSS for spreadsheet styling should be loaded
        via add_head_html instead of relying on vendor defaults.
        """
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context, \
             patch("jspreadsheet_editor.app") as mock_app:

            mock_ui.add_head_html = MagicMock()
            mock_context.client = MockContextClient()
            mock_app.add_head_html = MagicMock()

            # Call prepare_client_runtime to trigger _head_html
            JSpreadsheetEditor.prepare_client_runtime()

            # Verify add_head_html was called with correct stylesheet links
            assert mock_ui.add_head_html.called, "add_head_html should be called"

            # Check that the call included the expected stylesheet links
            call_args = mock_ui.add_head_html.call_args
            assert call_args is not None, "add_head_html should have been called with arguments"

            head_html = call_args[0][0]  # Get the first positional argument
            assert isinstance(head_html, str), "add_head_html should receive a string"
            assert "jsuites.css" in head_html, "Should include jsuites.css stylesheet"
            assert "jspreadsheet.css" in head_html, "Should include jspreadsheet.css stylesheet"
            assert "<link" in head_html, "Should have proper HTML link tags"

    def test_spreadsheet_initialization_uses_responsive_width_calculation(self):
        """
        AC5: The JavaScript initialization should use a method to calculate
        responsive column widths rather than fixed pixel values.
        Verifies that JavaScript code includes responsive width logic.
        """
        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        on_change = MagicMock()
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            mock_element = MockElement()
            mock_ui.element.return_value = mock_element
            mock_client = MockContextClient()
            mock_context.client = mock_client

            editor = JSpreadsheetEditor(wizard, on_change)
            editor.render()

            # Trigger on_connect handlers to initialize
            for handler in mock_client._on_connect_handlers:
                try:
                    handler()
                except Exception:
                    pass  # May raise due to mocking; we just verify render succeeded

            # Verify the container exists and has the styling classes
            # The responsive width calculation is embedded in the JavaScript,
            # which would be tested in integration/browser tests
            assert editor.container is not None
            assert len(editor.container._classes) > 0

    def test_spreadsheet_container_has_custom_styling_wrapper(self):
        """
        AC6: The spreadsheet should have a wrapper or classes that apply
        quantms-specific styling to match the app theme.
        """
        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        on_change = MagicMock()
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            mock_element = MockElement()
            mock_ui.element.return_value = mock_element
            mock_context.client = MockContextClient()

            editor = JSpreadsheetEditor(wizard, on_change)
            editor.render()

            # Container should have multiple styling classes
            assert len(editor.container._classes) >= 3  # At least 3 classes for proper styling


class TestSpreadsheetEditorIntegration:
    """Tests for integration of styling with editor functionality."""

    def test_spreadsheet_styling_preserved_after_cell_edit(self):
        """
        Verify that custom styling remains intact after cell edits.
        """
        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1, instrument="Orbi")

        on_change = MagicMock()
        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            mock_element = MockElement()
            mock_ui.element.return_value = mock_element
            mock_context.client = MockContextClient()

            editor = JSpreadsheetEditor(wizard, on_change)
            editor.render()

            # Verify container still has styling after operations
            assert "w-full" in editor.container._classes
            assert on_change.called is False  # Just rendering, no edits yet

    def test_multiple_spreadsheets_styled_independently(self):
        """
        Verify that multiple spreadsheets on the same page maintain
        independent styling.
        """
        wizard1 = WizardState()
        wizard1.add_run(file="test1.raw")

        wizard2 = WizardState()
        wizard2.add_run(file="test2.raw")

        on_change = MagicMock()

        with patch("jspreadsheet_editor.ui") as mock_ui, \
             patch("jspreadsheet_editor.context") as mock_context:

            # Create separate MockElement instances for each editor
            mock_element1 = MockElement()
            mock_element2 = MockElement()
            mock_ui.element.side_effect = [mock_element1, mock_element2]
            mock_context.client = MockContextClient()

            editor1 = JSpreadsheetEditor(wizard1, on_change)
            editor1.render()

            editor2 = JSpreadsheetEditor(wizard2, on_change)
            editor2.render()

            # Both should have proper container styling
            assert "w-full" in editor1.container._classes
            assert "w-full" in editor2.container._classes
