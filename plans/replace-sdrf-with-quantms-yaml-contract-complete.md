## Contract Definition Complete: Replace SDRF With quantms YAML

The YAML contract definition milestone is complete. The repository now contains a real schema artifact for the quantms YAML manifest, schema-based tests using standard validator tooling, and corrected documentation that treats YAML as the approved replacement contract while keeping runtime SDRF input unchanged until later implementation work lands.

**Files created/changed:**
- assets/schemas/quantms_yaml_manifest.json
- tests/yaml_contract/test_yaml_input_contract.py
- tests/yaml_contract/fixtures/valid_tmtplex.yml
- docs/usage.md
- README.md
- nextflow_schema.json
- nextflow.config

**Functions created/changed:**
- validate_yaml_against_schema
- load_schema
- load_yaml
- get_schema_path
- test_valid_fixture
- test_valid_without_mod_profiles
- test_missing_required_section_samples
- test_invalid_mod_profile_wrong_type
- test_invalid_mod_profile_missing_id
- test_mod_profile_with_structured_modifications
- test_invalid_experiment_wrong_method

**Tests created/changed:**
- tests/yaml_contract/test_yaml_input_contract.py
- tests/yaml_contract/fixtures/valid_tmtplex.yml

**Review Status:** APPROVED with minor recommendations addressed

**Git Commit Message:**
chore: define quantms YAML contract

- add JSON Schema for the YAML experiment manifest
- replace custom YAML checks with schema-based tests
- correct mod_profiles to support custom and engine-specific mods
- clarify that YAML runtime support is deferred
