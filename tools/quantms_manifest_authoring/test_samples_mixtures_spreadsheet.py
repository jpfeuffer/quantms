#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Test suite for samples and mixtures spreadsheet adapter contracts.

Tests the translation between WizardState samples/mixtures and spreadsheet rows,
and synchronization of edits back to wizard state while preserving validation.
"""

import pytest
import sys
from pathlib import Path
from typing import List, Dict, Any

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState
from spreadsheet_adapter import (
    SpreadsheetAdapter,
    SpreadsheetRow,
)


class TestSampleFieldInfo:
    """Tests for sample field metadata."""

    def test_sample_field_info_exists(self):
        """Test that SampleFieldInfo class exists."""
        from spreadsheet_adapter import SampleFieldInfo
        assert SampleFieldInfo is not None

    def test_sample_field_info_has_all_standard_fields(self):
        """Test that SampleFieldInfo provides all standard sample fields."""
        from spreadsheet_adapter import SampleFieldInfo
        fields = SampleFieldInfo.get_all_fields()
        assert "id" in fields
        assert "organism" in fields
        assert "organism_part" in fields
        assert "condition" in fields
        assert "biological_replicate" in fields
        assert "technical_replicate" in fields
        assert "disease" in fields
        assert "cell_type" in fields

    def test_sample_field_info_id_is_required(self):
        """Test that sample id field is required."""
        from spreadsheet_adapter import SampleFieldInfo
        field_info = SampleFieldInfo.get_field_info("id")
        assert field_info["required"] is True

    def test_sample_field_info_metadata_fields_are_optional(self):
        """Test that metadata fields are optional."""
        from spreadsheet_adapter import SampleFieldInfo
        optional_fields = ["organism", "organism_part", "condition", "biological_replicate",
                          "technical_replicate", "disease", "cell_type"]
        for field in optional_fields:
            field_info = SampleFieldInfo.get_field_info(field)
            assert field_info["required"] is False


class TestSampleSpreadsheetRow:
    """Tests for SampleSpreadsheetRow data structure."""

    def test_sample_spreadsheet_row_creation_from_wizard_sample(self):
        """Test creating a spreadsheet row from a wizard sample dict."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        sample = {
            "id": "sample1",
            "organism": "homo sapiens",
            "condition": "treated",
        }
        row = SampleSpreadsheetRow.from_wizard_sample(sample, row_index=0)
        assert row.id == "sample1"
        assert row.organism == "homo sapiens"
        assert row.condition == "treated"

    def test_sample_spreadsheet_row_with_all_fields(self):
        """Test sample spreadsheet row with all fields filled."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        sample = {
            "id": "sample1",
            "organism": "homo sapiens",
            "organism_part": "liver",
            "condition": "treated",
            "biological_replicate": 1,
            "technical_replicate": 2,
            "disease": "healthy",
            "cell_type": "hepatocyte",
        }
        row = SampleSpreadsheetRow.from_wizard_sample(sample, row_index=0)
        assert row.id == "sample1"
        assert row.organism == "homo sapiens"
        assert row.organism_part == "liver"
        assert row.condition == "treated"
        assert row.biological_replicate == 1
        assert row.technical_replicate == 2
        assert row.disease == "healthy"
        assert row.cell_type == "hepatocyte"

    def test_sample_spreadsheet_row_to_dict(self):
        """Test converting sample spreadsheet row back to dict."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        original = {
            "id": "sample1",
            "organism": "homo sapiens",
            "condition": "treated",
        }
        row = SampleSpreadsheetRow.from_wizard_sample(original, row_index=0)
        result = row.to_dict()
        assert result["id"] == "sample1"
        assert result["organism"] == "homo sapiens"
        assert result["condition"] == "treated"

    def test_sample_spreadsheet_row_to_dict_excludes_none_values(self):
        """Test that to_dict strictly excludes None values."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        sample = {
            "id": "sample1",
            "organism": None,
            "condition": None,
        }
        row = SampleSpreadsheetRow.from_wizard_sample(sample, row_index=0)
        result = row.to_dict()
        assert result["id"] == "sample1"
        assert "organism" not in result
        assert "condition" not in result

    def test_sample_spreadsheet_row_validation_requires_id(self):
        """Test that sample row validation requires id field."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        row = SampleSpreadsheetRow(id=None, row_index=0)
        with pytest.raises(ValueError, match="Sample ID is required"):
            row.validate()

    def test_sample_spreadsheet_row_validation_accepts_valid_row(self):
        """Test that valid sample row passes validation."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        row = SampleSpreadsheetRow(id="sample1", row_index=0)
        row.validate()  # Should not raise


class TestMixtureFieldInfo:
    """Tests for mixture field metadata."""

    def test_mixture_field_info_exists(self):
        """Test that MixtureFieldInfo class exists."""
        from spreadsheet_adapter import MixtureFieldInfo
        assert MixtureFieldInfo is not None

    def test_mixture_field_info_has_id_and_channels(self):
        """Test that MixtureFieldInfo provides core mixture fields."""
        from spreadsheet_adapter import MixtureFieldInfo
        fields = MixtureFieldInfo.get_all_fields()
        # Mixtures have id and channel mappings; channels may be expanded per item
        assert "id" in fields


class TestMixtureSpreadsheetRow:
    """Tests for MixtureSpreadsheetRow data structure."""

    def test_mixture_spreadsheet_row_creation_from_wizard_mixture(self):
        """Test creating a spreadsheet row from a wizard mixture dict."""
        from spreadsheet_adapter import MixtureSpreadsheetRow
        mixture = {
            "id": "mix1",
            "channels": {
                "TMT126": "sample1",
                "TMT127N": "sample2",
            }
        }
        row = MixtureSpreadsheetRow.from_wizard_mixture(mixture, row_index=0)
        assert row.id == "mix1"
        assert row.channels == {"TMT126": "sample1", "TMT127N": "sample2"}

    def test_mixture_spreadsheet_row_to_dict(self):
        """Test converting mixture spreadsheet row back to dict."""
        from spreadsheet_adapter import MixtureSpreadsheetRow
        original = {
            "id": "mix1",
            "channels": {
                "TMT126": "sample1",
            }
        }
        row = MixtureSpreadsheetRow.from_wizard_mixture(original, row_index=0)
        result = row.to_dict()
        assert result["id"] == "mix1"
        assert result["channels"] == {"TMT126": "sample1"}

    def test_mixture_spreadsheet_row_validation_requires_id(self):
        """Test that mixture row validation requires id field."""
        from spreadsheet_adapter import MixtureSpreadsheetRow
        row = MixtureSpreadsheetRow(id=None, channels={}, row_index=0)
        with pytest.raises(ValueError, match="Mixture ID is required"):
            row.validate()

    def test_mixture_spreadsheet_row_validation_requires_channels(self):
        """Test that mixture row validation requires at least one channel."""
        from spreadsheet_adapter import MixtureSpreadsheetRow
        row = MixtureSpreadsheetRow(id="mix1", channels={}, row_index=0)
        with pytest.raises(ValueError, match="At least one channel"):
            row.validate()


class TestSpreadsheetAdapterSamples:
    """Tests for spreadsheet adapter with samples."""

    def test_adapter_convert_empty_wizard_samples_to_rows(self):
        """Test converting empty wizard samples to spreadsheet rows."""
        wizard = WizardState()
        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_samples_to_spreadsheet()
        assert rows == []

    def test_adapter_convert_single_sample_to_row(self):
        """Test converting single wizard sample to spreadsheet row."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens", condition="treated")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_samples_to_spreadsheet()

        assert len(rows) == 1
        assert rows[0].id == "sample1"
        assert rows[0].organism == "homo sapiens"
        assert rows[0].condition == "treated"

    def test_adapter_convert_multiple_samples_to_rows(self):
        """Test converting multiple wizard samples to spreadsheet rows."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens", condition="treated")
        wizard.add_sample(id="sample2", organism="mus musculus", biological_replicate=1)
        wizard.add_sample(id="sample3")

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_samples_to_spreadsheet()

        assert len(rows) == 3
        assert rows[0].id == "sample1"
        assert rows[1].id == "sample2"
        assert rows[1].biological_replicate == 1
        assert rows[2].id == "sample3"

    def test_adapter_convert_sample_row_to_wizard_sample(self):
        """Test converting single spreadsheet row to wizard sample dict."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        adapter = SpreadsheetAdapter(WizardState())
        row = SampleSpreadsheetRow(
            id="sample1",
            organism="homo sapiens",
            condition="treated",
            row_index=0,
        )
        result = adapter.spreadsheet_row_to_wizard_sample(row)
        assert result["id"] == "sample1"
        assert result["organism"] == "homo sapiens"
        assert result["condition"] == "treated"

    def test_adapter_sync_sample_edits(self):
        """Test syncing spreadsheet edits back to wizard samples."""
        wizard = WizardState()
        wizard.add_sample(id="sample1", organism="homo sapiens")

        adapter = SpreadsheetAdapter(wizard)

        # Modify the spreadsheet row
        rows = adapter.wizard_samples_to_spreadsheet()
        rows[0].organism = "mus musculus"
        rows[0].condition = "control"

        # Sync back
        adapter.sync_sample_edits(rows)

        # Verify wizard state changed
        assert len(wizard.samples) == 1
        assert wizard.samples[0]["organism"] == "mus musculus"
        assert wizard.samples[0]["condition"] == "control"

    def test_adapter_add_sample_via_spreadsheet_row(self):
        """Test adding a new sample via spreadsheet row sync."""
        from spreadsheet_adapter import SampleSpreadsheetRow
        wizard = WizardState()
        wizard.add_sample(id="sample1")

        adapter = SpreadsheetAdapter(wizard)

        # Create new row and sync
        rows = adapter.wizard_samples_to_spreadsheet()
        new_row = SampleSpreadsheetRow(id="sample2", organism="homo sapiens", row_index=1)
        rows.append(new_row)

        adapter.sync_sample_edits(rows)

        assert len(wizard.samples) == 2
        assert wizard.samples[1]["id"] == "sample2"
        assert wizard.samples[1]["organism"] == "homo sapiens"

    def test_adapter_delete_sample_via_spreadsheet_row(self):
        """Test deleting a sample via spreadsheet row sync."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")

        adapter = SpreadsheetAdapter(wizard)

        # Remove first sample from rows
        rows = adapter.wizard_samples_to_spreadsheet()
        rows_deleted = [rows[1]]  # Keep only sample2

        adapter.sync_sample_edits(rows_deleted)

        assert len(wizard.samples) == 1
        assert wizard.samples[0]["id"] == "sample2"


class TestSpreadsheetAdapterMixtures:
    """Tests for spreadsheet adapter with mixtures."""

    def test_adapter_convert_empty_wizard_mixtures_to_rows(self):
        """Test converting empty wizard mixtures to spreadsheet rows."""
        wizard = WizardState()
        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_mixtures_to_spreadsheet()
        assert rows == []

    def test_adapter_convert_single_mixture_to_row(self):
        """Test converting single wizard mixture to spreadsheet row."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_mixtures_to_spreadsheet()

        assert len(rows) == 1
        assert rows[0].id == "mix1"
        assert rows[0].channels == {"TMT126": "sample1"}

    def test_adapter_convert_multiple_mixtures_to_rows(self):
        """Test converting multiple wizard mixtures to spreadsheet rows."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})
        wizard.add_mixture(id="mix2", channels={"TMT127N": "sample2", "TMT128N": "sample1"})

        adapter = SpreadsheetAdapter(wizard)
        rows = adapter.wizard_mixtures_to_spreadsheet()

        assert len(rows) == 2
        assert rows[0].id == "mix1"
        assert rows[1].id == "mix2"

    def test_adapter_convert_mixture_row_to_wizard_mixture(self):
        """Test converting single spreadsheet row to wizard mixture dict."""
        from spreadsheet_adapter import MixtureSpreadsheetRow
        adapter = SpreadsheetAdapter(WizardState())
        row = MixtureSpreadsheetRow(
            id="mix1",
            channels={"TMT126": "sample1", "TMT127N": "sample2"},
            row_index=0,
        )
        result = adapter.spreadsheet_row_to_wizard_mixture(row)
        assert result["id"] == "mix1"
        assert result["channels"] == {"TMT126": "sample1", "TMT127N": "sample2"}

    def test_adapter_sync_mixture_edits(self):
        """Test syncing spreadsheet edits back to wizard mixtures."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        adapter = SpreadsheetAdapter(wizard)

        # Modify the spreadsheet row
        rows = adapter.wizard_mixtures_to_spreadsheet()
        rows[0].channels = {"TMT126": "sample2", "TMT127N": "sample1"}

        # Sync back
        adapter.sync_mixture_edits(rows)

        # Verify wizard state changed
        assert len(wizard.mixtures) == 1
        assert wizard.mixtures[0]["channels"] == {"TMT126": "sample2", "TMT127N": "sample1"}

    def test_adapter_add_mixture_via_spreadsheet_row(self):
        """Test adding a new mixture via spreadsheet row sync."""
        from spreadsheet_adapter import MixtureSpreadsheetRow
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_sample(id="sample2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        adapter = SpreadsheetAdapter(wizard)

        # Create new row and sync
        rows = adapter.wizard_mixtures_to_spreadsheet()
        new_row = MixtureSpreadsheetRow(id="mix2", channels={"TMT127N": "sample2"}, row_index=1)
        rows.append(new_row)

        adapter.sync_mixture_edits(rows)

        assert len(wizard.mixtures) == 2
        assert wizard.mixtures[1]["id"] == "mix2"
        assert wizard.mixtures[1]["channels"] == {"TMT127N": "sample2"}

    def test_adapter_delete_mixture_via_spreadsheet_row(self):
        """Test deleting a mixture via spreadsheet row sync."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})
        wizard.add_mixture(id="mix2", channels={"TMT127N": "sample1"})

        adapter = SpreadsheetAdapter(wizard)

        # Remove first mixture from rows
        rows = adapter.wizard_mixtures_to_spreadsheet()
        rows_deleted = [rows[1]]  # Keep only mix2

        adapter.sync_mixture_edits(rows_deleted)

        assert len(wizard.mixtures) == 1
        assert wizard.mixtures[0]["id"] == "mix2"

    def test_mixture_sync_validates_all_samples_exist(self):
        """Test that mixture sync validates referenced samples exist."""
        wizard = WizardState()
        wizard.add_sample(id="sample1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "sample1"})

        adapter = SpreadsheetAdapter(wizard)

        # Try to add mixture with non-existent sample
        from spreadsheet_adapter import MixtureSpreadsheetRow
        rows = adapter.wizard_mixtures_to_spreadsheet()
        bad_row = MixtureSpreadsheetRow(id="mix2", channels={"TMT127N": "nonexistent"}, row_index=1)
        rows.append(bad_row)

        with pytest.raises(ValueError, match="Sample.*not found"):
            adapter.sync_mixture_edits(rows)
