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
Phase 4: Tests for explicit sample/mixture association ownership.

Verifies that:
1. Runs step does NOT suggest sample/mixture association happens there
2. Assignments step CLEARLY communicates sample/mixture linking
3. Phase 3 dropdown behavior is preserved
4. Runs schema remains reduced (file/fraction/instrument only)
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState, WizardStep
from spreadsheet_adapter import SpreadsheetAdapter, RunFieldInfo
from gui_nicegui import create_runs_step, create_assignments_step
from jspreadsheet_bridge import JSpreadsheetBridge


class TestRunsStepOwnership:
    """Tests for Runs step ownership - file/fraction/instrument only."""

    def test_runs_spreadsheet_schema_excludes_sample_mixture(self):
        """Verify Runs spreadsheet schema only has file, fraction, instrument."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")

        adapter = SpreadsheetAdapter(wizard)
        headers = adapter.get_column_headers()

        # Should only have these fields
        expected_fields = {"file", "fraction", "instrument"}
        actual_fields = set(headers)

        assert actual_fields == expected_fields, (
            f"Runs spreadsheet should only have {expected_fields}, "
            f"but has {actual_fields}"
        )

    def test_run_field_info_defines_only_correct_fields(self):
        """Verify RunFieldInfo metadata is limited to file, fraction, instrument."""
        all_fields = RunFieldInfo.get_all_fields()
        expected = ["file", "fraction", "instrument"]

        assert set(all_fields) == set(expected), (
            f"RunFieldInfo should only define {expected}, but has {all_fields}"
        )

    def test_add_run_without_sample_mixture_succeeds(self):
        """Verify runs can be added without sample or mixture parameters."""
        wizard = WizardState()
        # Should succeed without sample/mixture
        wizard.add_run(file="/data/test.raw", fraction=1)

        assert len(wizard.runs) == 1
        run = wizard.runs[0]
        assert run["file"] == "/data/test.raw"
        assert run["fraction"] == 1
        assert "sample" not in run, "Run should not have sample property"
        assert "mixture" not in run, "Run should not have mixture property"

    def test_jspreadsheet_bridge_schema_matches_reduced_fields(self):
        """Verify JSpreadsheetBridge respects reduced schema."""
        wizard = WizardState()
        wizard.add_run(file="test1.raw", fraction=1)
        wizard.add_run(file="test2.raw", instrument="Q-TOF")

        bridge = JSpreadsheetBridge(wizard)
        data = bridge.get_spreadsheet_data()

        # Should have exactly 3 columns
        assert set(data["headers"]) == {"file", "fraction", "instrument"}

        # No sample or mixture columns
        assert "sample" not in data["headers"]
        assert "mixture" not in data["headers"]

    def test_runs_step_ui_copy_does_not_mention_sample_assignment(self):
        """Verify Runs step copy doesn't suggest sample/mixture assignment."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        refresh_ui = MagicMock()

        # Mock NiceGUI to capture labels
        ui_labels = []

        def mock_label(text=""):
            ui_labels.append(text)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            return mock

        with patch("gui_nicegui.ui") as mock_ui, \
             patch("jspreadsheet_editor.ui") as mock_editor_ui, \
             patch("jspreadsheet_editor.app"):

            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = mock_label
            mock_ui.button = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.input = MagicMock(return_value=MagicMock(value="", classes=MagicMock(return_value=MagicMock())))
            mock_ui.row = MagicMock()
            mock_ui.row.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.row.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.notify = MagicMock()

            mock_editor_ui.element = MagicMock(return_value=MagicMock())
            mock_editor_ui.run_javascript = MagicMock()

            create_runs_step(wizard, refresh_ui)

            # Combine all labels
            all_labels = " ".join(ui_labels)

            # Should mention file/fraction/instrument
            assert "file" in all_labels.lower(), "Runs step should mention files"
            assert "assignments step" in all_labels.lower(), (
                "Runs step should explicitly defer sample/mixture linking to the Assignments step"
            )

            # Should NOT suggest sample/mixture assignment happens here
            forbidden_phrases = [
                "assign to sample",
                "assign to mixture",
                "sample or mixture",
                "link to sample",
                "link to mixture"
            ]
            for phrase in forbidden_phrases:
                assert phrase.lower() not in all_labels.lower(), (
                    f"Runs step should NOT mention '{phrase}'"
                )


class TestAssignmentsStepOwnership:
    """Tests for Assignments step ownership - clear sample/mixture linking."""

    def test_assignments_step_title_mentions_samples_mixtures(self):
        """Verify Assignments step title clearly mentions sample/mixture linking."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_sample(id="s1")

        refresh_ui = MagicMock()
        ui_labels = []

        def mock_label(text=""):
            ui_labels.append(text)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            return mock

        with patch("gui_nicegui.ui") as mock_ui:
            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = mock_label
            mock_ui.select = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.input = MagicMock(return_value=MagicMock(value="", classes=MagicMock(return_value=MagicMock())))
            mock_ui.button = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.expansion = MagicMock()
            mock_ui.expansion.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.expansion.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

            all_labels = " ".join(ui_labels)

            # Title should clearly mention sample/mixture
            assert "assign" in all_labels.lower(), "Title should mention assignment"
            assert ("sample" in all_labels.lower() or "mixture" in all_labels.lower()), (
                "Title should mention sample or mixture assignment"
            )

            # Should mention linking
            assert "link" in all_labels.lower() or "assign" in all_labels.lower(), (
                "Description should mention linking/assignment"
            )

    def test_assignments_step_does_not_reintroduce_fraction_or_instrument_inputs(self):
        """Verify Assignments step focuses on sample/mixture linking only."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")
        wizard.add_sample(id="s1")

        refresh_ui = MagicMock()
        input_calls = []

        def mock_input(**kwargs):
            input_calls.append(kwargs)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            mock.value = kwargs.get("value", "")
            return mock

        with patch("gui_nicegui.ui") as mock_ui:
            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.select = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.input = mock_input
            mock_ui.button = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.expansion = MagicMock()
            mock_ui.expansion.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.expansion.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

        labels = [call.get("label", "") for call in input_calls]
        assert "Fraction Number (optional)" not in labels
        assert "Instrument (optional)" not in labels

    def test_assign_run_method_validates_sample_mixture_references(self):
        """Verify assign_run validates that samples/mixtures exist."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")

        # Try to assign to non-existent sample - should fail
        with pytest.raises(ValueError, match="not found in samples"):
            wizard.assign_run(
                run_index=0,
                sample="nonexistent_sample",
                mixture=None
            )

        # Try to assign to non-existent mixture - should fail
        with pytest.raises(ValueError, match="not found in mixtures"):
            wizard.assign_run(
                run_index=0,
                sample=None,
                mixture="nonexistent_mixture"
            )

    def test_assign_run_method_works_with_valid_sample_mixture(self):
        """Verify assign_run succeeds with valid sample/mixture."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"TMT126": "s1"})

        # Should succeed
        wizard.assign_run(run_index=0, sample="s1", mixture=None, fraction=1)

        run = wizard.runs[0]
        assert run["sample"] == "s1"
        assert run["fraction"] == 1


class TestPhase3DropdownBehaviorPreserved:
    """Tests to ensure Phase 3 dropdown behavior is intact."""

    def test_assignments_step_shows_sample_dropdown(self):
        """Verify Assignments step renders sample selection dropdown."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")

        refresh_ui = MagicMock()
        select_calls = []

        def mock_select(**kwargs):
            select_calls.append(kwargs)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            mock.value = kwargs.get("value")
            return mock

        with patch("gui_nicegui.ui") as mock_ui:
            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.select = mock_select
            mock_ui.input = MagicMock(return_value=MagicMock(value="", classes=MagicMock(return_value=MagicMock())))
            mock_ui.button = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.expansion = MagicMock()
            mock_ui.expansion.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.expansion.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

            # Should have sample selection dropdown
            labels = [call.get("label", "") for call in select_calls]
            assert any("Sample" in str(label) or "sample" in str(label) for label in labels), (
                "Assignments step should have sample dropdown"
            )

    def test_assignments_step_shows_mixture_dropdown(self):
        """Verify Assignments step renders mixture selection dropdown."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"TMT126": "s1"})

        refresh_ui = MagicMock()
        select_calls = []

        def mock_select(**kwargs):
            select_calls.append(kwargs)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            mock.value = kwargs.get("value")
            return mock

        with patch("gui_nicegui.ui") as mock_ui:
            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.select = mock_select
            mock_ui.input = MagicMock(return_value=MagicMock(value="", classes=MagicMock(return_value=MagicMock())))
            mock_ui.button = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.expansion = MagicMock()
            mock_ui.expansion.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.expansion.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

            # Should have mixture selection dropdown
            labels = [call.get("label", "") for call in select_calls]
            assert any("Mixture" in str(label) or "mixture" in str(label) for label in labels), (
                "Assignments step should have mixture dropdown"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
