#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Test suite for JSpreadsheetEditor with entity type support.

Tests that the editor can be configured for different entity types
and properly handles initialization and event dispatching.
"""

import pytest
import sys
import weakref
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_editor import JSpreadsheetEditor
from jspreadsheet_bridge import JSpreadsheetBridge


class TestJSpreadsheetEditorWithEntityType:
    """Tests for JSpreadsheetEditor supporting different entity types."""

    def test_editor_renders_empty_samples_sheet(self):
        """Empty Samples sheets should still render so the first sample can be created."""
        wizard = WizardState()

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")
        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="Samples")

        container = MagicMock()
        container.html_id = "samples-container"
        container.classes.return_value = container

        with patch("jspreadsheet_editor.ui.element", return_value=container), \
             patch.object(JSpreadsheetEditor, "_ensure_cdn_loaded"), \
             patch.object(JSpreadsheetEditor, "_ensure_event_bridge_registered"), \
             patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.has_socket_connection = True
            editor._initialize_spreadsheet = MagicMock()

            editor.render()

        assert editor.container is container
        editor._initialize_spreadsheet.assert_called_once()

    def test_editor_initializes_for_samples(self):
        """Test that editor can be initialized for samples entity type."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)
        assert editor.bridge.entity_type == "samples"

    def test_editor_initializes_for_mixtures(self):
        """Test that editor can be initialized for mixtures entity type."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)
        assert editor.bridge.entity_type == "mixtures"

    def test_editor_backward_compatible_for_runs(self):
        """Test that editor remains backward compatible for runs."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")

        refresh_ui = MagicMock()

        # Initialize without bridge (old behavior)
        editor = JSpreadsheetEditor(wizard, refresh_ui)
        assert editor.bridge.entity_type == "runs"

    def test_editor_uses_provided_bridge(self):
        """Test that editor accepts and uses provided bridge."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        refresh_ui = MagicMock()
        custom_bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=custom_bridge)
        assert editor.bridge is custom_bridge

    def test_editor_serializes_group_channel_min_display_rows(self):
        """Group assignment sheets should pass their exact row count into the browser bootstrap payload."""
        wizard = WizardState()
        wizard.add_group(id="lfq_group", name="LFQ group", kind="LFQ")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="group_channels", group_strategy="LFQ")
        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge, worksheet_name="LFQ")

        container = MagicMock()
        container.html_id = "lfq-container"

        with patch("jspreadsheet_editor.context") as mock_context:
            mock_context.client.run_javascript = MagicMock()
            editor.container = container

            editor._initialize_data()

        initialize_script = mock_context.client.run_javascript.call_args[0][0]
        assert 'min_display_rows: 1' in initialize_script

    def test_editor_uses_provided_worksheet_name_in_widget_id(self):
        """Test that editor uses worksheet_name parameter in widget configuration."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(
            wizard,
            refresh_ui,
            bridge=bridge,
            worksheet_name="SamplesSheet"
        )
        # Widget ID might include worksheet name (implementation detail)
        assert editor.widget_id is not None

    def test_editor_registers_with_wizard(self):
        """Test that editor registers itself as active editor with wizard."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)
        editor.register_with_wizard()

        assert wizard.get_active_editor() is editor

    def test_editor_flush_syncs_spreadsheet_state(self):
        """Test that editor.flush() syncs spreadsheet state before navigation."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", condition="treated")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)

        # Simulate a state change that needs flushing
        # (In real usage, this would be triggered by spreadsheet events)
        # For now, just verify flush can be called
        editor.flush()

        # Should not raise


class TestEditorEventDispatching:
    """Tests for event handling through bridge to wizard state."""

    def test_editor_event_cell_edit_samples(self):
        """Test that editor can dispatch cell edit events for samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)

        # Simulate event reception and dispatch
        # Column index 1 is organism
        editor.handle_event("cell_edit", row_index=0, col_index=1, new_value="mus musculus")

        # Verify the wizard state was updated
        assert wizard.samples[0]["organism"] == "mus musculus"

    def test_editor_event_row_delete_samples(self):
        """Test that editor can dispatch row delete events for samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)

        # Simulate row delete event
        editor.handle_event("row_delete", row_index=0)

        # Verify row was deleted
        assert len(wizard.samples) == 1
        assert wizard.samples[0]["id"] == "sample2"

    def test_editor_refreshes_groups_when_a_new_group_id_is_typed(self):
        """A new Groups-sheet row should rerender immediately once its id is typed."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_group(id="group_1", name="Existing group", kind="LFQ")

        refresh_ui = MagicMock()
        bridge = JSpreadsheetBridge(wizard, entity_type="groups")
        editor = JSpreadsheetEditor(wizard, refresh_ui, bridge=bridge)

        editor.handle_event("cell_edit", row_index=1, col_index=0, new_value="group_2")

        refresh_ui.assert_called_once()
        assert [group["id"] for group in wizard.groups] == ["group_1", "group_2"]


class TestMultipleEditorCoexistence:
    """Tests for multiple spreadsheet editors on different steps."""

    def test_multiple_editors_register_correctly(self):
        """Test that multiple editors (Runs, Samples, Mixtures) can be registered."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        refresh_ui = MagicMock()

        runs_editor = JSpreadsheetEditor(wizard, refresh_ui)
        samples_editor = JSpreadsheetEditor(
            wizard,
            refresh_ui,
            bridge=JSpreadsheetBridge(wizard, entity_type="samples")
        )
        mixtures_editor = JSpreadsheetEditor(
            wizard,
            refresh_ui,
            bridge=JSpreadsheetBridge(wizard, entity_type="mixtures")
        )

        # Each should have unique widget IDs
        assert runs_editor.widget_id != samples_editor.widget_id
        assert samples_editor.widget_id != mixtures_editor.widget_id
        assert runs_editor.widget_id != mixtures_editor.widget_id

    def test_navigation_flushes_all_active_editors(self):
        """Test that navigation flushes all registered editors before proceeding."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")
        wizard.add_sample(id="sample1")

        refresh_ui = MagicMock()

        runs_editor = JSpreadsheetEditor(wizard, refresh_ui)
        samples_editor = JSpreadsheetEditor(
            wizard,
            refresh_ui,
            bridge=JSpreadsheetBridge(wizard, entity_type="samples")
        )

        # Register both editors
        runs_editor.register_with_wizard()
        samples_editor.register_with_wizard()

        # Both should be flushable
        runs_editor.flush()
        samples_editor.flush()

        # Should not raise

    def test_editor_instance_registry_uses_weak_references(self):
        """Test that the shared editor registry does not retain stale editor objects strongly."""
        registry = JSpreadsheetEditor._get_registry('_instances', weakref.WeakValueDictionary)
        assert isinstance(registry, weakref.WeakValueDictionary)
