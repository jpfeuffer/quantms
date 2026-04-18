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
Phase 4 Revised: Tests for Assignments Spreadsheet UI/Editor and Quantification-Aware Linking.

Verifies that:
1. Assignments spreadsheet UI/editor is properly wired
2. LFQ assignments expose only sample linkage (no mixture linkage)
3. Multiplexed assignments expose only mixture linkage (no sample linkage)
4. Manifest serialization preserves direct LFQ sample links without synthetic mixtures
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState, WizardStep
from spreadsheet_adapter import SpreadsheetAdapter, AssignmentFieldInfo, AssignmentSpreadsheetRow
from jspreadsheet_bridge import JSpreadsheetBridge
from manifest_core import ManifestState
from gui_nicegui import create_assignments_step


class TestCreateAssignmentsStepUIWiring:
    """Tests for create_assignments_step UI/Editor wiring."""

    def test_create_assignments_step_returns_jspreadsheet_editor(self):
        """Verify create_assignments_step returns Optional[JSpreadsheetEditor]."""
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        refresh_ui = MagicMock()

        with patch("gui_nicegui.JSpreadsheetEditor") as mock_editor_class, \
             patch("gui_nicegui.JSpreadsheetBridge"), \
             patch("gui_nicegui.ui"):

            editor_instance = MagicMock(spec=JSpreadsheetEditor)
            mock_editor_class.return_value = editor_instance
            mock_editor_class.prepare_client_runtime = MagicMock()

            with patch("gui_nicegui.ui.card") as mock_card, \
                 patch("gui_nicegui.ui.label") as mock_label, \
                 patch("gui_nicegui.ui.column") as mock_column:

                mock_card.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_card.return_value.__exit__ = MagicMock(return_value=None)
                mock_column.return_value.__enter__ = MagicMock(return_value=MagicMock())
                mock_column.return_value.__exit__ = MagicMock(return_value=None)
                mock_label.return_value.classes = MagicMock(return_value=MagicMock())

                result = create_assignments_step(wizard, refresh_ui)

                # Should return the editor instance
                assert result is not None, "create_assignments_step should return an editor when runs exist"
                assert result == editor_instance

    def test_create_assignments_step_returns_none_when_no_runs(self):
        """Verify create_assignments_step returns None (empty state) when no runs."""
        wizard = WizardState()
        # No runs added

        refresh_ui = MagicMock()

        with patch("gui_nicegui.ui") as mock_ui:
            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))

            result = create_assignments_step(wizard, refresh_ui)

            # Should return None for empty state
            assert result is None


class TestAssignmentsSpreadsheetAdapter:
    """Tests for assignments spreadsheet adapter infrastructure."""

    def test_assignment_field_info_exists(self):
        """Verify AssignmentFieldInfo class exists with required fields."""
        # Should have at least run_file and either sample or mixture
        all_fields = AssignmentFieldInfo.get_all_fields()
        assert "run_file" in all_fields, "Should have run_file field"
        assert len(all_fields) >= 2, "Should have at least run_file and one linkage field"

    def test_assignment_spreadsheet_row_creation(self):
        """Verify AssignmentSpreadsheetRow can be created from run data."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        # Create assignment row
        run = wizard.runs[0]
        row = AssignmentSpreadsheetRow(
            run_file=run["file"],
            sample=None,
            mixture=None,
            row_index=0
        )

        assert row.run_file == "/data/test.raw"
        assert row.sample is None
        assert row.mixture is None

    def test_adapter_get_assignment_headers_lfq(self):
        """Verify adapter returns correct headers for LFQ mode."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        adapter = SpreadsheetAdapter(wizard)
        headers = adapter.get_assignment_headers_for_quantification(wizard.experiment.get("quantification_method"))

        # For LFQ, should have run_file and sample, but NOT mixture
        assert "run_file" in headers
        assert "sample" in headers
        assert "mixture" not in headers, "LFQ assignments should not expose mixture column"

    def test_adapter_get_assignment_headers_multiplexed(self):
        """Verify adapter returns correct headers for multiplexed quantification."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"TMT126": "s1"})
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="TMT")

        adapter = SpreadsheetAdapter(wizard)
        headers = adapter.get_assignment_headers_for_quantification(wizard.experiment.get("quantification_method"))

        # For multiplexed, should have run_file and mixture, but NOT sample
        assert "run_file" in headers
        assert "mixture" in headers
        assert "sample" not in headers, "Multiplexed assignments should not expose sample column"

    def test_adapter_get_assignment_headers_itraq(self):
        """Verify iTRAQ is recognized as multiplexed quantification."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"iTRAQ114": "s1"})
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="iTRAQ")

        adapter = SpreadsheetAdapter(wizard)
        headers = adapter.get_assignment_headers_for_quantification(wizard.experiment.get("quantification_method"))

        # iTRAQ is multiplexed
        assert "mixture" in headers
        assert "sample" not in headers, "iTRAQ assignments should not expose sample column"

    def test_adapter_get_assignment_headers_empty_quantification(self):
        """Verify empty quantification defaults to LFQ-like (sample) behavior."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method=None)

        adapter = SpreadsheetAdapter(wizard)
        headers = adapter.get_assignment_headers_for_quantification(wizard.experiment.get("quantification_method"))

        # Empty should default to sample-based (non-multiplexed)
        assert "run_file" in headers
        assert "sample" in headers
        assert "mixture" not in headers


class TestAssignmentsSpreadsheetBridge:
    """Tests for assignments spreadsheet bridge wiring."""

    def test_jspreadsheet_bridge_supports_assignments_entity_type(self):
        """Verify JSpreadsheetBridge can be initialized with assignments entity type."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")
        assert bridge.entity_type == "assignments"

    def test_jspreadsheet_bridge_get_spreadsheet_data_lfq(self):
        """Verify bridge returns LFQ-appropriate data (sample column, no mixture)."""
        wizard = WizardState()
        wizard.add_run(file="test1.raw", fraction=1)
        wizard.add_run(file="test2.raw", fraction=2)
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")
        data = bridge.get_spreadsheet_data()

        # Should have 2 rows (one per run)
        assert len(data["data"]) == 2

        # Headers should include run_file and sample, not mixture
        assert "run_file" in data["headers"]
        assert "sample" in data["headers"]
        assert "mixture" not in data["headers"]

        # Column config should be present
        assert "column_config" in data

    def test_jspreadsheet_bridge_get_spreadsheet_data_multiplexed(self):
        """Verify bridge returns multiplexed-appropriate data (mixture column, no sample)."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"TMT126": "s1"})
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="TMT")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")
        data = bridge.get_spreadsheet_data()

        # Headers should include run_file and mixture, not sample
        assert "run_file" in data["headers"]
        assert "mixture" in data["headers"]
        assert "sample" not in data["headers"]

    def test_jspreadsheet_bridge_sync_from_spreadsheet_lfq(self):
        """Verify bridge syncs LFQ assignments back to wizard correctly."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        bridge = JSpreadsheetBridge(wizard, entity_type="assignments")

        # Simulate user editing the spreadsheet (updated sample assignment)
        spreadsheet_data = [
            ["test.raw", "s1"]  # run_file, sample
        ]

        bridge.sync_from_spreadsheet_data(spreadsheet_data)

        # Wizard should be updated with sample assignment
        assert wizard.runs[0].get("sample") == "s1"
        # Should NOT have mixture assigned
        assert "mixture" not in wizard.runs[0] or wizard.runs[0].get("mixture") is None


class TestManifestSerializationLFQ:
    """Tests for manifest serialization preserving direct LFQ sample links."""

    def test_manifest_lfq_preserves_direct_sample_links(self):
        """Verify manifest preserves direct run-to-sample links without synthetic mixtures."""
        wizard = WizardState()
        wizard.add_run(file="test1.raw")
        wizard.add_run(file="test2.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        # Assign runs to samples (no mixtures created)
        wizard.assign_run(run_index=0, sample="s1")
        wizard.assign_run(run_index=1, sample="s2")

        manifest = wizard.to_manifest_state()

        # Manifest should have runs with direct sample references
        assert len(manifest.runs) == 2
        assert manifest.runs[0].sample == "s1"
        assert manifest.runs[1].sample == "s2"

        # Manifest should NOT have synthetic mixtures
        assert len(manifest.mixtures) == 0

    def test_manifest_lfq_no_synthetic_mixtures_in_output(self):
        """Verify saved manifest doesn't include synthetic mixtures for LFQ."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")
        wizard.assign_run(run_index=0, sample="s1")

        manifest = wizard.to_manifest_state()
        manifest_dict = manifest.to_dict()

        # Should have runs with sample
        assert len(manifest_dict["runs"]) == 1
        assert manifest_dict["runs"][0]["sample"] == "s1"

        # Should NOT have mixtures key or should be empty
        assert "mixtures" not in manifest_dict or len(manifest_dict.get("mixtures", [])) == 0


class TestManifestSerializationMultiplexed:
    """Tests for manifest serialization with multiplexed methods."""

    def test_manifest_tmt_preserves_run_to_mixture_links(self):
        """Verify manifest preserves run-to-mixture links for TMT."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"TMT126": "s1"})
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="TMT")

        # Assign run to mixture
        wizard.assign_run(run_index=0, mixture="m1")

        manifest = wizard.to_manifest_state()

        # Manifest should have run with mixture reference
        assert len(manifest.runs) == 1
        assert manifest.runs[0].mixture == "m1"
        assert manifest.runs[0].sample is None, "TMT run should NOT have direct sample link"

        # Manifest should have mixture
        assert len(manifest.mixtures) == 1
        assert manifest.mixtures[0].id == "m1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
