#!/usr/bin/env python3
"""
Tests for YAML manifest normalizer.

Tests the yaml_normalizer module to ensure correct conversion from
YAML manifests to runtime TSV tables (config and experimental design).
"""

import sys
import tempfile
from pathlib import Path
import pytest

# Add bin to path
sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))

try:
    from yaml_normalizer import (
        load_manifest,
        validate_manifest,
        generate_config_tsv,
        generate_openms_experimental_design,
        extract_modifications,
        get_quantification_method,
        normalize_modification,
    )
except ImportError as e:
    print(f"ERROR: Failed to import yaml_normalizer: {e}")
    sys.exit(1)


class TestManifestValidation:
    """Test manifest validation."""

    def test_validate_valid_lfq_manifest(self):
        """Test validation passes for valid LFQ manifest."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_lfq.yml"
        )
        manifest = load_manifest(str(manifest_path))
        # Should not raise
        validate_manifest(manifest)

    def test_validate_valid_tmt_manifest(self):
        """Test validation passes for valid TMT manifest."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_tmtplex.yml"
        )
        manifest = load_manifest(str(manifest_path))
        # Should not raise
        validate_manifest(manifest)

    def test_validate_valid_silac_manifest(self):
        """Test validation passes for valid SILAC manifest."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_silac.yml"
        )
        manifest = load_manifest(str(manifest_path))
        # Should not raise
        validate_manifest(manifest)

    def test_validate_missing_samples(self):
        """Test validation fails when samples missing."""
        manifest = {
            "experiment": {"acquisition_method": "DDA", "enzyme": "Trypsin"},
            "samples": [],
            "mixtures": [],
            "runs": [],
        }
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_missing_runs(self):
        """Test validation fails when runs missing."""
        manifest = {
            "experiment": {"acquisition_method": "DDA", "enzyme": "Trypsin"},
            "samples": [{"id": "s1"}],
            "mixtures": [],
            "runs": [],
        }
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_run_without_sample_or_mixture(self):
        """Test validation fails for run with neither sample nor mixture."""
        manifest = {
            "experiment": {"acquisition_method": "DDA", "enzyme": "Trypsin"},
            "samples": [{"id": "s1"}],
            "mixtures": [],
            "runs": [{"file": "test.raw"}],
        }
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_run_references_missing_sample(self):
        """Test validation fails when run references non-existent sample."""
        manifest_path = (
            Path(__file__).parent
            / "yaml_contract"
            / "fixtures"
            / "invalid_missing_run_sample.yml"
        )
        manifest = load_manifest(str(manifest_path))
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_run_references_missing_mixture(self):
        """Test validation fails when run references non-existent mixture."""
        manifest_path = (
            Path(__file__).parent
            / "yaml_contract"
            / "fixtures"
            / "invalid_missing_run_mixture.yml"
        )
        manifest = load_manifest(str(manifest_path))
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_mixture_channel_references_missing_sample(self):
        """Test validation fails when mixture channel references non-existent sample."""
        manifest_path = (
            Path(__file__).parent
            / "yaml_contract"
            / "fixtures"
            / "invalid_mixture_channel_missing_sample.yml"
        )
        manifest = load_manifest(str(manifest_path))
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_empty_mixture(self):
        """Test validation fails when mixture has all empty channels."""
        manifest_path = (
            Path(__file__).parent
            / "yaml_contract"
            / "fixtures"
            / "invalid_empty_mixture.yml"
        )
        manifest = load_manifest(str(manifest_path))
        with pytest.raises(SystemExit):
            validate_manifest(manifest)

    def test_validate_invalid_acquisition_method(self):
        """Test validation fails for unsupported acquisition_method."""
        manifest = {
            "experiment": {"acquisition_method": "SRM", "enzyme": "Trypsin"},
            "samples": [{"id": "s1"}],
            "mixtures": [],
            "runs": [{"file": "test.raw", "sample": "s1"}],
        }
        with pytest.raises(SystemExit):
            validate_manifest(manifest)


class TestModifications:
    """Test modification handling."""

    def test_extract_modifications_lfq(self):
        """Test modification extraction from LFQ manifest."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_lfq.yml"
        )
        manifest = load_manifest(str(manifest_path))
        fixed, variable = extract_modifications(manifest)
        assert "UNIMOD:4" in fixed
        assert "UNIMOD:35" in variable

    def test_normalize_ontology_mod(self):
        """Test normalization of ontology-based modification."""
        mod = {
            "kind": "ontology",
            "ontology_id": "UNIMOD:21",
            "name": "Phosphorylation",
            "residues": ["S", "T", "Y"],
            "mode": "variable",
        }
        result = normalize_modification(mod)
        assert "UNIMOD:21" in result
        assert "S" in result

    def test_normalize_custom_mod(self):
        """Test normalization of custom modification."""
        mod = {
            "kind": "custom",
            "name": "Lab Isotope",
            "residues": "N",
            "mass_shift": 1.008,
            "mode": "fixed",
        }
        result = normalize_modification(mod)
        assert "1.008" in result
        assert "N" in result


class TestQuantificationMethods:
    """Test quantification method detection."""

    def test_lfq_quantification(self):
        """Test LFQ quantification detection."""
        manifest = {
            "experiment": {"quantification_method": "LFQ"},
            "samples": [{"id": "s1"}],
            "mixtures": [],
            "runs": [{"file": "test.raw", "sample": "s1"}],
        }
        result = get_quantification_method(manifest)
        assert result == "label free"

    def test_tmt_quantification(self):
        """Test TMT quantification detection."""
        manifest = {
            "experiment": {"quantification_method": "TMT"},
            "samples": [{"id": "s1"}],
            "mixtures": [],
            "runs": [{"file": "test.raw", "sample": "s1"}],
        }
        result = get_quantification_method(manifest)
        assert result == "tmt"

    def test_silac_quantification(self):
        """Test SILAC quantification detection."""
        manifest = {
            "experiment": {"quantification_method": "SILAC"},
            "samples": [{"id": "s1"}],
            "mixtures": [],
            "runs": [{"file": "test.raw", "sample": "s1"}],
        }
        result = get_quantification_method(manifest)
        assert result == "silac"


class TestConfigTSVGeneration:
    """Test config TSV generation."""

    def test_config_lfq_single_sample(self):
        """Test config TSV for simple LFQ with single sample."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_lfq.yml"
        )
        manifest = load_manifest(str(manifest_path))
        config = generate_config_tsv(manifest)

        # Check headers
        lines = config.split("\n")
        assert "Label" in lines[0]
        assert "Filename" in lines[0]
        assert "Sample" in lines[0]

        # Check data rows
        assert len([l for l in lines if l and not l.startswith("Label")]) >= 4
        assert "control_rep1.raw" in config
        assert "label free" in config

    def test_config_tmt_multiplexed(self):
        """Test config TSV for TMT multiplexed experiment."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_tmtplex.yml"
        )
        manifest = load_manifest(str(manifest_path))
        config = generate_config_tsv(manifest)

        # Check quantification method
        assert "tmt" in config
        assert "mix_batch1" in config or "mixture" in config.lower()

    def test_config_silac(self):
        """Test config TSV for SILAC experiment."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_silac.yml"
        )
        manifest = load_manifest(str(manifest_path))
        config = generate_config_tsv(manifest)

        # Check quantification method
        assert "silac" in config


class TestOpenMSDesignGeneration:
    """Test OpenMS experimental design TSV generation."""

    def test_design_lfq(self):
        """Test OpenMS design TSV for LFQ."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_lfq.yml"
        )
        manifest = load_manifest(str(manifest_path))
        design = generate_openms_experimental_design(manifest)

        # Check headers
        lines = design.split("\n")
        assert "Fraction_Group" in lines[0]
        assert "Spectrum_File" in lines[0]
        assert "Sample" in lines[0]

        # Check data rows
        assert "control_rep1" in design
        assert "treated_rep1" in design

    def test_design_tmt(self):
        """Test OpenMS design TSV for TMT."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_tmtplex.yml"
        )
        manifest = load_manifest(str(manifest_path))
        design = generate_openms_experimental_design(manifest)

        # Check for mixture references
        assert "mix_batch" in design or "Spectrum_File" in design

    def test_design_has_required_columns(self):
        """Test OpenMS design has all required columns."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_lfq.yml"
        )
        manifest = load_manifest(str(manifest_path))
        design = generate_openms_experimental_design(manifest)

        lines = design.split("\n")
        header = lines[0]
        required_cols = [
            "Fraction_Group",
            "Fraction_ID",
            "Spectrum_File",
            "Sample",
            "Condition",
        ]
        for col in required_cols:
            assert col in header, f"Missing column: {col}"


class TestEndToEnd:
    """End-to-end tests with actual manifest fixtures."""

    def test_lfq_fixture_roundtrip(self):
        """Test complete normalization of LFQ fixture."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_lfq.yml"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = load_manifest(str(manifest_path))
            validate_manifest(manifest)

            config = generate_config_tsv(manifest)
            design = generate_openms_experimental_design(manifest)

            # Verify outputs
            assert config
            assert design
            assert "control_rep" in config
            assert "label free" in config
            assert len(config.split("\n")) >= 5  # header + 4 runs
            assert len(design.split("\n")) >= 5  # header + 4 runs

    def test_tmt_fixture_roundtrip(self):
        """Test complete normalization of TMT fixture."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_tmtplex.yml"
        )
        manifest = load_manifest(str(manifest_path))
        validate_manifest(manifest)

        config = generate_config_tsv(manifest)
        design = generate_openms_experimental_design(manifest)

        # Verify outputs
        assert config
        assert design
        assert "tmt" in config
        assert "fraction" in design.lower()

    def test_silac_fixture_roundtrip(self):
        """Test complete normalization of SILAC fixture."""
        manifest_path = (
            Path(__file__).parent / "yaml_contract" / "fixtures" / "valid_silac.yml"
        )
        manifest = load_manifest(str(manifest_path))
        validate_manifest(manifest)

        config = generate_config_tsv(manifest)
        design = generate_openms_experimental_design(manifest)

        # Verify outputs
        assert config
        assert design
        assert "silac" in config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
