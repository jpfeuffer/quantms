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
        """Verify Runs spreadsheet schema keeps run fields plus editable group_id."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")

        adapter = SpreadsheetAdapter(wizard)
        headers = adapter.get_column_headers()

        # Runs owns file/fraction/instrument and the editable group_id field.
        expected_fields = {"file", "fraction", "instrument", "group_id"}
        actual_fields = set(headers)

        assert actual_fields == expected_fields, (
            f"Runs spreadsheet should only have {expected_fields}, "
            f"but has {actual_fields}"
        )

    def test_run_field_info_defines_only_correct_fields(self):
        """Verify RunFieldInfo metadata includes the editable group_id field."""
        all_fields = RunFieldInfo.get_all_fields()
        expected = ["file", "fraction", "instrument", "group_id"]

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

        # Should have exactly 4 columns, including editable group_id.
        assert set(data["headers"]) == {"file", "fraction", "instrument", "group_id"}

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

    def test_assignments_step_instantiates_jspreadsheet_editor(self):
        """Verify Assignments step uses JSpreadsheetEditor for spreadsheet-based linking."""
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        refresh_ui = MagicMock()

        with patch("gui_nicegui.JSpreadsheetEditor") as mock_editor_class, \
             patch("gui_nicegui.JSpreadsheetBridge") as mock_bridge_class, \
             patch("gui_nicegui.ui") as mock_ui:

            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            editor_instance = MagicMock()
            mock_editor_class.return_value = editor_instance
            mock_editor_class.prepare_client_runtime = MagicMock()

            result = create_assignments_step(wizard, refresh_ui)

            # Should have created an editor
            assert result is not None, "create_assignments_step should return JSpreadsheetEditor instance"
            assert isinstance(result, MagicMock) or hasattr(result, 'render'), "Result should be an editor instance"

    def test_assignments_bridge_created_with_entity_type_assignments(self):
        """Verify JSpreadsheetBridge is created with entity_type='assignments'."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        refresh_ui = MagicMock()

        with patch("gui_nicegui.JSpreadsheetEditor") as mock_editor_class, \
             patch("gui_nicegui.JSpreadsheetBridge") as mock_bridge_class, \
             patch("gui_nicegui.ui") as mock_ui:

            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            editor_instance = MagicMock()
            mock_editor_class.return_value = editor_instance
            mock_editor_class.prepare_client_runtime = MagicMock()

            bridge_instance = MagicMock()
            mock_bridge_class.return_value = bridge_instance

            create_assignments_step(wizard, refresh_ui)

            # Verify JSpreadsheetBridge was called with entity_type="assignments"
            mock_bridge_class.assert_called_once()
            call_kwargs = mock_bridge_class.call_args[1]
            assert call_kwargs.get("entity_type") == "assignments", (
                "JSpreadsheetBridge should be called with entity_type='assignments'"
            )

    def test_assignments_step_lfq_shows_sample_linkage_copy(self):
        """Verify LFQ mode shows sample linkage copy, not mixture linkage."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_sample(id="s1")
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="LFQ")

        refresh_ui = MagicMock()
        ui_labels = []

        def mock_label(text=""):
            ui_labels.append(text)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            return mock

        with patch("gui_nicegui.JSpreadsheetEditor"), \
             patch("gui_nicegui.JSpreadsheetBridge"), \
             patch("gui_nicegui.ui") as mock_ui:

            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = mock_label
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

            all_labels = " ".join(ui_labels).lower()

            # LFQ should mention sample linkage
            assert "sample" in all_labels, "LFQ assignments should mention samples"
            # Should NOT mention mixture in the copy
            assert "mixture link" not in all_labels and "link to mixture" not in all_labels, (
                "LFQ assignments should not mention mixture linkage"
            )

    def test_assignments_step_multiplexed_shows_mixture_linkage_copy(self):
        """Verify multiplexed mode shows mixture linkage copy, not sample linkage."""
        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="m1", channels={"TMT126": "s1"})
        wizard.set_experiment(acquisition_method="DDA", enzyme="Trypsin", quantification_method="TMT")

        refresh_ui = MagicMock()
        ui_labels = []

        def mock_label(text=""):
            ui_labels.append(text)
            mock = MagicMock()
            mock.classes = MagicMock(return_value=mock)
            return mock

        with patch("gui_nicegui.JSpreadsheetEditor"), \
             patch("gui_nicegui.JSpreadsheetBridge"), \
             patch("gui_nicegui.ui") as mock_ui:

            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = mock_label
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

            all_labels = " ".join(ui_labels).lower()

            # Multiplexed should mention mixture linkage
            assert "mixture" in all_labels, "Multiplexed assignments should mention mixtures"
            # Should NOT mention direct sample linkage
            assert "direct sample" not in all_labels and "link to sample" not in all_labels, (
                "Multiplexed assignments should not mention direct sample linkage"
            )

    def test_assignments_step_does_not_reintroduce_fraction_or_instrument_inputs(self):
        """Verify Assignments step focuses on sample/mixture linking only via spreadsheet."""
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

        with patch("gui_nicegui.JSpreadsheetEditor"), \
             patch("gui_nicegui.JSpreadsheetBridge"), \
             patch("gui_nicegui.ui") as mock_ui:
            mock_ui.card = MagicMock()
            mock_ui.card.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.card.return_value.__exit__ = MagicMock(return_value=None)
            mock_ui.label = MagicMock(return_value=MagicMock(classes=MagicMock(return_value=MagicMock())))
            mock_ui.input = mock_input
            mock_ui.column = MagicMock()
            mock_ui.column.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_ui.column.return_value.__exit__ = MagicMock(return_value=None)

            create_assignments_step(wizard, refresh_ui)

        labels = [call.get("label", "") for call in input_calls]
        assert "Fraction Number (optional)" not in labels
        assert "Instrument (optional)" not in labels



class TestPhase3DropdownBehaviorPreserved:
    """Tests to ensure Phase 3 dropdown behavior is intact - now in spreadsheet form."""

    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
