#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
#   "jsonschema",
# ]
# ///
"""
Test suite for quantms manifest authoring core functionality.

Tests cover manifest state management, YAML serialization, validation integration,
and channel builder behavior for different multiplex types.
"""

import pytest
import yaml
import tempfile
from pathlib import Path
import sys

# Add parent directories to path to import from tools
sys.path.insert(0, str(Path(__file__).parent))

from manifest_core import (
    ManifestState,
    Sample,
    Mixture,
    Run,
    Modification,
    Experiment,
)


class TestManifestStateSerialization:
    """Tests for manifest state serialization to YAML."""

    def test_empty_manifest_state_creation(self):
        """Test creating a new empty manifest state."""
        manifest = ManifestState()
        assert manifest.experiment is None
        assert manifest.samples == []
        assert manifest.mixtures == []
        assert manifest.runs == []
        assert manifest.modifications == []

    def test_manifest_state_with_basic_experiment(self):
        """Test creating manifest state with experiment metadata."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="LFQ",
            dissociation_method="HCD",
        )
        assert manifest.experiment is not None
        assert manifest.experiment.acquisition_method == "DDA"
        assert manifest.experiment.enzyme == "Trypsin"

    def test_add_sample_to_manifest(self):
        """Test adding a sample to the manifest."""
        manifest = ManifestState()
        manifest.add_sample(
            id="sample_1",
            organism="homo sapiens",
            organism_part="liver",
            condition="treated",
            biological_replicate=1,
        )
        assert len(manifest.samples) == 1
        assert manifest.samples[0].id == "sample_1"

    def test_add_mixture_to_manifest(self):
        """Test adding a mixture to the manifest."""
        manifest = ManifestState()
        manifest.add_sample(id="s1")
        manifest.add_sample(id="s2")
        manifest.add_mixture(
            id="mix_1",
            channels={"TMT126": "s1", "TMT127N": "s2"}
        )
        assert len(manifest.mixtures) == 1
        assert manifest.mixtures[0].id == "mix_1"

    def test_add_run_to_manifest(self):
        """Test adding a run to the manifest."""
        manifest = ManifestState()
        manifest.add_run(
            file="s3://bucket/file.raw",
            mixture="mix_1",
            fraction=1,
        )
        assert len(manifest.runs) == 1
        assert manifest.runs[0].file == "s3://bucket/file.raw"

    def test_serialize_manifest_to_dict(self):
        """Test serializing manifest state to dictionary."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(
            id="s1",
            organism="homo sapiens",
            organism_part="liver",
            condition="control",
            biological_replicate=1,
        )
        manifest.add_mixture(
            id="mix_1",
            channels={"TMT126": "s1"}
        )
        manifest.add_run(
            file="file.raw",
            mixture="mix_1",
            fraction=1,
        )

        result = manifest.to_dict()
        assert "experiment" in result
        assert result["experiment"]["acquisition_method"] == "DDA"
        assert len(result["samples"]) == 1
        assert len(result["mixtures"]) == 1
        assert len(result["runs"]) == 1

    def test_serialize_manifest_to_yaml(self):
        """Test serializing manifest state to YAML string."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(
            id="s1",
            organism="homo sapiens",
            condition="control",
            biological_replicate=1,
        )

        yaml_str = manifest.to_yaml()
        assert isinstance(yaml_str, str)
        assert "experiment:" in yaml_str
        assert "acquisition_method: DDA" in yaml_str
        assert "samples:" in yaml_str

    def test_save_manifest_to_file(self):
        """Test saving manifest state to YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ManifestState()
            manifest.set_experiment(
                acquisition_method="DDA",
                enzyme="Trypsin",
            )
            manifest.add_sample(
                id="s1",
                organism="homo sapiens",
                condition="control",
                biological_replicate=1,
            )

            output_file = Path(tmpdir) / "manifest.yml"
            manifest.save_to_file(output_file)

            assert output_file.exists()
            with open(output_file) as f:
                loaded = yaml.safe_load(f)
            assert loaded["experiment"]["acquisition_method"] == "DDA"

    def test_load_manifest_from_file(self):
        """Test loading manifest state from YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                },
                "samples": [
                    {
                        "id": "s1",
                        "organism": "homo sapiens",
                        "condition": "control",
                        "biological_replicate": 1,
                    }
                ],
                "mixtures": [],
                "runs": [
                    {
                        "file": "file.raw",
                        "mixture": None,
                        "fraction": 1,
                    }
                ],
            }

            output_file = Path(tmpdir) / "test.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            manifest = ManifestState.load_from_file(output_file)
            assert manifest.experiment.acquisition_method == "DDA"
            assert len(manifest.samples) == 1
            assert manifest.samples[0].id == "s1"


class TestChannelBuilder:
    """Tests for multiplex channel builder behavior."""

    def test_tmt_plex_channels_available(self):
        """Test that TMT plex type returns correct channel names."""
        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="TMT16")
        channels = builder.get_available_channels()
        expected = [f"TMT{label}" for label in ["126", "127N", "127C", "128N", "128C", "129N", "129C", "130N", "130C", "131N", "131C", "132N", "132C", "133N", "133C", "134N"]]
        assert set(channels) == set(expected)

    def test_tmt6_plex_channels(self):
        """Test TMT6plex specific channels."""
        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="TMT6")
        channels = builder.get_available_channels()
        expected = ["TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N"]
        assert len(channels) == 6

    def test_itraq4_plex_channels(self):
        """Test iTRAQ4plex channels."""
        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="iTRAQ4")
        channels = builder.get_available_channels()
        assert len(channels) == 4
        assert all(c.startswith("iTRAQ") for c in channels)

    def test_itraq8_plex_channels(self):
        """Test iTRAQ8plex channels."""
        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="iTRAQ8")
        channels = builder.get_available_channels()
        assert len(channels) == 8

    def test_silac_2plex_channels(self):
        """Test SILAC 2plex (light/heavy) channels."""
        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="SILAC_2plex")
        channels = builder.get_available_channels()
        assert len(channels) == 2
        assert "light" in [c.lower() for c in channels]

    def test_silac_3plex_channels(self):
        """Test SILAC 3plex (light/medium/heavy) channels."""
        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="SILAC_3plex")
        channels = builder.get_available_channels()
        assert len(channels) == 3

    def test_invalid_plex_type_raises_error(self):
        """Test that invalid plex type raises error."""
        from manifest_core import ChannelBuilder
        with pytest.raises(ValueError):
            ChannelBuilder(plex_type="INVALID_PLEX")

    def test_assigning_samples_to_channels(self):
        """Test assigning samples to mixture channels."""
        manifest = ManifestState()
        manifest.add_sample(id="s1")
        manifest.add_sample(id="s2")

        from manifest_core import ChannelBuilder
        builder = ChannelBuilder(plex_type="TMT6")
        channels = builder.get_available_channels()

        mixture_channels = {
            channels[0]: "s1",
            channels[1]: "s2",
        }
        manifest.add_mixture(id="mix_1", channels=mixture_channels)
        assert len(manifest.mixtures[0].channels) == 2


class TestValidationFeedback:
    """Tests for validation feedback integration."""

    def test_validate_manifest_returns_errors(self):
        """Test that validation returns list of validation errors."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        # Empty manifest should have errors
        errors = validate_manifest(manifest)
        assert isinstance(errors, list)
        assert len(errors) > 0

    def test_valid_manifest_passes_validation(self):
        """Test that a properly formed manifest passes validation."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(
            id="s1",
            organism="homo sapiens",
            condition="control",
            biological_replicate=1,
        )
        manifest.add_mixture(
            id="mix_1",
            channels={"TMT126": "s1"}
        )
        manifest.add_run(
            file="file.raw",
            mixture="mix_1",
            fraction=1,
        )

        errors = validate_manifest(manifest)
        # Should have no errors or only warnings
        critical_errors = [e for e in errors if e.get("level") == "error"]
        assert len(critical_errors) == 0

    def test_validation_error_includes_field_info(self):
        """Test that validation errors include field information."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        errors = validate_manifest(manifest)
        assert any("experiment" in str(e) for e in errors)

    def test_validation_tracks_error_location(self):
        """Test that validation errors specify which section has the issue."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        manifest.add_sample(id="s1")  # No required organism field
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_mixture(id="mix_1", channels={"TMT126": "s1"})
        manifest.add_run(file="file.raw", mixture="mix_1", fraction=1)

        errors = validate_manifest(manifest)
        # Should report missing organism info in samples
        assert any("organism" in str(e) or "sample" in str(e).lower() for e in errors)


class TestModificationProfiles:
    """Tests for modification profile handling."""

    def test_add_fixed_modification(self):
        """Test adding a fixed modification to manifest."""
        manifest = ManifestState()
        manifest.add_modification(
            mode="fixed",
            kind="ontology",
            name="Carbamidomethyl",
            residues="C",
        )
        assert len(manifest.modifications) == 1
        assert manifest.modifications[0].name == "Carbamidomethyl"

    def test_add_variable_modification(self):
        """Test adding a variable modification to manifest."""
        manifest = ManifestState()
        manifest.add_modification(
            mode="variable",
            kind="ontology",
            name="Oxidation",
            residues="M",
        )
        assert len(manifest.modifications) == 1
        assert manifest.modifications[0].mode == "variable"

    def test_add_modification_with_profile(self):
        """Test adding modification with named profile."""
        manifest = ManifestState()
        manifest.add_modification(
            mode="fixed",
            kind="ontology",
            name="Carbamidomethyl",
            residues="C",
            profile="default",
        )
        manifest.add_modification(
            mode="fixed",
            kind="ontology",
            name="TMT6plex",
            residues="K",
            profile="tmt",
        )
        assert manifest.modifications[0].profile == "default"
        assert manifest.modifications[1].profile == "tmt"

    def test_set_default_profile(self):
        """Test setting default modification profile for experiment."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        # Add modifications with profiles
        manifest.add_modification(
            mode="fixed",
            kind="ontology",
            name="Carbamidomethyl",
            residues="C",
            profile="default",
        )
        manifest.add_modification(
            mode="variable",
            kind="ontology",
            name="Oxidation",
            residues="M",
            profile="default",
        )

        # Verify modifications are in manifest with profile
        profs = [m.profile for m in manifest.modifications]
        assert "default" in profs


class TestMetadataHandling:
    """Tests for manifest metadata handling."""

    def test_set_schema_version(self):
        """Test setting schema version in metadata."""
        from manifest_core import Metadata
        metadata = Metadata(schema_version="1.0.0")
        assert metadata.schema_version == "1.0.0"

    def test_set_ontology_versions(self):
        """Test setting ontology versions in metadata."""
        from manifest_core import Metadata
        metadata = Metadata(
            ontology_versions={"psi-ms": "4.1.135"}
        )
        assert metadata.ontology_versions["psi-ms"] == "4.1.135"

    def test_manifest_includes_metadata_in_yaml(self):
        """Test that manifest includes metadata section in exported YAML."""
        manifest = ManifestState()
        manifest.metadata.schema_version = "1.0.0"
        manifest.metadata.ontology_versions = {"psi-ms": "4.1.135"}
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(
            id="s1",
            organism="homo sapiens",
            condition="control",
            biological_replicate=1,
        )

        yaml_dict = manifest.to_dict()
        assert "metadata" in yaml_dict
        assert yaml_dict["metadata"]["schema_version"] == "1.0.0"


class TestMixtureAuthoring:
    """Tests for multi-channel mixture authoring logic."""

    def test_multi_channel_mixture_with_distinct_samples(self):
        """Test creating a mixture where each channel maps to a different sample."""
        manifest = ManifestState()
        manifest.add_sample(id="sample1")
        manifest.add_sample(id="sample2")
        manifest.add_sample(id="sample3")
        manifest.add_sample(id="sample4")

        # Create a TMT6 mixture with 4 distinct samples (leaving 2 channels unassigned or repeated)
        channels = {
            "TMT126": "sample1",
            "TMT127N": "sample2",
            "TMT127C": "sample3",
            "TMT128N": "sample4",
        }
        manifest.add_mixture(id="mix_1", channels=channels)

        # Verify all channels are correctly stored
        assert len(manifest.mixtures[0].channels) == 4
        assert manifest.mixtures[0].channels["TMT126"] == "sample1"
        assert manifest.mixtures[0].channels["TMT127N"] == "sample2"
        assert manifest.mixtures[0].channels["TMT127C"] == "sample3"
        assert manifest.mixtures[0].channels["TMT128N"] == "sample4"

    def test_mixture_serialization_preserves_channel_assignments(self):
        """Test that channel assignments are preserved in YAML serialization."""
        manifest = ManifestState()
        for i in range(1, 4):
            manifest.add_sample(id=f"sample{i}")

        channels = {
            "TMT126": "sample1",
            "TMT127N": "sample2",
            "TMT127C": "sample3",
        }
        manifest.add_mixture(id="mix_1", channels=channels, description="Test mixture")

        # Serialize to dict
        manifest_dict = manifest.to_dict()
        mixture_dict = manifest_dict["mixtures"][0]

        assert mixture_dict["id"] == "mix_1"
        assert mixture_dict["channels"]["TMT126"] == "sample1"
        assert mixture_dict["channels"]["TMT127N"] == "sample2"
        assert mixture_dict["channels"]["TMT127C"] == "sample3"

    def test_load_mixture_with_multiple_channel_assignments(self):
        """Test loading and verifying correct channel assignments from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = ManifestState()
            manifest.add_sample(id="control_1")
            manifest.add_sample(id="control_2")
            manifest.add_sample(id="treated_1")
            manifest.add_sample(id="treated_2")
            manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
            manifest.add_mixture(
                id="plex_1",
                channels={
                    "TMT126": "control_1",
                    "TMT127N": "control_2",
                    "TMT127C": "treated_1",
                    "TMT128N": "treated_2",
                },
            )
            manifest.add_run(file="file.raw", mixture="plex_1", fraction=1)

            # Save and load
            save_path = Path(tmpdir) / "test_mixture.yml"
            manifest.save_to_file(save_path)
            loaded = ManifestState.load_from_file(save_path)

            # Verify loaded mixture has all channel assignments intact
            assert len(loaded.mixtures) == 1
            mixture = loaded.mixtures[0]
            assert len(mixture.channels) == 4
            assert mixture.channels["TMT126"] == "control_1"
            assert mixture.channels["TMT127N"] == "control_2"
            assert mixture.channels["TMT127C"] == "treated_1"
            assert mixture.channels["TMT128N"] == "treated_2"

    def test_build_channel_assignments_from_user_selections(self):
        """Test helper to build channel assignments from user selections."""
        from manifest_core import ChannelBuilder

        manifest = ManifestState()
        manifest.add_sample(id="s1")
        manifest.add_sample(id="s2")
        manifest.add_sample(id="s3")

        builder = ChannelBuilder("TMT6")
        channels = builder.get_available_channels()

        # Simulate user selections: first 3 channels mapped to 3 samples
        user_selections = {
            channels[0]: "s1",
            channels[1]: "s2",
            channels[2]: "s3",
        }

        manifest.add_mixture(id="test_mix", channels=user_selections)

        assert len(manifest.mixtures[0].channels) == 3
        assert manifest.mixtures[0].channels[channels[0]] == "s1"
        assert manifest.mixtures[0].channels[channels[1]] == "s2"
        assert manifest.mixtures[0].channels[channels[2]] == "s3"

    def test_validation_rejects_invalid_sample_references_in_mixture(self):
        """Test that validation catches invalid sample references in mixture channels."""
        from manifest_core import validate_manifest

        manifest = ManifestState()
        manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
        manifest.add_sample(id="real_sample")

        # Mixture with invalid sample reference
        manifest.add_mixture(id="bad_mix", channels={"TMT126": "nonexistent_sample"})
        manifest.add_run(file="file.raw", mixture="bad_mix", fraction=1)

        errors = validate_manifest(manifest)
        # Should have validation error about nonexistent sample
        error_msgs = [e.get("message", "").lower() for e in errors]
        assert any("nonexistent_sample" in msg or "unknown" in msg for msg in error_msgs)


class TestModificationLoadingRobustness:
    """Tests for robustness when loading manifests with schema-valid modification fields."""

    def test_load_manifest_with_extra_modification_fields(self):
        """Regression test: load manifest with extra modification fields the schema allows."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test file with extra modification fields from schema
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                },
                "samples": [
                    {
                        "id": "s1",
                        "organism": "homo sapiens",
                    }
                ],
                "mixtures": [],
                "runs": [
                    {
                        "file": "file.raw",
                        "mixture": None,
                    }
                ],
                "modifications": [
                    {
                        "mode": "variable",
                        "kind": "ontology",
                        "name": "Phosphorylation",
                        "ontology_id": "UNIMOD:21",
                        "residues": ["S", "T", "Y"],
                        "mass_shift": 79.966331,
                        "formula": "HO3P",
                        "binary_group": 1,
                        "min_occurrences": 0,
                        "distance_from_terminus": -1,
                    }
                ],
            }

            output_file = Path(tmpdir) / "test.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            # Should not crash on extra fields
            manifest = ManifestState.load_from_file(output_file)
            assert len(manifest.modifications) == 1
            assert manifest.modifications[0].name == "Phosphorylation"
            assert manifest.modifications[0].formula == "HO3P"
            assert manifest.modifications[0].binary_group == 1
            assert manifest.modifications[0].min_occurrences == 0
            assert manifest.modifications[0].distance_from_terminus == -1

    def test_load_manifest_with_deprecated_accession_alias(self):
        """Test loading manifest with deprecated 'accession' field (should map to ontology_id)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                },
                "samples": [
                    {
                        "id": "s1",
                        "organism": "homo sapiens",
                    }
                ],
                "mixtures": [],
                "runs": [
                    {
                        "file": "file.raw",
                        "mixture": None,
                    }
                ],
                "modifications": [
                    {
                        "mode": "variable",
                        "kind": "ontology",
                        "accession": "UNIMOD:21",
                        "residues": ["S", "T", "Y"],
                        "mass_shift": 79.966331,
                    }
                ],
            }

            output_file = Path(tmpdir) / "test.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            manifest = ManifestState.load_from_file(output_file)
            assert len(manifest.modifications) == 1
            assert manifest.modifications[0].ontology_id == "UNIMOD:21"

    def test_load_manifest_with_deprecated_term_spec_alias(self):
        """Test loading manifest with deprecated 'term_spec' field (should map to term_specificity)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                },
                "samples": [
                    {
                        "id": "s1",
                        "organism": "homo sapiens",
                    }
                ],
                "mixtures": [],
                "runs": [
                    {
                        "file": "file.raw",
                        "mixture": None,
                    }
                ],
                "modifications": [
                    {
                        "mode": "variable",
                        "kind": "custom",
                        "name": "Custom PTM",
                        "residues": "K",
                        "mass_shift": 42.0,
                        "term_spec": "n-term",
                    }
                ],
            }

            output_file = Path(tmpdir) / "test.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            manifest = ManifestState.load_from_file(output_file)
            assert len(manifest.modifications) == 1
            assert manifest.modifications[0].term_specificity == "n-term"

    def test_load_manifest_canonical_takes_precedence_over_alias(self):
        """Test that canonical field takes precedence over deprecated alias."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                },
                "samples": [
                    {
                        "id": "s1",
                        "organism": "homo sapiens",
                    }
                ],
                "mixtures": [],
                "runs": [
                    {
                        "file": "file.raw",
                        "mixture": None,
                    }
                ],
                "modifications": [
                    {
                        "mode": "variable",
                        "kind": "ontology",
                        "ontology_id": "UNIMOD:21",
                        "accession": "UNIMOD:1",  # This should be ignored
                        "residues": ["S", "T", "Y"],
                        "mass_shift": 79.966331,
                    }
                ],
            }

            output_file = Path(tmpdir) / "test.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            manifest = ManifestState.load_from_file(output_file)
            assert len(manifest.modifications) == 1
            # Canonical field should win
            assert manifest.modifications[0].ontology_id == "UNIMOD:21"


class TestAPIConsistency:
    """Tests for API consistency improvements."""

    def test_run_mixture_has_default_none(self):
        """Test that Run.mixture has a default value of None."""
        from manifest_core import Run

        # Should be able to create Run with just file parameter
        run = Run(file="data.raw")
        assert run.file == "data.raw"
        assert run.mixture is None


class TestModificationValidation:
    """Tests for semantic validation of modifications."""

    def test_validate_manifest_catches_invalid_modification_mode(self):
        """Test that validate_manifest catches invalid mode even without jsonschema."""
        from manifest_core import validate_manifest

        manifest = ManifestState()
        manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
        manifest.add_sample(id="s1")
        manifest.add_run(file="file.raw")

        # Manually create a modification with invalid mode
        manifest.modifications.append(Modification(
            mode="invalid_mode",
            kind="custom",
            name="Bad mod",
            residues="K",
            mass_shift=42.0
        ))

        errors = validate_manifest(manifest)
        # Should have error about invalid mode
        error_msgs = [e.get("message", "") for e in errors]
        assert any("invalid mode" in msg.lower() for msg in error_msgs)

    def test_validate_manifest_catches_invalid_modification_kind(self):
        """Test that validate_manifest catches invalid kind."""
        from manifest_core import validate_manifest

        manifest = ManifestState()
        manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
        manifest.add_sample(id="s1")
        manifest.add_run(file="file.raw")

        # Manually create a modification with invalid kind
        manifest.modifications.append(Modification(
            mode="fixed",
            kind="invalid_kind",
            name="Bad mod",
            residues="K",
        ))

        errors = validate_manifest(manifest)
        # Should have error about invalid kind
        error_msgs = [e.get("message", "") for e in errors]
        assert any("invalid kind" in msg.lower() for msg in error_msgs)


class TestDissociationMethodExplicit:
    """Tests for explicit dissociation method behavior - Phase 1."""

    def test_dissociation_method_is_none_when_not_set(self):
        """Test that dissociation_method starts as None."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        assert manifest.experiment.dissociation_method is None

    def test_dissociation_method_is_none_for_dia_without_explicit_setting(self):
        """Test that DIA manifests don't infer dissociation_method."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DIA",
            enzyme="Trypsin",
            quantification_method="LFQ",
        )
        # Should remain None - no inference
        assert manifest.experiment.dissociation_method is None

    def test_dissociation_method_preserved_when_explicitly_set(self):
        """Test that explicitly set dissociation_method is preserved."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="HCD",
        )
        assert manifest.experiment.dissociation_method == "HCD"

    def test_dissociation_method_preserved_when_loaded_from_yaml(self):
        """Test that dissociation_method loaded from YAML is not inferred, just preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                    "dissociation_method": "ETD",
                },
                "samples": [{"id": "s1"}],
                "mixtures": [],
                "runs": [{"file": "file.raw"}],
            }

            output_file = Path(tmpdir) / "test.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            manifest = ManifestState.load_from_file(output_file)
            # Should be exactly what was in the YAML, not inferred
            assert manifest.experiment.dissociation_method == "ETD"

    def test_dissociation_method_serializes_when_set(self):
        """Test that dissociation_method appears in YAML when explicitly set."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            dissociation_method="CID",
        )
        manifest.add_sample(id="s1")
        manifest.add_run(file="file.raw")

        yaml_str = manifest.to_yaml()
        assert "dissociation_method: CID" in yaml_str

    def test_dissociation_method_does_not_serialize_when_none(self):
        """Test that dissociation_method does not appear in YAML when None."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(id="s1")
        manifest.add_run(file="file.raw")

        yaml_str = manifest.to_yaml()
        # Should not appear in YAML
        lines = [l.strip() for l in yaml_str.split('\n') if 'dissociation_method' in l]
        assert len(lines) == 0


class TestOntologyOptionProvider:
    """Tests for ontology/CV option provider - Phase 1."""

    def test_option_provider_module_exists(self):
        """Test that ontology_provider module can be imported."""
        try:
            from ontology_provider import OntologyOptionProvider
            assert OntologyOptionProvider is not None
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_returns_enzyme_choices(self):
        """Test that option provider returns enzyme choices."""
        try:
            from ontology_provider import OntologyOptionProvider
            provider = OntologyOptionProvider()
            enzymes = provider.get_options("enzyme")
            assert isinstance(enzymes, list)
            assert len(enzymes) > 0
            # Should include common enzymes
            enzyme_names = [e if isinstance(e, str) else e.get("label", "") for e in enzymes]
            common_enzymes = ["trypsin", "pepsin", "chymotrypsin", "lys-c"]
            assert any(enzyme.lower() in str(enzyme_names).lower() for enzyme in common_enzymes)
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_returns_dissociation_method_choices(self):
        """Test that option provider returns dissociation method choices."""
        try:
            from ontology_provider import OntologyOptionProvider
            provider = OntologyOptionProvider()
            methods = provider.get_options("dissociation_method")
            assert isinstance(methods, list)
            assert len(methods) > 0
            # Should include common dissociation methods
            method_names = [m if isinstance(m, str) else m.get("label", "") for m in methods]
            common_methods = ["hcd", "cid", "etd"]
            assert any(method.lower() in str(method_names).lower() for method in common_methods)
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_graceful_fallback_when_oaklib_unavailable(self):
        """Test that option provider returns fallback defaults when Oaklib is unavailable."""
        try:
            from ontology_provider import OntologyOptionProvider
            provider = OntologyOptionProvider()

            # Should not crash even if Oaklib is not available
            enzymes = provider.get_options("enzyme")
            assert isinstance(enzymes, list)
            assert len(enzymes) > 0
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_supports_organism_field(self):
        """Test that option provider supports organism field."""
        try:
            from ontology_provider import OntologyOptionProvider
            provider = OntologyOptionProvider()

            organisms = provider.get_options("organism")
            assert isinstance(organisms, list)
            # Should have fallback options available
            assert len(organisms) > 0
            # All options should be dicts with label and value keys
            for option in organisms:
                assert isinstance(option, dict)
                assert "label" in option
                assert "value" in option
            # Should contain expected common organisms in fallback
            organism_labels = [o["label"] for o in organisms]
            assert any("sapiens" in label.lower() or "homo" in label.lower() for label in organism_labels)
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_returns_consistent_format(self):
        """Test that option provider returns consistent option format."""
        try:
            from ontology_provider import OntologyOptionProvider
            provider = OntologyOptionProvider()

            # All returned options should be either strings or dicts with 'label' and 'value'
            for field in ["enzyme", "dissociation_method"]:
                options = provider.get_options(field)
                for option in options:
                    if isinstance(option, dict):
                        assert "label" in option
                        assert "value" in option
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_returns_modification_choices(self):
        """Test that option provider returns dropdown-ready modification choices."""
        try:
            from ontology_provider import OntologyOptionProvider

            provider = OntologyOptionProvider()
            options = provider.get_modification_options()

            assert isinstance(options, list)
            assert len(options) > 0

            for option in options:
                assert isinstance(option, dict)
                assert option.get("label")
                assert option.get("value")
                assert option.get("kind") in {"ontology", "custom"}
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_prefers_live_modification_adapter(self):
        """Test that live lookup is used before bundled fallback for modifications."""
        try:
            from ontology_provider import OntologyOptionProvider

            class MockLiveAdapter:
                def search(self, term, limit=None):
                    if term == "Carbamidomethyl":
                        return ["UNIMOD:99999"]
                    return []

                def get_label(self, curie):
                    return {"UNIMOD:99999": "Live Mock Modification"}.get(curie)

            provider = OntologyOptionProvider(oak_adapter=MockLiveAdapter())
            options = provider.get_modification_options()

            assert any(option["value"] == "UNIMOD:99999" for option in options)
            assert all(option["value"] != "UNIMOD:4" for option in options)
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_normalizes_numeric_unimod_queries_and_preserves_text_search(self):
        """Test that UniMod shorthand, canonical accessions, and free-text queries all resolve."""
        try:
            from ontology_provider import OntologyOptionProvider

            class MockLiveAdapter:
                def __init__(self):
                    self.search_terms = []

                def search(self, term, limit=None):
                    self.search_terms.append(term)
                    if term in {"UNIMOD:1224", "UNIMOD:1239", "carbamidomethyl"}:
                        return [term]
                    return []

                def get_label(self, curie):
                    return {
                        "UNIMOD:1224": "Mock UniMod 1224",
                        "UNIMOD:1239": "Mock UniMod 1239",
                        "carbamidomethyl": "Carbamidomethyl",
                    }.get(curie)

            provider = OntologyOptionProvider(oak_adapter=MockLiveAdapter())

            shorthand_options = provider.get_modification_options(query="1224")
            accession_options = provider.get_modification_options(query="UNIMOD:1239")
            text_options = provider.get_modification_options(query="carbamidomethyl")

            assert shorthand_options[0]["value"] == "UNIMOD:1224"
            assert accession_options[0]["value"] == "UNIMOD:1239"
            assert text_options[0]["value"] == "carbamidomethyl"

            search_terms = provider._modification_adapter.search_terms
            assert "UNIMOD:1224" in search_terms
            assert "UNIMOD:1239" in search_terms
            assert "carbamidomethyl" in search_terms
            assert "1224" not in search_terms
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_uses_ols_style_adapter_for_full_unimod_results(self):
        """Test that OLS-backed UniMod search returns full-record accessions instead of falling back."""
        try:
            from ontology_provider import OntologyOptionProvider

            class MockOlsClient:
                def __init__(self):
                    self.search_terms = []

                def search(self, term, params=None):
                    self.search_terms.append(term)
                    records = {
                        "substitution": [
                            {
                                "iri": "http://purl.obolibrary.org/obo/UNIMOD_1044",
                                "obo_id": "UNIMOD:1044",
                                "short_form": "UNIMOD_1044",
                                "label": "Ala->Cys",
                                "description": ["Ala->Cys substitution."],
                                "synonym": ["Misacylation of the tRNA or editing of the charged tRNA"],
                            },
                            {
                                "iri": "http://purl.obolibrary.org/obo/UNIMOD_1224",
                                "obo_id": "UNIMOD:1224",
                                "short_form": "UNIMOD_1224",
                                "label": "Trp->Ala",
                                "description": ["Trp->Ala substitution."],
                                "synonym": ["Misacylation of the tRNA or editing of the charged tRNA"],
                            },
                        ],
                        "UNIMOD:1224": [
                            {
                                "iri": "http://purl.obolibrary.org/obo/UNIMOD_1224",
                                "obo_id": "UNIMOD:1224",
                                "short_form": "UNIMOD_1224",
                                "label": "Trp->Ala",
                                "description": ["Trp->Ala substitution."],
                                "synonym": ["Misacylation of the tRNA or editing of the charged tRNA"],
                            }
                        ],
                        "Carbamidomethyl": [
                            {
                                "iri": "http://purl.obolibrary.org/obo/UNIMOD_4",
                                "obo_id": "UNIMOD:4",
                                "short_form": "UNIMOD_4",
                                "label": "Carbamidomethyl",
                                "description": ["Iodoacetamide derivative."],
                                "synonym": ["Carboxyamidomethylation"],
                            }
                        ],
                    }
                    return records.get(term, [])

            class MockOlsAdapter:
                def __init__(self):
                    self.focus_ontology = "unimod"
                    self.client = MockOlsClient()

            provider = OntologyOptionProvider(oak_adapter=MockOlsAdapter())

            substitution_options = provider.get_modification_options(query="substitution")
            accession_options = provider.get_modification_options(query="1224")
            text_options = provider.get_modification_options(query="Carbamidomethyl")

            substitution_values = {option["value"] for option in substitution_options}
            assert "UNIMOD:1044" in substitution_values
            assert "UNIMOD:1224" in substitution_values
            assert accession_options[0]["value"] == "UNIMOD:1224"
            assert text_options[0]["value"] == "UNIMOD:4"
            assert provider._modification_adapter.client.search_terms == [
                "substitution",
                "UNIMOD:1224",
                "Carbamidomethyl",
            ]
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_enriches_selected_unimod_option_with_term_metadata(self):
        """Test that a selected OLS-backed UniMod hit is hydrated with mass and specificity metadata."""
        try:
            from ontology_provider import OntologyOptionProvider

            class MockOlsClient:
                def search(self, term, params=None):
                    if term != "Carbamidomethyl":
                        return []
                    return [
                        {
                            "iri": "http://purl.obolibrary.org/obo/UNIMOD_4",
                            "obo_id": "UNIMOD:4",
                            "short_form": "UNIMOD_4",
                            "label": "Carbamidomethyl",
                            "description": ["Iodoacetamide derivative."],
                            "synonym": ["Carboxyamidomethylation"],
                        }
                    ]

                def get_term(self, ontology, iri):
                    assert ontology == "unimod"
                    assert iri == "http://purl.obolibrary.org/obo/UNIMOD_4"
                    return {
                        "_embedded": {
                            "terms": [
                                {
                                    "obo_id": "UNIMOD:4",
                                    "label": "Carbamidomethyl",
                                    "obo_xref": [
                                        {"id": "delta_mono_mass", "description": "57.021464"},
                                        {"id": "delta_composition", "description": "H(3) C(2) N O"},
                                        {"id": "spec_1_hidden", "description": "0"},
                                        {"id": "spec_1_position", "description": "Anywhere"},
                                        {"id": "spec_1_site", "description": "C"},
                                        {"id": "spec_2_hidden", "description": "0"},
                                        {"id": "spec_2_position", "description": "Any N-term"},
                                        {"id": "spec_2_site", "description": "N-term"},
                                    ],
                                }
                            ]
                        }
                    }

            class MockOlsAdapter:
                def __init__(self):
                    self.focus_ontology = "unimod"
                    self.client = MockOlsClient()

            provider = OntologyOptionProvider(oak_adapter=MockOlsAdapter())

            option = provider.get_modification_options(query="Carbamidomethyl")[0]
            enriched_option = provider.enrich_modification_option(option)

            assert enriched_option["mass_shift"] == 57.021464
            assert enriched_option["formula"] == "H(3) C(2) N O"
            assert enriched_option["residues"] == "C"
            assert enriched_option["term_specificity"] == "none"
            assert enriched_option["allowed_term_specificities"] == ["none", "n-term"]
            assert enriched_option["allowed_sites_by_term_specificity"]["none"] == ["C"]
            assert enriched_option["allowed_sites_by_term_specificity"]["n-term"] == []
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_uses_bundled_modification_fallback_when_live_lookup_fails(self):
        """Test that bundled modification options are used when live lookup returns nothing."""
        try:
            from ontology_provider import OntologyOptionProvider

            class EmptyLiveAdapter:
                def search(self, term, limit=None):
                    return []

            provider = OntologyOptionProvider(oak_adapter=EmptyLiveAdapter())
            options = provider.get_modification_options()

            option_values = {option["value"] for option in options}
            assert "UNIMOD:4" in option_values
            assert "UNIMOD:21" in option_values or "UNIMOD:35" in option_values
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_searches_bundled_substitution_entries_offline(self):
        """Test that offline fallback resolves bundled substitution entries and accessions."""
        try:
            from ontology_provider import OntologyOptionProvider

            class EmptyLiveAdapter:
                def search(self, term, limit=None):
                    return []

            provider = OntologyOptionProvider(oak_adapter=EmptyLiveAdapter())

            substitution_options = provider.get_modification_options(query="substitution")
            shorthand_1224_options = provider.get_modification_options(query="1224")
            shorthand_1239_options = provider.get_modification_options(query="1239")
            carbamidomethyl_options = provider.get_modification_options(query="Carbamidomethyl")

            substitution_values = {option["value"] for option in substitution_options}
            assert "UNIMOD:1224" in substitution_values
            assert "UNIMOD:1239" in substitution_values

            assert shorthand_1224_options[0]["value"] == "UNIMOD:1224"
            assert shorthand_1239_options[0]["value"] == "UNIMOD:1239"
            assert carbamidomethyl_options[0]["value"] == "UNIMOD:4"
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_merges_custom_modification_entries(self):
        """Test that custom modification entries can coexist with ontology-backed ones."""
        try:
            from ontology_provider import OntologyOptionProvider

            provider = OntologyOptionProvider()
            custom_options = [
                {
                    "label": "My Lab Label",
                    "value": "custom:my-lab-label",
                    "kind": "custom",
                }
            ]

            options = provider.get_modification_options(custom_options=custom_options)
            option_values = {option["value"] for option in options}

            assert "custom:my-lab-label" in option_values
            assert any(option["kind"] == "ontology" for option in options)
            assert any(option["kind"] == "custom" for option in options)
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_handles_unknown_field(self):
        """Test that option provider gracefully handles unknown field."""
        try:
            from ontology_provider import OntologyOptionProvider
            provider = OntologyOptionProvider()

            # Should return empty list or raise appropriate error for unknown field
            unknown_options = provider.get_options("unknown_field_xyz")
            assert isinstance(unknown_options, list)
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_accepts_injectable_oak_adapter(self):
        """Test that option provider accepts injectable Oaklib adapter for testing."""
        try:
            from ontology_provider import OntologyOptionProvider
            # Mock adapter that returns test data
            class MockOakAdapter:
                def get_label(self, curie):
                    """Return mock labels for test CURIEs."""
                    mock_data = {
                        "CHEBI:9025": "Enzyme Type A",
                        "CHEBI:9026": "Enzyme Type B",
                    }
                    return mock_data.get(curie)

                def search(self, term, limit=None):
                    """Return mock search results."""
                    mock_results = {
                        "protease": ["CHEBI:9025", "CHEBI:9026"],
                        "enzyme": ["CHEBI:9025", "CHEBI:9026"],
                    }
                    return mock_results.get(term, [])

            mock_adapter = MockOakAdapter()
            provider = OntologyOptionProvider(oak_adapter=mock_adapter)
            # Provider should be created successfully with injected adapter
            assert provider._oak_adapter is mock_adapter
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")

    def test_option_provider_oaklib_branch_is_reachable(self):
        """Test that Oaklib code path is actually reachable and used when adapter is provided."""
        try:
            from ontology_provider import OntologyOptionProvider

            # Create a mock adapter that returns distinct options from fallback
            class MockOakAdapter:
                def __init__(self):
                    self.search_called = False
                    self.get_label_called = False

                def search(self, term, limit=None):
                    """Return mock enzyme CURIEs."""
                    self.search_called = True
                    # Return distinct mock values that won't appear in fallback
                    if term in ["protease", "enzyme"]:
                        return ["CHEBI:9025", "CHEBI:9026"]
                    return []

                def get_label(self, curie):
                    """Return mock enzyme labels distinct from fallback."""
                    self.get_label_called = True
                    # Use distinctive labels that are NOT in fallback enzyme list
                    mock_data = {
                        "CHEBI:9025": "MOCK_OAKLIB_PROTEASE_A",
                        "CHEBI:9026": "MOCK_OAKLIB_PROTEASE_B",
                    }
                    return mock_data.get(curie)

            mock_adapter = MockOakAdapter()
            provider = OntologyOptionProvider(oak_adapter=mock_adapter)

            # Get options using the mock adapter
            # This should call _get_options_from_oaklib which uses the adapter
            enzymes = provider.get_options("enzyme")

            # Verify we got options from the Oaklib branch
            assert isinstance(enzymes, list)
            assert len(enzymes) > 0, "Should have enzyme options from mock adapter"

            # All options should have label and value keys
            for option in enzymes:
                assert isinstance(option, dict)
                assert "label" in option
                assert "value" in option

            # Prove mock adapter was used: options contain mock values, not fallback
            enzyme_labels = [o["label"] for o in enzymes]
            assert any("MOCK_OAKLIB" in label for label in enzyme_labels), \
                f"Expected mock Oaklib values in labels, got: {enzyme_labels}"

            # Prove the adapter methods were called
            assert mock_adapter.search_called, "search() method was not called"
            assert mock_adapter.get_label_called, "get_label() method was not called"
        except ImportError as e:
            pytest.skip(f"ontology_provider module not yet implemented: {e}")


class TestRunSampleSerialization:
    """Tests for run sample field serialization and deserialization (Phase 1)."""

    def test_add_run_with_sample_for_lfq(self):
        """Test adding a run with a sample for LFQ workflow."""
        manifest = ManifestState()
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_run(
            file="file.raw",
            sample="s1",
            fraction=1,
        )
        assert len(manifest.runs) == 1
        assert manifest.runs[0].file == "file.raw"
        assert manifest.runs[0].sample == "s1"

    def test_run_serializes_sample_field_to_dict(self):
        """Test that run sample field is serialized in to_dict."""
        manifest = ManifestState()
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_run(
            file="file.raw",
            sample="s1",
            fraction=1,
        )
        result = manifest.to_dict()
        assert len(result["runs"]) == 1
        assert result["runs"][0]["sample"] == "s1"

    def test_run_with_sample_serializes_to_yaml(self):
        """Test that run with sample serializes correctly to YAML."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_run(
            file="file.raw",
            sample="s1",
            fraction=1,
        )
        yaml_str = manifest.to_yaml()
        assert "sample: s1" in yaml_str or "sample:\n        s1" in yaml_str.replace(" ", "")

    def test_load_run_with_sample_from_file(self):
        """Test loading a manifest with run sample field from YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_data = {
                "experiment": {
                    "acquisition_method": "DDA",
                    "enzyme": "Trypsin",
                },
                "samples": [
                    {
                        "id": "s1",
                        "organism": "homo sapiens",
                    }
                ],
                "mixtures": [],
                "runs": [
                    {
                        "file": "file.raw",
                        "sample": "s1",
                        "fraction": 1,
                    }
                ],
            }

            output_file = Path(tmpdir) / "test_sample.yml"
            with open(output_file, "w") as f:
                yaml.safe_dump(test_data, f)

            manifest = ManifestState.load_from_file(output_file)
            assert len(manifest.runs) == 1
            assert manifest.runs[0].sample == "s1"

    def test_run_without_sample_still_works(self):
        """Test that runs without sample field still work (backward compatibility)."""
        manifest = ManifestState()
        manifest.add_run(
            file="file.raw",
            mixture="mix_1",
            fraction=1,
        )
        assert len(manifest.runs) == 1
        assert manifest.runs[0].sample is None
        assert manifest.runs[0].mixture == "mix_1"

    def test_run_with_both_sample_and_mixture_allowed(self):
        """Test that a run can have both sample and mixture (though semantically unusual)."""
        manifest = ManifestState()
        manifest.add_sample(id="s1")
        manifest.add_mixture(id="mix_1", channels={"TMT126": "s1"})
        manifest.add_run(
            file="file.raw",
            sample="s1",
            mixture="mix_1",
            fraction=1,
        )
        assert manifest.runs[0].sample == "s1"
        assert manifest.runs[0].mixture == "mix_1"


class TestRunMutationAPIs:
    """Tests for run mutation APIs (update, remove) (Phase 1)."""

    def test_update_run_property(self):
        """Test updating a run property."""
        manifest = ManifestState()
        manifest.add_run(file="file.raw", fraction=1)
        manifest.update_run(0, fraction=2)
        assert manifest.runs[0].fraction == 2

    def test_update_run_sample(self):
        """Test updating a run's sample assignment."""
        manifest = ManifestState()
        manifest.add_sample(id="s1")
        manifest.add_sample(id="s2")
        manifest.add_run(file="file.raw", sample="s1")
        manifest.update_run(0, sample="s2")
        assert manifest.runs[0].sample == "s2"

    def test_update_run_multiple_fields(self):
        """Test updating multiple run properties at once."""
        manifest = ManifestState()
        manifest.add_run(file="file.raw", fraction=1, instrument="Orbitrap")
        manifest.update_run(0, fraction=3, instrument="Lumos")
        assert manifest.runs[0].fraction == 3
        assert manifest.runs[0].instrument == "Lumos"

    def test_remove_run_by_index(self):
        """Test removing a run by index."""
        manifest = ManifestState()
        manifest.add_run(file="file1.raw")
        manifest.add_run(file="file2.raw")
        manifest.add_run(file="file3.raw")
        assert len(manifest.runs) == 3
        manifest.remove_run(1)
        assert len(manifest.runs) == 2
        assert manifest.runs[0].file == "file1.raw"
        assert manifest.runs[1].file == "file3.raw"

    def test_remove_run_invalid_index(self):
        """Test that removing a run with invalid index raises error."""
        manifest = ManifestState()
        manifest.add_run(file="file.raw")
        with pytest.raises(IndexError):
            manifest.remove_run(5)

    def test_update_run_invalid_index(self):
        """Test that updating a run with invalid index raises error."""
        manifest = ManifestState()
        manifest.add_run(file="file.raw")
        with pytest.raises(IndexError):
            manifest.update_run(5, fraction=2)


class TestValidationWithSampleAndMixtureReferences:
    """Tests for fallback semantic validation of run sample/mixture references (Phase 1)."""

    def test_validate_invalid_run_sample_reference(self):
        """Test that validation catches invalid run sample reference."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(id="s1")
        manifest.add_run(file="file.raw", sample="invalid_sample")

        errors = validate_manifest(manifest)
        assert any(
            "sample" in e.get("message", "").lower() and "invalid_sample" in e.get("message", "")
            for e in errors
        )

    def test_validate_invalid_run_mixture_reference(self):
        """Test that validation catches invalid run mixture reference."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(id="s1")
        manifest.add_run(file="file.raw", mixture="invalid_mixture")

        errors = validate_manifest(manifest)
        assert any(
            "mixture" in e.get("message", "").lower() and "invalid_mixture" in e.get("message", "")
            for e in errors
        )

    def test_validate_valid_run_sample_reference(self):
        """Test that validation passes for valid run sample reference."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_run(file="file.raw", sample="s1", fraction=1)

        errors = validate_manifest(manifest)
        # Should not have errors about invalid sample reference
        assert not any(
            "sample" in e.get("message", "").lower() and "invalid" in e.get("message", "").lower()
            for e in errors
        )

    def test_validate_run_without_sample_or_mixture_allowed(self):
        """Test that runs without sample or mixture are allowed."""
        from manifest_core import validate_manifest
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_run(file="file.raw", fraction=1)  # No sample or mixture

        errors = validate_manifest(manifest)
        # Should not complain about missing sample/mixture
        assert not any(
            "file.raw" in e.get("message", "") and "sample" in e.get("message", "").lower()
            for e in errors
        )


class TestWizardStateManifestCompatibility:
    """Tests for wizard state to manifest state conversion compatibility (Phase 1)."""

    def test_wizard_add_run_with_sample_converts_to_manifest(self):
        """Test that wizard's add_run with sample converts correctly to manifest."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="file.raw", sample="s1", fraction=1)
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )

        manifest = wizard.to_manifest_state()
        assert len(manifest.runs) == 1
        assert manifest.runs[0].sample == "s1"

    def test_wizard_assign_run_sample_converts_to_manifest(self):
        """Test that wizard's assign_run sample conversion works correctly."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="file.raw")
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.assign_run(0, sample="s1")
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )

        manifest = wizard.to_manifest_state()
        assert len(manifest.runs) == 1
        assert manifest.runs[0].sample == "s1"

    def test_wizard_state_roundtrip_with_sample(self):
        """Test wizard state to manifest and back maintains sample."""
        from gui_wizard_state import WizardState
        wizard = WizardState()
        wizard.add_run(file="file.raw", sample="s1")
        wizard.add_sample(id="s1", organism="homo sapiens")
        wizard.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
        )

        manifest = wizard.to_manifest_state()

        # Verify manifest has the sample
        assert manifest.runs[0].sample == "s1"

        # Verify serialization includes sample
        manifest_dict = manifest.to_dict()
        assert manifest_dict["runs"][0]["sample"] == "s1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
