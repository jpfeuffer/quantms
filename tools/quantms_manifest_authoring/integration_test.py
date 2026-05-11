#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pytest",
#   "pyyaml",
# ]
# ///
"""
Integration tests for quantms manifest authoring.

Tests the full manifest authoring workflow including creating LFQ and multiplex
manifests, validation, serialization, and round-trip load/save scenarios.
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from manifest_core import ManifestState, validate_manifest


class TestLFQManifestWorkflow:
    """Integration tests for LFQ manifest authoring workflow."""

    def test_create_lfq_manifest(self):
        """Test creating a complete LFQ manifest."""
        manifest = ManifestState()

        # Set metadata
        manifest.metadata.schema_version = "1.0.0"
        manifest.metadata.ontology_versions = {"psi-ms": "4.1.135"}

        # Set experiment
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="LFQ",
            dissociation_method="HCD",
            precursor_mass_tolerance="10 ppm",
            fragment_mass_tolerance="0.02 Da",
        )

        # Add samples
        manifest.add_sample(
            id="control_rep1",
            organism="homo sapiens",
            organism_part="cell line",
            condition="control",
            biological_replicate=1,
        )
        manifest.add_sample(
            id="control_rep2",
            organism="homo sapiens",
            organism_part="cell line",
            condition="control",
            biological_replicate=2,
        )
        manifest.add_sample(
            id="treated_rep1",
            organism="homo sapiens",
            organism_part="cell line",
            condition="treated",
            biological_replicate=1,
        )

        # Add runs (no mixture for LFQ)
        manifest.add_run(
            file="s3://bucket/control_rep1_F1.raw",
            mixture=None,
            fraction=1,
        )
        manifest.add_run(
            file="s3://bucket/control_rep2_F1.raw",
            mixture=None,
            fraction=1,
        )
        manifest.add_run(
            file="s3://bucket/treated_rep1_F1.raw",
            mixture=None,
            fraction=1,
        )

        # Add modifications
        manifest.add_modification(
            mode="fixed",
            kind="ontology",
            name="Carbamidomethyl",
            residues="C",
        )
        manifest.add_modification(
            mode="variable",
            kind="ontology",
            name="Oxidation",
            residues="M",
        )

        # Verify structure
        assert manifest.experiment.acquisition_method == "DDA"
        assert manifest.experiment.quantification_method == "LFQ"
        assert len(manifest.samples) == 3
        assert len(manifest.runs) == 3
        assert len(manifest.modifications) == 2

    def test_lfq_manifest_validation(self):
        """Test that a valid LFQ manifest passes validation."""
        manifest = ManifestState()
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="LFQ",
        )
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_run(file="file.raw", mixture=None, fraction=1)

        errors = validate_manifest(manifest)
        critical_errors = [e for e in errors if e.get("level") == "error"]
        assert len(critical_errors) == 0

    def test_lfq_manifest_persistence(self):
        """Test saving and loading LFQ manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manifest
            manifest = ManifestState()
            manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
            manifest.add_sample(id="s1", organism="homo sapiens")
            manifest.add_run(file="file.raw", mixture=None, fraction=1)

            # Save
            save_path = Path(tmpdir) / "lfq_manifest.yml"
            manifest.save_to_file(save_path)
            assert save_path.exists()

            # Load and verify
            loaded = ManifestState.load_from_file(save_path)
            assert loaded.experiment.acquisition_method == "DDA"
            assert len(loaded.samples) == 1
            assert len(loaded.runs) == 1


class TestTMTManifestWorkflow:
    """Integration tests for TMT multiplex manifest authoring workflow."""

    def test_create_tmt_manifest(self):
        """Test creating a complete TMT multiplex manifest."""
        manifest = ManifestState()

        # Set metadata
        manifest.metadata.schema_version = "1.0.0"
        manifest.metadata.ontology_versions = {"psi-ms": "4.1.135"}

        # Set experiment
        manifest.set_experiment(
            acquisition_method="DDA",
            enzyme="Trypsin",
            quantification_method="TMT",
            dissociation_method="HCD",
        )

        # Add samples
        for condition in ["control", "treated"]:
            for rep in range(1, 3):
                manifest.add_sample(
                    id=f"{condition}_rep{rep}",
                    organism="homo sapiens",
                    organism_part="tissue",
                    condition=condition,
                    biological_replicate=rep,
                )

        # Define TMT6plex mixture
        channels = {
            "TMT126": "control_rep1",
            "TMT127N": "control_rep2",
            "TMT127C": "treated_rep1",
            "TMT128N": "treated_rep2",
        }
        manifest.add_mixture(
            id="plex_1",
            channels=channels,
            description="TMT6 mix with 2 control + 2 treated",
        )

        # Add runs
        manifest.add_run(
            file="s3://bucket/plex_1_F1.raw",
            mixture="plex_1",
            fraction=1,
        )
        manifest.add_run(
            file="s3://bucket/plex_1_F2.raw",
            mixture="plex_1",
            fraction=2,
        )

        # Add modifications
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
            name="TMT",
            residues="K,N-term",
            profile="default",
        )
        manifest.add_modification(
            mode="variable",
            kind="ontology",
            name="Oxidation",
            residues="M",
            profile="default",
        )

        # Verify structure
        assert manifest.experiment.quantification_method == "TMT"
        assert len(manifest.samples) == 4
        assert len(manifest.mixtures) == 1
        assert len(manifest.mixtures[0].channels) == 4
        assert len(manifest.runs) == 2
        assert len(manifest.modifications) == 3

    def test_tmt_mixture_channels_preserved(self):
        """Test that TMT mixture channel assignments are correctly preserved."""
        manifest = ManifestState()
        for i in range(1, 5):
            manifest.add_sample(id=f"sample{i}")

        channels = {
            "TMT126": "sample1",
            "TMT127N": "sample2",
            "TMT127C": "sample3",
            "TMT128N": "sample4",
        }
        manifest.add_mixture(id="plex_1", channels=channels)

        # Verify channels preserved in dict
        manifest_dict = manifest.to_dict()
        mixture = manifest_dict["mixtures"][0]
        assert mixture["channels"]["TMT126"] == "sample1"
        assert mixture["channels"]["TMT127N"] == "sample2"
        assert mixture["channels"]["TMT127C"] == "sample3"
        assert mixture["channels"]["TMT128N"] == "sample4"

    def test_tmt_manifest_validation(self):
        """Test that a valid TMT manifest passes validation."""
        manifest = ManifestState()
        manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
        manifest.add_sample(id="s1", organism="homo sapiens")
        manifest.add_mixture(id="mix_1", channels={"TMT126": "s1"})
        manifest.add_run(file="file.raw", mixture="mix_1", fraction=1)

        errors = validate_manifest(manifest)
        critical_errors = [e for e in errors if e.get("level") == "error"]
        assert len(critical_errors) == 0

    def test_tmt_manifest_persistence(self):
        """Test saving and loading TMT manifest with channel preservation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manifest
            manifest = ManifestState()
            manifest.set_experiment(acquisition_method="DDA", enzyme="Trypsin")
            manifest.add_sample(id="s1")
            manifest.add_sample(id="s2")
            manifest.add_sample(id="s3")
            manifest.add_mixture(
                id="plex_1",
                channels={
                    "TMT126": "s1",
                    "TMT127N": "s2",
                    "TMT127C": "s3",
                },
            )
            manifest.add_run(file="file.raw", mixture="plex_1", fraction=1)

            # Save
            save_path = Path(tmpdir) / "tmt_manifest.yml"
            manifest.save_to_file(save_path)

            # Load and verify
            loaded = ManifestState.load_from_file(save_path)
            assert loaded.experiment.quantification_method is None  # Not set in this test
            assert len(loaded.samples) == 3
            assert len(loaded.mixtures) == 1

            loaded_mixture = loaded.mixtures[0]
            assert loaded_mixture.channels["TMT126"] == "s1"
            assert loaded_mixture.channels["TMT127N"] == "s2"
            assert loaded_mixture.channels["TMT127C"] == "s3"


class TestRoundTripSerialization:
    """Integration tests for manifest round-trip (create -> save -> load -> verify)."""

    def test_complex_manifest_round_trip(self):
        """Test a complex manifest survives save/load cycle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a complex manifest
            manifest = ManifestState()
            manifest.metadata.schema_version = "1.0.0"
            manifest.set_experiment(
                acquisition_method="DDA",
                enzyme="Trypsin",
                quantification_method="TMT",
            )

            # Add multiple samples
            for cond in ["ctrl", "trt"]:
                for rep in range(1, 3):
                    manifest.add_sample(
                        id=f"{cond}_{rep}",
                        organism="homo sapiens",
                        condition=cond,
                        biological_replicate=rep,
                    )

            # Add mixture
            manifest.add_mixture(
                id="plex1",
                channels={
                    "TMT126": "ctrl_1",
                    "TMT127N": "ctrl_2",
                    "TMT127C": "trt_1",
                    "TMT128N": "trt_2",
                },
            )

            # Add runs
            for frac in range(1, 3):
                manifest.add_run(
                    file=f"file{frac}.raw",
                    mixture="plex1",
                    fraction=frac,
                )

            # Save
            save_path = Path(tmpdir) / "complex.yml"
            manifest.save_to_file(save_path)

            # Load
            loaded = ManifestState.load_from_file(save_path)

            # Verify everything
            assert loaded.experiment.enzyme == "Trypsin"
            assert len(loaded.samples) == 4
            assert len(loaded.mixtures) == 1
            assert len(loaded.runs) == 2
            assert loaded.mixtures[0].channels["TMT126"] == "ctrl_1"
            assert loaded.runs[0].mixture == "plex1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
