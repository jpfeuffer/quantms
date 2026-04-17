#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Test suite for Samples and Mixtures steps using JSpreadsheetEditor.

Tests that the UI steps properly render spreadsheet editors for managing
samples and mixtures data.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState


class TestCreateSamplesStepWithSpreadsheet:
    """Tests for create_samples_step rendering JSpreadsheetEditor."""

    def test_create_samples_step_renders_spreadsheet_editor_when_samples_exist(self):
        """
        AC: When samples exist, create_samples_step should render
        a JSpreadsheetEditor instance (not modal dialogs).
        """
        with patch('gui_nicegui.ui') as mock_ui, \
             patch('gui_nicegui.JSpreadsheetEditor') as mock_editor_class:
            
            from gui_nicegui import create_samples_step
            
            wizard = WizardState()
            wizard.add_sample(id="sample1", organism="homo sapiens")
            wizard.add_sample(id="sample2", organism="mus musculus")
            
            refresh_ui = MagicMock()
            
            # Mock the UI components
            mock_card = MagicMock()
            mock_ui.card.return_value.__enter__.return_value = mock_card
            mock_ui.label.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.input.return_value = MagicMock()
            mock_ui.button.return_value = MagicMock()
            
            mock_editor = MagicMock()
            mock_editor_class.return_value = mock_editor
            
            # Call the step
            create_samples_step(wizard, refresh_ui)
            
            # Verify JSpreadsheetEditor was instantiated
            # (Should be called with wizard and refresh_ui)
            mock_editor_class.assert_called()

    def test_create_samples_step_does_not_render_spreadsheet_when_empty(self):
        """Test that create_samples_step does not render spreadsheet when no samples exist."""
        with patch('gui_nicegui.ui') as mock_ui, \
             patch('gui_nicegui.JSpreadsheetEditor') as mock_editor_class:
            
            from gui_nicegui import create_samples_step
            
            wizard = WizardState()
            # No samples added
            
            refresh_ui = MagicMock()
            
            # Mock the UI components
            mock_card = MagicMock()
            mock_ui.card.return_value.__enter__.return_value = mock_card
            mock_ui.label.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.input.return_value = MagicMock()
            mock_ui.button.return_value = MagicMock()
            
            # Call the step
            create_samples_step(wizard, refresh_ui)
            
            # JSpreadsheetEditor should NOT be called when no samples
            mock_editor_class.assert_not_called()

    def test_create_samples_step_editor_initialized_with_samples_bridge(self):
        """Test that samples editor is initialized with entity_type='samples'."""
        with patch('gui_nicegui.ui') as mock_ui, \
             patch('gui_nicegui.JSpreadsheetEditor') as mock_editor_class, \
             patch('gui_nicegui.JSpreadsheetBridge') as mock_bridge_class:
            
            from gui_nicegui import create_samples_step
            
            wizard = WizardState()
            wizard.add_sample(id="sample1")
            
            refresh_ui = MagicMock()
            
            # Mock the UI components
            mock_card = MagicMock()
            mock_ui.card.return_value.__enter__.return_value = mock_card
            mock_ui.label.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.input.return_value = MagicMock()
            mock_ui.button.return_value = MagicMock()
            
            mock_bridge = MagicMock()
            mock_bridge_class.return_value = mock_bridge
            
            mock_editor = MagicMock()
            mock_editor_class.return_value = mock_editor
            
            # Call the step
            create_samples_step(wizard, refresh_ui)
            
            # Bridge should be created with entity_type='samples'
            mock_bridge_class.assert_called()
            call_kwargs = mock_bridge_class.call_args[1] if mock_bridge_class.call_args[1] else {}
            assert call_kwargs.get('entity_type') == 'samples' or \
                   'samples' in str(mock_bridge_class.call_args)


class TestCreateMixturesStepWithSpreadsheet:
    """Tests for create_mixtures_step rendering JSpreadsheetEditor."""

    def test_create_mixtures_step_renders_spreadsheet_editor_when_mixtures_exist(self):
        """
        AC: When mixtures exist, create_mixtures_step should render
        a JSpreadsheetEditor instance (not modal dialogs).
        """
        with patch('gui_nicegui.ui') as mock_ui, \
             patch('gui_nicegui.JSpreadsheetEditor') as mock_editor_class:
            
            from gui_nicegui import create_mixtures_step
            
            wizard = WizardState()
            wizard.add_sample(id="sample1")
            wizard.add_sample(id="sample2")
            wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})
            wizard.add_mixture(id="mix2", channels={"TMT127N": "sample2"})
            
            refresh_ui = MagicMock()
            
            # Mock the UI components
            mock_card = MagicMock()
            mock_ui.card.return_value.__enter__.return_value = mock_card
            mock_ui.label.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.input.return_value = MagicMock()
            mock_ui.select.return_value = MagicMock()
            mock_ui.button.return_value = MagicMock()
            
            mock_editor = MagicMock()
            mock_editor_class.return_value = mock_editor
            
            # Call the step
            create_mixtures_step(wizard, refresh_ui)
            
            # Verify JSpreadsheetEditor was instantiated
            mock_editor_class.assert_called()

    def test_create_mixtures_step_does_not_render_spreadsheet_when_empty(self):
        """Test that create_mixtures_step does not render spreadsheet when no mixtures exist."""
        with patch('gui_nicegui.ui') as mock_ui, \
             patch('gui_nicegui.JSpreadsheetEditor') as mock_editor_class:
            
            from gui_nicegui import create_mixtures_step
            
            wizard = WizardState()
            wizard.add_sample(id="sample1")
            # No mixtures added
            
            refresh_ui = MagicMock()
            
            # Mock the UI components
            mock_card = MagicMock()
            mock_ui.card.return_value.__enter__.return_value = mock_card
            mock_ui.label.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.input.return_value = MagicMock()
            mock_ui.select.return_value = MagicMock()
            mock_ui.button.return_value = MagicMock()
            
            # Call the step
            create_mixtures_step(wizard, refresh_ui)
            
            # JSpreadsheetEditor should NOT be called when no mixtures
            mock_editor_class.assert_not_called()

    def test_create_mixtures_step_editor_initialized_with_mixtures_bridge(self):
        """Test that mixtures editor is initialized with entity_type='mixtures'."""
        with patch('gui_nicegui.ui') as mock_ui, \
             patch('gui_nicegui.JSpreadsheetEditor') as mock_editor_class, \
             patch('gui_nicegui.JSpreadsheetBridge') as mock_bridge_class:
            
            from gui_nicegui import create_mixtures_step
            
            wizard = WizardState()
            wizard.add_sample(id="sample1")
            wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})
            
            refresh_ui = MagicMock()
            
            # Mock the UI components
            mock_card = MagicMock()
            mock_ui.card.return_value.__enter__.return_value = mock_card
            mock_ui.label.return_value = MagicMock()
            mock_ui.column.return_value.__enter__.return_value = MagicMock()
            mock_ui.row.return_value.__enter__.return_value = MagicMock()
            mock_ui.input.return_value = MagicMock()
            mock_ui.select.return_value = MagicMock()
            mock_ui.button.return_value = MagicMock()
            
            mock_bridge = MagicMock()
            mock_bridge_class.return_value = mock_bridge
            
            mock_editor = MagicMock()
            mock_editor_class.return_value = mock_editor
            
            # Call the step
            create_mixtures_step(wizard, refresh_ui)
            
            # Bridge should be created with entity_type='mixtures'
            mock_bridge_class.assert_called()
            call_kwargs = mock_bridge_class.call_args[1] if mock_bridge_class.call_args[1] else {}
            assert call_kwargs.get('entity_type') == 'mixtures' or \
                   'mixtures' in str(mock_bridge_class.call_args)


class TestSpreadsheetStepsDeleteBehavior:
    """Tests for row deletion behavior in spreadsheet steps."""

    def test_samples_step_row_delete_via_spreadsheet(self):
        """Test that sample rows can be deleted via spreadsheet events."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")
        
        # Simulate row deletion through bridge
        from jspreadsheet_bridge import JSpreadsheetBridge
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")
        bridge.handle_row_delete(row_index=0)
        
        assert len(wizard.samples) == 1
        assert wizard.samples[0]["id"] == "sample2"

    def test_mixtures_step_row_delete_via_spreadsheet(self):
        """Test that mixture rows can be deleted via spreadsheet events."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})
        wizard.add_mixture(id="mix2", channels={"TMT127N": "sample1"})
        
        # Simulate row deletion through bridge
        from jspreadsheet_bridge import JSpreadsheetBridge
        bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")
        bridge.handle_row_delete(row_index=0)
        
        assert len(wizard.mixtures) == 1
        assert wizard.mixtures[0]["id"] == "mix2"
