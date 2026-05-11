# quantms YAML Schema Contract

## Overview

The quantms YAML manifest defines a machine-validated schema for proteomics experiments with structured metadata, controlled vocabularies, and multiplex constraints.

**Current Status:** The schema is stable and validated. Contract validation tests are comprehensive. Pipeline runtime integration for YAML consumption is not yet implemented.

## Schema Features

### 1. Controlled Vocabularies and Enums

The following fields now enforce **controlled vocabularies** via machine validation:

#### Experiment Settings

| Field                 | Valid Values                                                                            | CV Source                   | Validation            |
| --------------------- | --------------------------------------------------------------------------------------- | --------------------------- | --------------------- |
| `acquisition_method`  | DDA, DIA                                                                                | quantms_acquisition_methods | Schema enum + runtime |
| `enzyme`              | Trypsin, Chymotrypsin, Pepsin, Elastase, LysC, Asp-N, Glu-C, Arg-C, None, Whole protein | PSI-MS (MS:1001045)         | Runtime validation    |
| `dissociation_method` | HCD, CID, ETD, PSD, ECD, IRMPD, PQD, UVPD, SID, NETD, SURMAC, CX                        | PSI-MS (MS:1000044)         | Runtime validation    |

#### Valid Dissociation Methods

- **HCD**: Higher-energy C-trap dissociation (Orbitrap instruments)
- **CID**: Collision-induced dissociation (common on Q-TOF, ion traps)
- **ETD**: Electron-transfer dissociation (Orbitrap, Ion trap)
- **ECD**: Electron-capture dissociation
- **PSD**: Post-source decay (MALDI instruments)
- **PQD**: Pulsed q dissociation (Orbitrap)
- **IRMPD**: Infrared multi-photon dissociation
- **UVPD**: Ultraviolet photodissociation
- **SID**: Surface-induced dissociation
- **NETD**: Negative electron transfer dissociation
- **SURMAC**: Supplemental Ultra-Rapid, Multi-stage Activation with Collision
- **CX**: Chemical cross-linking dissociation

### 2. Ontology-Aware Sample Metadata

Sample metadata fields can reference external ontologies. Machine validation documents expected CV sources:

| Field           | Ontology/CV             | Expected Format        | Example                            |
| --------------- | ----------------------- | ---------------------- | ---------------------------------- |
| `organism`      | NCBI Taxonomy           | lowercase names        | "homo sapiens", "mus musculus"     |
| `organism_part` | UBERON (Uberon anatomy) | tissue/organ names     | "liver", "brain", "hippocampus"    |
| `disease`       | DOID (Disease Ontology) | disease terms          | "lung cancer", "diabetes mellitus" |
| `cell_type`     | CL (Cell Ontology)      | cell type terms        | "HeLa", "neuron", "T cell"         |
| `instrument`    | PSI-MS (MS:1000031)     | instrument model names | "Q Exactive HF", "Orbitrap Fusion" |

**Note on Ontology Validation:** The schema annotations document the expected ontologies. Full online lookup is **not** implemented. Expected ontology values are curated locally for validation. See the section on "Validation Scope" below.

### 3. Modification Model

The canonical modification collection is the top-level `modifications` array. Each entry defines one ontology-backed or custom modification and may optionally belong to a named `profile`. Deprecated aliases (`experiment.modifications`, `mod_profiles`, `accession`, `term_spec`) are still recognized by the validator but are no longer the preferred contract.

#### Modification Types: Ontology-backed vs Custom

```yaml
modifications:
  # Ontology-backed: minimal specification can be name only
  - kind: ontology
    name: "Phosphorylation"
    mode: variable

  # Ontology-backed: ontology_id only is also valid
  - kind: ontology
    ontology_id: "UNIMOD:4"
    mode: fixed

  # Dataset-specific subset of ontology-allowed residues / specificity
  - kind: ontology
    profile: phospho_enriched
    ontology_id: "UNIMOD:21"
    residues: [S, T, Y]
    mode: variable
    binary_group: 1

  # Custom modification
  - id: custom_linker
    kind: custom
    name: "My Custom Label"
    residues: K
    mode: fixed
    mass_shift: 150.5
    min_occurrences: 0
    max_occurrences: 5
```

#### Modification Fields

| Field                                                          | Type               | Required    | Description                                                                                                                                                                          |
| -------------------------------------------------------------- | ------------------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `id`                                                           | string             | No          | Optional identifier for one modification entry                                                                                                                                       |
| `profile`                                                      | string             | No          | Optional profile name grouping modifications into alternative search settings                                                                                                        |
| `kind`                                                         | enum               | No          | `ontology` or `custom` (defaults semantically to ontology)                                                                                                                           |
| `name`                                                         | string             | Conditional | Human-readable modification name. Required for custom, optional for ontology if `ontology_id` is provided                                                                            |
| `ontology_id`                                                  | string             | Conditional | Preferred ontology identifier (`UNIMOD:\d+` or `MOD:\d+`). For ontology modifications, either `ontology_id` or `name` is required                                                    |
| `accession`                                                    | string             | Conditional | Deprecated alias for `ontology_id`                                                                                                                                                   |
| `residues`                                                     | string or string[] | Conditional | Dataset-specific subset of allowed amino-acid residues. Do **not** encode N-term/C-term here; use `term_specificity` instead so terminal modifications stay semantically unambiguous |
| `mode`                                                         | enum               | **Yes**     | `fixed` or `variable`                                                                                                                                                                |
| `mass_shift`                                                   | number             | Conditional | Required for custom. Optional for ontology-backed modifications, but validated against curated ontology values when known                                                            |
| `formula`                                                      | string             | No          | Optional formula; ontology-backed values are cross-checked when curated locally                                                                                                      |
| `term_specificity`                                             | enum               | No          | Optional dataset-specific specificity restriction: `none`, `n-term`, `c-term`, `protein-n-term`, `protein-c-term`                                                                    |
| `term_spec`                                                    | enum               | No          | Deprecated alias for `term_specificity`                                                                                                                                              |
| `binary_group`                                                 | integer            | No          | Optional Comet binary group number                                                                                                                                                   |
| `min_occurrences` / `max_occurrences`                          | integer            | No          | Optional minimum / maximum occurrence constraints                                                                                                                                    |
| `distance_from_terminus`                                       | integer            | No          | Optional Comet-style distance constraint relative to the chosen terminus                                                                                                             |
| `localize_mass_shift` / `label_mass_shift` / `custom_mod_code` | mixed              | No          | Optional flat tool-specific annotations kept directly on the modification object                                                                                                     |

#### Supported Ontology Identifier Formats

- **UNIMOD**: `UNIMOD:<number>` — UniMod database (https://www.unimod.org/)
- **MOD**: `MOD:<number>` — PSI-MOD ontology (https://www.ebi.ac.uk/ols/ontologies/mod)
- `accession` is accepted as a deprecated alias, but `ontology_id` is preferred in new manifests

#### Engine-Specific Parameters (Root-Level)

Optional tool-specific parameters are kept as flat optional fields on each modification entry:

```yaml
modifications:
  - kind: ontology
    ontology_id: "UNIMOD:21"
    residues: [S, T, Y]
    mode: variable

    binary_group: 1
    min_occurrences: 0
    max_occurrences: 3
    distance_from_terminus: -1
    localize_mass_shift: true
    label_mass_shift: 79.9663
    custom_mod_code: "*"
```

### 4. Multiplex Channel Validation

Multiplex experiments are now validated for correct channel sets per plex type:

#### TMT 16-plex Example

```yaml
mixtures:
  - id: batch1
    channels:
      TMT126: treated_rep1
      TMT127N: treated_rep2
      TMT127C: control_rep1
      TMT128N: control_rep2
      # ... up to TMT134N
```

**Valid TMT Plexes and Their Channels:**

| Plex  | Channels                                           | Count |
| ----- | -------------------------------------------------- | ----- |
| TMT2  | TMT126, TMT127                                     | 2     |
| TMT6  | TMT126, TMT127N, TMT127C, TMT128N, TMT128C, TMT129 | 6     |
| TMT10 | TMT126–TMT131 (10 channels)                        | 10    |
| TMT11 | TMT126–TMT131C (11 channels)                       | 11    |
| TMT16 | TMT126–TMT134N (16 channels)                       | 16    |
| TMT18 | TMT126–TMT135N (18 channels)                       | 18    |

**Channel Validation Rule:** All channel names must be valid TMT identifiers. The validator checks for:

- Correct prefix (TMT followed by numbers and optional suffix like N, C)
- Membership in at least one known TMT plex
- No invalid custom channel names like `TMT999`

#### SILAC Example

```yaml
mixtures:
  - id: silac_2plex
    channels:
      light: sample_unlabeled
      heavy: sample_labeled

  - id: silac_3plex
    channels:
      light_R0K0: sample_light
      medium_R6K4: sample_medium
      heavy_R10K8: sample_heavy
```

**Valid SILAC Configurations:**

- **2-plex**: light/heavy, light/labeled, unlabeled/labeled (2 channels)
- **3-plex**: light/medium/heavy or with SILAC isotope codes (3 channels)

**Channel Validation Rule:** SILAC mixtures must have exactly 2 or 3 channels. Custom channel names are allowed (e.g., `silac_light`, `light_R0K0`).

## Validation Implementation

### Schema-Level Validation (JSON Schema)

The `assets/schemas/quantms_yaml_manifest.json` enforces:

- **Required sections** and field types
- **Enum constraints** for closed sets (acquisition_method, terminus_scope)
- **Pattern constraints** for tolerances and formats
- **Nested structures** for modifications and engine-specific fields
- **Schema annotations** documenting expected CV/ontology via `x-ontology`, `x-controlled-vocabulary`, `x-cv-source` fields

### Runtime Semantic Validation

The test suite (`tests/yaml_contract/test_yaml_input_contract.py`) implements custom semantic validation:

```python
def validate_with_custom_semantics(yaml_path: Path, schema_path: Path) -> tuple:
    """
    Validate YAML against schema + custom semantic constraints.
    Returns (is_valid: bool, errors: list[str])
    """
```

**Current Validations:**

1. **Dissociation Method**: Must be in `{HCD, CID, ETD, PSD, ECD, IRMPD, PQD, UVPD, SID, NETD, SURMAC, CX}`
2. **Enzyme**: Must be in known protease set
3. **Modification Accessions**: Must match `UNIMOD:\d+` or `MOD:\d+` format
4. **TMT Channels**: Must be valid TMT identifiers from known plexes
5. **SILAC Channels**: Must have 2–3 labels (custom names allowed)

### Validation Scope and Limitations

**What IS currently validated:**

- ✅ JSON schema structural constraints (types, required fields, enums)
- ✅ Canonical top-level `modifications` collection with deprecated alias support
- ✅ Modification type discrimination (kind: ontology|custom)
- ✅ Modification mode requirement (fixed|variable — no longer separate booleans)
- ✅ Modification profile grouping via the optional `profile` field, including run-level profile selection when multiple profiles exist
- ✅ Ontology-backed modifications: at least one of `ontology_id` / deprecated `accession` / `name` must be present
- ✅ Ontology identifier format (`UNIMOD:\d+` / `MOD:\d+`)
- ✅ Ontology-backed residue subset, specificity, and optional correction fields (`mass_shift`, `formula`) against curated local ontology values when known
- ✅ Terminus specificity values (`term_specificity`: none|n-term|c-term|protein-n-term|protein-c-term)
- ✅ Rejection of terminal residue aliases like `N-term` / `C-term`
- ✅ Flat optional tool-specific fields such as `binary_group`
- ✅ Sample metadata overlap checks for `additional_metadata`
- ✅ Modification profile references from runs
- ✅ Dissociation method names (against known MS methods)
- ✅ Enzyme names (against known proteases)
- ✅ TMT channel names and membership in known plexes
- ✅ SILAC channel counts (2–3 labels)

**What is NOT currently validated (deferred for runtime implementation):**

- ❌ Online ontology lookups for organism, disease, cell_type (would require network access)
- ❌ Instrument model validation against PSI-MS instrument CV (documented but not enforced)
- ❌ Cross-references (e.g., sample IDs in channels match declared samples)
- ❌ Numeric accession validation (e.g., checking that UNIMOD:21 actually exists in UniMod)
- ❌ Sample-to-mixture consistency
- ❌ File path validation or existence checks
- ❌ Full SDRF-to-YAML runtime normalization
- ❌ Semantic validation of all tool-specific parameter meanings

**Documentation Note:** The schema includes `x-ontology` and `x-cv-source` annotations to guide future full validation. These are informational reference metadata.

## Example YAML with Contract Features

```yaml
experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  dissociation_method: HCD
  precursor_mass_tolerance: "10 ppm"
  fragment_mass_tolerance: "0.02 Da"

samples:
  - id: HeLa_treated_rep1
    organism: homo sapiens # NCBI Taxonomy
    organism_part: cell line # UBERON
    cell_type: HeLa # CL Ontology
    condition: treated
    biological_replicate: 1
    characteristics:
      passage: 10

  - id: HeLa_control_rep1
    organism: homo sapiens
    organism_part: cell line
    cell_type: HeLa
    condition: control
    biological_replicate: 1
    characteristics:
      passage: 10

mixtures:
  - id: batch_A
    channels:
      TMT126: HeLa_treated_rep1
      TMT127N: HeLa_control_rep1

runs:
  - file: s3://bucket/batch_A_F1.raw
    fraction: 1
    mixture: batch_A
    instrument: Q Exactive HF # PSI-MS instrument
    modification_profile: phospho_enriched

modifications:
  - profile: phospho_enriched
    id: phospho_sty
    kind: ontology
    name: "Phosphorylation"
    ontology_id: "UNIMOD:21" # Valid UNIMOD format
    residues: [S, T, Y]
    mode: variable # Required: fixed|variable
    binary_group: 1
    min_occurrences: 0
    max_occurrences: 3

  - profile: phospho_enriched
    id: carbamidomethyl
    kind: ontology
    ontology_id: "UNIMOD:4"
    residues: C
    mode: fixed

  - profile: phospho_enriched
    id: custom_label
    kind: custom
    name: "Custom Labeling"
    residues: K
    mode: fixed
    mass_shift: 138.068
```

## Testing the Schema

Run the test suite to validate your YAML files:

```bash
# Install uv if not present
pip install uv

# Run all tests
uv run tests/yaml_contract/test_yaml_input_contract.py

# Expected output:
# ✓ All 39 tests passed!
```

### Test Coverage

| Test                                         | Feature                     | Status |
| -------------------------------------------- | --------------------------- | ------ |
| `test_valid_fixture`                         | TMT 16-plex fixture         | ✓ Pass |
| `test_valid_dissociation_method_hcd`         | HCD dissociation            | ✓ Pass |
| `test_valid_dissociation_method_etd`         | ETD dissociation            | ✓ Pass |
| `test_invalid_dissociation_method`           | Invalid dissociation        | ✓ Pass |
| `test_valid_enzyme_trypsin`                  | Trypsin enzyme              | ✓ Pass |
| `test_invalid_enzyme`                        | Invalid enzyme              | ✓ Pass |
| `test_valid_tmt16_channels`                  | TMT16 channels              | ✓ Pass |
| `test_invalid_tmt_channel_name`              | Invalid TMT channel         | ✓ Pass |
| `test_valid_modification_accession_unimod`   | UNIMOD / ontology_id format | ✓ Pass |
| `test_valid_modification_accession_mod`      | MOD / ontology_id format    | ✓ Pass |
| `test_invalid_modification_accession_format` | Invalid ontology identifier | ✓ Pass |
| `test_valid_silac_two_plex`                  | SILAC 2-plex                | ✓ Pass |
| `test_valid_silac_three_plex`                | SILAC 3-plex                | ✓ Pass |

## Future Roadmap

The following enhancements are planned:

- **GUI Validator** — Add interactive UI for YAML creation with real-time validation feedback
- **Runtime Normalizer** — Parse validated YAML into quantms runtime config and OpenMS experimental design tables
- **YAML-Native Workflow** — Consume YAML directly in `quantms.nf` and replace SDRF parser with YAML normalizer
- **SDRF Deprecation** — YAML becomes the primary input format; SDRF becomes deprecated in docs and public API

## References

- **JSON Schema**: `assets/schemas/quantms_yaml_manifest.json`
- **Tests**: `tests/yaml_contract/test_yaml_input_contract.py`
- **Fixtures**: `tests/yaml_contract/fixtures/`

### External References

- **UniMod**: https://www.unimod.org/
- **PSI Modification Ontology (MOD)**: https://www.ebi.ac.uk/ols/ontologies/mod
- **PSI-MS Ontology**: https://www.ebi.ac.uk/ols/ontologies/ms
- **NCBI Taxonomy**: https://www.ncbi.nlm.nih.gov/taxonomy
- **UBERON (Anatomy Ontology)**: https://www.ebi.ac.uk/ols/ontologies/uberon
- **Cell Ontology (CL)**: https://www.ebi.ac.uk/ols/ontologies/cl
- **Disease Ontology (DOID)**: https://disease-ontology.org/
