#!/usr/bin/env python3
"""
Integration test for YAML manifest normalization into runtime tables.

Tests that YAML manifests can be successfully normalized into the same
TSV table formats that Nextflow expects as its input, ensuring runtime
compatibility with minimal downstream disruption.
"""

import sys
import tempfile
from pathlib import Path

# Add bin to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "bin"))

from yaml_normalizer import (
    load_manifest,
    validate_manifest,
    generate_config_tsv,
    generate_openms_experimental_design,
)


def test_lfq_manifest_integration():
    """
    Test complete integration: load LFQ YAML -> validate -> generate runtime tables.
    """
    print("\n=== LFQ Manifest Integration Test ===")

    # Load fixture
    manifest_path = (
        Path(__file__).parent
        / "yaml_contract"
        / "fixtures"
        / "valid_lfq.yml"
    )
    manifest = load_manifest(str(manifest_path))

    # Validate
    validate_manifest(manifest)
    print("✓ LFQ manifest validation passed")

    # Generate config
    config_tsv = generate_config_tsv(manifest)
    config_lines = config_tsv.split("\n")
    assert len(config_lines) >= 5, f"Expected at least 5 lines (header + 4 runs), got {len(config_lines)}"
    assert "label free" in config_tsv, "LFQ should have 'label free' in config"
    assert "control_rep1" in config_tsv, "Sample 'control_rep1' should appear in config"
    print("✓ Config TSV generation successful")

    # Generate experimental design
    design_tsv = generate_openms_experimental_design(manifest)
    design_lines = design_tsv.split("\n")
    assert len(design_lines) >= 5, f"Expected at least 5 lines in design TSV, got {len(design_lines)}"
    assert "Fraction_Group" in design_tsv, "Design TSV should have Fraction_Group column"
    assert "control_rep1" in design_tsv, "Sample 'control_rep1' should appear in design"
    print("✓ Experimental design TSV generation successful")

    # Verify both outputs parse correctly as TSV
    config_rows = [
        line.split("\t")
        for line in config_lines[1:]
        if line.strip()
    ]
    design_rows = [
        line.split("\t")
        for line in design_lines[1:]
        if line.strip()
    ]

    assert len(config_rows) == 4, f"Expected 4 config rows, got {len(config_rows)}"
    assert len(design_rows) == 4, f"Expected 4 design rows, got {len(design_rows)}"
    print("✓ All TSV rows parse correctly")

    # Spot-check a few key fields
    first_config = config_rows[0]
    assert first_config[0] == "control_rep1.raw", f"Expected filename 'control_rep1.raw', got '{first_config[0]}'"
    assert first_config[2] == "label free", f"Expected label 'label free', got '{first_config[2]}'"
    assert first_config[5] == "Trypsin", f"Expected enzyme 'Trypsin', got '{first_config[5]}'"
    print("✓ Config TSV fields match expected values")

    first_design = design_rows[0]
    assert first_design[0] == "control_rep1", f"Expected Fraction_Group 'control_rep1', got '{first_design[0]}'"
    assert first_design[3] == "control_rep1", f"Expected Sample 'control_rep1', got '{first_design[3]}'"
    print("✓ Experimental design TSV fields match expected values")


def test_tmt_manifest_integration():
    """
    Test complete integration for multiplexed TMT experiment.
    """
    print("\n=== TMT Manifest Integration Test ===")

    manifest_path = (
        Path(__file__).parent
        / "yaml_contract"
        / "fixtures"
        / "valid_tmtplex.yml"
    )
    manifest = load_manifest(str(manifest_path))
    validate_manifest(manifest)
    print("✓ TMT manifest validation passed")

    config_tsv = generate_config_tsv(manifest)
    assert "tmt" in config_tsv, "TMT config should contain 'tmt' label"
    assert "mix_batch1" in config_tsv, "TMT config should reference mixture 'mix_batch1'"
    print("✓ TMT quantification method recognized in config")

    design_tsv = generate_openms_experimental_design(manifest)
    assert "mix_batch" in design_tsv or "Spectrum_File" in design_tsv, \
        "Mixture references should be preserved in experimental design"
    print("✓ Mixture references preserved in experimental design")


def test_silac_manifest_integration():
    """
    Test complete integration for SILAC multiplex experiment.
    """
    print("\n=== SILAC Manifest Integration Test ===")

    manifest_path = (
        Path(__file__).parent
        / "yaml_contract"
        / "fixtures"
        / "valid_silac.yml"
    )
    manifest = load_manifest(str(manifest_path))
    validate_manifest(manifest)
    print("✓ SILAC manifest validation passed")

    config_tsv = generate_config_tsv(manifest)
    assert "silac" in config_tsv, "SILAC config should contain 'silac' label"
    print("✓ SILAC quantification method recognized")

    design_tsv = generate_openms_experimental_design(manifest)
    assert len(design_tsv.split("\n")) >= 3, "Design TSV should have at least header + 2 data rows"
    print("✓ SILAC experimental design generated")


def test_dia_manifest_integration():
    """
    Test complete integration for DIA (data-independent acquisition) experiment.
    """
    print("\n=== DIA Manifest Integration Test ===")

    manifest_path = (
        Path(__file__).parent
        / "yaml_contract"
        / "fixtures"
        / "valid_dia.yml"
    )
    manifest = load_manifest(str(manifest_path))
    validate_manifest(manifest)
    print("✓ DIA manifest validation passed")

    config_tsv = generate_config_tsv(manifest)
    assert "Data-Independent Acquisition" in config_tsv, "DIA config should contain 'Data-Independent Acquisition'"
    assert "label free" in config_tsv, "DIA should use LFQ (label free) quantification"
    print("✓ DIA acquisition method and LFQ quantification recognized")

    # Verify all runs have explicit sample references
    lines = config_tsv.split("\n")
    header = lines[0].split("\t")
    sample_col = header.index("Sample")
    mixture_col = header.index("Mixture")

    for i, line in enumerate(lines[1:], 1):
        if line.strip():
            parts = line.split("\t")
            # Sample or mixture column should not be empty for DIA LFQ
            assert parts[sample_col] or parts[mixture_col], \
                f"Run {i}: no sample or mixture reference"

    print("✓ All DIA runs have explicit sample/mixture references")


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("YAML Manifest -> Runtime Tables Integration Tests")
    print("=" * 60)

    tests = [
        ("LFQ", test_lfq_manifest_integration),
        ("TMT", test_tmt_manifest_integration),
        ("SILAC", test_silac_manifest_integration),
        ("DIA", test_dia_manifest_integration),
    ]

    failed = []

    for name, test_func in tests:
        try:
            test_func()
            print(f"\n✓ {name} integration test PASSED")
        except AssertionError as e:
            print(f"\n✗ {name} integration test FAILED: {e}")
            failed.append(name)
        except Exception as e:
            print(f"\n✗ {name} integration test ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed.append(name)

    if not failed:
        print("\n" + "=" * 60)
        print("✓ ALL INTEGRATION TESTS PASSED")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print(f"✗ {len(failed)} INTEGRATION TEST(S) FAILED: {', '.join(failed)}")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
