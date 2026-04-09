#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "jsonschema",
#   "pyyaml",
# ]
# ///
"""
Test suite for quantms YAML input contract validation.

Validates YAML manifests against the quantms_yaml_manifest.json schema.
The schema defines the contract for experiment metadata, samples, mixtures, runs,
and named modification profiles.

IMPORTANT: This test validates the current, approved schema contract.
Runtime consumption of YAML manifests is not yet implemented.
The current pipeline still accepts SDRF format for data processing.

Tests use jsonschema + PyYAML for standards-based validation.
"""

import sys
import json
import re
import yaml
import tempfile
from pathlib import Path

try:
    import jsonschema
except ImportError:
    print("ERROR: jsonschema not installed. Install with: pip install jsonschema")
    sys.exit(1)


KNOWN_ONTOLOGY_MODIFICATIONS = {
    'UNIMOD:4': {
        'names': {'carbamidomethyl'},
        'residues': {'C'},
        'term_specificities': {'none'},
        'mass_shift': 57.021464,
    },
    'UNIMOD:21': {
        'names': {'phosphorylation'},
        'residues': {'S', 'T', 'Y'},
        'term_specificities': {'none'},
        'mass_shift': 79.966331,
        'formula': 'HO3P',
    },
}

SAMPLE_EXPLICIT_FIELDS = {
    'id',
    'organism',
    'organism_part',
    'condition',
    'biological_replicate',
    'technical_replicate',
    'disease',
    'cell_type',
}

ONTOLOGY_NAME_INDEX = {
    name: ontology_id
    for ontology_id, entry in KNOWN_ONTOLOGY_MODIFICATIONS.items()
    for name in entry.get('names', set())
}

MASS_SHIFT_TOLERANCE = 0.001


def _normalize_modification_name_for_lookup(value: str | None) -> str | None:
    """Normalize names by lowercasing and stripping non-alphanumeric characters for local matching."""
    if not value:
        return None
    return re.sub(r'[^a-z0-9]+', '', value.lower())


def _as_list(value) -> list:
    """Return a scalar or array field as a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _get_term_specificity(modification: dict) -> str | None:
    """Return the canonical term-specificity value, supporting the deprecated term_spec alias."""
    return modification.get('term_specificity') if 'term_specificity' in modification else modification.get('term_spec')


def _get_ontology_id(modification: dict) -> str | None:
    """Return the canonical ontology identifier, supporting the deprecated accession alias."""
    ontology_id = modification.get('ontology_id')
    accession = modification.get('accession')
    return ontology_id or accession


def _has_mismatched_ontology_identifiers(modification: dict) -> bool:
    """Return True when ontology_id and deprecated accession are both present but disagree."""
    ontology_id = modification.get('ontology_id')
    accession = modification.get('accession')
    return bool(ontology_id and accession and ontology_id != accession)


def _resolve_known_ontology_entry(modification: dict) -> tuple[str | None, dict | None]:
    """Resolve a modification to the local ontology registry by ontology_id or normalized name."""
    ontology_id = _get_ontology_id(modification)
    name_key = _normalize_modification_name_for_lookup(modification.get('name'))

    if ontology_id and ontology_id in KNOWN_ONTOLOGY_MODIFICATIONS:
        return ontology_id, KNOWN_ONTOLOGY_MODIFICATIONS[ontology_id]

    if name_key and name_key in ONTOLOGY_NAME_INDEX:
        resolved_id = ONTOLOGY_NAME_INDEX[name_key]
        return resolved_id, KNOWN_ONTOLOGY_MODIFICATIONS[resolved_id]

    return ontology_id, None


def _get_modification_sources(data: dict) -> list[tuple[str, list]]:
    """Return the configured modification collections, including deprecated aliases."""
    sources = []
    if data.get('modifications'):
        sources.append(('modifications', data.get('modifications') or []))

    experiment = data.get('experiment', {})
    if experiment.get('modifications'):
        sources.append(('experiment.modifications', experiment.get('modifications') or []))

    if data.get('mod_profiles'):
        sources.append(('mod_profiles', data.get('mod_profiles') or []))

    return sources


def _iter_modifications(data: dict):
    """Yield all direct modification entries from the canonical collection or deprecated aliases."""
    for source_name, source_entries in _get_modification_sources(data):
        for i, modification in enumerate(source_entries):
            yield f"{source_name}[{i}]", modification


def get_schema_path() -> Path:
    """Get path to the quantms YAML manifest schema."""
    schema_path = Path(__file__).parent.parent.parent / 'assets' / 'schemas' / 'quantms_yaml_manifest.json'
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")
    return schema_path


def load_schema(schema_path: Path) -> dict:
    """Load JSON schema from file."""
    try:
        with open(schema_path, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in schema: {e}")


def load_yaml(yaml_path: Path) -> dict:
    """Load and parse YAML file."""
    try:
        with open(yaml_path, 'r') as f:
            data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ValueError("YAML root must be a dictionary")
            return data
    except FileNotFoundError:
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error: {e}")


def validate_yaml_against_schema(yaml_path: Path, schema_path: Path) -> tuple:
    """
    Validate a YAML file against the schema.

    Returns:
        (is_valid: bool, error_messages: list[str])
    """
    errors = []

    try:
        schema = load_schema(schema_path)
        data = load_yaml(yaml_path)
    except (FileNotFoundError, ValueError) as e:
        return False, [str(e)]

    # Validate against schema
    validator = jsonschema.Draft7Validator(schema)
    validation_errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

    if validation_errors:
        for error in validation_errors:
            path = '.'.join(str(p) for p in error.absolute_path) or '<root>'
            errors.append(f"[{path}] {error.message}")
        return False, errors

    return True, []


# ============================================================================
# Test Suite
# ============================================================================


def test_valid_fixture():
    """Test that the canonical valid_tmtplex.yml fixture passes schema validation."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'valid_tmtplex.yml'
    schema_path = get_schema_path()

    is_valid, errors = validate_with_custom_semantics(fixture_path, schema_path)

    if not is_valid:
        print(f"✗ Fixture validation failed: {fixture_path}")
        for error in errors:
            print(f"  {error}")
        assert False, f"Fixture should be valid: {errors}"

    print(f"✓ test_valid_fixture passed")


def test_valid_lfq_fixture():
    """Test that the valid_lfq.yml fixture (label-free quantification) passes schema validation."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'valid_lfq.yml'
    schema_path = get_schema_path()

    is_valid, errors = validate_with_custom_semantics(fixture_path, schema_path)

    if not is_valid:
        print(f"✗ LFQ fixture validation failed: {fixture_path}")
        for error in errors:
            print(f"  {error}")
        assert False, f"LFQ fixture should be valid: {errors}"

    print(f"✓ test_valid_lfq_fixture passed")


def test_valid_silac_fixture():
    """Test that the valid_silac.yml fixture (SILAC with compound labels) passes schema validation."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'valid_silac.yml'
    schema_path = get_schema_path()

    is_valid, errors = validate_with_custom_semantics(fixture_path, schema_path)

    if not is_valid:
        print(f"✗ SILAC fixture validation failed: {fixture_path}")
        for error in errors:
            print(f"  {error}")
        assert False, f"SILAC fixture should be valid: {errors}"

    print(f"✓ test_valid_silac_fixture passed")


def test_valid_without_mod_profiles():
    """Test that YAML without mod_profiles section is valid (optional section)."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: HCD
  modifications:
    - kind: ontology
      ontology_id: "UNIMOD:4"
      name: "Carbamidomethyl"
      residues: C
      mode: fixed
    - kind: ontology
      ontology_id: "UNIMOD:35"
      name: "Oxidation"
      residues: M
      mode: variable
  precursor_mass_tolerance: "5 ppm"
  fragment_mass_tolerance: "0.02 Da"

samples:
  - id: sample1
    organism: homo sapiens
    condition: control
    biological_replicate: 1
  - id: sample2
    organism: homo sapiens
    condition: treated
    biological_replicate: 1

mixtures:
  - id: mix1
    channels:
      TMT126: sample1
      TMT127N: sample2

runs:
  - file: s3://bucket/data.raw
    fraction: 1
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Valid YAML without modifications should pass: {errors}"
        print("✓ test_valid_without_mod_profiles passed")
    finally:
        yaml_path.unlink()


def test_missing_required_section_samples():
    """Test that YAML missing required 'samples' section fails."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert not is_valid, "YAML missing 'samples' should fail"
        assert any("'samples' is a required property" in e for e in errors), \
            f"Error should mention 'samples' requirement: {errors}"
        print(f"✓ test_missing_required_section_samples passed")
    finally:
        yaml_path.unlink()


def test_invalid_modification_collection_wrong_type():
    """Test that modifications with wrong type (not list) fails validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

modifications:
  invalid: "profile"
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert not is_valid, "YAML with invalid modifications type should fail"
        assert any("is not of type 'array'" in e for e in errors), \
            f"Error should mention array type requirement: {errors}"
        print("✓ test_invalid_modification_collection_wrong_type passed")
    finally:
        yaml_path.unlink()


def test_multiple_profiles_require_run_profile():
    """Test that runs must select a profile when multiple modification profiles are defined."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

modifications:
  - profile: default
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mode: variable
  - profile: phospho_enriched
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: T
    mode: variable
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Runs must choose a profile when multiple are defined"
        assert any("must set modification_profile" in e for e in errors), \
            f"Error should mention missing modification_profile: {errors}"
        print("✓ test_multiple_profiles_require_run_profile passed")
    finally:
        yaml_path.unlink()


def test_additional_metadata_overlap_is_rejected():
    """Test that additional_metadata cannot duplicate explicit or SDRF-derived sample fields."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens
    characteristics:
      cell_line: HeLa
    additional_metadata:
      organism: duplicate
      cell_line: duplicate

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Overlapping additional_metadata should fail"
        assert any("additional_metadata overlaps" in e for e in errors), f"Unexpected errors: {errors}"
        print("✓ test_additional_metadata_overlap_is_rejected passed")
    finally:
        yaml_path.unlink()


def test_mod_profile_with_root_level_engine_fields():
    """Test that flat optional tool-specific fields on modifications validate correctly."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  # Ontology-backed modification with Comet engine block at root level
  - id: phospho_sty
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues:
      - S
      - T
      - Y
    mode: variable
    mass_shift: 79.966331
    formula: "HO3P"
    term_specificity: none
    binary_group: 1
    min_occurrences: 0
    max_occurrences: 3
    localize_mass_shift: true
  # Custom modification with fixed mode
  - id: custom_crosslink
    kind: custom
    name: "Custom crosslink"
    residues: K
    mode: fixed
    mass_shift: 138.068
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        if not is_valid:
            print(f"Errors: {errors}")
        assert is_valid, f"mod_profile with root-level engine blocks should pass: {errors}"
        print(f"✓ test_mod_profile_with_root_level_engine_fields passed")
    finally:
        yaml_path.unlink()


def test_ontology_mod_accession_only():
    """Test that ontology-backed modification with accession only (no name) passes validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho_tyr
    kind: ontology
    accession: "UNIMOD:21"
    residues: Y
    mode: variable
    mass_shift: 79.966331
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Ontology mod with accession only should pass: {errors}"
        print(f"✓ test_ontology_mod_accession_only passed")
    finally:
        yaml_path.unlink()


def test_ontology_mod_name_only():
    """Test that ontology-backed modification with name only (no accession) passes validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho_thr
    kind: ontology
    name: "Phosphorylation"
    residues: T
    mode: variable
    mass_shift: 79.966331
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Ontology mod with name only should pass: {errors}"
        print(f"✓ test_ontology_mod_name_only passed")
    finally:
        yaml_path.unlink()


def test_custom_modification_shape():
    """Test that custom modification (without ontology reference) validates correctly."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: my_custom_mod
    kind: custom
    name: "My Custom Label"
    residues: K
    mode: fixed
    mass_shift: 150.5
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Custom modification should pass: {errors}"
        print(f"✓ test_custom_modification_shape passed")
    finally:
        yaml_path.unlink()


def test_missing_required_mode_field():
    """Test that modification without 'mode' field fails validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: incomplete_mod
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mass_shift: 79.966331
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert not is_valid, "Modification without 'mode' should fail"
        assert any("'mode' is a required property" in e for e in errors), \
            f"Error should mention 'mode' requirement: {errors}"
        print(f"✓ test_missing_required_mode_field passed")
    finally:
        yaml_path.unlink()


def test_invalid_mode_value():
    """Test that modification with invalid mode value fails validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: bad_mode_mod
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mode: optional
    mass_shift: 79.966331
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert not is_valid, "Modification with invalid mode should fail"
        assert any("is not one of" in e or "enum" in e.lower() for e in errors), \
            f"Error should mention enum constraint: {errors}"
        print(f"✓ test_invalid_mode_value passed")
    finally:
        yaml_path.unlink()


def test_invalid_term_specificity_value():
    """Test that modification with invalid term_specificity value fails validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: bad_term_specificity
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mode: variable
    mass_shift: 79.966331
    term_specificity: invalid_terminus
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert not is_valid, "Modification with invalid term_specificity should fail"
        assert any("is not one of" in e or "enum" in e.lower() for e in errors), \
            f"Error should mention enum constraint: {errors}"
        print(f"✓ test_invalid_term_specificity_value passed")
    finally:
        yaml_path.unlink()


def test_valid_term_specificity_values():
    """Test that all valid term_specificity values are accepted."""
    valid_term_specificities = ["none", "n-term", "c-term", "protein-n-term", "protein-c-term"]

    for term_specificity in valid_term_specificities:
        yaml_content = f"""experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho_test
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mode: variable
    mass_shift: 79.966331
    term_specificity: {term_specificity}
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(yaml_content)
            yaml_path = Path(f.name)

        try:
            schema_path = get_schema_path()
            is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

            assert is_valid, f"term_specificity='{term_specificity}' should pass: {errors}"
        finally:
            yaml_path.unlink()

    print(f"✓ test_valid_term_specificity_values passed")


def test_ontology_mod_without_accession_or_name():
    """Test that ontology modification without ontology_id/accession AND name fails."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: incomplete_ontology_mod
    kind: ontology
    residues: S
    mode: variable
    mass_shift: 79.966331
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Ontology modification without ontology_id or name should fail"
        # The error should come from semantic validation
        assert any("ontology_id" in e.lower() and "name" in e.lower() for e in errors) or \
               any("missing" in e.lower() for e in errors), \
            f"Error should mention missing ontology_id/name: {errors}"
        print(f"✓ test_ontology_mod_without_accession_or_name passed")
    finally:
        yaml_path.unlink()


def test_experiment_level_modifications_use_shared_structure():
    """Test that the canonical top-level modifications collection accepts shared ontology/custom entries."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

modifications:
  - kind: ontology
    name: "Phosphorylation"
    residues:
      - S
      - T
    mode: variable
    binary_group: 1
  - kind: custom
    name: "Custom Crosslinker"
    residues: K
    mode: fixed
    mass_shift: 138.068
    localize_mass_shift: true
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Experiment-level modifications should use shared structure: {errors}"
        print("✓ test_experiment_level_modifications_use_shared_structure passed")
    finally:
        yaml_path.unlink()


def test_known_ontology_mod_rejects_invalid_residue_subset():
    """Test that ontology residue subsets are checked against locally curated ontology values."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  modifications:
    - kind: ontology
      ontology_id: "UNIMOD:21"
      residues: K
      mode: variable

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Invalid ontology residue subset should fail"
        assert any("allowed residue subset" in e for e in errors), f"Unexpected errors: {errors}"
        print("✓ test_known_ontology_mod_rejects_invalid_residue_subset passed")
    finally:
        yaml_path.unlink()


def test_known_ontology_mod_rejects_incorrect_mass_shift():
    """Test that user-specified ontology mass shifts are checked against curated ontology values."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  modifications:
    - kind: ontology
      ontology_id: "UNIMOD:21"
      name: "Phosphorylation"
      mode: variable
      mass_shift: 80.0

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Incorrect ontology mass_shift should fail"
        assert any("disagrees with the curated ontology value" in e for e in errors), f"Unexpected errors: {errors}"
        print("✓ test_known_ontology_mod_rejects_incorrect_mass_shift passed")
    finally:
        yaml_path.unlink()


def test_terminal_modification_must_use_term_specificity():
    """Test that terminal modifications cannot encode N-term/C-term in the residues field."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

modifications:
  - kind: ontology
    name: "TMT16plex"
    residues: N-term
    mode: fixed
    term_specificity: n-term
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Terminal residue aliases should fail"
        assert any("must use 'term_specificity'" in e for e in errors), f"Unexpected errors: {errors}"
        print("✓ test_terminal_modification_must_use_term_specificity passed")
    finally:
        yaml_path.unlink()


def test_invalid_experiment_wrong_method():
    """Test that invalid acquisition_method is rejected."""
    yaml_content = """experiment:
  acquisition_method: INVALID_METHOD
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert not is_valid, "Invalid acquisition_method should fail"
        assert any("is not one of" in e for e in errors), \
            f"Error should mention enum constraint: {errors}"
        print(f"✓ test_invalid_experiment_wrong_method passed")
    finally:
        yaml_path.unlink()


# ============================================================================
# Ontology, Enum, and Multiplex Validation Tests
# ============================================================================
# These tests enforce controlled vocabularies, ontology fields, and multiplex
# channel constraints including dissociation methods, enzymes, and TMT/SILAC.


def validate_with_custom_semantics(yaml_path: Path, schema_path: Path) -> tuple:
    """
    Validate YAML against schema plus custom semantic constraints.

    Returns:
        (is_valid: bool, error_messages: list[str])
    """
    # First, run JSON schema validation
    schema_errors = []
    try:
        schema = load_schema(schema_path)
        data = load_yaml(yaml_path)
    except (FileNotFoundError, ValueError) as e:
        return False, [str(e)]

    validator = jsonschema.Draft7Validator(schema)
    validation_errors = sorted(validator.iter_errors(data), key=lambda e: e.path)

    if validation_errors:
        for error in validation_errors:
            path = '.'.join(str(p) for p in error.absolute_path) or '<root>'
            schema_errors.append(f"[{path}] {error.message}")

    # Then apply custom semantic validation
    semantic_errors = _validate_semantic_constraints(data)

    all_errors = schema_errors + semantic_errors
    return len(all_errors) == 0, all_errors


def _validate_semantic_constraints(data: dict) -> list:
    """Validate semantic constraints beyond JSON schema."""
    errors = []

    modification_sources = _get_modification_sources(data)
    if len(modification_sources) > 1:
        errors.append(
            "[modifications] Use only one modification collection: top-level 'modifications' is canonical; "
            "do not combine it with deprecated aliases such as experiment.modifications or mod_profiles."
        )

    # Dissociation method validation (known MS fragmentation methods)
    valid_dissociation_methods = {
        'HCD', 'CID', 'ETD', 'PSD', 'ECD', 'IRMPD', 'PQD',
        'UVPD', 'SID', 'NETD', 'SURMAC', 'CX'
    }
    if 'experiment' in data and 'dissociation_method' in data['experiment']:
        method = data['experiment'].get('dissociation_method', '').upper()
        if method and method not in valid_dissociation_methods:
            errors.append(
                f"[experiment.dissociation_method] '{method}' is not a recognized MS dissociation method. "
                f"Valid methods: {', '.join(sorted(valid_dissociation_methods))}"
            )

    # Enzyme validation (known proteases)
    valid_enzymes = {
        'Trypsin', 'Chymotrypsin', 'Pepsin', 'Elastase', 'LysC',
        'Asp-N', 'Glu-C', 'Arg-C', 'None', 'Whole protein'
    }
    if 'experiment' in data and 'enzyme' in data['experiment']:
        enzyme = data['experiment'].get('enzyme', '').strip()
        if enzyme and enzyme not in valid_enzymes:
            errors.append(
                f"[experiment.enzyme] '{enzyme}' is not a recognized protease. "
                f"Valid enzymes: {', '.join(sorted(valid_enzymes))}"
            )

    # Sample metadata overlap checks
    for i, sample in enumerate(data.get('samples', []) or []):
        path = f"samples[{i}]"
        characteristics = set((sample.get('characteristics') or {}).keys())
        factor_values = set((sample.get('factor_values') or {}).keys())
        additional = set((sample.get('additional_metadata') or {}).keys())
        explicit = {key for key in SAMPLE_EXPLICIT_FIELDS if key in sample}

        duplicate_standard = (characteristics | factor_values) & explicit
        if duplicate_standard:
            errors.append(
                f"[{path}] Explicit sample properties must not be duplicated under characteristics/factor_values: "
                f"{sorted(duplicate_standard)}."
            )

        additional_overlap = additional & (explicit | characteristics | factor_values)
        if additional_overlap:
            errors.append(
                f"[{path}.additional_metadata] User-specific additional_metadata overlaps with standard sample metadata: "
                f"{sorted(additional_overlap)}."
            )

    # Modification validation: semantic constraints for ontology-backed and custom mods
    for path, modification in _iter_modifications(data):
        kind = modification.get('kind', 'ontology')
        canonical_ontology_id = _get_ontology_id(modification)
        term_specificity = _get_term_specificity(modification)
        residues = set(_as_list(modification.get('residues')))

        if _has_mismatched_ontology_identifiers(modification):
            errors.append(
                f"[{path}] ontology_id '{modification.get('ontology_id')}' and deprecated accession "
                f"'{modification.get('accession')}' must match when both are provided."
            )

        if canonical_ontology_id and not (
            canonical_ontology_id.startswith('UNIMOD:') or canonical_ontology_id.startswith('MOD:')
        ):
            errors.append(
                f"[{path}.ontology_id] '{canonical_ontology_id}' does not match expected format "
                "(UNIMOD:<number> or MOD:<number>)"
            )

        if kind == 'ontology':
            if not (modification.get('name') or canonical_ontology_id):
                errors.append(
                    f"[{path}] Ontology-backed modification (kind='ontology') must have at least one of "
                    f"'name' or 'ontology_id' defined."
                )
        elif kind == 'custom':
            if canonical_ontology_id:
                errors.append(
                    f"[{path}] Custom modification (kind='custom') must not declare ontology_id/accession."
                )

            if not modification.get('name'):
                errors.append(
                    f"[{path}] Custom modification (kind='custom') must have 'name' field "
                    f"to uniquely define the modification."
                )

            if modification.get('mass_shift') is None:
                errors.append(
                    f"[{path}] Custom modification (kind='custom') must have 'mass_shift' field "
                    f"to specify the mass change in Daltons."
                )

            if not residues and not term_specificity:
                errors.append(
                    f"[{path}] Custom modification (kind='custom') must define 'residues' and/or 'term_specificity'."
                )

        terminal_residue_aliases = {'n-term', 'c-term', 'N-term', 'C-term'}
        if residues & terminal_residue_aliases:
            errors.append(
                f"[{path}.residues] Terminal modifications must use 'term_specificity' instead of residues "
                f"like N-term/C-term."
            )

        resolved_ontology_id, known_entry = _resolve_known_ontology_entry(modification)

        if (
            kind == 'ontology'
            and modification.get('name')
            and canonical_ontology_id in KNOWN_ONTOLOGY_MODIFICATIONS
        ):
            normalized_name = _normalize_modification_name_for_lookup(modification.get('name'))
            if normalized_name not in KNOWN_ONTOLOGY_MODIFICATIONS[canonical_ontology_id].get('names', set()):
                errors.append(
                    f"[{path}] Modification name '{modification.get('name')}' does not match known ontology entry "
                    f"'{canonical_ontology_id}'."
                )

        if kind == 'ontology' and known_entry:
            if residues and not residues.issubset(known_entry.get('residues', set())):
                errors.append(
                    f"[{path}.residues] {sorted(residues)} is not an allowed residue subset for "
                    f"{resolved_ontology_id or modification.get('name')}."
                )

            if term_specificity and term_specificity not in known_entry.get('term_specificities', {term_specificity}):
                errors.append(
                    f"[{path}.term_specificity] '{term_specificity}' is not an allowed specificity for "
                    f"{resolved_ontology_id or modification.get('name')}."
                )

            mass_shift = modification.get('mass_shift')
            if mass_shift is not None and known_entry.get('mass_shift') is not None:
                if abs(float(mass_shift) - float(known_entry['mass_shift'])) > MASS_SHIFT_TOLERANCE:
                    errors.append(
                        f"[{path}.mass_shift] {mass_shift} disagrees with the curated ontology value "
                        f"{known_entry['mass_shift']} for {resolved_ontology_id or modification.get('name')}."
                    )

            formula = modification.get('formula')
            if formula and known_entry.get('formula') and formula != known_entry['formula']:
                errors.append(
                    f"[{path}.formula] '{formula}' disagrees with the curated ontology value "
                    f"'{known_entry['formula']}' for {resolved_ontology_id or modification.get('name')}."
                )

    profile_ids = {
        modification.get('profile') or 'default'
        for _, modification in _iter_modifications(data)
    }
    reference_scopes = [('experiment', data.get('experiment', {}))]
    reference_scopes.extend((f"runs[{i}]", run) for i, run in enumerate(data.get('runs', []) or []))

    for path, scope in reference_scopes:
        ref_new = scope.get('modification_profile')
        ref_old = scope.get('custom_mod_profile')

        if ref_new and ref_old and ref_new != ref_old:
            errors.append(
                f"[{path}] modification_profile and custom_mod_profile must match when both are provided."
            )

        ref_value = ref_new or ref_old
        if ref_value and ref_value not in profile_ids:
            errors.append(f"[{path}] references unknown modification profile '{ref_value}'.")

        if path.startswith('runs[') and len(profile_ids) > 1 and not ref_value:
            errors.append(
                f"[{path}] must set modification_profile when multiple modification profiles are defined."
            )

    # Multiplex validation: TMT and SILAC channels
    if 'mixtures' in data:
        for i, mixture in enumerate(data['mixtures']):
            channels = mixture.get('channels', {})
            if channels:
                channel_names = set(channels.keys())

                # Detect TMT plex from channel names
                tmt_channels = {c for c in channel_names if c.startswith('TMT')}
                if tmt_channels:
                    errors.extend(_validate_tmt_channels(tmt_channels, i))

                # Detect iTRAQ labels from channel names
                itraq_channels = {c for c in channel_names if c.startswith('iTRAQ')}
                if itraq_channels:
                    errors.extend(_validate_itraq_channels(itraq_channels, i))

                # Detect SILAC labels from channel names
                # Match: explicit 'silac*' prefix, or light/medium/heavy (with optional compound suffixes)
                silac_channels = set()
                for c in channel_names:
                    if 'silac' in c.lower():
                        silac_channels.add(c)
                    elif any(c.lower().startswith(prefix) for prefix in ['light', 'medium', 'heavy', 'labeled', 'unlabeled']):
                        # Matches light_R0K0, light, heavy, medium_R6K4, etc.
                        silac_channels.add(c)
                if silac_channels:
                    errors.extend(_validate_silac_channels(silac_channels, i))

    return errors


def _validate_tmt_channels(channel_names: set, mixture_idx: int) -> list:
    """Validate TMT channel set for correctness."""
    errors = []

    # Valid TMT plexes and their channels
    valid_tmt_plexes = {
        'TMT2': {'TMT126', 'TMT127'},
        'TMT6': {'TMT126', 'TMT127N', 'TMT127C', 'TMT128N', 'TMT128C', 'TMT129'},
        'TMT10': {'TMT126', 'TMT127N', 'TMT127C', 'TMT128N', 'TMT128C',
                  'TMT129N', 'TMT129C', 'TMT130N', 'TMT130C', 'TMT131'},
        'TMT11': {'TMT126', 'TMT127N', 'TMT127C', 'TMT128N', 'TMT128C',
                  'TMT129N', 'TMT129C', 'TMT130N', 'TMT130C', 'TMT131N', 'TMT131C'},
        'TMT16': {'TMT126', 'TMT127N', 'TMT127C', 'TMT128N', 'TMT128C',
                  'TMT129N', 'TMT129C', 'TMT130N', 'TMT130C', 'TMT131N',
                  'TMT131C', 'TMT132N', 'TMT132C', 'TMT133N', 'TMT133C', 'TMT134N'},
        'TMT18': {'TMT126', 'TMT127N', 'TMT127C', 'TMT128N', 'TMT128C',
                  'TMT129N', 'TMT129C', 'TMT130N', 'TMT130C', 'TMT131N',
                  'TMT131C', 'TMT132N', 'TMT132C', 'TMT133N', 'TMT133C', 'TMT134N',
                  'TMT134C', 'TMT135N'},
    }

    # Check if channels form a valid subset
    valid_all_tmt = set()
    for channels_set in valid_tmt_plexes.values():
        valid_all_tmt.update(channels_set)

    invalid_channels = channel_names - valid_all_tmt
    if invalid_channels:
        errors.append(
            f"[mixtures[{mixture_idx}].channels] Invalid TMT channel names: {invalid_channels}. "
            f"Valid TMT channels: {sorted(valid_all_tmt)}"
        )

    return errors


def _validate_itraq_channels(channel_names: set, mixture_idx: int) -> list:
    """Validate iTRAQ channel set for correctness."""
    errors = []

    # Valid iTRAQ plexes and their channels
    valid_itraq_plexes = {
        'iTRAQ4': {'iTRAQ114', 'iTRAQ115', 'iTRAQ116', 'iTRAQ117'},
        'iTRAQ8': {'iTRAQ113', 'iTRAQ114', 'iTRAQ115', 'iTRAQ116',
                   'iTRAQ117', 'iTRAQ118', 'iTRAQ119', 'iTRAQ121'},
    }

    # Check if channels form a valid subset
    valid_all_itraq = set()
    for channels_set in valid_itraq_plexes.values():
        valid_all_itraq.update(channels_set)

    invalid_channels = channel_names - valid_all_itraq
    if invalid_channels:
        errors.append(
            f"[mixtures[{mixture_idx}].channels] Invalid iTRAQ channel names: {invalid_channels}. "
            f"Valid iTRAQ channels: {sorted(valid_all_itraq)}"
        )

    return errors


def _validate_silac_channels(channel_names: set, mixture_idx: int) -> list:
    """Validate SILAC label set for correctness."""
    errors = []

    # Valid SILAC channel name patterns (prefixes and full names)
    valid_silac_base_names = {
        'light', 'heavy', 'labeled', 'unlabeled',
        'medium', 'silac_light', 'silac_heavy', 'silac_medium'
    }

    # Validate label count: SILAC uses 2 or 3 channels
    if len(channel_names) < 2 or len(channel_names) > 3:
        errors.append(
            f"[mixtures[{mixture_idx}].channels] SILAC mixture has {len(channel_names)} channels; "
            f"SILAC typically uses 2 or 3 labels."
        )

    # Validate individual channel names match SILAC patterns
    for channel_name in channel_names:
        name_lower = channel_name.lower()
        is_valid = False

        # Must contain 'silac' or start with a valid base name
        if 'silac' in name_lower:
            is_valid = True
        else:
            # Check if it starts with a valid base name (allows suffixes like _R0K0)
            for base_name in valid_silac_base_names:
                if name_lower == base_name or name_lower.startswith(base_name + '_'):
                    is_valid = True
                    break

        if not is_valid:
            errors.append(
                f"[mixtures[{mixture_idx}].channels] Invalid SILAC label '{channel_name}'. "
                f"SILAC labels must contain 'silac' or start with {', '.join(sorted(valid_silac_base_names))} "
                f"(e.g., 'light', 'heavy', 'light_R0K0', 'medium_R6K4')."
            )

    return errors


# Dissociation Method Validation Tests
def test_valid_dissociation_method_hcd():
    """Test that HCD dissociation method is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: HCD

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid HCD dissociation method should pass: {errors}"
        print(f"✓ test_valid_dissociation_method_hcd passed")
    finally:
        yaml_path.unlink()


def test_valid_dissociation_method_etd():
    """Test that ETD dissociation method is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: ETD

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid ETD dissociation method should pass: {errors}"
        print(f"✓ test_valid_dissociation_method_etd passed")
    finally:
        yaml_path.unlink()


def test_invalid_dissociation_method():
    """Test that invalid dissociation method fails semantic validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: INVALID_DISSOCIATION

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Invalid dissociation method should fail"
        assert any("dissociation_method" in e and "not a recognized MS dissociation method" in e for e in errors), \
            f"Error should mention invalid dissociation method: {errors}"
        print(f"✓ test_invalid_dissociation_method passed")
    finally:
        yaml_path.unlink()


# Enzyme Validation Tests
def test_valid_enzyme_trypsin():
    """Test that Trypsin enzyme is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid Trypsin enzyme should pass: {errors}"
        print(f"✓ test_valid_enzyme_trypsin passed")
    finally:
        yaml_path.unlink()


def test_invalid_enzyme():
    """Test that invalid enzyme fails semantic validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: InvalidProteaseXYZ

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Invalid enzyme should fail"
        assert any("enzyme" in e and "not a recognized protease" in e for e in errors), \
            f"Error should mention invalid enzyme: {errors}"
        print(f"✓ test_invalid_enzyme passed")
    finally:
        yaml_path.unlink()


# TMT Plex Channel Validation Tests
def test_valid_tmt16_channels():
    """Test that valid TMT16 channel subset is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens
  - id: sample2
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1
      TMT127N: sample2
      TMT127C: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid TMT16 channel subset should pass: {errors}"
        print(f"✓ test_valid_tmt16_channels passed")
    finally:
        yaml_path.unlink()


def test_invalid_tmt_channel_name():
    """Test that invalid TMT channel name fails semantic validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT999: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Invalid TMT channel name should fail"
        assert any("Invalid TMT channel" in e for e in errors), \
            f"Error should mention invalid TMT channel: {errors}"
        print(f"✓ test_invalid_tmt_channel_name passed")
    finally:
        yaml_path.unlink()


# Modification Accession Validation Tests
def test_valid_modification_accession_unimod():
    """Test that UNIMOD accession format is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mode: variable
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid UNIMOD accession should pass: {errors}"
        print(f"✓ test_valid_modification_accession_unimod passed")
    finally:
        yaml_path.unlink()


def test_valid_modification_accession_mod():
    """Test that MOD accession format is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho
    kind: ontology
    name: "Phosphorylation"
    accession: "MOD:00696"
    residues: S
    mode: variable
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid MOD accession should pass: {errors}"
        print(f"✓ test_valid_modification_accession_mod passed")
    finally:
        yaml_path.unlink()


def test_invalid_modification_accession_format():
    """Test that invalid accession format fails semantic validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho
    name: "Phosphorylation"
    accession: "INVALID:12345"
    residues: S
    mode: variable
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Invalid accession format should fail"
        assert any(("accession" in e or "ontology_id" in e) and "does not match expected format" in e for e in errors), \
            f"Error should mention invalid accession format: {errors}"
        print(f"✓ test_invalid_modification_accession_format passed")
    finally:
        yaml_path.unlink()


# SILAC Multiplex Validation Tests
def test_valid_silac_two_plex():
    """Test that valid 2-plex SILAC channel set is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample_unlabeled
    organism: homo sapiens
  - id: sample_labeled
    organism: homo sapiens

mixtures:
  - id: silac_mix
    channels:
      light: sample_unlabeled
      heavy: sample_labeled

runs:
  - file: data.raw
    mixture: silac_mix
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid 2-plex SILAC should pass: {errors}"
        print(f"✓ test_valid_silac_two_plex passed")
    finally:
        yaml_path.unlink()


def test_valid_silac_three_plex():
    """Test that valid 3-plex SILAC channel set is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1_light
    organism: homo sapiens
  - id: sample1_medium
    organism: homo sapiens
  - id: sample1_heavy
    organism: homo sapiens

mixtures:
  - id: silac_3plex_mix
    channels:
      light_R0K0: sample1_light
      medium_R6K4: sample1_medium
      heavy_R10K8: sample1_heavy

runs:
  - file: data.raw
    mixture: silac_3plex_mix
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid 3-plex SILAC should pass: {errors}"
        print(f"✓ test_valid_silac_three_plex passed")
    finally:
        yaml_path.unlink()


def test_invalid_silac_single_label():
    """Test that single-label SILAC fails semantic validation (requires at least 2 labels)."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: silac_invalid
    channels:
      light: sample1

runs:
  - file: data.raw
    mixture: silac_invalid
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        # Single-label SILAC mixture should fail validation
        assert not is_valid, "Single-label SILAC should fail semantic validation"
        assert any("SILAC" in e and "2 or 3 labels" in e for e in errors), \
            f"Error should mention SILAC requires 2-3 labels: {errors}"
        print(f"✓ test_invalid_silac_single_label passed")
    finally:
        yaml_path.unlink()


# Label-Free Quantification (LFQ) Tests
def test_valid_lfq_without_mixtures():
    """Test that LFQ experiments work without mixtures section (label-free, no multiplexing)."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: HCD
  modifications:
    - kind: ontology
      ontology_id: "UNIMOD:4"
      name: "Carbamidomethyl"
      residues: C
      mode: fixed
    - kind: ontology
      ontology_id: "UNIMOD:35"
      name: "Oxidation"
      residues: M
      mode: variable
  precursor_mass_tolerance: "5 ppm"
  fragment_mass_tolerance: "0.02 Da"
  quantification_method: LFQ

samples:
  - id: sample_control_1
    organism: homo sapiens
    condition: control
    biological_replicate: 1
  - id: sample_treated_1
    organism: homo sapiens
    condition: treated
    biological_replicate: 1
  - id: sample_treated_2
    organism: homo sapiens
    condition: treated
    biological_replicate: 2

mixtures: []

runs:
  - file: s3://bucket/control_1.raw
    fraction: 1
    mixture: null
  - file: s3://bucket/treated_1.raw
    fraction: 1
    mixture: null
  - file: s3://bucket/treated_2.raw
    fraction: 1
    mixture: null
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid LFQ experiment should pass: {errors}"
        print(f"✓ test_valid_lfq_without_mixtures passed")
    finally:
        yaml_path.unlink()


# Technical Replicate Tests
def test_valid_sample_with_technical_replicate():
    """Test that technical_replicate field is accepted in samples."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1_bio_rep1_tech1
    organism: homo sapiens
    condition: control
    biological_replicate: 1
    technical_replicate: 1
  - id: sample1_bio_rep1_tech2
    organism: homo sapiens
    condition: control
    biological_replicate: 1
    technical_replicate: 2

mixtures:
  - id: mix1
    channels:
      TMT126: sample1_bio_rep1_tech1
      TMT127N: sample1_bio_rep1_tech2

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Sample with technical_replicate field should pass: {errors}"
        print(f"✓ test_valid_sample_with_technical_replicate passed")
    finally:
        yaml_path.unlink()


# Quantification Method Declaration Tests
def test_valid_explicit_quantification_method_lfq():
    """Test that explicit quantification_method LFQ declaration is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  quantification_method: LFQ

samples:
  - id: sample1
    organism: homo sapiens

mixtures: []

runs:
  - file: data.raw
    fraction: 1
    mixture: null
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Valid quantification_method LFQ should pass: {errors}"
        print(f"✓ test_valid_explicit_quantification_method_lfq passed")
    finally:
        yaml_path.unlink()


def test_valid_explicit_quantification_method_tmt():
    """Test that explicit quantification_method TMT declaration is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  quantification_method: TMT
  modifications:
    - kind: ontology
      name: "TMT16plex"
      residues: K
      mode: fixed
    - kind: ontology
      name: "TMT16plex"
      term_specificity: n-term
      mode: fixed

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_yaml_against_schema(yaml_path, schema_path)

        assert is_valid, f"Valid quantification_method TMT should pass: {errors}"
        print(f"✓ test_valid_explicit_quantification_method_tmt passed")
    finally:
        yaml_path.unlink()


# DIA Acquisition Method Tests
def test_valid_dia_fixture():
    """Test that the valid_dia.yml fixture (DIA LFQ) passes schema validation."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'valid_dia.yml'
    schema_path = get_schema_path()

    is_valid, errors = validate_with_custom_semantics(fixture_path, schema_path)

    if not is_valid:
        print(f"✗ DIA fixture validation failed: {fixture_path}")
        for error in errors:
            print(f"  {error}")
        assert False, f"DIA fixture should be valid: {errors}"

    print(f"✓ test_valid_dia_fixture passed")


def test_valid_custom_mods_fixture():
    """Test that the valid_custom_mods.yml fixture (custom modifications) passes schema validation."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'valid_custom_mods.yml'
    schema_path = get_schema_path()

    is_valid, errors = validate_with_custom_semantics(fixture_path, schema_path)

    if not is_valid:
        print(f"✗ Custom mods fixture validation failed: {fixture_path}")
        for error in errors:
            print(f"  {error}")
        assert False, f"Custom mods fixture should be valid: {errors}"

    print(f"✓ test_valid_custom_mods_fixture passed")


def test_valid_dia_acquisition_method():
    """Test that DIA acquisition method is accepted."""
    yaml_content = """experiment:
  acquisition_method: DIA
  enzyme: Trypsin
  dissociation_method: HCD
  quantification_method: LFQ
  modifications:
    - kind: ontology
      ontology_id: "UNIMOD:4"
      name: "Carbamidomethyl"
      residues: C
      mode: fixed
    - kind: ontology
      ontology_id: "UNIMOD:35"
      name: "Oxidation"
      residues: M
      mode: variable

samples:
  - id: sample1
    organism: homo sapiens
  - id: sample2
    organism: homo sapiens

mixtures: []

runs:
  - file: data1.raw
    fraction: 1
    mixture: null
  - file: data2.raw
    fraction: 1
    mixture: null
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid DIA acquisition method should pass: {errors}"
        print(f"✓ test_valid_dia_acquisition_method passed")
    finally:
        yaml_path.unlink()


# iTRAQ Multiplex Tests
def test_valid_itraq_fixture():
    """Test that the valid_itraq.yml fixture (iTRAQ 8-plex) passes schema validation."""
    fixture_path = Path(__file__).parent / 'fixtures' / 'valid_itraq.yml'
    schema_path = get_schema_path()

    is_valid, errors = validate_with_custom_semantics(fixture_path, schema_path)

    if not is_valid:
        print(f"✗ iTRAQ fixture validation failed: {fixture_path}")
        for error in errors:
            print(f"  {error}")
        assert False, f"iTRAQ fixture should be valid: {errors}"

    print(f"✓ test_valid_itraq_fixture passed")


def test_valid_itraq8_channels():
    """Test that valid iTRAQ8 channel subset is accepted."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: HCD
  quantification_method: iTRAQ
  modifications:
    - kind: ontology
      ontology_id: "UNIMOD:4"
      name: "Carbamidomethyl"
      residues: C
      mode: fixed
    - kind: ontology
      name: "iTRAQ8plex"
      residues: K
      mode: fixed
    - kind: ontology
      name: "iTRAQ8plex"
      term_specificity: n-term
      mode: fixed

samples:
  - id: sample1
    organism: homo sapiens
  - id: sample2
    organism: homo sapiens

mixtures:
  - id: itraq_mix1
    channels:
      iTRAQ113: sample1
      iTRAQ114: sample2
      iTRAQ115: sample1
      iTRAQ116: sample2

runs:
  - file: data.raw
    mixture: itraq_mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Valid iTRAQ8 channel subset should pass: {errors}"
        print(f"✓ test_valid_itraq8_channels passed")
    finally:
        yaml_path.unlink()


def test_invalid_itraq_channel_name():
    """Test that invalid iTRAQ channel name fails semantic validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  quantification_method: iTRAQ

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: itraq_mix1
    channels:
      iTRAQ999: sample1

runs:
  - file: data.raw
    mixture: itraq_mix1
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Invalid iTRAQ channel name should fail"
        assert any("Invalid iTRAQ channel" in e for e in errors), \
            f"Error should mention invalid iTRAQ channel: {errors}"
        print(f"✓ test_invalid_itraq_channel_name passed")
    finally:
        yaml_path.unlink()


# ============================================================================
# Custom Modification Validation Tests (Phase 2 Requirements)
# ============================================================================
# These tests enforce the strict requirements for custom modifications:
# Custom modifications (kind='custom') must include:
# - id, kind, name, mode, residues, mass_shift
# - term_specificity, formula, and root-level engine blocks are optional

def test_custom_mod_missing_name():
    """Test that custom modification without 'name' field fails validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: custom_without_name
    kind: custom
    residues: K
    mode: fixed
    mass_shift: 150.5
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Custom modification without 'name' should fail"
        assert any("Custom modification" in e and "name" in e for e in errors), \
            f"Error should mention custom mod requires 'name': {errors}"
        print(f"✓ test_custom_mod_missing_name passed")
    finally:
        yaml_path.unlink()


def test_custom_mod_missing_mass_shift():
    """Test that custom modification without 'mass_shift' field fails validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: custom_without_mass
    kind: custom
    name: "Custom Label"
    residues: K
    mode: fixed
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Custom modification without 'mass_shift' should fail"
        assert any("Custom modification" in e and "mass_shift" in e for e in errors), \
            f"Error should mention custom mod requires 'mass_shift': {errors}"
        print(f"✓ test_custom_mod_missing_mass_shift passed")
    finally:
        yaml_path.unlink()


def test_custom_mod_complete_required_fields():
    """Test that custom modification with all required fields passes validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: custom_complete
    kind: custom
    name: "Custom Crosslinker"
    residues: K
    mode: fixed
    mass_shift: 138.068
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Custom modification with required fields should pass: {errors}"
        print(f"✓ test_custom_mod_complete_required_fields passed")
    finally:
        yaml_path.unlink()


def test_custom_mod_with_optional_formula():
    """Test that custom modification can include optional 'formula' field."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: custom_with_formula
    kind: custom
    name: "Custom Label with Formula"
    residues: K
    mode: fixed
    mass_shift: 150.5
    formula: "C6H12N2O"
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Custom modification with optional formula should pass: {errors}"
        print(f"✓ test_custom_mod_with_optional_formula passed")
    finally:
        yaml_path.unlink()


def test_custom_mod_with_engine_blocks():
    """Test that custom modification can include optional flat tool-specific fields."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: custom_with_engines
    kind: custom
    name: "Custom with Engine Blocks"
    residues: K
    mode: fixed
    mass_shift: 138.068
    term_specificity: none
    binary_group: 1
    localize_mass_shift: true
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Custom modification with engine blocks should pass: {errors}"
        print(f"✓ test_custom_mod_with_engine_blocks passed")
    finally:
        yaml_path.unlink()


# ============================================================================
# Ontology Modification Validation Tests (Phase 2 Requirements)
# ============================================================================
# These tests enforce the strict requirements for ontology modifications:
# Ontology modifications (kind='ontology') must include:
# - id, kind, mode
# - at least one of (ontology_id | accession | name)
# - residues / term_specificity are optional dataset-level constraints
# - NO requirement for mass_shift or formula (chemical shift is provided by ontology)
# - optional root-level engine blocks

def test_ontology_mod_without_mass_shift():
    """Test that ontology modification without mass_shift still passes (mass is from ontology)."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho_no_mass
    kind: ontology
    name: "Phosphorylation"
    accession: "UNIMOD:21"
    residues: S
    mode: variable
    term_specificity: none
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Ontology modification without mass_shift should pass: {errors}"
        print(f"✓ test_ontology_mod_without_mass_shift passed")
    finally:
        yaml_path.unlink()


def test_ontology_mod_without_formula():
    """Test that ontology modification without formula still passes (formula is from ontology)."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: acetyl_no_formula
    kind: ontology
    name: "Acetylation"
    accession: "UNIMOD:1"
    mode: variable
    term_specificity: protein-n-term
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Ontology modification without formula should pass: {errors}"
        print(f"✓ test_ontology_mod_without_formula passed")
    finally:
        yaml_path.unlink()


def test_modifications_missing_residues():
    """Test that custom modifications without residues fail semantic validation."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: phospho_no_residues
    kind: custom
    name: "Custom Label"
    mode: variable
    mass_shift: 100.0
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert not is_valid, "Custom modification without 'residues' should fail semantic validation"
        assert any("must define 'residues'" in e for e in errors), \
            f"Error should mention custom residue requirement: {errors}"
        print(f"✓ test_modifications_missing_residues passed")
    finally:
        yaml_path.unlink()


def test_modifications_without_term_specificity_are_allowed():
    """Test that term_specificity is optional and defaults semantically to no extra restriction."""
    yaml_content = """experiment:
  acquisition_method: DDA
  enzyme: Trypsin

samples:
  - id: sample1
    organism: homo sapiens

mixtures:
  - id: mix1
    channels:
      TMT126: sample1

runs:
  - file: data.raw
    mixture: mix1

mod_profiles:
  - id: custom_no_term_specificity
    kind: custom
    name: "Custom Mod"
    residues: K
    mode: fixed
    mass_shift: 100.0
"""

    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        yaml_path = Path(f.name)

    try:
        schema_path = get_schema_path()
        is_valid, errors = validate_with_custom_semantics(yaml_path, schema_path)

        assert is_valid, f"Modification without 'term_specificity' should pass: {errors}"
        print(f"✓ test_modifications_without_term_specificity_are_allowed passed")
    finally:
        yaml_path.unlink()


# ============================================================================
# CLI execution
# ============================================================================

if __name__ == '__main__':
    print("Running YAML contract validation tests for the quantms YAML schema")
    print(f"Schema location: {get_schema_path()}\n")

    tests = [
        test_valid_fixture,
        test_valid_lfq_fixture,
        test_valid_silac_fixture,
        test_valid_without_mod_profiles,
        test_missing_required_section_samples,
        test_invalid_modification_collection_wrong_type,
        test_multiple_profiles_require_run_profile,
        test_additional_metadata_overlap_is_rejected,
        test_mod_profile_with_root_level_engine_fields,
        test_ontology_mod_accession_only,
        test_ontology_mod_name_only,
        test_custom_modification_shape,
        test_missing_required_mode_field,
        test_invalid_mode_value,
        test_invalid_term_specificity_value,
        test_valid_term_specificity_values,
        test_ontology_mod_without_accession_or_name,
        test_experiment_level_modifications_use_shared_structure,
        test_known_ontology_mod_rejects_invalid_residue_subset,
        test_known_ontology_mod_rejects_incorrect_mass_shift,
        test_terminal_modification_must_use_term_specificity,
        test_invalid_experiment_wrong_method,
        # Dissociation and Enzyme validation tests
        test_valid_dissociation_method_hcd,
        test_valid_dissociation_method_etd,
        test_invalid_dissociation_method,
        test_valid_enzyme_trypsin,
        test_invalid_enzyme,
        # TMT validation tests
        test_valid_tmt16_channels,
        test_invalid_tmt_channel_name,
        # Modification accession validation tests
        test_valid_modification_accession_unimod,
        test_valid_modification_accession_mod,
        test_invalid_modification_accession_format,
        # SILAC validation tests
        test_valid_silac_two_plex,
        test_valid_silac_three_plex,
        test_invalid_silac_single_label,
        # LFQ tests
        test_valid_lfq_without_mixtures,
        # Technical replicate tests
        test_valid_sample_with_technical_replicate,
        # Quantification method tests
        test_valid_explicit_quantification_method_lfq,
        test_valid_explicit_quantification_method_tmt,
        # DIA acquisition tests
        test_valid_dia_fixture,
        test_valid_dia_acquisition_method,
        # Custom modifications fixture test
        test_valid_custom_mods_fixture,
        # iTRAQ multiplex tests
        test_valid_itraq_fixture,
        test_valid_itraq8_channels,
        test_invalid_itraq_channel_name,
        # Custom modification validation tests (Phase 2)
        test_custom_mod_missing_name,
        test_custom_mod_missing_mass_shift,
        test_custom_mod_complete_required_fields,
        test_custom_mod_with_optional_formula,
        test_custom_mod_with_engine_blocks,
        # Ontology modification validation tests (Phase 2)
        test_ontology_mod_without_mass_shift,
        test_ontology_mod_without_formula,
        test_modifications_missing_residues,
        test_modifications_without_term_specificity_are_allowed,
    ]

    failed = []

    for test_func in tests:
        try:
            test_func()
        except AssertionError as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            failed.append(test_func.__name__)
        except Exception as e:
            print(f"✗ {test_func.__name__} error: {e}")
            import traceback
            traceback.print_exc()
            failed.append(test_func.__name__)

    print()
    if failed:
        print(f"✗ {len(failed)} test(s) failed: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"✓ All {len(tests)} tests passed!")
        sys.exit(0)
