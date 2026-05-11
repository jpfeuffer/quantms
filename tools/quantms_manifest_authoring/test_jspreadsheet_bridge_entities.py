#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Test suite for JSpreadsheetBridge entity type support (runs, samples, mixtures).

Tests the bridge's ability to initialize and sync data for multiple entity types.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from jspreadsheet_bridge import JSpreadsheetBridge


class TestJSpreadsheetBridgeForSamples:
    """Tests for JSpreadsheetBridge with samples entity type."""

    def test_bridge_can_create_first_sample_from_empty_state(self):
        """An empty Samples sheet should accept the first sample row through the edit path."""
        wizard = WizardState()

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")
        headers = bridge.get_spreadsheet_data()["headers"]

        bridge.handle_cell_edit(row_index=0, col_index=headers.index("id"), new_value="sample1")

        assert len(wizard.samples) == 1
        assert wizard.samples[0]["id"] == "sample1"

    def test_bridge_initializes_with_entity_type_samples(self):
        """Test that bridge can be initialized with entity_type='samples'."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens")

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")
        assert bridge.entity_type == "samples"

    def test_bridge_get_spreadsheet_data_for_samples(self):
        """Test that bridge generates correct spreadsheet data structure for samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens", condition="treated")
        wizard.add_sample(id="sample2", organism="mus musculus", condition="control")

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")
        data = bridge.get_spreadsheet_data()

        assert "headers" in data
        assert "data" in data
        assert "column_config" in data

        # Verify headers include sample fields
        assert "id" in data["headers"]

        # Verify data has correct number of rows
        assert len(data["data"]) == 2

        # Verify first row maps to sample1
        assert data["data"][0][0] == "sample1"  # id column

    def test_bridge_handle_cell_edit_for_samples(self):
        """Test that bridge can handle cell edits for samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens")

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        # Edit organism column (assuming column 1)
        bridge.handle_cell_edit(row_index=0, col_index=1, new_value="mus musculus")

        # Verify wizard state was updated
        assert wizard.samples[0]["organism"] == "mus musculus"

    def test_bridge_handle_cell_edit_required_field_samples(self):
        """Test that bridge validates required fields (id) for samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        # Try to clear id field (should fail)
        with pytest.raises(ValueError, match="required"):
            bridge.handle_cell_edit(row_index=0, col_index=0, new_value="")

    def test_bridge_handle_row_delete_samples(self):
        """Test that bridge can delete rows for samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")
        bridge.handle_row_delete(row_index=0)

        # Verify first sample was deleted
        assert len(wizard.samples) == 1
        assert wizard.samples[0]["id"] == "sample2"

    def test_bridge_rejects_row_append_for_samples(self):
        """Test that append is only supported for the runs entity type."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        bridge = JSpreadsheetBridge(wizard, entity_type="samples")

        with pytest.raises(NotImplementedError, match="only supported for runs"):
            bridge.handle_row_append("/data/unused.raw")


class TestJSpreadsheetBridgeForMixtures:
    """Tests for JSpreadsheetBridge with mixtures entity type."""

    def test_bridge_initializes_with_entity_type_mixtures(self):
        """Test that bridge can be initialized with entity_type='mixtures'."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")
        assert bridge.entity_type == "mixtures"

    def test_bridge_get_spreadsheet_data_for_mixtures(self):
        """Test that bridge generates correct spreadsheet data for mixtures with channel columns."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1", "TMT127N": "sample2"})

        bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")
        data = bridge.get_spreadsheet_data()

        assert "headers" in data
        assert "data" in data

        # Verify headers include id and channel columns
        assert "id" in data["headers"]
        assert "TMT126" in data["headers"]
        assert "TMT127N" in data["headers"]

        # Verify data has correct number of rows
        assert len(data["data"]) == 1

        # Verify mix1 data
        assert data["data"][0][0] == "mix1"  # id column

    def test_bridge_handle_cell_edit_for_mixture_channel(self):
        """Test that bridge can handle cell edits for mixture channel assignments."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")

        # Edit channel assignment - find TMT126 column
        headers = bridge.adapter.get_column_headers_mixtures()
        col_index = headers.index("TMT126")

        bridge.handle_cell_edit(row_index=0, col_index=col_index, new_value="sample2")

        # Verify wizard state was updated
        assert wizard.mixtures[0]["channels"]["TMT126"] == "sample2"

    def test_bridge_handle_row_delete_mixtures(self):
        """Test that bridge can delete rows for mixtures."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})
        wizard.add_mixture(id="mix2", channels={"TMT126": "sample1"})

        bridge = JSpreadsheetBridge(wizard, entity_type="mixtures")
        bridge.handle_row_delete(row_index=0)

        # Verify first mixture was deleted
        assert len(wizard.mixtures) == 1
        assert wizard.mixtures[0]["id"] == "mix2"


class TestJSpreadsheetBridgeBackwardCompatibility:
    """Tests that bridge remains backward compatible for runs (default entity type)."""

    def test_bridge_default_entity_type_is_runs(self):
        """Test that bridge defaults to entity_type='runs' for backward compatibility."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")

        bridge = JSpreadsheetBridge(wizard)
        assert bridge.entity_type == "runs"

    def test_bridge_runs_entity_type_explicit(self):
        """Test that bridge accepts explicit entity_type='runs'."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")

        bridge = JSpreadsheetBridge(wizard, entity_type="runs")
        assert bridge.entity_type == "runs"

    def test_bridge_get_spreadsheet_data_runs_unchanged(self):
        """Test that runs spreadsheet data generation is unchanged."""
        wizard = WizardState()
        wizard.add_run(file="/data/sample1.raw", fraction=1)
        wizard.add_run(file="/data/sample2.raw", fraction=2)

        bridge = JSpreadsheetBridge(wizard, entity_type="runs")
        data = bridge.get_spreadsheet_data()

        assert "headers" in data
        assert "data" in data
        assert data["headers"] == ["file", "fraction", "instrument"]
        assert len(data["data"]) == 2
        assert data["data"][0][0] == "/data/sample1.raw"
