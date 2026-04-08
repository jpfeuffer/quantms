## Phase 2 Complete: Add Typed YAML Schema With Ontology And Enum Constraints

The quantms YAML contract now has typed schema coverage plus semantic validation for LFQ, TMT, iTRAQ, SILAC, and DIA manifests, with ontology and CV annotations applied across the manifest where practical. The modification model was also reworked into explicit ontology-backed and custom entries with a required mode enum, shared term specificity, and root-level engine blocks; the contract suite now passes 39 tests while runtime YAML support remains clearly deferred.

**Files created/changed:**
- assets/schemas/quantms_yaml_manifest.json
- tests/yaml_contract/test_yaml_input_contract.py
- tests/yaml_contract/fixtures/valid_tmtplex.yml
- tests/yaml_contract/fixtures/valid_lfq.yml
- tests/yaml_contract/fixtures/valid_silac.yml
- tests/yaml_contract/fixtures/valid_dia.yml
- tests/yaml_contract/fixtures/valid_itraq.yml
- docs/yaml_schema.md
- docs/usage.md
- README.md
- nextflow.config
- nextflow_schema.json
- plans/replace-sdrf-with-quantms-yaml-plan.md

**Functions created/changed:**
- validate_with_custom_semantics
- _validate_semantic_constraints
- _validate_tmt_channels
- _validate_itraq_channels
- _validate_silac_channels
- test_valid_lfq_fixture
- test_valid_silac_fixture
- test_valid_dia_fixture
- test_valid_dia_acquisition_method
- test_valid_itraq_fixture
- test_valid_itraq8_channels
- test_invalid_itraq_channel_name
- test_mod_profile_with_root_level_engine_fields
- test_ontology_mod_accession_only
- test_ontology_mod_name_only
- test_custom_modification_shape
- test_missing_required_mode_field
- test_invalid_mode_value
- test_invalid_term_spec_value
- test_valid_term_spec_values
- test_ontology_mod_without_accession_or_name
- test_valid_sample_with_technical_replicate
- test_valid_explicit_quantification_method_lfq
- test_valid_explicit_quantification_method_tmt

**Tests created/changed:**
- tests/yaml_contract/test_yaml_input_contract.py
- tests/yaml_contract/fixtures/valid_tmtplex.yml
- tests/yaml_contract/fixtures/valid_lfq.yml
- tests/yaml_contract/fixtures/valid_silac.yml
- tests/yaml_contract/fixtures/valid_dia.yml
- tests/yaml_contract/fixtures/valid_itraq.yml

**Review Status:** APPROVED

**Git Commit Message:**
feat: refine quantms YAML modification contract

- split modification entries into ontology-backed and custom variants
- require mode enums and shared term specificity on YAML modifications
- keep YAML support schema-only while runtime ingestion remains deferred