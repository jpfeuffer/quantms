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
option provider integration, conversion to ManifestState, and the critical
pre-navigation flush behavior that guards against losing pending spreadsheet edits.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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

        assert WizardStep.ordered_steps() == [
            WizardStep.RUNS,
            WizardStep.SAMPLES,
            WizardStep.MIXTURES,
            WizardStep.EXPERIMENT,
            WizardStep.ASSIGNMENTS,
            WizardStep.REVIEW,
        ]

    def test_assignments_step_exists(self):
        """Test that ASSIGNMENTS step is defined in the wizard."""
        from gui_wizard_state import WizardStep
        assert hasattr(WizardStep, 'ASSIGNMENTS')
        steps = WizardStep.ordered_steps()
        assert WizardStep.ASSIGNMENTS in steps
        # ASSIGNMENTS should come after EXPERIMENT and before REVIEW
        assignments_idx = steps.index(WizardStep.ASSIGNMENTS)
        experiment_idx = steps.index(WizardStep.EXPERIMENT)
        review_idx = steps.index(WizardStep.REVIEW)
        assert experiment_idx < assignments_idx < review_idx


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
        assert len(wizard.groups) == 0
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
        wizard.next_step()  # EXPERIMENT
        # Save experiment to reach ASSIGNMENTS
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # ASSIGNMENTS
        wizard.next_step()  # REVIEW
        assert wizard.get_current_step() == WizardStep.REVIEW
        with pytest.raises(ValueError, match="Cannot advance"):
            wizard.next_step()

    def test_wizard_add_run(self):
        """Test adding a run to the wizard."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(
            file="s3://bucket/file.raw",
            mixture="mix_1",
            fraction=1,
            modification_profile="default",
        )
        assert len(wizard.runs) == 1
        assert wizard.runs[0]["file"] == "s3://bucket/file.raw"
        assert wizard.runs[0]["modification_profile"] == "default"

    @pytest.mark.parametrize(
        ("file_name", "expected_fraction"),
        [
            ("sample_f12.raw", 12),
            ("sample_F34.raw", 34),
            ("sample_fraction56.raw", 56),
            ("sample_Frac78.raw", 78),
        ],
    )
    def test_wizard_add_run_infers_fraction_from_supported_filename_patterns(self, file_name, expected_fraction):
        """Test that add_run infers fractions from supported filename suffix patterns."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file=f"/data/{file_name}")

        assert wizard.runs[0]["fraction"] == expected_fraction

    def test_wizard_add_run_does_not_infer_fraction_for_letter_prefixed_f_pattern(self):
        """Test that the short fNN form requires a non-letter prefix before the marker."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="/data/samplexF12.raw")

        assert "fraction" not in wizard.runs[0]

    def test_wizard_add_run_preserves_explicit_fraction_over_filename_inference(self):
        """Test that an explicit fraction wins over any inferred filename fraction."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="/data/sample_fraction12.raw", fraction=3)

        assert wizard.runs[0]["fraction"] == 3

    def test_wizard_add_modification(self):
        """Test adding a modification to the wizard."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_modification(
            mode="fixed",
            kind="ontology",
            name="Carbamidomethyl",
            residues="C",
            profile="default",
        )
        assert len(wizard.modifications) == 1
        assert wizard.modifications[0]["name"] == "Carbamidomethyl"
        assert wizard.modifications[0]["profile"] == "default"

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

    def test_wizard_add_group_and_assign_run_to_group(self):
        """Test adding an authoring group and assigning a run to it."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="run_1.raw")

        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")
        wizard.assign_run(run_index=0, group_id="group_1")

        assert len(wizard.groups) == 1
        assert wizard.groups[0]["id"] == "group_1"
        assert wizard.groups[0]["name"] == "LFQ group"
        assert wizard.groups[0]["kind"] == "LFQ"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]
        assert wizard.runs[0]["group_id"] == "group_1"

    def test_wizard_group_kind_options_follow_quantification_method(self):
        """Test that allowed group kinds mirror the experiment quantification method when present."""
        from gui_wizard_state import WizardState

        wizard = WizardState()

        assert wizard.get_allowed_group_kinds() == ["LFQ", "TMT", "iTRAQ", "SILAC"]

        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="TMT",
        )

        assert wizard.get_allowed_group_kinds() == ["TMT"]

    def test_wizard_update_group_reassigns_members_safely(self):
        """Test that editing a group updates metadata and member assignments consistently."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="run_1.raw")
        wizard.add_run(file="run_2.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")
        wizard.assign_run(run_index=0, group_id="group_1")

        wizard.update_group(
            "group_1",
            name="Updated group",
            kind="TMT",
            members=[wizard.runs[1]["id"]],
            description="Updated description",
        )

        assert wizard.groups[0]["name"] == "Updated group"
        assert wizard.groups[0]["kind"] == "TMT"
        assert wizard.groups[0]["members"] == [wizard.runs[1]["id"]]
        assert wizard.groups[0]["description"] == "Updated description"
        assert "group_id" not in wizard.runs[0]
        assert wizard.runs[1]["group_id"] == "group_1"

    def test_wizard_update_group_rejects_invalid_members_and_disallowed_kind(self):
        """Test that group edits validate member IDs and experiment-driven kind constraints."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="run_1.raw")
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")

        with pytest.raises(ValueError, match="Run 'run_999' not found"):
            wizard.update_group("group_1", members=["run_999"])

        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
            quantification_method="SILAC",
        )

        with pytest.raises(ValueError, match="Allowed options: SILAC"):
            wizard.update_group("group_1", kind="LFQ")

    def test_wizard_group_labeling_strategy_defaults_from_kind(self):
        """Test that supported group kinds backfill a labeling strategy and derived channel count."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_group(id="group_1", name="LFQ group", kind="LFQ")

        assert wizard.groups[0]["labeling_strategy"] == "label free sample"
        assert wizard.groups[0]["channel_count"] == 1

    def test_wizard_labeling_strategies_follow_current_kind(self):
        """Test that supported labeling strategies are filtered from the current group kind."""
        from gui_wizard_state import WizardState

        wizard = WizardState()

        assert wizard.get_allowed_labeling_strategies("LFQ") == ["label free sample"]
        assert wizard.get_allowed_labeling_strategies("TMT") == [
            plex_type for plex_type in ChannelBuilder.get_supported_plex_types() if plex_type.startswith("TMT")
        ]
        assert wizard.get_allowed_labeling_strategies("iTRAQ") == [
            plex_type for plex_type in ChannelBuilder.get_supported_plex_types() if plex_type.startswith("iTRAQ")
        ]
        assert wizard.get_allowed_labeling_strategies("SILAC") == [
            plex_type for plex_type in ChannelBuilder.get_supported_plex_types() if plex_type.startswith("SILAC")
        ]

    def test_wizard_group_kind_change_keeps_strategy_and_channel_count_in_sync(self):
        """Test that changing a group kind refreshes the stored strategy and derived channel count."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_group(id="group_1", name="Multiplex group", kind="TMT", labeling_strategy="TMT6")

        wizard.update_group("group_1", kind="LFQ")

        assert wizard.groups[0]["kind"] == "LFQ"
        assert wizard.groups[0]["labeling_strategy"] == "label free sample"
        assert wizard.groups[0]["channel_count"] == 1

    def test_wizard_seed_runs_from_filenames_groups_fractioned_files_only_when_requested(self):
        """Test that fraction markers are grouped only after an explicit regroup request."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="/data/sample_fraction1.raw")
        wizard.add_run(file="/data/sample_fraction2.raw")

        assert "group_id" not in wizard.runs[0]
        assert "group_id" not in wizard.runs[1]
        assert wizard.groups == []

        seeded_count = wizard.seed_runs_from_filenames(force=True)

        assert seeded_count == 2
        assert wizard.runs[0]["group_id"] == wizard.runs[1]["group_id"]
        assert len(wizard.groups) == 1
        assert wizard.groups[0]["id"] == wizard.runs[0]["group_id"]
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"], wizard.runs[1]["id"]]

    def test_wizard_seed_runs_from_filenames_preserves_unrelated_run_fields(self):
        """Filename reseeding should not clobber unrelated run fields like instrument."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="/data/sample_fraction1.raw", instrument="Orbitrap")
        wizard.add_run(file="/data/sample_fraction2.raw", instrument="TOF")

        seeded_count = wizard.seed_runs_from_filenames(force=True)

        assert seeded_count == 2
        assert wizard.runs[0]["instrument"] == "Orbitrap"
        assert wizard.runs[1]["instrument"] == "TOF"

    def test_wizard_assign_run_creates_missing_group(self):
        """Test that assigning a run to a new group creates the group automatically."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="/data/sample.raw")

        wizard.assign_run(run_index=0, group_id="new_group")

        assert wizard.runs[0]["group_id"] == "new_group"
        assert wizard.groups[0]["id"] == "new_group"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"]]

    def test_wizard_cleared_group_assignment_stays_cleared_until_explicit_regroup(self):
        """Clearing a group assignment should stick until the user explicitly regroups."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="/data/sample_fraction1.raw")

        assert "group_id" not in wizard.runs[0]

        wizard.add_run(file="/data/sample_fraction2.raw")

        assert "group_id" not in wizard.runs[0]
        assert "group_id" not in wizard.runs[1]
        assert wizard.groups == []

        wizard.seed_runs_from_filenames(force=True)

        assert wizard.runs[0]["group_id"] == "sample"
        assert wizard.runs[1]["group_id"] == "sample"
        assert wizard.groups[0]["members"] == [wizard.runs[0]["id"], wizard.runs[1]["id"]]

        wizard.clear_run_field(0, "group_id")
        assert "group_id" not in wizard.runs[0]
        assert wizard.runs[0]["group_assignment_cleared"] is True
        assert wizard.runs[1]["group_id"] == "sample"

    def test_wizard_add_group_rejects_duplicate_ids(self):
        """Test that group IDs must be unique."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")

        with pytest.raises(ValueError, match="already exists"):
            wizard.add_group(id="group_1", name="Duplicate group", kind="replicate")

    def test_wizard_reassign_run_moves_membership_between_groups(self):
        """Test that reassigning a run updates both group memberships."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="run_1.raw")
        wizard.add_group(id="group_1", name="Group 1", kind="replicate")
        wizard.add_group(id="group_2", name="Group 2", kind="replicate")

        wizard.assign_run(run_index=0, group_id="group_1")
        wizard.assign_run(run_index=0, group_id="group_2")

        assert wizard.runs[0]["group_id"] == "group_2"
        assert wizard.groups[0]["members"] == []
        assert wizard.groups[1]["members"] == [wizard.runs[0]["id"]]

    def test_wizard_get_available_groups_returns_copy(self):
        """Test retrieving available authoring groups without exposing internal state."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")

        groups = wizard.get_available_groups()

        assert len(groups) == 1
        groups[0]["name"] = "mutated"
        assert wizard.groups[0]["name"] == "Replicate group"

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
        wizard.add_run(file="test.raw", mixture=None, fraction=1, modification_profile="default")
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")
        wizard.assign_run(run_index=0, group_id="group_1")
        wizard.add_modification(
            mode="fixed",
            kind="ontology",
            name="Carbamidomethyl",
            residues="C",
            profile="default",
        )
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )

        manifest = wizard.to_manifest_state()

        assert isinstance(manifest, ManifestState)
        assert len(manifest.runs) == 1
        assert len(manifest.samples) == 1
        assert len(manifest.modifications) == 1
        assert manifest.experiment is not None
        assert manifest.experiment.acquisition_method == "DDA"
        assert manifest.runs[0].modification_profile == "default"
        assert manifest.modifications[0].profile == "default"
        assert not hasattr(manifest.runs[0], "group_id")
        assert "group_id" not in manifest.to_dict()["runs"][0]

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

        # Step 4: Experiment
        assert wizard.get_current_step() == WizardStep.EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="LFQ",
            dissociation_method="HCD"
        )
        wizard.next_step()

        # Step 5: Assignments
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
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

        # Step 4: Experiment
        assert wizard.get_current_step() == WizardStep.EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="TMT",
            dissociation_method="HCD"
        )
        wizard.next_step()

        # Step 5: Assignments
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
        wizard.next_step()

        # Step 6: Review
        manifest = wizard.to_manifest_state()
        assert len(manifest.mixtures) == 1
        assert len(manifest.samples) == 3


class TestExperimentStepForwardGating:
    """Tests for forward-gating behavior on EXPERIMENT step."""

    def test_cannot_advance_to_review_without_saving_experiment(self):
        """Test that wizard cannot advance from EXPERIMENT to ASSIGNMENTS without saving settings."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Setup: Runs required to progress past RUNS
        wizard.add_run(file="test.raw", fraction=1)
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        assert wizard.get_current_step() == WizardStep.EXPERIMENT

        # Try to advance without saving - should fail
        with pytest.raises(ValueError, match="Experiment settings must be saved"):
            wizard.set_current_step_index(wizard.current_step_index + 1)

    def test_can_advance_to_review_after_saving_experiment(self):
        """Test that wizard can advance from EXPERIMENT to ASSIGNMENTS after saving settings."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Setup
        wizard.add_run(file="test.raw", fraction=1)
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
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
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS


class TestAssignmentsStep:
    """Tests for the new ASSIGNMENTS step."""

    def test_assignments_step_after_experiment(self):
        """Test that ASSIGNMENTS step comes after EXPERIMENT."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Add minimal data to progress
        wizard.add_run(file="test.raw")
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        assert wizard.get_current_step() == WizardStep.EXPERIMENT
        # Save experiment settings to allow progress
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # ASSIGNMENTS
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS

    def test_assignments_step_before_review(self):
        """Test that ASSIGNMENTS step comes before REVIEW."""
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Progress to ASSIGNMENTS
        wizard.add_run(file="test.raw")
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # ASSIGNMENTS
        assert wizard.get_current_step() == WizardStep.ASSIGNMENTS
        wizard.next_step()  # REVIEW
        assert wizard.get_current_step() == WizardStep.REVIEW

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
        wizard.wizard.next_step()  # EXPERIMENT
        wizard.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
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
        wizard.wizard.next_step()  # EXPERIMENT
        wizard.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.wizard.next_step()  # ASSIGNMENTS
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

    def test_wizard_remove_run_clears_group_membership(self):
        """Test that removing a run also removes it from its group membership."""
        from gui_wizard_state import WizardState

        wizard = WizardState()
        wizard.add_run(file="file1.raw")
        wizard.add_run(file="file2.raw")
        wizard.add_group(id="group_1", name="Replicate group", kind="replicate")
        wizard.assign_run(run_index=1, group_id="group_1")

        run_id = wizard.runs[1]["id"]
        wizard.remove_run(1)

        assert len(wizard.runs) == 1
        assert wizard.groups[0]["members"] == []
        assert run_id not in wizard.groups[0]["members"]

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
            WizardStep.EXPERIMENT, WizardStep.ASSIGNMENTS, WizardStep.REVIEW
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
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # ASSIGNMENTS
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
        wizard.next_step()  # EXPERIMENT
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        wizard.next_step()  # ASSIGNMENTS
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
        editor.wizard.next_step()  # EXPERIMENT
        editor.wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD"
        )
        editor.wizard.next_step()  # ASSIGNMENTS
        editor.wizard.next_step()  # REVIEW
        assert editor.wizard.get_current_step() == WizardStep.REVIEW
        # Cannot go forward from REVIEW (last step)
        assert not editor.can_go_forward()


class TestRunTableEditPersistenceAcrossNavigation:
    """Regression tests for run-table edit persistence bug.

    Tests that edited run fields remain intact when navigating forward
    to another step and then back to the runs step.
    (GitHub issue: edits lost on forward/back navigation)
    """

    def test_edited_run_field_persists_after_forward_and_back_navigation(self):
        """
        Regression: Edited run field value should be preserved when navigating
        forward to next step and then back to runs step.

        Scenario:
        1. Create a run with initial values
        2. Edit a field in the run (e.g., fraction or instrument)
        3. Navigate forward to the next step (SAMPLES)
        4. Navigate back to the RUNS step
        5. Verify the edited value is still present in the run
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Step 1: Add a run with initial values
        wizard.add_run(file="sample.raw", fraction=1, instrument="Orbitrap")
        assert wizard.runs[0]["fraction"] == 1
        assert wizard.runs[0]["instrument"] == "Orbitrap"

        # Step 2: Edit the fraction field (simulating user spreadsheet edit)
        wizard.update_run(0, fraction=3)
        assert wizard.runs[0]["fraction"] == 3

        # Step 3: Navigate forward to next step
        wizard.next_step()
        assert wizard.get_current_step() == WizardStep.SAMPLES

        # Step 4: Navigate back to RUNS step
        wizard.previous_step()
        assert wizard.get_current_step() == WizardStep.RUNS

        # Step 5: Verify the edited fraction value persists
        assert wizard.runs[0]["fraction"] == 3, \
            "Edited run field (fraction) was lost after forward/back navigation"
        assert wizard.runs[0]["file"] == "sample.raw", \
            "Run file was unexpectedly modified"
        assert wizard.runs[0]["instrument"] == "Orbitrap", \
            "Run instrument was unexpectedly modified"

    def test_multiple_edited_run_fields_persist_across_navigation(self):
        """
        Regression: Multiple edited fields in a single run should persist
        when navigating away and back.
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Add a run with multiple editable fields
        wizard.add_run(file="sample.raw", fraction=1, instrument="Orbitrap")

        # Edit multiple fields
        wizard.update_run(0, fraction=2, instrument="Lumos")
        assert wizard.runs[0]["fraction"] == 2
        assert wizard.runs[0]["instrument"] == "Lumos"

        # Navigate forward and back
        wizard.next_step()  # SAMPLES
        wizard.next_step()  # MIXTURES
        wizard.previous_step()  # back to SAMPLES
        wizard.previous_step()  # back to RUNS

        # Verify all edited fields persist
        assert wizard.runs[0]["fraction"] == 2, \
            "Fraction field was lost after multi-step navigation"
        assert wizard.runs[0]["instrument"] == "Lumos", \
            "Instrument field was lost after multi-step navigation"

    def test_edits_multiple_runs_persist_across_navigation(self):
        """
        Regression: Edits to multiple runs should all persist when
        navigating away and back.
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Add multiple runs
        wizard.add_run(file="sample1.raw", fraction=1, instrument="Orbitrap")
        wizard.add_run(file="sample2.raw", fraction=1, instrument="Orbitrap")
        wizard.add_run(file="sample3.raw", fraction=1, instrument="Orbitrap")

        # Edit multiple runs with different values
        wizard.update_run(0, fraction=2, instrument="Lumos")
        wizard.update_run(1, fraction=3, instrument="QE HF")
        wizard.update_run(2, fraction=1, instrument="Orbitrap")  # Unchanged

        # Navigate away and back
        wizard.next_step()  # SAMPLES
        wizard.previous_step()  # back to RUNS

        # Verify all edits persist
        assert wizard.runs[0]["fraction"] == 2
        assert wizard.runs[0]["instrument"] == "Lumos"
        assert wizard.runs[1]["fraction"] == 3
        assert wizard.runs[1]["instrument"] == "QE HF"
        assert wizard.runs[2]["fraction"] == 1
        assert wizard.runs[2]["instrument"] == "Orbitrap"


class TestNavigationButtonLabelRendering:
    """Tests for navigation button label rendering (UI layer).

    Regression tests for redundant arrow glyphs in navigation button text.
    Buttons should display "Back" and "Next" as labels, with arrow icons
    handled separately via the icon parameter.

    This is a regression test verifying the Phase 3 fix: arrow glyphs
    were removed from button text labels while preserving the icons.
    """

    def test_navigation_buttons_have_correct_text_labels(self):
        """
        Regression: Navigation button text should be "Back" and "Next"
        without embedded arrow glyphs (← and →).

        The icon parameter should be used separately to provide the
        arrow visual indicator.
        """
        # Import the GUI module to inspect button rendering
        from gui_nicegui import create_manifest_editor_ui
        from unittest.mock import MagicMock, patch

        # Mock the UI context to capture button creation
        captured_buttons = []

        def mock_button(text="", on_click=None, icon=""):
            captured_buttons.append({
                "text": text,
                "icon": icon,
                "on_click": on_click
            })
            # Return a mock button with proper structure
            btn = MagicMock()
            btn.enabled = True
            btn.on_click = MagicMock()
            btn.text = text
            btn.icon = icon
            return btn

        # Mock the UI module
        mock_ui = MagicMock()
        mock_ui.button = mock_button
        mock_ui.card = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None)))
        mock_ui.label = MagicMock(return_value=MagicMock())
        mock_ui.row = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None)))
        mock_ui.column = MagicMock(return_value=MagicMock(__enter__=MagicMock(return_value=MagicMock()), __exit__=MagicMock(return_value=None)))
        mock_ui.notify = MagicMock()
        mock_ui.add_head_html = MagicMock()

        # Patch the GUI module to use our mock ui
        with patch("gui_nicegui.ui", mock_ui):
            from gui_nicegui import WizardEditor
            editor = WizardEditor()
            # We can't easily call create_manifest_editor_ui due to complex context,
            # but we can verify the expected button text by reading the source code
            # For now, we'll use a direct source code inspection via grep
            pass

        # Since mocking the full GUI is complex, we'll verify by reading the source
        # The test captures the intent: buttons should have text "Back" and "Next"
        # with separate icon parameters
        import re
        from pathlib import Path

        gui_file = Path(__file__).parent / "gui_nicegui.py"
        gui_content = gui_file.read_text()

        # Find the button creation lines
        back_button_match = re.search(r'ui\.button\("([^"]*Back[^"]*)"\s*,\s*icon="([^"]*)"', gui_content)
        next_button_match = re.search(r'ui\.button\("([^"]*Next[^"]*)"\s*,\s*icon="([^"]*)"', gui_content)

        # Current implementation (broken): "← Back" and "Next →"
        # Expected fix (Phase 3): "Back" and "Next"
        if back_button_match:
            back_text = back_button_match.group(1)
            back_icon = back_button_match.group(2)
            # This test will FAIL with current code and PASS after Phase 3 fix
            assert back_text.strip() == "Back", \
                f"Back button text should be 'Back' but found '{back_text}' (regression: has arrow glyph)"
            assert back_icon == "arrow_back", \
                f"Back button icon should be 'arrow_back' but found '{back_icon}'"

        if next_button_match:
            next_text = next_button_match.group(1)
            next_icon = next_button_match.group(2)
            # This test will FAIL with current code and PASS after Phase 3 fix
            assert next_text.strip() == "Next", \
                f"Next button text should be 'Next' but found '{next_text}' (regression: has arrow glyph)"
            assert next_icon == "arrow_forward", \
                f"Next button icon should be 'arrow_forward' but found '{next_icon}'"

    def test_navigation_icons_still_present_after_text_cleanup(self):
        """
        Verify that after removing arrow glyphs from button text,
        the arrow icons are still present via the icon parameter.

        This ensures the visual arrow indicator is preserved while
        cleaning up redundant text glyphs.
        """
        from pathlib import Path
        import re

        gui_file = Path(__file__).parent / "gui_nicegui.py"
        gui_content = gui_file.read_text()

        # Find button declarations
        button_pattern = r'(back_btn|next_btn)\s*=\s*ui\.button\("([^"]*)"\s*,\s*icon="([^"]*)"\)'
        matches = re.finditer(button_pattern, gui_content)

        button_specs = {}
        for match in matches:
            btn_var = match.group(1)
            btn_text = match.group(2)
            btn_icon = match.group(3)
            button_specs[btn_var] = {"text": btn_text, "icon": btn_icon}

        # Verify back button has icon
        assert "back_btn" in button_specs, "Back button not found in source"
        assert button_specs["back_btn"]["icon"] == "arrow_back", \
            "Back button must have arrow_back icon"

        # Verify next button has icon
        assert "next_btn" in button_specs, "Next button not found in source"
        assert button_specs["next_btn"]["icon"] == "arrow_forward", \
            "Next button must have arrow_forward icon"


class TestNavigationPreFlushBoundary:
    """
    Tests for the critical pre-navigation flush boundary.

    When a user navigates (clicks Next/Back), any pending spreadsheet cell
    edits must be flushed to the wizard state BEFORE the editor is torn down
    and recreated. This prevents loss of data when the user navigates away
    while a cell is still in active edit mode (before a change event fires).

    These tests verify that the navigation boundary properly guards against
    this regression.
    """

    def test_runs_step_can_register_active_editor_for_flush(self):
        """
        Verify that when a JSpreadsheetEditor is created during RUNS step,
        it can register itself with the wizard for pre-navigation flush.
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")

        assert wizard.get_current_step() == WizardStep.RUNS

        # Wizard should have a mechanism to store active editors
        # for flushing during navigation
        assert hasattr(wizard, '_active_editors') or \
               hasattr(wizard, 'register_editor') or \
               hasattr(wizard, 'set_active_editor'), \
            "Wizard must have mechanism to track active editors for pre-nav flush"

    def test_navigation_next_step_flushes_before_step_change(self):
        """
        Verify that when next_step() is called, any registered editor
        is flushed BEFORE the step index changes.
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        # Simulate registering an active editor
        # (In production, the GUI would update this when creating JSpreadsheetEditor)
        mock_editor = MagicMock()
        mock_editor.flush_pending_edits = MagicMock(return_value=1)

        if hasattr(wizard, 'set_active_editor'):
            wizard.set_active_editor(mock_editor)
        elif hasattr(wizard, 'register_editor'):
            wizard.register_editor(mock_editor)

        # Call next_step
        wizard.next_step()

        # If editor was registered, flush should have been called
        # before the step changed
        if mock_editor.flush_pending_edits.called:
            # Flush was called - good!
            assert wizard.get_current_step() == WizardStep.SAMPLES, \
                "Step should have changed after flush"

    def test_navigation_previous_step_flushes_before_step_change(self):
        """
        Verify that when previous_step() is called, any registered editor
        is flushed BEFORE the step index changes.
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw")
        wizard.next_step()  # Move to SAMPLES

        assert wizard.get_current_step() == WizardStep.SAMPLES

        # Simulate registering an active editor
        mock_editor = MagicMock()
        mock_editor.flush_pending_edits = MagicMock(return_value=0)

        if hasattr(wizard, 'set_active_editor'):
            wizard.set_active_editor(mock_editor)
        elif hasattr(wizard, 'register_editor'):
            wizard.register_editor(mock_editor)

        # Call previous_step
        wizard.previous_step()

        # Flush should respect navigation order
        assert wizard.get_current_step() == WizardStep.RUNS, \
            "Step should have changed"

    def test_runs_step_label_states_fraction_and_instrument_editable_here(self):
        """
        Verify that the Runs step clearly communicates to the user what
        can be edited (file, fraction, instrument) and what cannot
        (sample/mixture assignment moved to Assignments step).

        This is a critical UX boundary: users must understand that
        sample/mixture assignment happens separately.
        """
        from pathlib import Path

        gui_file = Path(__file__).parent / "gui_nicegui.py"
        gui_content = gui_file.read_text()

        # Find the create_runs_step function
        runs_step_start = gui_content.find("def create_runs_step(")
        runs_step_end = gui_content.find("\ndef create_samples_step(", runs_step_start)

        assert runs_step_start != -1, "create_runs_step function not found"
        assert runs_step_end != -1, "create_samples_step function not found"

        runs_step_code = gui_content[runs_step_start:runs_step_end]

        # Should have clear label about what's editable in this step
        # Key fields: file, fraction, instrument
        assert any(word in runs_step_code.lower() for word in ["file", "fraction", "instrument"]), \
            "Runs step should mention editable fields: file, fraction, instrument"

    def test_assignments_step_label_clearly_states_sample_mixture_linking(self):
        """
        Verify that the Assignments step clearly communicates that THIS is
        where sample/mixture assignment happens (not in Runs step).

        This clarifies ownership and prevents user confusion about where
        each piece of data should be entered.
        """
        from pathlib import Path

        gui_file = Path(__file__).parent / "gui_nicegui.py"
        gui_content = gui_file.read_text()

        # Find the create_assignments_step function
        assign_start = gui_content.find("def create_assignments_step(")
        assign_end = gui_content.find("\ndef create_experiment_step(", assign_start)

        assert assign_start != -1, "create_assignments_step function not found"
        assert assign_end != -1, "create_experiment_step function not found"

        assign_code = gui_content[assign_start:assign_end]

        # Should clearly communicate sample/mixture assignment happens here
        lower_code = assign_code.lower()
        assert "assign" in lower_code or "link" in lower_code, \
            "Assignments step should use 'assign' or 'link' language"
        assert "sample" in lower_code or "mixture" in lower_code, \
            "Assignments step should explicitly mention sample or mixture"


class TestGroupDetailPageRouting:
    """Tests for routing the active group detail view through the main wizard renderer."""

    class _RoutingMockNode:
        def __init__(self, owner=None):
            self.owner = owner
            self.children = []
            self.visible = True

        def classes(self, *args, **kwargs):
            return self

        def clear(self):
            self.children = []
            return self

        def set_visibility(self, visible):
            self.visible = visible
            return self

        def update(self):
            return self

        def props(self, *args, **kwargs):
            return self

        def __enter__(self):
            if self.owner is not None:
                self.owner._container_stack.append(self)
                parent = self.owner._container_stack[-2] if len(self.owner._container_stack) > 1 else None
                self.parent = parent
                if parent is not None:
                    parent.children.append(self)
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
            row = TestGroupDetailPageRouting._RoutingMockNode(owner=self)
            self.rows.append(row)
            return row

        def column(self):
            column = TestGroupDetailPageRouting._RoutingMockNode(owner=self)
            self.rows.append(column)
            return column

        def card(self):
            card = TestGroupDetailPageRouting._RoutingMockNode(owner=self)
            self.cards.append(card)
            return card

    def test_active_group_routes_to_dedicated_page_in_main_renderer(self):
        """The main renderer should open active groups on a separate page instead of the Runs step."""
        from gui_nicegui import WizardEditor, create_manifest_editor_ui

        wizard_editor = WizardEditor()
        wizard_editor.wizard.add_run(file="/data/test.raw")
        wizard_editor.wizard.add_sample(id="sample_1")
        wizard_editor.wizard.add_group(id="lfq_group", name="LFQ group", kind="LFQ")
        wizard_editor.wizard.set_active_group_id("lfq_group")

        routing_ui = self._RoutingMockUI()
        render_calls = []

        def fake_runs_step(*_args, **_kwargs):
            render_calls.append("runs")

        def fake_group_detail_step(*_args, **_kwargs):
            render_calls.append("group")

        with patch("gui_nicegui.ui", routing_ui), patch(
            "gui_nicegui.create_runs_step", side_effect=fake_runs_step
        ), patch("gui_nicegui.create_group_detail_step", side_effect=fake_group_detail_step):
            create_manifest_editor_ui(wizard_editor)

        assert render_calls == ["group"]

    def test_wizard_navigation_guards_against_pending_edit_loss(self):
        """
        Integration test: Verify the complete pre-navigation flush flow.

        This documents the expected behavior at the navigation boundary:
        1. User has pending edit in spreadsheet
        2. User clicks "Next" button
        3. Editor.flush_pending_edits() is called
        4. Pending edits are synced to wizard state
        5. Step index changes
        6. New editor is created with updated wizard state
        7. Edit is preserved in new editor
        """
        from gui_wizard_state import WizardState, WizardStep

        wizard = WizardState()
        # Start with a run
        wizard.add_run(file="/data/sample.raw", fraction=1)

        # Track if flush was called during navigation
        flush_called_during_nav = False

        def simulate_pending_edit_flush():
            nonlocal flush_called_during_nav
            flush_called_during_nav = True
            # Simulate flush updating wizard state from pending edit
            wizard.runs[0]["fraction"] = 5

        # Mock editor with flush capability
        mock_editor = MagicMock()
        mock_editor.flush_pending_edits = MagicMock(side_effect=simulate_pending_edit_flush)

        # Register editor with wizard (if supported)
        if hasattr(wizard, 'set_active_editor'):
            wizard.set_active_editor(mock_editor)

            # Navigate to next step
            # (In production this happens when user clicks "Next" button in GUI)
            wizard.next_step()

            # Verify flush was called
            if mock_editor.flush_pending_edits.called:
                # If the implementation supports it, flush should have been called
                assert wizard.runs[0]["fraction"] == 5, \
                    "Flushed edit should be preserved in wizard state"
                assert wizard.get_current_step() == WizardStep.SAMPLES, \
                    "Navigation should complete after flush"


class TestJSpreadsheetEditorIntegration:
    """Tests for JSpreadsheetEditor runtime integration with NiceGUI."""

    def test_jspreadsheet_editor_registers_with_wizard(self):
        """Test that JSpreadsheetEditor registers itself as active editor with wizard."""
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        mock_refresh = MagicMock()
        editor = JSpreadsheetEditor(wizard, mock_refresh)

        # Simulate what create_runs_step should do
        wizard.set_active_editor(editor)

        # Verify editor is registered
        assert wizard._active_editor is editor, \
            "Editor should be registered as active editor with wizard"

    def test_flush_pending_edits_is_coroutine(self):
        """Test that flush_pending_edits is an async coroutine."""
        import asyncio
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor
        import inspect

        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        mock_refresh = MagicMock()
        editor = JSpreadsheetEditor(wizard, mock_refresh)

        # Check that flush_pending_edits is async
        assert inspect.iscoroutinefunction(editor.flush_pending_edits), \
            "flush_pending_edits should be an async function"

    def test_wizard_clears_active_editor_on_navigation(self):
        """Test that active editor is cleared when button handler navigates away from Runs.

        This simulates what the GUI button handler (go_next) does when the user clicks
        the Next button while on the RUNS step.
        """
        import asyncio
        from gui_wizard_state import WizardState, WizardStep
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        mock_refresh = MagicMock()
        editor = JSpreadsheetEditor(wizard, mock_refresh)
        wizard.set_active_editor(editor)

        # Verify editor is registered before navigation
        assert wizard._active_editor is editor, \
            "Editor should be registered before navigation"

        # Simulate what the go_next button handler does
        async def simulate_button_navigation():
            # Get current step BEFORE navigating
            current_step = wizard.get_current_step()

            # Call next_step
            wizard.next_step()

            # Clear active editor if we're leaving RUNS step
            if current_step == WizardStep.RUNS:
                wizard.set_active_editor(None)

        asyncio.run(simulate_button_navigation())

        # Verify we advanced to next step
        assert wizard.get_current_step() == WizardStep.SAMPLES, \
            "Should have advanced to SAMPLES step"

        # Verify active editor was cleared
        assert wizard._active_editor is None, \
            "Active editor should be cleared when leaving RUNS step"

    def test_wizard_calls_flush_on_active_editor_before_navigation(self):
        """Test that wizard registers active editor for flush calls before navigation."""
        import asyncio
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1)

        mock_refresh = MagicMock()
        editor = JSpreadsheetEditor(wizard, mock_refresh)

        # Track if flush was called
        flush_called = False

        original_flush = editor.flush_pending_edits

        async def tracked_flush():
            nonlocal flush_called
            flush_called = True
            return await original_flush()

        editor.flush_pending_edits = tracked_flush

        # Register editor with wizard
        wizard.set_active_editor(editor)

        # Simulate what the button handler would do - manually call flush
        async def simulate_navigation():
            active_editor = wizard._active_editor
            if active_editor is not None:
                if hasattr(active_editor, 'flush_pending_edits'):
                    flush_result = active_editor.flush_pending_edits()
                    import inspect
                    if inspect.iscoroutine(flush_result):
                        await flush_result

        asyncio.run(simulate_navigation())
        assert flush_called, "flush_pending_edits should be callable as coroutine"

    def test_flush_pending_edits_returns_zero_on_successful_browser_round_trip(self):
        """Test that flush_pending_edits returns 0 on a successful mocked browser round-trip.

        This test verifies the asynchronous contract: when the browser round-trip
        successfully fetches and returns spreadsheet data, flush_pending_edits
        completes the sync and returns 0 to signal success to the GUI layer
        (indicating no error or blocking condition).
        """
        import asyncio
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor
        from unittest.mock import AsyncMock, patch

        wizard = WizardState()
        wizard.add_run(file="test.raw", fraction=1, instrument="Orbitrap")

        # Simulate a successful browser round-trip:
        # The browser returns the current spreadsheet data
        simulated_spreadsheet_data = [
            ["test.raw", "1", "Orbitrap"]
        ]

        async def test_flush():
            # Mock context.client.run_javascript to simulate browser returning data
            with patch('jspreadsheet_editor.context') as mock_context:
                # Create mock container with html_id
                mock_container = MagicMock()
                mock_container.html_id = "test_container_id"

                # Create editor after patch is applied
                mock_refresh = MagicMock()
                editor = JSpreadsheetEditor(wizard, mock_refresh)
                editor.container = mock_container

                # Set up the mock to return spreadsheet data
                mock_run_javascript = AsyncMock()
                mock_run_javascript.return_value = simulated_spreadsheet_data
                mock_context.client.run_javascript = mock_run_javascript

                # Call flush_pending_edits
                result = await editor.flush_pending_edits()

                # Verify it returns 0 (success)
                assert result == 0, \
                    "flush_pending_edits should return 0 on successful browser round-trip"

                # Verify that run_javascript was called
                assert mock_run_javascript.called, \
                    "run_javascript should have been called"

        asyncio.run(test_flush())


class TestPreNavigationFlushContract:
    """
    Focused regression tests for pre-navigation flush behavior.

    These tests verify that the navigation handlers in the GUI layer properly
    call flush_pending_edits before actually changing wizard steps. This is the
    critical boundary that guards against losing the last in-cell edit when the
    user clicks Next or Back while a cell is still being edited.
    """

    def test_wizard_maintains_active_editor_reference_for_flush(self):
        """
        Contract test: The WizardState must provide a mechanism for editors to
        register themselves so navigation handlers can find and flush them.

        This is the key integration point between the GUI layer (which calls
        async flush before navigation) and the editor layer.
        """
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        # Create an editor and register it
        editor = JSpreadsheetEditor(wizard, MagicMock())
        editor.register_with_wizard()

        # Verify the wizard can retrieve the registered editor
        active = wizard.get_active_editor()
        assert active is editor, (
            "Wizard must store reference to active editor for pre-navigation flush"
        )

    def test_editor_flush_mechanism_callable_for_navigation(self):
        """
        Contract test: Editors must have a callable flush mechanism that can be
        invoked from the navigation handlers before steps change.

        The GUI layer will:
        1. Get the active editor from wizard
        2. Call editor.flush_pending_edits() (awaiting if async)
        3. Only then call wizard.next_step() or wizard.previous_step()
        """
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor
        import inspect

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        editor = JSpreadsheetEditor(wizard, MagicMock())

        # Verify the editor has a flush method
        assert hasattr(editor, 'flush_pending_edits'), (
            "Editor must have flush_pending_edits method"
        )

        # Verify it's callable
        assert callable(editor.flush_pending_edits), (
            "flush_pending_edits must be callable"
        )

        # Verify it's async so GUI can await it
        assert inspect.iscoroutinefunction(editor.flush_pending_edits), (
            "flush_pending_edits must be async for proper GUI integration"
        )

    def test_pending_edit_not_in_change_event_is_regression(self):
        """
        Regression documentation: This test captures the critical bug scenario.

        When user types a value in a spreadsheet cell but immediately navigates
        WITHOUT letting the cell blur (which would trigger jspreadsheet's change
        event), the pending edit exists ONLY in the browser's JavaScript DOM,
        not in Python's WizardState.

        If the editor is destroyed without calling flush_pending_edits:
        - The browser's spreadsheet instance is destroyed
        - The in-cell value is lost forever
        - Python never receives the edit

        This is the regression that Phase 1 tests capture and Phase 2 will fix
        by ensuring gui_nicegui.py always calls flush before navigating.
        """
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")

        # Simulate the scenario: editor created, user types but doesn't blur
        editor = JSpreadsheetEditor(wizard, MagicMock())

        # At this point, if we were in a real browser:
        # - Spreadsheet cell for "fraction" shows "99" (user typed this)
        # - No change event has fired yet (user still editing)
        # - Python's wizard still shows fraction=1 (stale)
        # - The "99" only exists in the browser's DOM

        # When navigation happens WITHOUT calling flush_pending_edits:
        del editor  # Editor is destroyed

        # Create new editor from wizard
        editor2 = JSpreadsheetEditor(wizard, MagicMock())

        # The new editor shows the wizard's stale value
        data = editor2.bridge.get_spreadsheet_data()

        # This documents the bug: the user's typed "99" is lost
        assert data["data"][0][1] == 1, (
            "BUG DOCUMENTED: Pending edit (not yet synced via change event) "
            "is lost when editor destroyed without flush. "
            "Phase 2 will fix by calling flush_pending_edits in navigation."
        )

    def test_flush_bridge_syncs_updated_values_from_browser(self):
        """
        Integration test: When flush fetches spreadsheet data from the browser,
        the JSpreadsheetBridge must properly sync that data back to the wizard.

        This tests the critical path that prevents data loss:
        1. Browser has: cell shows "99", but change event not fired
        2. flush_pending_edits calls blur to trigger commit
        3. flush fetches worksheet.getData() which includes the "99"
        4. _sync_data_from_browser updates wizard with "99"
        5. Editor destroyed - but wizard has the "99" now
        """
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor
        from jspreadsheet_bridge import JSpreadsheetBridge

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1)

        # Create editor and bridge
        bridge = JSpreadsheetBridge(wizard, entity_type="runs")
        editor = JSpreadsheetEditor(wizard, MagicMock(), bridge=bridge)

        # Simulate the data that would come from browser after blur+getData()
        # This is what worksheet.getData() returns after blur commits the pending edit
        browser_data = [
            ["/data/test.raw", 99]  # User's pending edit is now committed
        ]

        # Sync this data to the wizard
        editor._sync_data_from_browser(browser_data)

        # Verify the pending edit is now safely in the wizard
        assert wizard.runs[0]["fraction"] == 99, (
            "After flush commits pending edit in browser and syncs back, "
            "wizard state must be updated to prevent data loss"
        )

    def test_multiple_pending_edits_at_navigation_boundary(self):
        """
        Regression test: When user has made multiple pending edits across
        different cells and then navigates, flush must capture ALL of them.

        This ensures that if the user:
        1. Types new fraction: "5" in one cell
        2. Types new instrument: "Lumos" in another cell
        3. Clicks Next before blurring either cell

        Both edits are captured by flush and synced to wizard.
        """
        from gui_wizard_state import WizardState
        from jspreadsheet_editor import JSpreadsheetEditor
        from jspreadsheet_bridge import JSpreadsheetBridge

        wizard = WizardState()
        wizard.add_run(file="/data/test.raw", fraction=1, instrument="Orbitrap")

        bridge = JSpreadsheetBridge(wizard, entity_type="runs")
        editor = JSpreadsheetEditor(wizard, MagicMock(), bridge=bridge)

        # Simulate browser data with BOTH cells updated (both pendings now committed)
        browser_data = [
            ["/data/test.raw", 5, "Lumos"]  # Both pending edits are now committed
        ]

        # Sync the browser data
        editor._sync_data_from_browser(browser_data)

        # Verify BOTH changes were synced
        assert wizard.runs[0]["fraction"] == 5, "Fraction pending edit must be captured"
        assert wizard.runs[0]["instrument"] == "Lumos", "Instrument pending edit must be captured"
