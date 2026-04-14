# quantms YAML Manifest Authoring Tool

Python application with two interfaces for authoring quantms YAML manifests:
1. **TUI** (Terminal User Interface) - Interactive Textual-based terminal application
2. **GUI** (Web UI) - Interactive NiceGUI-based web application

## Overview

The quantms pipeline requires configuration via YAML manifests that define:
- **Experiment**: Acquisition method, enzyme, quantification approach, dissociation method
- **Samples**: Biological samples with metadata (organism, tissue, condition, replicates)
- **Mixtures**: Multiplex groupings (TMT, iTRAQ, SILAC) mapping channels to samples
- **Runs**: Raw MS data files with fraction and mixture assignments
- **Modifications**: Fixed and variable post-translational modifications with optional profiles

This tool provides both TUI and GUI interfaces to guide users step-by-step through creating valid YAML manifests with real-time validation feedback.

## Installation

Both interfaces use Python with uv-managed dependencies. No separate installation needed beyond having Python 3.11+.

### Dependencies

- **TUI**: `textual`, `pyyaml`
- **GUI**: `nicegui`, `fastapi`, `uvicorn`, `pyyaml`
- **CLI**: `click`
- **Core**: `pyyaml`

All dependencies are specified in the script headers using PEP 723 uv format. When running scripts directly with `uv run`, dependencies are automatically installed.

## Usage

### via uv (recommended)

```bash
# Run TUI
uv run tools/quantms_manifest_authoring/tui_textual.py

# Run GUI
uv run tools/quantms_manifest_authoring/gui_nicegui.py

# Run CLI with subcommands
uv run tools/quantms_manifest_authoring/cli.py tui
uv run tools/quantms_manifest_authoring/cli.py gui
uv run tools/quantms_manifest_authoring/cli.py info
```

### via Python directly (if dependencies are pre-installed)

```bash
# TUI
python tools/quantms_manifest_authoring/tui_textual.py

# GUI
python tools/quantms_manifest_authoring/gui_nicegui.py

# CLI
python tools/quantms_manifest_authoring/cli.py --help
```

## Interfaces

### Terminal User Interface (TUI)

**File**: `tui_textual.py`

A full-featured terminal interface using the Textual framework:
- Tab-based navigation (Experiment, Samples, Mixtures, Runs)
- Form inputs for each section
- Real-time YAML preview
- Validation feedback panel
- File save/load functionality

**Keyboard shortcuts**:
- `Ctrl+S`: Save manifest to file
- `Ctrl+L`: Load manifest from file
- `Ctrl+Q`: Quit application
- `Tab` / `Shift+Tab`: Navigate between fields

**File location**: `~/quantms_manifest.yml` (default)

### Web GUI (NiceGUI)

**File**: `gui_nicegui.py`

A modern web interface accessible via browser:
- Tabbed interface (Experiment, Samples, Mixtures, Runs)
- Interactive forms with validation
- Real-time YAML preview
- Live validation status
- File save/load functionality
- Expandable sections showing current state

**Startup**:
```bash
uv run tools/quantms_manifest_authoring/gui_nicegui.py
# Opens browser to http://127.0.0.1:8080
```

**Port customization**:
```bash
python -c "
import sys
sys.path.insert(0, 'tools/quantms_manifest_authoring')
from gui_nicegui import run_gui
run_gui(port=5000, host='0.0.0.0')
"
```

**File location**: `~/quantms_manifest.yml` (default)

## Core Module

**File**: `manifest_core.py`

Provides the data model and utilities:

### Classes

- **ManifestState**: In-memory manifest representation with serialization/loading
- **Sample**: Biological sample with metadata fields
- **Mixture**: Multiplex groupings with channel-to-sample mappings
- **Run**: Raw MS data file with assignment metadata
- **Modification**: PTM definition with fixedness, residues, and profiles
- **Experiment**: Top-level experiment settings
- **Metadata**: Manifest-level metadata (schema version, ontology versions)
- **ChannelBuilder**: Helper for multiplex channel management

### Functions

- **validate_manifest(manifest)**: Validate manifest state, returns list of issues

### Usage Example

```python
from manifest_core import ManifestState, ChannelBuilder

# Create manifest
manifest = ManifestState()

# Set experiment
manifest.set_experiment(
    acquisition_method="DDA",
    enzyme="Trypsin",
    quantification_method="TMT",
    dissociation_method="HCD",
)

# Add samples
manifest.add_sample(
    id="sample_1",
    organism="homo sapiens",
    organism_part="liver",
    condition="treated",
    biological_replicate=1,
)

# Add mixture
manifest.add_mixture(
    id="mix_1",
    channels={"TMT126": "sample_1"}
)

# Add run
manifest.add_run(
    file="s3://bucket/mix_1_F1.raw",
    mixture="mix_1",
    fraction=1,
)

# Validate
from manifest_core import validate_manifest
issues = validate_manifest(manifest)

# Export to YAML
yaml_string = manifest.to_yaml()
manifest.save_to_file("my_manifest.yml")

# Load from YAML
loaded = ManifestState.load_from_file("my_manifest.yml")
```

## Supported Multiplex Types

The ChannelBuilder supports the following plex types:

### TMT (Tandem Mass Tags)
- **TMT2**: 2 channels (126, 127C)
- **TMT6**: 6 channels
- **TMT10**: 10 channels
- **TMT11**: 11 channels
- **TMT16**: 16 channels (most common)
- **TMT18**: 18 channels

### iTRAQ (Isobaric Tags for Relative and Absolute Quantification)
- **iTRAQ4**: 4 channels (113-116)
- **iTRAQ8**: 8 channels (113-121)

### SILAC (Stable Isotope Labeling by Amino Acids in Cell Culture)
- **SILAC_2plex**: Light / Heavy
- **SILAC_3plex**: Light / Medium / Heavy

## Validation Feedback

Both interfaces integrate with the `validate_manifest()` function to provide real-time feedback on:
- Missing required sections (experiment, samples, runs)
- Invalid field values
- Missing ontology information
- Reference integrity (mixture IDs, sample IDs)

Validation issues are categorized as:
- **Error**: Critical - must be fixed before saving
- **Warning**: Informational - encourages best practices

## Testing

Comprehensive test suite included in `test_manifest_authoring.py`:

```bash
# Run all tests
python -m pytest tools/quantms_manifest_authoring/test_manifest_authoring.py -v

# Run specific test class
python -m pytest tools/quantms_manifest_authoring/test_manifest_authoring.py::TestManifestStateSerialization -v

# Run with coverage
python -m pytest tools/quantms_manifest_authoring/test_manifest_authoring.py --cov=manifest_core
```

**Test coverage**:
- Manifest state creation and manipulation
- YAML serialization/deserialization
- File I/O operations
- Channel builder behavior for all plex types
- Validation feedback integration
- Modification profile handling
- Metadata management

## Integration with Pipeline

Once a valid manifest is created and saved:

1. Check location: Default saves to `~/quantms_manifest.yml`
2. Move to expected pipeline location: `data/manifest.yml`
3. Run pipeline: `nextflow run . -params-file manifest.yml`

The pipeline will consume the YAML manifest for:
- Sample metadata and grouping
- Multiplex channel assignments
- Run-to-fraction mapping
- Modification profiles

## Architecture

### State Management

`ManifestState` is the single source of truth for manifest content:
- Holds experiment, samples, mixtures, runs, modifications
- Provides high-level methods (`add_sample`, `add_mixture`, etc.)
- Serializes to/from YAML via standard `to_dict()` and `to_yaml()` methods
- Loads from files via `load_from_file()`

### Validation

`validate_manifest()` performs semantic validation:
- Checks presence of required sections
- Validates field relationships (mixture references, sample IDs)
- Returns structured list of issues with severity levels
- Does NOT require external schema files (self-contained)

### UI Independence

Core module is UI-agnostic:
- TUI and GUI both use the same `ManifestState` class
- Validation is shared
- Both save/load to same YAML format
- Easy to add new interfaces (CLI, API, etc.)

## Phase 4 Scope

This implementation provides:
- ✅ Shared Python module for manifest state/serialization/validation
- ✅ Two entrypoints: TUI (Textual) and GUI (NiceGUI)
- ✅ Support for core sections: experiment, samples, mixtures, runs, modifications
- ✅ Metadata section (schema_version, ontology_versions)
- ✅ Channel builder for multiplex types (TMT, iTRAQ, SILAC)
- ✅ Real-time validation feedback
- ✅ YAML serialization/deserialization
- ✅ File save/load functionality
- ✅ Comprehensive test suite (28 passing tests)

Not included (future phases):
- YAML → runtime normalizer (phase 5)
- Nextflow integration (phase 6)
- SDRF removal (phase 7)

## Future Enhancements

Potential improvements for future phases:
1. Modification profile editor UI for advanced users
2. Channel-to-sample assignment UI in mixtures section
3. Template/preset profiles for common experiments
4. Drag-and-drop file upload for raw data paths
5. Connection to pipeline execution interface
6. Undo/redo functionality
7. Collaborative editing features

## Contributing

When modifying the manifest authoring tool:

1. **Keep core module UI-agnostic**: All UI-specific code in TUI/GUI files
2. **Add tests first**: Use TDD for new features
3. **Update both interfaces**: Changes to schema should update TUI and GUI
4. **Maintain uv compatibility**: Use PEP 723 script headers for dependencies
5. **Document changes**: Update this README if interfaces change

## References

- [quantms Documentation](https://quantms.readthedocs.io/)
- [YAML Manifest Schema](../schemas/quantms_yaml_manifest.json)
- [Textual Framework](https://textualize.io/textual/)
- [NiceGUI Documentation](https://nicegui.io/)
