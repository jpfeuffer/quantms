## Plan: Replace SDRF With quantms YAML

Replace SDRF with a quantms-native YAML contract in `.yml` format, centered on explicit `samples`, `mixtures`, `prefractionation_runs`, and `mod_profiles`, then generate the two runtime artifacts the pipeline actually needs: the execution config table and the OpenMS experimental design table. This keeps downstream analysis stable while moving metadata authoring to a cleaner, ontology-aware model and adds a guided Python GUI for stepwise file creation.

**Implementation Roadmap**

The following milestones describe the sequential path from domain model freeze to full YAML-native workflow:

1. **Freeze The YAML Domain Model**
    - **Objective:** Define the canonical quantms YAML structure and semantics, including overrides and modification profiles.
    - **Files/Functions to Modify/Create:** `nextflow_schema.json`, `nextflow.config`, `README.md`, `docs/usage.md`
    - **Tests to Write:** input-mode validation tests for `.yml` input, required-section tests, override precedence tests
    - **Steps:**
        1. Write failing validation cases for the new top-level sections: `samples`, `mixtures`, `runs`, and `mod_profiles`.
        2. Define precedence rules for experiment-level defaults, run-level overrides, mixture-level semantics, and `mod_profile`.
        3. Document the YAML contract and start deprecating SDRF as the primary input model.
    - **Example:**
```yaml
experiment:
  acquisition_method: DDA
  enzyme: Trypsin
  fixed_mods:
    - "Carbamidomethyl (C)"
    - "TMT16plex (K)"
    - "TMT16plex (N-term)"
  variable_mods: ["Oxidation (M)"]
  dissociation_method: HCD
  precursor_mass_tolerance: "10 ppm"
  fragment_mass_tolerance: "0.02 Da"

samples:
  - id: treated_rep1
    organism: homo sapiens
    organism_part: cell line
    condition: treated
    biological_replicate: 1
  - id: control_rep1
    organism: homo sapiens
    organism_part: cell line
    condition: control
    biological_replicate: 1
  # ... one entry per unique biological sample

mixtures:
  - id: mix_A
    channels:
      TMT126:  treated_rep1
      TMT127N: treated_rep2
      TMT127C: control_rep1
      TMT128N: control_rep2
      # ... up to plex capacity
  - id: mix_B
    channels:
      TMT126:  treated_rep3
      TMT127N: control_rep3

runs:
  - file: s3://bucket/mix_A_F1.raw
    fraction: 1
    mixture: mix_A
  - file: s3://bucket/mix_A_F2.raw
    fraction: 2
    mixture: mix_A
  - file: s3://bucket/mix_B_F1.raw
    fraction: 1
    mixture: mix_B
```

2. **Add A Typed YAML Schema With Ontology And Enum Constraints**
    - **Objective:** Create a machine-validated schema for the YAML input, including controlled vocabularies, enums, and structured multiplex rules.
    - **Files/Functions to Modify/Create:** new YAML schema assets under the repo, `nextflow_schema.json` if used as entrypoint wiring, docs
    - **Tests to Write:** schema validation tests for required ontologies, allowed acquisition methods, allowed plex names, valid channel sets per plex, SILAC label validation
    - **Steps:**
        1. Write failing schema tests for known-good and known-bad YAML examples.
        2. Encode enums for acquisition methods, plex names, dissociation methods, and other closed sets.
        3. Encode channel constraints so a declared plex determines the valid label namespace and allowed channel identifiers.

3. **Add A Python GUI With uv-Managed Dependencies**
    - **Objective:** Provide a top-level Python GUI that guides users step by step through creating the YAML input.
    - **Files/Functions to Modify/Create:** new Python app with dependency manifest in the scripts header using uv
    - **Tests to Write:** unit tests for manifest serialization, validation feedback, multiplex channel builder behavior, mod-profile editor behavior
    - **Steps:**
        1. Write failing tests for YAML generation from GUI state.
        2. Build a stepwise GUI covering samples, mixtures, runs, and modification profiles.
        3. Hook the GUI to the schema validator so users get immediate ontology, enum, and channel validation feedback.

4. **Build The YAML-To-Runtime Normalizer**
    - **Objective:** Replace SDRF parsing with a native normalizer that emits the exact runtime tables quantms needs.
    - **Files/Functions to Modify/Create:** `modules/local/samplesheet_check/main.nf`, `modules/local/sdrf_parsing/main.nf`, new parser or normalizer under `modules/local` or `bin`
    - **Tests to Write:** LFQ normalization tests, TMT normalization tests, SILAC normalization tests, DIA normalization tests, `mod_profile` resolution tests
    - **Steps:**
        1. Write failing tests that compare normalized runtime outputs against expected config and OpenMS design tables.
        2. Implement parsing of `samples`, `mixtures`, `prefractionation_runs`, and `mod_profiles`.
        3. Generate the execution config table and OpenMS design table directly, with implicit fraction-group derivation where valid.

5. **Rewire quantms To Consume YAML Natively**
    - **Objective:** Make YAML the live ingest contract while preserving downstream workflow behavior.
    - **Files/Functions to Modify/Create:** `subworkflows/local/input_check/main.nf`, `subworkflows/local/create_input_channel/main.nf`, `workflows/quantms.nf`
    - **Tests to Write:** workflow routing regressions for LFQ, TMT, SILAC, DIA, and identification-only modes
    - **Steps:**
        1. Write failing workflow tests for YAML-driven execution in all supported modes.
        2. Preserve current behavior for file resolution, acquisition detection, label routing, duplicate-file checks, and modification precedence.
        3. Remove SDRF-specific logic from the hot path while keeping any temporary compatibility shim isolated.

6. **Remove SDRF From The Public Contract**
    - **Objective:** Complete the migration in docs, outputs, and tests.
    - **Files/Functions to Modify/Create:** `docs/output.md`, `conf/modules/shared.config`, `conf/modules/verbose_modules.config`, `tests/default.nf.test`, `conf/tests`, `CHANGELOG.md`
    - **Tests to Write:** snapshot updates and YAML-native CI profiles
    - **Steps:**
        1. Rename the published metadata area away from SDRF naming.
        2. Replace SDRF-based test fixtures with YAML fixtures.
        3. Document the deprecation and removal path clearly.

**Open Questions**
1. Should YAML schema validation be implemented purely inside quantms, or should it be factored so parts can later be reused outside the pipeline?
2. Should the first GUI target be a desktop app, a local web app, or a terminal UI if we want the smallest maintenance surface?
3. Should backward compatibility with SDRF exist only as a short transition layer, or remain as an optional import path for several releases?
4. Should future non-isobaric label systems beyond SILAC also reuse `mixtures.channels`, or should that abstraction be revisited when the first counterexample appears?
