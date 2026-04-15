#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Test suite for NiceGUI wizard pattern implementation.

Tests cover wizard state management, step progression, runs-first requirement,
option provider integration, and conversion to ManifestState.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from manifest_core import ManifestState, ChannelBuilder
from ontology_provider import OntologyOptionProvider


class TestWizardStep:
    """Tests for WizardStep enum and representation."""

    def test_wizard_steps_exist(self):
        """Test that wizard steps are properly defined (import check)."""
        from gui_wizard_state import WizardStep
        assert hasattr(WizardStep, 'RUNS')
        assert hasattr(WizardStep, 'SAMPLES')
        assert hasattr(WizardStep, 'MIXTURES')
        assert hasattr(WizardStep, 'EXPERIMENT')
        assert hasattr(WizardStep, 'REVIEW')

    def test_wizard_steps_ordered(self):
        """Test that wizard steps have a defined order."""
        from gui_wizard_state import WizardStep
        steps = [WizardStep.RUNS, WizardStep.SAMPLES, WizardStep.MIXTURES,
                 WizardStep.ASSIGNMENTS, WizardStep.EXPERIMENT, WizardStep.REVIEW]
        assert len(steps) == 6

    def test_assignments_step_exists(self):
        """Test that ASSIGNMENTS step is defined in the wizard."""
        from gui_wizard_state import WizardStep
        assert hasattr(WizardStep, 'ASSIGNMENTS')
        steps = WizardStep.ordered_steps()
        assert WizardStep.ASSIGNMENTS in steps
        # ASSIGNMENTS should come after MIXTURES and before EXPERIMENT
        assignments_idx = steps.index(WizardStep.ASSIGNMENTS)
        mixtures_idx = steps.index(WizardStep.MIXTURES)
        experiment_idx = steps.index(WizardStep.EXPERIMENT)
        assert mixtures_idx < assignments_idx < experiment_idx


class TestWizardState:
    """Tests for wizard state management."""

    def test_wizard_state_creation(self):
        """Test creating a new wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        assert wizard.current_step_index == 0
        assert len(wizard.runs) == 0
        assert len(wizard.samples) == 0
        assert len(wizard.mixtures) == 0
        assert wizard.experiment is None

    def test_wizard_starts_at_runs_step(self):
        """Test that wizard always starts at RUNS step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        assert wizard.get_current_step() == WizardStep.RUNS

    def test_wizard_cannot_skip_steps(self):
        """Test that wizard cannot skip to later steps."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        # Try to jump to step 3 (MIXTURES), should fail
        with pytest.raises(ValueError, match="Cannot skip"):
            wizard.set_current_step_index(3)

    def test_wizard_requires_runs_first(self):
        """Test that at least one run must exist before moving past RUNS step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        wizard.add_run(file="test.raw", mixture=None, fraction=1)
        # Now we can advance
        wizard.set_current_step_index(1)
        assert wizard.get_current_step() == WizardStep.SAMPLES

    def test_wizard_advance_to_next_step(self):
        """Test advancing wizard to next step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        wizard.add_run(file="test.raw", mixture=None, fraction=1)
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.SAMPLES

    def test_wizard_go_back_to_previous_step(self):
        """Test going back to previous step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        wizard.add_run(file="test.raw", mixture=None, fraction=1)
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.SAMPLES
        wizard.previous_step()
        assert wizard.get_current_step() == WizardStep.RUNS

    def test_wizard_cannot_go_back_from_first_step(self):
        """Test that we cannot go back from first step."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        with pytest.raises(ValueError, match="Cannot go back"):
            wizard.previous_step()

    def test_wizard_cannot_advance_past_last_step(self):
        """Test that we cannot advance past the last step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        # Populate minimal data to reach end
        wizard.add_run(file="test.raw", mixture=None, fraction=1)
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        wizard.next_step()  # EXPERIMENT
        # Save experiment to reach REVIEW
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # REVIEW
        assert wizard.get_current_step() == WizardStep.REVIEW
        with pytest.raises(ValueError, match="Cannot advance"):
            wizard.next_step()

    def test_wizard_add_run(self):
        """Test adding a run to the wizard."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="s3://bucket/file.raw", mixture="mix_1", fraction=1)
        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "s3://bucket/file.raw"

    def test_wizard_add_sample(self):
        """Test adding a sample to the wizard."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="sample_1", organism="homo sapiens", organism_part="liver")
        assert len(wizard.samples) == 1
        assert wizard.samples[0]["id"] == "sample_1"

    def test_wizard_add_mixture(self):
        """Test adding a mixture to the wizard."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_mixture(id="mix_1", channels={"TMT126": "s1", "TMT127N": "s2"})
        assert len(wizard.mixtures) == 1
        assert wizard.mixtures[0]["id"] == "mix_1"

    def test_wizard_mixture_channels_reference_existing_samples(self):
        """Test that mixture channels can only reference existing samples."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")
        # Try to reference non-existent sample
        with pytest.raises(ValueError, match="not found in samples"):
            wizard.add_mixture(id="mix_1", channels={"TMT126": "s1", "TMT127N": "nonexistent"})

    def test_wizard_set_experiment(self):
        """Test setting experiment parameters."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="TMT"
        )
        assert wizard.experiment["acquisition_method"] == "DDA"
        assert wizard.experiment["enzyme"] == "Trypsin"
        assert wizard.experiment["dissociation_method"] == "HCD"

    def test_wizard_to_manifest_state(self):
        """Test converting wizard state to ManifestState."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="test.raw", mixture=None, fraction=1)
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )

        manifest = wizard.to_manifest_state()

        assert isinstance(manifest, ManifestState)
        assert len(manifest.runs) == 1
        assert len(manifest.samples) == 1
        assert manifest.experiment is not None
        assert manifest.experiment.acquisition_method == "DDA"

    def test_wizard_validation_deferred_to_review(self):
        """Test that validation only happens in review step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        # Add incomplete data - should not validate until review
        wizard.add_run(file="test.raw")
        wizard.next_step()
        # At SAMPLES step, validation should not happen yet
        # (only validate when we call to_manifest_state or in REVIEW step)
        assert wizard.get_current_step() == WizardStep.SAMPLES

    def test_wizard_get_available_runs(self):
        """Test retrieving available runs."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="test1.raw")
        wizard.add_run(file="test2.mzML")
        runs = wizard.get_available_runs()
        assert len(runs) == 2
        assert any(r["file"] == "test1.raw" for r in runs)

    def test_wizard_get_available_samples(self):
        """Test retrieving available samples."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.add_sample(id="s2", organism="mus musculus")
        samples = wizard.get_available_samples()
        assert len(samples) == 2
        assert any(s["id"] == "s1" for s in samples)


class TestOntologyOptionProviderIntegration:
    """Tests for option provider integration with wizard."""

    def test_get_enzyme_options(self):
        """Test getting enzyme options from provider."""
        provider = OntologyOptionProvider()
        options = provider.get_options("enzyme")
        assert len(options) > 0
        # Should include Trypsin at least
        assert any("Trypsin" in str(opt) for opt in options)

    def test_get_dissociation_method_options(self):
        """Test getting dissociation method options from provider."""
        provider = OntologyOptionProvider()
        options = provider.get_options("dissociation_method")
        assert len(options) > 0
        # Should include HCD at least
        assert any("HCD" in str(opt) for opt in options)

    def test_get_organism_options(self):
        """Test getting organism options from provider."""
        provider = OntologyOptionProvider()
        options = provider.get_options("organism")
        assert len(options) > 0

    def test_get_organism_part_options(self):
        """Test getting organism part options from provider."""
        provider = OntologyOptionProvider()
        options = provider.get_options("organism_part")
        assert len(options) > 0

    def test_get_instrument_options(self):
        """Test getting instrument options from provider."""
        provider = OntologyOptionProvider()
        options = provider.get_options("instrument")
        assert len(options) > 0

    def test_unknown_field_returns_empty(self):
        """Test that unknown field returns empty list."""
        provider = OntologyOptionProvider()
        options = provider.get_options("unknown_field")
        assert options == []

    def test_option_provider_supported_fields(self):
        """Test getting list of supported fields."""
        provider = OntologyOptionProvider()
        fields = provider.get_supported_fields()
        assert "enzyme" in fields
        assert "dissociation_method" in fields
        assert "organism" in fields


class TestChannelBuilderIntegration:
    """Tests for channel builder integration."""

    def test_get_tmt6_channels(self):
        """Test getting TMT6 channel list."""
        builder = ChannelBuilder("TMT6")
        channels = builder.get_available_channels()
        assert len(channels) == 6
        assert "TMT126" in channels

    def test_get_silac_channels(self):
        """Test getting SILAC channel list."""
        builder = ChannelBuilder("SILAC_2plex")
        channels = builder.get_available_channels()
        assert "Light" in channels
        assert "Heavy" in channels

    def test_get_supported_plex_types(self):
        """Test getting list of supported plex types."""
        plex_types = ChannelBuilder.get_supported_plex_types()
        assert "TMT6" in plex_types
        assert "TMT11" in plex_types
        assert "SILAC_2plex" in plex_types

    def test_unknown_plex_raises_error(self):
        """Test that unknown plex type raises error."""
        with pytest.raises(ValueError):
            ChannelBuilder("UNKNOWN_PLEX")


class TestWizardWorkflow:
    """Integration tests for complete wizard workflow."""

    def test_complete_lfq_workflow(self):
        """Test complete LFQ wizard workflow."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()

        # Step 1: Runs
        assert wizard.get_current_step() == WizardStep.RUNS
        wizard.add_run(file="sample1.raw", fraction=1)
        wizard.add_run(file="sample2.raw", fraction=1)
        wizard.next_step()

        # Step 2: Samples
        assert wizard.get_current_step() == WizardStep.SAMPLES
        wizard.add_sample(id="treated", organism="homo sapiens", condition="treated")
        wizard.add_sample(id="control", organism="homo sapiens", condition="control")
        wizard.next_step()

        # Step 3: Mixtures (skip for LFQ)
        assert wizard.get_current_step() == WizardStep.MIXTURES
        wizard.next_step()

        # Step 4: Assignments
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
        wizard.next_step()

        # Step 5: Experiment
        assert wizard.get_current_step() == WizardStep.EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="LFQ",
            dissociation_method="HCD"
        )
        wizard.next_step()

        # Step 6: Review
        assert wizard.get_current_step() == WizardStep.REVIEW
        manifest = wizard.to_manifest_state()
        assert len(manifest.runs) == 2
        assert len(manifest.samples) == 2

    def test_complete_tmt_workflow(self):
        """Test complete TMT wizard workflow."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()

        # Step 1: Runs
        wizard.add_run(file="mix1_f1.raw", mixture="mix1", fraction=1)
        wizard.add_run(file="mix1_f2.raw", mixture="mix1", fraction=2)
        wizard.next_step()

        # Step 2: Samples
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_sample(id="s3")
        wizard.next_step()

        # Step 3: Mixtures
        assert wizard.get_current_step() == WizardStep.MIXTURES
        wizard.add_mixture(id="mix1", channels={
            "TMT126": "s1",
            "TMT127N": "s2",
            "TMT127C": "s3"
        })
        wizard.next_step()

        # Step 4: Assignments
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
        wizard.next_step()

        # Step 5: Experiment
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="TMT",
            dissociation_method="HCD"
        )
        wizard.next_step()

        # Step 6: Review
        manifest = wizard.to_manifest_state()
        assert len(manifest.mixtures) == 1
        assert len(manifest.samples) == 3


class TestExperimentStepForwardGating:
    """Tests for forward-gating behavior on EXPERIMENT step."""

    def test_cannot_advance_to_review_without_saving_experiment(self):
        """Test that wizard cannot advance from EXPERIMENT to REVIEW without saving settings."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Setup: Runs required to progress past RUNS
        wizard.add_run(file="test.raw", fraction=1)
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        wizard.next_step()  # EXPERIMENT
        assert wizard.get_current_step() == WizardStep.EXPERIMENT

        # Try to advance without saving - should fail
        with pytest.raises(ValueError, match="Experiment settings must be saved"):
            wizard.set_current_step_index(wizard.current_step_index + 1)

    def test_can_advance_to_review_after_saving_experiment(self):
        """Test that wizard can advance from EXPERIMENT to REVIEW after saving settings."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Setup
        wizard.add_run(file="test.raw", fraction=1)
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        wizard.next_step()  # EXPERIMENT
        assert wizard.get_current_step() == WizardStep.EXPERIMENT

        # Save experiment settings
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )

        # Now advancing should work
        wizard.set_current_step_index(wizard.current_step_index + 1)
        assert wizard.get_current_step() == WizardStep.REVIEW


class TestAssignmentsStep:
    """Tests for the new ASSIGNMENTS step."""

    def test_assignments_step_after_mixtures(self):
        """Test that ASSIGNMENTS step comes after MIXTURES in sequence."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Add minimal data to progress
        wizard.add_run(file="test.raw")
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        assert wizard.get_current_step() == WizardStep.MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS

    def test_assignments_step_before_experiment(self):
        """Test that ASSIGNMENTS step comes before EXPERIMENT."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Progress to ASSIGNMENTS
        wizard.add_run(file="test.raw")
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
        wizard.next_step()  # EXPERIMENT
        assert wizard.get_current_step() == WizardStep.EXPERIMENT

    def test_assign_run_to_sample(self):
        """Test assigning a run to an existing sample."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Add data
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="sample_1")
        # Assign run to sample
        wizard.assign_run(run_index=0, sample="sample_1", instrument="Orbitrap Exploris")
        # Check assignment was recorded
        assert wizard.runs[0].get("sample") == "sample_1"
        assert wizard.runs[0].get("instrument") == "Orbitrap Exploris"

    def test_assign_run_to_mixture(self):
        """Test assigning a run to an existing mixture."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        # Add data
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="mix_1", channels={"TMT126": "s1"})
        # Assign run to mixture
        wizard.assign_run(run_index=0, mixture="mix_1", fraction=1, instrument="Orbitrap Exploris")
        # Check assignment
        assert wizard.runs[0].get("mixture") == "mix_1"
        assert wizard.runs[0].get("fraction") == 1
        assert wizard.runs[0].get("instrument") == "Orbitrap Exploris"

    def test_assign_run_with_invalid_sample_raises_error(self):
        """Test that assigning run to non-existent sample raises error."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="test.raw")
        # Try to assign to non-existent sample
        with pytest.raises(ValueError, match="Sample.*not found"):
            wizard.assign_run(run_index=0, sample="nonexistent")

    def test_assign_run_with_invalid_mixture_raises_error(self):
        """Test that assigning run to non-existent mixture raises error."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="test.raw")
        # Try to assign to non-existent mixture
        with pytest.raises(ValueError, match="Mixture.*not found"):
            wizard.assign_run(run_index=0, mixture="nonexistent")

    def test_get_run_assignment(self):
        """Test retrieving run assignment."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1")
        wizard.assign_run(run_index=0, sample="s1", instrument="Orbitrap")

        assignment = wizard.get_run_assignment(0)
        assert assignment["sample"] == "s1"
        assert assignment["instrument"] == "Orbitrap"

    def test_get_available_mixtures(self):
        """Test retrieving list of available mixtures."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "s1", "TMT127N": "s2"})
        wizard.add_mixture(id="mix2", channels={"TMT126": "s2"})

        mixtures = wizard.get_available_mixtures()
        assert len(mixtures) == 2
        assert any(m["id"] == "mix1" for m in mixtures)
        assert any(m["id"] == "mix2" for m in mixtures)

    def test_multiple_runs_independent_assignments(self):
        """Test that multiple runs have independent assignments."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="run1.raw")
        wizard.add_run(file="run2.raw")
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")

        # Assign each run to different sample
        wizard.assign_run(run_index=0, sample="s1", instrument="Instrument1")
        wizard.assign_run(run_index=1, sample="s2", instrument="Instrument2")

        # Verify independent assignments
        assert wizard.runs[0].get("sample") == "s1"
        assert wizard.runs[0].get("instrument") == "Instrument1"
        assert wizard.runs[1].get("sample") == "s2"
        assert wizard.runs[1].get("instrument") == "Instrument2"


class TestCanGoForwardGating:
    """Tests for can_go_forward() properly gating step progression."""

    def test_can_go_forward_from_runs_requires_at_least_one_run(self):
        """Test that RUNS step requires at least one run to go forward."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep

        wizard = ManifestEditingWizard()
        assert wizard.get_current_step() == WizardStep.RUNS
        # Should not be able to go forward without runs
        assert not wizard.can_go_forward()

        # Add run
        wizard.wizard.add_run(file="test.raw")
        # Now should be able to go forward
        assert wizard.can_go_forward()

    def test_can_go_forward_from_samples_always_true(self):
        """Test that SAMPLES step always allows forward navigation."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep

        wizard = ManifestEditingWizard()
        wizard.wizard.add_run(file="test.raw")
        wizard.wizard.next_step()  # SAMPLES
        assert wizard.get_current_step() == WizardStep.SAMPLES
        # Should allow forward even without samples (empty is valid for skip)
        assert wizard.can_go_forward()

    def test_can_go_forward_from_mixtures_always_true(self):
        """Test that MIXTURES step always allows forward navigation."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep

        wizard = ManifestEditingWizard()
        wizard.wizard.add_run(file="test.raw")
        wizard.wizard.next_step()  # SAMPLES
        wizard.wizard.next_step()  # MIXTURES
        assert wizard.get_current_step() == WizardStep.MIXTURES
        # Should allow forward even without mixtures (skip for LFQ)
        assert wizard.can_go_forward()

    def test_can_go_forward_from_assignments_always_true(self):
        """Test that ASSIGNMENTS step always allows forward navigation."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep

        wizard = ManifestEditingWizard()
        wizard.wizard.add_run(file="test.raw")
        wizard.wizard.next_step()  # SAMPLES
        wizard.wizard.next_step()  # MIXTURES
        wizard.wizard.next_step()  # ASSIGNMENTS
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
        # Should allow forward (assignments are deferred to review)
        assert wizard.can_go_forward()

    def test_can_go_forward_from_experiment_requires_saved_settings(self):
        """Test that EXPERIMENT step requires saved settings to go forward."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep

        wizard = ManifestEditingWizard()
        wizard.wizard.add_run(file="test.raw")
        wizard.wizard.next_step()  # SAMPLES
        wizard.wizard.next_step()  # MIXTURES
        wizard.wizard.next_step()  # ASSIGNMENTS
        wizard.wizard.next_step()  # EXPERIMENT
        assert wizard.get_current_step() == WizardStep.EXPERIMENT

        # Should not allow forward without saved experiment
        assert not wizard.can_go_forward()

        # Save experiment
        wizard.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        # Now should allow forward
        assert wizard.can_go_forward()

    def test_can_go_forward_from_review_always_false(self):
        """Test that REVIEW step never allows forward navigation."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep

        wizard = ManifestEditingWizard()
        wizard.wizard.add_run(file="test.raw")
        wizard.wizard.next_step()  # SAMPLES
        wizard.wizard.next_step()  # MIXTURES
        wizard.wizard.next_step()  # ASSIGNMENTS
        wizard.wizard.next_step()  # EXPERIMENT
        wizard.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.wizard.next_step()  # REVIEW
        assert wizard.get_current_step() == WizardStep.REVIEW

        # Should not allow forward from REVIEW
        assert not wizard.can_go_forward()


class TestWizardStateRowMutations:
    """Tests for wizard state row mutation operations (Phase 1)."""

    def test_wizard_remove_run(self):
        """Test removing a run from wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="file1.raw")
        wizard.add_run(file="file2.raw")
        wizard.add_run(file="file3.raw")
        assert len(wizard.runs) == 3

        wizard.remove_run(1)
        assert len(wizard.runs) == 2
        assert wizard.runs[0]["file"] == "file1.raw"
        assert wizard.runs[1]["file"] == "file3.raw"

    def test_wizard_update_run(self):
        """Test updating a run in wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="file.raw", fraction=1, instrument="Orbitrap")

        wizard.update_run(0, fraction=2, instrument="Lumos")
        assert wizard.runs[0]["fraction"] == 2
        assert wizard.runs[0]["instrument"] == "Lumos"
        assert wizard.runs[0]["file"] == "file.raw"  # Unchanged

    def test_wizard_remove_sample(self):
        """Test removing a sample from wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_sample(id="s3")
        assert len(wizard.samples) == 3

        wizard.remove_sample(1)
        assert len(wizard.samples) == 2
        assert wizard.samples[0]["id"] == "s1"
        assert wizard.samples[1]["id"] == "s3"

    def test_wizard_update_sample(self):
        """Test updating a sample in wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1", organism="homo sapiens", condition="control")

        wizard.update_sample(0, organism="mus musculus", condition="treated")
        assert wizard.samples[0]["organism"] == "mus musculus"
        assert wizard.samples[0]["condition"] == "treated"
        assert wizard.samples[0]["id"] == "s1"  # Unchanged

    def test_wizard_remove_mixture(self):
        """Test removing a mixture from wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "s1"})
        wizard.add_mixture(id="mix2", channels={"TMT126": "s1"})
        assert len(wizard.mixtures) == 2

        wizard.remove_mixture(0)
        assert len(wizard.mixtures) == 1
        assert wizard.mixtures[0]["id"] == "mix2"

    def test_wizard_update_mixture(self):
        """Test updating a mixture in wizard state."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")
        wizard.add_sample(id="s2")
        wizard.add_mixture(id="mix1", channels={"TMT126": "s1"}, description="Original")

        wizard.update_mixture(0, description="Updated", channels={"TMT126": "s2"})
        assert wizard.mixtures[0]["description"] == "Updated"
        assert wizard.mixtures[0]["channels"]["TMT126"] == "s2"
        assert wizard.mixtures[0]["id"] == "mix1"  # Unchanged

    def test_wizard_run_mutation_invalid_index(self):
        """Test that invalid run index raises error during mutation."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="file.raw")

        with pytest.raises(IndexError):
            wizard.update_run(5, fraction=2)

        with pytest.raises(IndexError):
            wizard.remove_run(5)

    def test_wizard_sample_mutation_invalid_index(self):
        """Test that invalid sample index raises error during mutation."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")

        with pytest.raises(IndexError):
            wizard.update_sample(5, organism="homo sapiens")

        with pytest.raises(IndexError):
            wizard.remove_sample(5)

    def test_wizard_mixture_mutation_invalid_index(self):
        """Test that invalid mixture index raises error during mutation."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_sample(id="s1")
        wizard.add_mixture(id="mix1", channels={"TMT126": "s1"})

        with pytest.raises(IndexError):
            wizard.update_mixture(5, description="test")

        with pytest.raises(IndexError):
            wizard.remove_mixture(5)


class TestGuiWizardShellLockedProgression:
    """Tests for GUI-level locked wizard progression."""

    def test_wizard_gui_starts_at_runs_step(self):
        """Test that GUI wizard always starts at RUNS step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        assert wizard.get_current_step() == WizardStep.RUNS
        assert wizard.current_step_index == 0

    def test_wizard_gui_cannot_skip_forward_without_runs(self):
        """Test that GUI cannot advance past RUNS without adding runs."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        # No runs added
        with pytest.raises(ValueError, match="At least one run"):
            wizard.next_step()

    def test_wizard_gui_can_advance_with_run(self):
        """Test that GUI can advance RUNS after adding a run."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        # Should not raise
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.SAMPLES

    def test_wizard_gui_back_button_disabled_on_first_step(self):
        """Test that back button is disabled on first (RUNS) step."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        assert wizard.current_step_index == 0
        with pytest.raises(ValueError, match="Cannot go back"):
            wizard.previous_step()

    def test_wizard_gui_back_navigation_works_from_second_step(self):
        """Test that back navigation works from second step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.SAMPLES
        wizard.previous_step()
        assert wizard.get_current_step() == WizardStep.RUNS

    def test_wizard_gui_sequential_forward_progression(self):
        """Test complete sequential forward progression."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        steps = WizardStep.ordered_steps()
        expected_order = [
            WizardStep.RUNS, WizardStep.SAMPLES, WizardStep.MIXTURES,
            WizardStep.ASSIGNMENTS, WizardStep.EXPERIMENT, WizardStep.REVIEW
        ]
        assert steps == expected_order

    def test_wizard_gui_next_button_disabled_on_last_step(self):
        """Test that next button is disabled on last (REVIEW) step."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        # Populate and reach REVIEW
        wizard.add_run(file="test.raw")
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # REVIEW
        assert wizard.get_current_step() == WizardStep.REVIEW
        with pytest.raises(ValueError, match="Cannot advance"):
            wizard.next_step()

    def test_wizard_gui_review_step_allows_validation(self):
        """Test that REVIEW step can validate manifest state."""
        from gui_wizard_state import WizardState, WizardStep
        wizard = WizardState()
        wizard.add_run(file="test.raw")
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # ASSIGNMENTS
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # REVIEW
        assert wizard.get_current_step() == WizardStep.REVIEW
        # Should be able to convert to manifest for validation
        manifest = wizard.to_manifest_state()
        assert manifest is not None


class TestManifestEditingWizardCanGoForward:
    """Tests for the can_go_forward button logic."""

    def test_can_go_forward_blocked_without_runs(self):
        """Test that can_go_forward is False on RUNS step without any runs."""
        from gui_nicegui import ManifestEditingWizard
        editor = ManifestEditingWizard()
        # At RUNS step with no runs - cannot go forward
        assert not editor.can_go_forward()

    def test_can_go_forward_allowed_with_runs(self):
        """Test that can_go_forward is True on RUNS step with at least one run."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep
        editor = ManifestEditingWizard()
        editor.wizard.add_run(file="test.raw")
        # At RUNS step with a run - should be able to go forward
        assert editor.wizard.get_current_step() == WizardStep.RUNS
        assert editor.can_go_forward()

    def test_can_go_forward_allowed_on_samples_step(self):
        """Test that can_go_forward is True on SAMPLES step (always allows forward)."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep
        editor = ManifestEditingWizard()
        editor.wizard.add_run(file="test.raw")
        editor.wizard.next_step()
        assert editor.wizard.get_current_step() == WizardStep.SAMPLES
        # Should be able to go forward even without adding samples
        assert editor.can_go_forward()

    def test_can_go_forward_blocked_without_experiment_settings(self):
        """Test that can_go_forward is False on EXPERIMENT step without saved settings."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep
        editor = ManifestEditingWizard()
        # Prepare by reaching EXPERIMENT step
        editor.wizard.add_run(file="test.raw")
        editor.wizard.next_step()  # SAMPLES
        editor.wizard.next_step()  # MIXTURES
        editor.wizard.next_step()  # ASSIGNMENTS
        editor.wizard.next_step()  # EXPERIMENT
        assert editor.wizard.get_current_step() == WizardStep.EXPERIMENT
        # Without experiment settings saved, cannot go forward
        assert not editor.can_go_forward()

    def test_can_go_forward_allowed_with_experiment_settings(self):
        """Test that can_go_forward is True on EXPERIMENT step with saved settings."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep
        editor = ManifestEditingWizard()
        # Prepare by reaching EXPERIMENT step
        editor.wizard.add_run(file="test.raw")
        editor.wizard.next_step()  # SAMPLES
        editor.wizard.next_step()  # MIXTURES
        editor.wizard.next_step()  # ASSIGNMENTS
        editor.wizard.next_step()  # EXPERIMENT
        assert editor.wizard.get_current_step() == WizardStep.EXPERIMENT
        # Set experiment settings
        editor.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        # Now should be able to go forward
        assert editor.can_go_forward()

    def test_can_go_forward_blocked_on_review_step(self):
        """Test that can_go_forward is False on REVIEW (last) step."""
        from gui_nicegui import ManifestEditingWizard
        from gui_wizard_state import WizardStep
        editor = ManifestEditingWizard()
        # Populate and reach REVIEW
        editor.wizard.add_run(file="test.raw")
        editor.wizard.next_step()  # SAMPLES
        editor.wizard.next_step()  # MIXTURES
        editor.wizard.next_step()  # ASSIGNMENTS
        editor.wizard.next_step()  # EXPERIMENT
        editor.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        editor.wizard.next_step()  # REVIEW
        assert editor.wizard.get_current_step() == WizardStep.REVIEW
        # Cannot go forward from REVIEW (last step)
        assert not editor.can_go_forward()
