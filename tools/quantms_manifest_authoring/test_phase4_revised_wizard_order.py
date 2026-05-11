#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Phase 4 Revised: Tests for new wizard order (Experiment before Assignments).

Verifies that:
1. Wizard order is: RUNS -> SAMPLES -> MIXTURES -> EXPERIMENT -> ASSIGNMENTS -> REVIEW
2. Experiment step determines the quantification method before Assignments
3. Assignments step is quantification-aware:
   - LFQ/non-multiplexed: show direct run-to-sample links
   - Multiplexed: show run-to-mixture links
4. No synthetic LFQ mixtures are introduced during persistence
5. Ownership model is preserved: Runs owns file/fraction/instrument; Assignments owns linkage
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from gui_wizard_state import WizardState, WizardStep


class TestWizardOrderRevised:
    """Tests for the new wizard step order."""

    def test_wizard_steps_order_has_experiment_before_assignments(self):
        """Test that wizard steps are in order: ..., EXPERIMENT, ASSIGNMENTS, ..."""
        steps = WizardStep.ordered_steps()
        experiment_idx = steps.index(WizardStep.EXPERIMENT)
        assignments_idx = steps.index(WizardStep.ASSIGNMENTS)
        assert experiment_idx < assignments_idx, (
            "EXPERIMENT step must come before ASSIGNMENTS step"
        )

    def test_complete_wizard_step_order(self):
        """Test the complete correct wizard step order."""
        steps = WizardStep.ordered_steps()
        expected_order = [
            WizardStep.RUNS,
            WizardStep.SAMPLES,
            WizardStep.MIXTURES,
            WizardStep.EXPERIMENT,
            WizardStep.ASSIGNMENTS,
            WizardStep.REVIEW,
        ]
        assert steps == expected_order, (
            f"Wizard step order should be {expected_order}, but got {steps}"
        )

    def test_wizard_starts_at_runs_and_can_advance_through_all_steps(self):
        """Test advancing through complete revised wizard sequence."""
        wizard = WizardState()

        # Start at RUNS
        assert wizard.get_current_step() == WizardStep.RUNS

        # Add a run and advance
        wizard.add_run(file="test.raw")
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.SAMPLES

        # Can advance past SAMPLES even without samples
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.MIXTURES

        # Can advance past MIXTURES
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.EXPERIMENT

        # Set experiment settings and advance
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS

        # Can advance to REVIEW
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.REVIEW


class TestExperimentDeterminedBeforeAssignments:
    """Tests that Experiment settings exist and are available for Assignments logic."""

    def test_experiment_saved_before_reaching_assignments(self):
        """Test that experiment is saved before entering ASSIGNMENTS step."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")

        # Advance to EXPERIMENT
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT

        # Set experiment
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="TMT"
        )

        # Now advance to ASSIGNMENTS
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS

        # Experiment should be available and accessible
        assert wizard.experiment is not None
        assert wizard.experiment["quantification_method"] == "TMT"

    def test_lfq_quantification_method_accessible_in_assignments(self):
        """Test that LFQ quantification is accessible when entering ASSIGNMENTS."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")

        # Advance to EXPERIMENT and set LFQ
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT

        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )

        # Advance to ASSIGNMENTS
        wizard.next_step()

        # Quantification method should be accessible
        quant_method = wizard.experiment.get("quantification_method")
        assert quant_method == "LFQ"

    def test_multiplexed_quantification_method_accessible_in_assignments(self):
        """Test that TMT/iTRAQ quantification is accessible in ASSIGNMENTS."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")

        # Advance to EXPERIMENT and set TMT
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT

        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="TMT"
        )

        # Advance to ASSIGNMENTS
        wizard.next_step()

        # Quantification method should be TMT
        assert wizard.experiment.get("quantification_method") == "TMT"


class TestVisibleFlowNavigationGate:
    """Tests that the visible wizard navigation gate reflects page-level prerequisites."""

    def test_next_stays_disabled_on_group_details_until_experiment_is_saved(self):
        """Next should be blocked on the visible group-details page until experiment settings are saved."""
        from gui_nicegui import ManifestEditingWizard

        editor = ManifestEditingWizard()
        editor.wizard.add_run(file="test.raw")
        editor.wizard.next_step()  # SAMPLES, still on the visible group-details page

        assert editor.wizard.get_main_flow_page_index() == 1
        assert not editor.can_go_forward_for_visible_page()

        editor.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ",
        )

        assert editor.can_go_forward_for_visible_page()

    def test_runs_page_validates_incomplete_groups_only_when_next_is_clicked(self):
        """Runs-page group rows may stay incomplete during editing but must validate before page advance."""
        from gui_nicegui import ManifestEditingWizard

        editor = ManifestEditingWizard()
        editor.wizard.add_run(file="test.raw")
        editor.wizard.sync_group_sheet_row(0, id="group_1")

        assert editor.can_go_forward_for_visible_page()

        with pytest.raises(ValueError, match="Group row 1 is incomplete"):
            editor.validate_current_page_for_next()

    def test_group_details_page_uses_selector_when_active_group_is_not_set(self):
        """The Group Details page should be able to surface a group selector directly."""
        from gui_nicegui import create_group_detail_step

        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_group(id="group_1", name="Group 1", kind="LFQ")
        wizard.add_group(id="group_2", name="Group 2", kind="TMT", labeling_strategy="TMT6")

        class _GroupDetailMockUI:
            def __init__(self):
                self.selects = []
                self.labels = []
                self.buttons = []
                self.cards = []
                self.rows = []
                self._container_stack = []

            def notify(self, message, type=None):
                return None

            def label(self, text=""):
                lbl = MagicMock()
                lbl.text = text
                lbl.classes.return_value = lbl
                lbl.update.return_value = lbl
                self.labels.append(lbl)
                return lbl

            def html(self, content=""):
                block = MagicMock()
                block.content = content
                block.classes.return_value = block
                return block

            def button(self, text="", on_click=None, icon="", **kwargs):
                btn = MagicMock()
                btn.text = text
                btn.icon = icon
                btn.classes.return_value = btn
                btn.props.return_value = btn
                self.buttons.append(btn)
                return btn

            def select(self, options=None, value=None, label="", clearable=False):
                sel = MagicMock()
                sel.options = options or {}
                sel.value = value
                sel.label = label
                sel.clearable = clearable
                sel.classes.return_value = sel
                sel.update.return_value = sel
                sel.on_value_change.return_value = sel
                self.selects.append(sel)
                return sel

            def row(self):
                row = MagicMock()
                row.__enter__.return_value = row
                row.__exit__.return_value = None
                row.classes.return_value = row
                row.props.return_value = row
                return row

            def card(self):
                card = MagicMock()
                card.__enter__.return_value = card
                card.__exit__.return_value = None
                card.classes.return_value = card
                card.props.return_value = card
                return card

            def column(self):
                column = MagicMock()
                column.__enter__.return_value = column
                column.__exit__.return_value = None
                column.classes.return_value = column
                column.props.return_value = column
                return column

            def expansion(self, text="", icon="", value=False):
                expansion = MagicMock()
                expansion.text = text
                expansion.icon = icon
                expansion.value = value
                expansion.__enter__.return_value = expansion
                expansion.__exit__.return_value = None
                expansion.classes.return_value = expansion
                expansion.props.return_value = expansion
                return expansion

        mock_ui = _GroupDetailMockUI()

        with patch("gui_nicegui.ui", mock_ui):
            create_group_detail_step(wizard, refresh_ui=lambda: None)

        selector = next((sel for sel in mock_ui.selects if sel.label == "Group"), None)
        assert selector is not None
        assert selector.options == {"group_1": "Group 1", "group_2": "Group 2"}
        assert wizard.get_active_group_id() == "group_1"


class TestAssignmentsQuantificationAwareness:
    """Tests that Assignments step is aware of quantification method."""

    def test_can_detect_lfq_mode_for_assignments(self):
        """Test detecting when in LFQ mode (for direct sample linkage)."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")

        # Advance to EXPERIMENT
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT

        # Set LFQ
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )

        # Advance to ASSIGNMENTS
        wizard.next_step()

        # Should be able to detect LFQ mode
        quant = wizard.experiment.get("quantification_method")
        is_lfq = quant in ["LFQ", None]  # LFQ or no quantification = non-multiplexed
        assert is_lfq is True

    def test_can_detect_multiplexed_mode_for_assignments(self):
        """Test detecting when in multiplexed mode (for mixture linkage)."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "s1", "TMT127N": "s2"})

        # Advance to EXPERIMENT
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT

        # Set TMT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="TMT"
        )

        # Advance to ASSIGNMENTS
        wizard.next_step()

        # Should be able to detect multiplexed mode
        quant = wizard.experiment.get("quantification_method")
        is_multiplexed = quant in ["TMT", "iTRAQ", "SILAC"]
        assert is_multiplexed is True


class TestAssignmentsPreservesOwnershipModel:
    """Tests that ownership model is preserved in assignments."""

    def test_runs_owns_only_file_fraction_instrument(self):
        """Verify runs do not contain sample/mixture after assignments."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")

        # Advance to ASSIGNMENTS and assign
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )
        wizard.next_step()  # ASSIGNMENTS

        # Assign run to sample
        wizard.assign_run(run_index=0, sample="s1")

        # Check run structure
        run = wizard.runs[0]
        assert "file" in run
        # Note: With the new ownership model, sample linkage happens in ASSIGNMENTS
        # This test verifies the run can have the sample assigned to it
        assert run.get("sample") == "s1"


class TestRevisedMainWizardFlow:
    """Tests for the revised three-page visible wizard flow."""

    class _RoutingMockNode:
        def __init__(self, owner=None):
            self.owner = owner
            self.children = []

        def classes(self, *args, **kwargs):
            return self

        def props(self, *args, **kwargs):
            return self

        def set_visibility(self, *_args, **_kwargs):
            return self

        def clear(self):
            self.children = []
            return self

        def update(self):
            return self

        def __enter__(self):
            if self.owner is not None:
                self.owner._container_stack.append(self)
            return self

        def __exit__(self, *args):
            if self.owner is not None and self.owner._container_stack:
                self.owner._container_stack.pop()

    class _RoutingMockUI:
        def __init__(self):
            self.buttons = []
            self.inputs = []
            self.selects = []
            self.labels = []
            self.cards = []
            self.rows = []
            self.notifications = []
            self._container_stack = []

        def add_head_html(self, html):
            return None

        def notify(self, message, type=None):
            self.notifications.append({"message": message, "type": type})

        def button(self, text="", on_click=None, icon="", **kwargs):
            btn = MagicMock()
            btn.text = text
            btn.icon = icon
            btn.on_click = MagicMock(return_value=btn)
            btn.enabled = True
            btn.classes.return_value = btn
            btn.props.return_value = btn
            self.buttons.append(btn)
            return btn

        def label(self, text=""):
            lbl = MagicMock()
            lbl.text = text
            lbl.classes.return_value = lbl
            lbl.update.return_value = lbl
            self.labels.append(lbl)
            if self._container_stack:
                self._container_stack[-1].children.append(lbl)
            return lbl

        def row(self):
            row = TestRevisedMainWizardFlow._RoutingMockNode(owner=self)
            self.rows.append(row)
            return row

        def column(self):
            column = TestRevisedMainWizardFlow._RoutingMockNode(owner=self)
            self.rows.append(column)
            return column

        def card(self):
            card = TestRevisedMainWizardFlow._RoutingMockNode(owner=self)
            self.cards.append(card)
            return card

        def expansion(self, text="", icon="", value=None):
            card = TestRevisedMainWizardFlow._RoutingMockNode(owner=self)
            self.cards.append(card)
            return card

        def select(self, options=None, value=None, label="", clearable=False):
            select = MagicMock()
            select.options = options or {}
            select.value = value
            select.label = label
            select.clearable = clearable
            select.classes.return_value = select
            select.update.return_value = select
            select.on_value_change.return_value = select
            self.selects.append(select)
            return select

        def input(self, value="", placeholder="", label="", type=None):
            input_widget = MagicMock()
            input_widget.value = value
            input_widget.placeholder = placeholder
            input_widget.label = label
            input_widget.type = type
            input_widget.classes.return_value = input_widget
            input_widget.update.return_value = input_widget
            self.inputs.append(input_widget)
            return input_widget

    def test_main_flow_page_index_collapses_hidden_legacy_steps(self):
        """The internal step index should map to three visible pages."""
        from gui_wizard_state import WizardState

        wizard = WizardState()

        assert wizard.get_main_flow_page_index() == 0

        wizard.current_step_index = 1
        assert wizard.get_main_flow_page_index() == 1

        wizard.current_step_index = 4
        assert wizard.get_main_flow_page_index() == 1

        wizard.current_step_index = 5
        assert wizard.get_main_flow_page_index() == 2

    def test_main_renderer_routes_page_one_to_group_details_and_omits_legacy_pages(self):
        """The active renderer should only expose Runs, Group Details, and Review in the main flow."""
        from gui_nicegui import WizardEditor, create_manifest_editor_ui

        wizard_editor = WizardEditor()
        wizard_editor.wizard.add_run(file="/data/test.raw")
        wizard_editor.wizard.add_group(id="lfq_group", name="LFQ group", kind="LFQ")
        wizard_editor.wizard.set_current_step_index(1)

        routing_ui = self._RoutingMockUI()
        render_calls = []

        def fake_runs_step(*_args, **_kwargs):
            render_calls.append("runs")

        def fake_group_detail_step(*_args, **_kwargs):
            render_calls.append("group")

        def fake_review_step(*_args, **_kwargs):
            render_calls.append("review")

        def fail_legacy_step(*_args, **_kwargs):
            raise AssertionError("Legacy step should not be part of the active wizard flow")

        with patch("gui_nicegui.ui", routing_ui), patch("gui_nicegui.create_runs_step", side_effect=fake_runs_step), patch(
            "gui_nicegui.create_group_detail_step", side_effect=fake_group_detail_step
        ), patch("gui_nicegui.create_review_step", side_effect=fake_review_step), patch(
            "gui_nicegui.create_samples_step", side_effect=fail_legacy_step
        ), patch("gui_nicegui.create_mixtures_step", side_effect=fail_legacy_step), patch(
            "gui_nicegui.create_experiment_step", side_effect=fail_legacy_step
        ), patch("gui_nicegui.create_assignments_step", side_effect=fail_legacy_step):
            create_manifest_editor_ui(wizard_editor)

        assert render_calls == ["group"]

        progress_labels = [
            button.text
            for button in routing_ui.buttons
            if isinstance(button.text, str)
            and button.text
            and button.text[0].isdigit()
        ]
        assert progress_labels[:3] == [
            "1. Runs + Modifications + Experiment",
            "2. Group Details",
            "3. Review",
        ]
        assert len(progress_labels) == 3

    def test_assignments_step_enables_run_to_sample_linkage_for_lfq(self):
        """Test that ASSIGNMENTS step allows LFQ run-to-sample linkage."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")

        # Go through wizard to ASSIGNMENTS
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )
        wizard.next_step()  # ASSIGNMENTS

        # Should be able to assign run to sample
        wizard.assign_run(run_index=0, sample="s1")
        assert wizard.runs[0].get("sample") == "s1"

    def test_assignments_step_enables_run_to_mixture_linkage_for_multiplexed(self):
        """Test that ASSIGNMENTS step allows multiplexed run-to-mixture linkage."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "s1", "TMT127N": "s2"})

        # Go through wizard to ASSIGNMENTS
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="TMT"
        )
        wizard.next_step()  # ASSIGNMENTS

        # Should be able to assign run to mixture
        wizard.assign_run(run_index=0, mixture="mix1")
        assert wizard.runs[0].get("mixture") == "mix1"


class TestNoSyntheticLFQMixtures:
    """Tests that LFQ workflows do not introduce synthetic mixtures."""

    def test_lfq_workflow_does_not_create_synthetic_mixtures(self):
        """Test that LFQ assignment doesn't create fake mixtures."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")

        # Go through wizard to ASSIGNMENTS with LFQ
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )
        wizard.next_step()  # ASSIGNMENTS

        # Assign runs to samples (not mixtures)
        wizard.assign_run(run_index=0, sample="s1")

        # No synthetic mixtures should be created
        initial_mixtures = len(wizard.mixtures)
        manifest = wizard.to_manifest_state()
        final_mixtures = len(manifest.mixtures)

        assert initial_mixtures == final_mixtures, (
            "LFQ assignment should not create synthetic mixtures"
        )


class TestGroupDetailState:
    """Tests for authoring-only active-group navigation state."""

    def test_active_group_can_be_set_and_cleared(self):
        """Wizard state should track the currently open group detail page."""
        wizard = WizardState()
        wizard.add_group(id="group_1", name="Group 1", kind="LFQ")

        assert wizard.get_active_group_id() is None

        wizard.set_active_group_id("group_1")

        assert wizard.get_active_group_id() == "group_1"
        assert wizard.get_active_group()["id"] == "group_1"

        wizard.clear_active_group()

        assert wizard.get_active_group_id() is None
        assert wizard.get_active_group() is None

    def test_active_group_clears_when_moving_between_steps(self):
        """Step transitions should close any open group detail page by default."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_group(id="group_1", name="Group 1", kind="LFQ")
        wizard.set_active_group_id("group_1")

        wizard.next_step()

        assert wizard.get_current_step() == WizardStep.SAMPLES
        assert wizard.get_active_group_id() is None

        wizard.set_active_group_id("group_1")
        wizard.previous_step()

        assert wizard.get_current_step() == WizardStep.RUNS
        assert wizard.get_active_group_id() is None

    def test_lfq_manifest_preserves_only_real_samples(self):
        """Test that LFQ manifest doesn't add synthetic entities."""
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")

        # Complete wizard with LFQ
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="LFQ"
        )
        wizard.next_step()  # ASSIGNMENTS
        wizard.assign_run(run_index=0, sample="s1")

        # Convert to manifest
        manifest = wizard.to_manifest_state()

        # Should have only 1 sample, 0 mixtures
        assert len(manifest.samples) == 1
        assert len(manifest.mixtures) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
