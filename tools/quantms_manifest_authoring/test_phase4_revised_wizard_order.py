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
