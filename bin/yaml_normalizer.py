#!/usr/bin/env python3
"""
YAML Manifest Normalizer for quantms.

Reads a quantms YAML manifest and emits runtime tables:
  - config TSV: Maps runs to sample/mixture metadata
  - experimental design TSV: OpenMS experimental design format

Usage:
    python yaml_normalizer.py <manifest.yml> --outdir <output_directory>

Output files:
    - <manifest_basename>_config.tsv
    - <manifest_basename>_openms_design.tsv
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, Any, Tuple

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Install with: pip install pyyaml")
    sys.exit(1)


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """Load and parse YAML manifest."""
    try:
        with open(manifest_path, "r") as f:
            manifest = yaml.safe_load(f)
        if not manifest:
            raise ValueError("Manifest is empty")
        return manifest
    except FileNotFoundError:
        print(f"ERROR: Manifest file not found: {manifest_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"ERROR: Failed to parse YAML manifest: {e}")
        sys.exit(1)


def validate_manifest(manifest: Dict[str, Any]) -> None:
    """Basic validation of manifest structure."""
    required_keys = ["experiment", "samples", "mixtures", "runs"]
    missing = [k for k in required_keys if k not in manifest]
    if missing:
        print(f"ERROR: Missing required keys in manifest: {', '.join(missing)}")
        sys.exit(1)

    if not manifest.get("samples"):
        print("ERROR: Manifest must contain at least one sample")
        sys.exit(1)

    if not manifest.get("runs"):
        print("ERROR: Manifest must contain at least one run")
        sys.exit(1)

    # Validate all samples have IDs
    for i, sample in enumerate(manifest["samples"]):
        if not sample.get("id"):
            print(f"ERROR: Sample at index {i} is missing required 'id' field")
            sys.exit(1)

    # Validate all mixtures have IDs
    for i, mixture in enumerate(manifest.get("mixtures", [])):
        if not mixture.get("id"):
            print(f"ERROR: Mixture at index {i} is missing required 'id' field")
            sys.exit(1)
        if not mixture.get("channels"):
            print(f"ERROR: Mixture '{mixture.get('id')}' is missing required 'channels' field")
            sys.exit(1)

    # Validate all runs have file, sample, or mixture
    for i, run in enumerate(manifest["runs"]):
        if not run.get("file"):
            print(f"ERROR: Run at index {i} is missing required 'file' field")
            sys.exit(1)
        has_sample = "sample" in run
        has_mixture = "mixture" in run
        if not (has_sample or has_mixture):
            print(f"ERROR: Run at index {i} (file '{run.get('file')}') must have either 'sample' or 'mixture'")
            sys.exit(1)
        if has_sample and has_mixture:
            print(f"ERROR: Run at index {i} (file '{run.get('file')}') cannot have both 'sample' and 'mixture'")
            sys.exit(1)


def extract_modifications(manifest: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Extract and normalize modifications into fixed and variable sets.

    Returns:
        (fixed_mods_str, variable_mods_str) as semicolon-separated strings
    """
    fixed_mods = []
    variable_mods = []

    for mod in manifest.get("modifications", []):
        mod_str = normalize_modification(mod)
        mode = mod.get("mode", "variable")
        if mode == "fixed":
            fixed_mods.append(mod_str)
        else:
            variable_mods.append(mod_str)

    fixed_str = ";".join(fixed_mods) if fixed_mods else ""
    variable_str = ";".join(variable_mods) if variable_mods else ""

    return fixed_str, variable_str


def normalize_modification(mod: Dict[str, Any]) -> str:
    """
    Convert a modification dict to a normalized string representation.

    Format: [+/-]mass_shift@residues or ontology_id[residues]
    """
    if mod.get("kind") == "custom":
        mass_shift = mod.get("mass_shift", 0)
        sign = "+" if mass_shift >= 0 else ""
        residues = mod.get("residues", "")
        if isinstance(residues, list):
            residues = ",".join(residues)
        return f"{sign}{mass_shift:.6f}@{residues}"
    else:
        # Ontology modification
        ontology_id = mod.get("ontology_id") or mod.get("accession") or mod.get("name", "Unknown")
        residues = mod.get("residues", "")
        if isinstance(residues, list):
            residues = ",".join(residues)
        if residues:
            return f"{ontology_id}[{residues}]"
        else:
            return ontology_id


def get_quantification_method(manifest: Dict[str, Any]) -> str:
    """Get quantification method from manifest, defaulting to LFQ."""
    quant_method = manifest.get("experiment", {}).get("quantification_method", "LFQ")
    # Normalize to label string used in SDRF-style config
    method_map = {
        "LFQ": "label free",
        "TMT": "tmt",
        "iTRAQ": "itraq",
        "SILAC": "silac",
    }
    return method_map.get(quant_method, "label free")


def get_acquisition_method(manifest: Dict[str, Any]) -> str:
    """Get acquisition method from manifest, defaulting to DDA."""
    acq_method = manifest.get("experiment", {}).get("acquisition_method", "DDA")
    return acq_method.lower()


def get_acquisition_method_label(acq_method: str) -> str:
    """
    Map acquisition method abbreviation to full SDRF-compatible label.

    Must produce strings that create_meta_channel can match with substring checks:
    - "data-dependent acquisition" (for DDA)
    - "data-independent acquisition" (for DIA)
    """
    acq_lower = acq_method.lower()
    if "dda" in acq_lower or "dependent" in acq_lower:
        return "Data-Dependent Acquisition"
    elif "dia" in acq_lower or "independent" in acq_lower:
        return "Data-Independent Acquisition"
    else:
        # Fallback to a generic format
        return f"Data-{acq_method.upper()} Acquisition"


def get_dissociation_method(manifest: Dict[str, Any]) -> str:
    """Get dissociation method from manifest."""
    return manifest.get("experiment", {}).get("dissociation_method", "HCD")


def get_enzyme(manifest: Dict[str, Any]) -> str:
    """Get enzyme from manifest."""
    return manifest.get("experiment", {}).get("enzyme", "Trypsin")


def build_samples_map(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a map of sample_id -> sample_metadata."""
    samples_map = {}
    for sample in manifest.get("samples", []):
        sample_id = sample.get("id")
        samples_map[sample_id] = sample
    return samples_map


def build_mixtures_map(manifest: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Build a map of mixture_id -> mixture_metadata."""
    mixtures_map = {}
    for mixture in manifest.get("mixtures", []):
        mixture_id = mixture.get("id")
        mixtures_map[mixture_id] = mixture
    return mixtures_map


def generate_config_tsv(manifest: Dict[str, Any], experiment_id: str = "") -> str:
    """
    Generate config TSV from YAML manifest.

    Columns: filename, URI, label, acquisition method, enzyme, modifications, tolerances, sample/mixture references.
    """
    samples_map = build_samples_map(manifest)
    mixtures_map = build_mixtures_map(manifest)
    quant_method = get_quantification_method(manifest)
    acq_method = get_acquisition_method(manifest)
    acq_method_label = get_acquisition_method_label(acq_method)
    dissociation = get_dissociation_method(manifest)
    enzyme = get_enzyme(manifest)
    fixed_mods, variable_mods = extract_modifications(manifest)

    # Standard SDRF-compatible columns
    headers = [
        "Filename",
        "URI",
        "Label",
        "Proteomics Data Acquisition Method",
        "DissociationMethod",
        "Enzyme",
        "FixedModifications",
        "VariableModifications",
        "PrecursorMassTolerance",
        "PrecursorMassToleranceUnit",
        "FragmentMassTolerance",
        "FragmentMassToleranceUnit",
        "Sample",
        "Mixture",
        "ExperimentID",
    ]

    rows = []

    for run in manifest.get("runs", []):
        filename = Path(run.get("file")).name
        uri = run.get("file")

        # Determine sample reference
        sample_id = run.get("sample")
        mixture_id = run.get("mixture")

        # Get precursor and fragment tolerances (from run or experiment level)
        precursor_tol = run.get("precursor_mass_tolerance")
        if not precursor_tol:
            precursor_tol = manifest.get("experiment", {}).get("precursor_mass_tolerance", "")
        precursor_tol_value = extract_tolerance_value(precursor_tol)
        precursor_tol_unit = extract_tolerance_unit(precursor_tol)

        fragment_tol = run.get("fragment_mass_tolerance")
        if not fragment_tol:
            fragment_tol = manifest.get("experiment", {}).get("fragment_mass_tolerance", "")
        fragment_tol_value = extract_tolerance_value(fragment_tol)
        fragment_tol_unit = extract_tolerance_unit(fragment_tol)

        row = [
            filename,
            uri,
            quant_method,
            acq_method_label,
            dissociation,
            enzyme,
            fixed_mods,
            variable_mods,
            precursor_tol_value,
            precursor_tol_unit,
            fragment_tol_value,
            fragment_tol_unit,
            sample_id or "",
            mixture_id or "",
            experiment_id,
        ]

        rows.append(row)

    # Build TSV
    tsv_lines = ["\t".join(headers)]
    for row in rows:
        tsv_lines.append("\t".join(str(x) for x in row))

    return "\n".join(tsv_lines)


def extract_tolerance_value(tolerance_str: str) -> str:
    """Extract numeric value from tolerance string (e.g., '10 ppm' -> '10')."""
    if not tolerance_str:
        return ""
    parts = tolerance_str.strip().split()
    return parts[0] if parts else ""


def extract_tolerance_unit(tolerance_str: str) -> str:
    """Extract unit from tolerance string (e.g., '10 ppm' -> 'ppm')."""
    if not tolerance_str:
        return ""
    parts = tolerance_str.strip().split()
    return parts[-1] if len(parts) > 1 else ""


def generate_openms_experimental_design(manifest: Dict[str, Any]) -> str:
    """
    Generate OpenMS experimental design TSV.

    Format (tab-separated):
        Fraction_Group | Fraction_ID | file_path | Sample | Condition | Replicate

    For multiplexed experiments (TMT, iTRAQ, SILAC), generates one row per
    channel/sample per run file to match OpenMS/MSstats expectations.

    Fraction_Group is constructed to ensure uniqueness across mixtures/batches:
    - For non-multiplexed: sample_name
    - For multiplexed: mixture_id_channel_label (ensures no collisions)
    """
    samples_map = build_samples_map(manifest)
    mixtures_map = build_mixtures_map(manifest)

    headers = [
        "Fraction_Group",
        "Fraction_ID",
        "Spectrum_File",
        "Sample",
        "Condition",
        "Replicate",
    ]

    rows = []

    for run in manifest.get("runs", []):
        file_path = run.get("file")
        fraction = run.get("fraction", 1)
        sample_id = run.get("sample")
        mixture_id = run.get("mixture")

        if sample_id and sample_id in samples_map:
            # Non-multiplexed case: one row per run
            sample_info = samples_map[sample_id]
            sample_name = sample_id
            condition = sample_info.get("condition", "unknown")
            bio_rep = sample_info.get("biological_replicate", 1)
            tech_rep = sample_info.get("technical_replicate", 1)
            replicate_id = f"{bio_rep}_{tech_rep}"

            fraction_group = sample_name
            fraction_id = str(fraction)  # Integer-compatible fraction number

            row = [
                fraction_group,
                fraction_id,
                file_path,
                sample_name,
                condition,
                replicate_id,
            ]
            rows.append(row)

        elif mixture_id and mixture_id in mixtures_map:
            # Multiplexed case: one row per channel/sample in the mixture
            mixture_info = mixtures_map[mixture_id]
            channels = mixture_info.get("channels", {})

            # Generate one row per channel in the mixture
            for channel_label, channel_sample_id in channels.items():
                if not channel_sample_id:
                    # Skip empty channels
                    continue

                if channel_sample_id in samples_map:
                    sample_info = samples_map[channel_sample_id]
                    sample_name = channel_sample_id
                    condition = sample_info.get("condition", "unknown")
                    bio_rep = sample_info.get("biological_replicate", 1)
                    tech_rep = sample_info.get("technical_replicate", 1)
                    replicate_id = f"{bio_rep}_{tech_rep}"
                else:
                    # Sample not found in samples_map but referenced in channel
                    sample_name = channel_sample_id
                    condition = "unknown"
                    replicate_id = "1"

                # FIXED: Include mixture_id to ensure uniqueness across batches/mixtures
                # This prevents collisions when the same channel label appears in different mixtures
                fraction_group = f"{mixture_id}_{channel_label}"
                fraction_id = str(fraction)  # Integer-compatible fraction number

                row = [
                    fraction_group,
                    fraction_id,
                    file_path,
                    sample_name,
                    condition,
                    replicate_id,
                ]
                rows.append(row)
        else:
            # Fallback for runs without sample or mixture reference
            sample_name = "unknown"
            condition = "unknown"
            replicate_id = "1"

            fraction_group = sample_name
            fraction_id = str(fraction)

            row = [
                fraction_group,
                fraction_id,
                file_path,
                sample_name,
                condition,
                replicate_id,
            ]
            rows.append(row)

    # Build TSV
    tsv_lines = ["\t".join(headers)]
    for row in rows:
        tsv_lines.append("\t".join(str(x) for x in row))

    return "\n".join(tsv_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convert quantms YAML manifest to runtime TSV tables"
    )
    parser.add_argument("manifest", help="Path to YAML manifest")
    parser.add_argument(
        "--outdir", default=".", help="Output directory (default: current directory)"
    )
    parser.add_argument(
        "--prefix", help="Output file prefix (default: manifest basename)"
    )

    args = parser.parse_args()

    # Load and validate manifest
    manifest = load_manifest(args.manifest)
    validate_manifest(manifest)

    # Generate output prefix
    manifest_path = Path(args.manifest)
    prefix = args.prefix or manifest_path.stem
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Generate tables
    config_tsv = generate_config_tsv(manifest, prefix)
    openms_design_tsv = generate_openms_experimental_design(manifest)

    # Write output files
    config_path = outdir / f"{prefix}_config.tsv"
    design_path = outdir / f"{prefix}_openms_design.tsv"

    config_path.write_text(config_tsv)
    design_path.write_text(openms_design_tsv)

    print(f"Generated: {config_path}")
    print(f"Generated: {design_path}")


if __name__ == "__main__":
    main()
