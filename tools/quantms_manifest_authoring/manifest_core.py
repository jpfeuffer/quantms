#!/usr/bin/env python3
"""
Core manifest authoring module for quantms YAML manifests.

Provides classes for managing manifest state, serialization, validation integration,
and channel builder behavior for multiplex types.
"""

import json
import yaml
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
import sys

try:
    from jsonschema import validate, ValidationError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


@dataclass
class Metadata:
    """Manifest-level metadata including schema version and ontology provenance."""
    schema_version: Optional[str] = None
    ontology_versions: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary, excluding None values."""
        result = {}
        if self.schema_version:
            result["schema_version"] = self.schema_version
        if self.ontology_versions:
            result["ontology_versions"] = self.ontology_versions
        return result if result else {}


@dataclass
class Experiment:
    """Experiment-level configuration."""
    acquisition_method: str  # DDA or DIA
    enzyme: str
    quantification_method: Optional[str] = None  # LFQ, TMT, iTRAQ, SILAC
    dissociation_method: Optional[str] = None  # HCD, CID, ETD, etc.
    precursor_mass_tolerance: Optional[str] = None
    fragment_mass_tolerance: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Sample:
    """Biological sample definition."""
    id: str
    organism: Optional[str] = None
    organism_part: Optional[str] = None
    condition: Optional[str] = None
    biological_replicate: Optional[int] = None
    technical_replicate: Optional[int] = None
    disease: Optional[str] = None
    cell_type: Optional[str] = None
    characteristics: Dict[str, Any] = field(default_factory=dict)
    factor_values: Dict[str, Any] = field(default_factory=dict)
    additional_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding empty collections."""
        result = {"id": self.id}
        if self.organism:
            result["organism"] = self.organism
        if self.organism_part:
            result["organism_part"] = self.organism_part
        if self.condition:
            result["condition"] = self.condition
        if self.biological_replicate:
            result["biological_replicate"] = self.biological_replicate
        if self.technical_replicate:
            result["technical_replicate"] = self.technical_replicate
        if self.disease:
            result["disease"] = self.disease
        if self.cell_type:
            result["cell_type"] = self.cell_type
        if self.characteristics:
            result["characteristics"] = self.characteristics
        if self.factor_values:
            result["factor_values"] = self.factor_values
        if self.additional_metadata:
            result["additional_metadata"] = self.additional_metadata
        return result


@dataclass
class Mixture:
    """Multiplex mixture definition."""
    id: str
    channels: Dict[str, str]  # channel -> sample_id mapping
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "channels": self.channels,
        }
        if self.description:
            result["description"] = self.description
        return result


@dataclass
class Run:
    """Raw data run definition."""
    file: str
    sample: Optional[str] = None
    mixture: Optional[str] = None
    fraction: Optional[int] = None
    instrument: Optional[str] = None
    modification_profile: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        result = {
            "file": self.file,
        }
        if self.sample:
            result["sample"] = self.sample
        if self.mixture:
            result["mixture"] = self.mixture
        if self.fraction:
            result["fraction"] = self.fraction
        if self.instrument:
            result["instrument"] = self.instrument
        if self.modification_profile:
            result["modification_profile"] = self.modification_profile
        return result


@dataclass
class Modification:
    """Modification definition."""
    mode: str  # fixed or variable
    kind: Optional[str] = None  # ontology, custom
    name: Optional[str] = None
    ontology_id: Optional[str] = None
    residues: Optional[str] = None
    term_specificity: Optional[str] = None
    mass_shift: Optional[float] = None
    profile: Optional[str] = None
    id: Optional[str] = None
    max_occurrences: Optional[int] = None
    required: Optional[bool] = None
    neutral_loss: Optional[float] = None
    localize_mass_shift: Optional[bool] = None
    label_mass_shift: Optional[float] = None
    custom_mod_code: Optional[str] = None
    formula: Optional[str] = None
    binary_group: Optional[int] = None
    min_occurrences: Optional[int] = None
    distance_from_terminus: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


class ChannelBuilder:
    """Helper for building multiplex channel configurations."""

    CHANNEL_CONFIGS = {
        "TMT2": ["TMT126", "TMT127C"],
        "TMT6": ["TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N"],
        "TMT10": ["TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N", "TMT129C", "TMT130N", "TMT130C", "TMT131N"],
        "TMT11": ["TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N", "TMT129C", "TMT130N", "TMT130C", "TMT131N", "TMT131C"],
        "TMT16": ["TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N", "TMT129C", "TMT130N", "TMT130C", "TMT131N", "TMT131C", "TMT132N", "TMT132C", "TMT133N", "TMT133C", "TMT134N"],
        "TMT18": ["TMT126", "TMT127N", "TMT127C", "TMT128N", "TMT128C", "TMT129N", "TMT129C", "TMT130N", "TMT130C", "TMT131N", "TMT131C", "TMT132N", "TMT132C", "TMT133N", "TMT133C", "TMT134N", "TMT135N", "TMT135C"],
        "iTRAQ4": ["iTRAQ114", "iTRAQ115", "iTRAQ116", "iTRAQ117"],
        "iTRAQ8": ["iTRAQ113", "iTRAQ114", "iTRAQ115", "iTRAQ116", "iTRAQ117", "iTRAQ118", "iTRAQ119", "iTRAQ121"],
        "SILAC_2plex": ["Light", "Heavy"],
        "SILAC_3plex": ["Light", "Medium", "Heavy"],
    }

    CHANNEL_PROVENANCE = {
        "TMT2": "PSI-MS / PRIDE bundled channel catalog",
        "TMT6": "PSI-MS / PRIDE bundled channel catalog",
        "TMT10": "PSI-MS / PRIDE bundled channel catalog",
        "TMT11": "PSI-MS / PRIDE bundled channel catalog",
        "TMT16": "PSI-MS / PRIDE bundled channel catalog",
        "TMT18": "PSI-MS / PRIDE bundled channel catalog",
        "iTRAQ4": "PSI-MS / PRIDE bundled channel catalog",
        "iTRAQ8": "PSI-MS / PRIDE bundled channel catalog",
        "SILAC_2plex": "PSI-MS / PRIDE bundled channel catalog",
        "SILAC_3plex": "PSI-MS / PRIDE bundled channel catalog",
    }

    def __init__(self, plex_type: str):
        """Initialize channel builder for a specific plex type."""
        if plex_type not in self.CHANNEL_CONFIGS:
            raise ValueError(
                f"Unknown plex type '{plex_type}'. "
                f"Supported types: {', '.join(sorted(self.CHANNEL_CONFIGS.keys()))}"
            )
        self.plex_type = plex_type

    def get_available_channels(self) -> List[str]:
        """Get list of available channels for this plex type."""
        return self.CHANNEL_CONFIGS[self.plex_type].copy()

    @staticmethod
    def get_supported_plex_types() -> List[str]:
        """Get list of all supported plex types."""
        return sorted(ChannelBuilder.CHANNEL_CONFIGS.keys())

    @classmethod
    def get_channel_catalog(cls) -> Dict[str, List[Dict[str, Any]]]:
        """Return a bundled channel catalog keyed by strategy name."""
        catalog: Dict[str, List[Dict[str, Any]]] = {}
        for strategy, channels in cls.CHANNEL_CONFIGS.items():
            provenance = cls.CHANNEL_PROVENANCE.get(strategy, "PSI-MS / PRIDE bundled channel catalog")
            catalog[strategy] = [
                {
                    "channel": channel,
                    "strategy": strategy,
                    "provenance": provenance,
                }
                for channel in channels
            ]
        return catalog


def validate_manifest(manifest: "ManifestState") -> List[Dict[str, Any]]:
    """
    Validate a manifest state against the schema and semantic constraints.

    Returns a list of validation issues (errors and warnings).
    Each issue is a dict with 'level', 'message', and optionally 'field'.
    """
    issues = []
    manifest_dict = manifest.to_dict()

    # Try to validate against JSON schema if available
    if JSONSCHEMA_AVAILABLE:
        try:
            schema_path = Path(__file__).parent.parent.parent / "assets" / "schemas" / "quantms_yaml_manifest.json"
            if schema_path.exists():
                with open(schema_path) as f:
                    schema = json.load(f)
                try:
                    validate(instance=manifest_dict, schema=schema)
                except ValidationError as e:
                    # Add schema validation errors
                    issues.append({
                        "level": "error",
                        "message": f"Schema validation failed: {e.message}",
                        "field": ".".join(str(p) for p in e.absolute_path) if e.absolute_path else "unknown",
                    })
        except Exception:
            # Schema validation not available, use semantic validation only
            pass

    # Semantic validation - required sections
    if manifest.experiment is None:
        issues.append({
            "level": "error",
            "message": "experiment section is required",
            "field": "experiment",
        })

    if not manifest.samples:
        issues.append({
            "level": "error",
            "message": "samples array must have at least one entry",
            "field": "samples",
        })

    if not manifest.runs:
        issues.append({
            "level": "error",
            "message": "runs array must have at least one entry",
            "field": "runs",
        })

    # Check for missing required fields in samples
    for idx, sample in enumerate(manifest.samples):
        if not sample.organism:
            issues.append({
                "level": "warning",
                "message": f"Sample '{sample.id}' is missing 'organism' field",
                "field": f"samples[{idx}].organism",
            })

    # Check for missing required fields in runs
    for idx, run in enumerate(manifest.runs):
        if not run.file:
            issues.append({
                "level": "error",
                "message": f"Run at index {idx} is missing required 'file' field",
                "field": f"runs[{idx}].file",
            })

    # Referential integrity checks
    sample_ids = {s.id for s in manifest.samples}
    mixture_ids = {m.id for m in manifest.mixtures}

    for idx, run in enumerate(manifest.runs):
        if run.sample and run.sample not in sample_ids:
            issues.append({
                "level": "error",
                "message": f"Run '{run.file}' references unknown sample '{run.sample}'",
                "field": f"runs[{idx}].sample",
            })
        if run.mixture and run.mixture not in mixture_ids:
            issues.append({
                "level": "error",
                "message": f"Run '{run.file}' references unknown mixture '{run.mixture}'",
                "field": f"runs[{idx}].mixture",
            })

    # Check sample references in mixtures
    for idx, mixture in enumerate(manifest.mixtures):
        for channel, sample_id in mixture.channels.items():
            if sample_id not in sample_ids:
                issues.append({
                    "level": "error",
                    "message": f"Mixture '{mixture.id}' channel '{channel}' references unknown sample '{sample_id}'",
                    "field": f"mixtures[{idx}].channels.{channel}",
                })

    # Validate modification mode and kind (semantic validation as fallback when schema unavailable)
    for idx, mod in enumerate(manifest.modifications):
        # Validate mode enum even when jsonschema is unavailable
        if mod.mode and mod.mode not in ["fixed", "variable"]:
            issues.append({
                "level": "error",
                "message": f"Modification '{mod.name or idx}' has invalid mode '{mod.mode}'. Must be 'fixed' or 'variable'",
                "field": f"modifications[{idx}].mode",
            })
        # Validate kind enum
        if mod.kind and mod.kind not in ["ontology", "custom"]:
            issues.append({
                "level": "error",
                "message": f"Modification '{mod.name or idx}' has invalid kind '{mod.kind}'. Must be 'ontology' or 'custom'",
                "field": f"modifications[{idx}].kind",
            })

    return issues


class ManifestState:
    """Manages the complete state of a quantms YAML manifest."""

    def __init__(self):
        """Initialize a new manifest state."""
        self.metadata = Metadata()
        self.experiment: Optional[Experiment] = None
        self.samples: List[Sample] = []
        self.mixtures: List[Mixture] = []
        self.runs: List[Run] = []
        self.modifications: List[Modification] = []

    def set_experiment(
        self,
        acquisition_method: str,
        enzyme: str,
        quantification_method: Optional[str] = None,
        dissociation_method: Optional[str] = None,
        precursor_mass_tolerance: Optional[str] = None,
        fragment_mass_tolerance: Optional[str] = None,
    ) -> None:
        """Set experiment configuration."""
        self.experiment = Experiment(
            acquisition_method=acquisition_method,
            enzyme=enzyme,
            quantification_method=quantification_method,
            dissociation_method=dissociation_method,
            precursor_mass_tolerance=precursor_mass_tolerance,
            fragment_mass_tolerance=fragment_mass_tolerance,
        )

    def add_sample(
        self,
        id: str,
        organism: Optional[str] = None,
        organism_part: Optional[str] = None,
        condition: Optional[str] = None,
        biological_replicate: Optional[int] = None,
        technical_replicate: Optional[int] = None,
        disease: Optional[str] = None,
        cell_type: Optional[str] = None,
    ) -> None:
        """Add a sample to the manifest."""
        sample = Sample(
            id=id,
            organism=organism,
            organism_part=organism_part,
            condition=condition,
            biological_replicate=biological_replicate,
            technical_replicate=technical_replicate,
            disease=disease,
            cell_type=cell_type,
        )
        self.samples.append(sample)

    def add_mixture(
        self,
        id: str,
        channels: Dict[str, str],
        description: Optional[str] = None,
    ) -> None:
        """Add a multiplex mixture to the manifest."""
        mixture = Mixture(
            id=id,
            channels=channels,
            description=description,
        )
        self.mixtures.append(mixture)

    def add_run(
        self,
        file: str,
        sample: Optional[str] = None,
        mixture: Optional[str] = None,
        fraction: Optional[int] = None,
        instrument: Optional[str] = None,
        modification_profile: Optional[str] = None,
    ) -> None:
        """Add a raw data run to the manifest."""
        run = Run(
            file=file,
            sample=sample,
            mixture=mixture,
            fraction=fraction,
            instrument=instrument,
            modification_profile=modification_profile,
        )
        self.runs.append(run)

    def add_modification(
        self,
        mode: str,
        kind: Optional[str] = None,
        name: Optional[str] = None,
        ontology_id: Optional[str] = None,
        residues: Optional[str] = None,
        term_specificity: Optional[str] = None,
        mass_shift: Optional[float] = None,
        profile: Optional[str] = None,
        **kwargs,
    ) -> None:
        """Add a modification definition to the manifest."""
        modification = Modification(
            mode=mode,
            kind=kind,
            name=name,
            ontology_id=ontology_id,
            residues=residues,
            term_specificity=term_specificity,
            mass_shift=mass_shift,
            profile=profile,
            **kwargs,
        )
        self.modifications.append(modification)

    def update_run(self, run_index: int, **kwargs) -> None:
        """
        Update properties of a run in the manifest.

        Args:
            run_index: Index of the run to update
            **kwargs: Properties to update (file, sample, mixture, fraction, instrument, etc.)

        Raises:
            IndexError: If run_index is out of range
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")

        run = self.runs[run_index]
        for key, value in kwargs.items():
            if hasattr(run, key):
                setattr(run, key, value)

    def remove_run(self, run_index: int) -> None:
        """
        Remove a run from the manifest.

        Args:
            run_index: Index of the run to remove

        Raises:
            IndexError: If run_index is out of range
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")
        del self.runs[run_index]

    def update_sample(self, sample_index: int, **kwargs) -> None:
        """
        Update properties of a sample in the manifest.

        Args:
            sample_index: Index of the sample to update
            **kwargs: Properties to update (organism, organism_part, condition, etc.)

        Raises:
            IndexError: If sample_index is out of range
        """
        if sample_index < 0 or sample_index >= len(self.samples):
            raise IndexError(f"Sample index {sample_index} out of range")

        sample = self.samples[sample_index]
        for key, value in kwargs.items():
            if hasattr(sample, key):
                setattr(sample, key, value)

    def remove_sample(self, sample_index: int) -> None:
        """
        Remove a sample from the manifest.

        Args:
            sample_index: Index of the sample to remove

        Raises:
            IndexError: If sample_index is out of range
        """
        if sample_index < 0 or sample_index >= len(self.samples):
            raise IndexError(f"Sample index {sample_index} out of range")
        del self.samples[sample_index]

    def update_mixture(self, mixture_index: int, **kwargs) -> None:
        """
        Update properties of a mixture in the manifest.

        Args:
            mixture_index: Index of the mixture to update
            **kwargs: Properties to update (channels, description, etc.)

        Raises:
            IndexError: If mixture_index is out of range
        """
        if mixture_index < 0 or mixture_index >= len(self.mixtures):
            raise IndexError(f"Mixture index {mixture_index} out of range")

        mixture = self.mixtures[mixture_index]
        for key, value in kwargs.items():
            if hasattr(mixture, key):
                setattr(mixture, key, value)

    def remove_mixture(self, mixture_index: int) -> None:
        """
        Remove a mixture from the manifest.

        Args:
            mixture_index: Index of the mixture to remove

        Raises:
            IndexError: If mixture_index is out of range
        """
        if mixture_index < 0 or mixture_index >= len(self.mixtures):
            raise IndexError(f"Mixture index {mixture_index} out of range")
        del self.mixtures[mixture_index]

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest state to dictionary suitable for YAML serialization."""
        result = {}

        # Add metadata if present
        metadata_dict = self.metadata.to_dict()
        if metadata_dict:
            result["metadata"] = metadata_dict

        # Add experiment (required)
        if self.experiment:
            result["experiment"] = self.experiment.to_dict()

        # Add samples (required)
        result["samples"] = [s.to_dict() for s in self.samples]

        # Add mixtures
        result["mixtures"] = [m.to_dict() for m in self.mixtures]

        # Add runs (required)
        result["runs"] = [r.to_dict() for r in self.runs]

        # Add modifications if present
        if self.modifications:
            result["modifications"] = [m.to_dict() for m in self.modifications]

        return result

    def to_yaml(self) -> str:
        """Serialize manifest state to YAML string."""
        return yaml.dump(
            self.to_dict(),
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )

    def save_to_file(self, filepath: Path) -> None:
        """Save manifest to YAML file."""
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            f.write(self.to_yaml())

    @staticmethod
    def load_from_file(filepath: Path) -> "ManifestState":
        """Load manifest from YAML file."""
        with open(filepath) as f:
            data = yaml.safe_load(f)

        manifest = ManifestState()

        # Load metadata
        if "metadata" in data:
            meta = data["metadata"]
            manifest.metadata = Metadata(
                schema_version=meta.get("schema_version"),
                ontology_versions=meta.get("ontology_versions", {}),
            )

        # Load experiment
        if "experiment" in data:
            exp = data["experiment"]
            manifest.set_experiment(
                acquisition_method=exp.get("acquisition_method"),
                enzyme=exp.get("enzyme"),
                quantification_method=exp.get("quantification_method"),
                dissociation_method=exp.get("dissociation_method"),
                precursor_mass_tolerance=exp.get("precursor_mass_tolerance"),
                fragment_mass_tolerance=exp.get("fragment_mass_tolerance"),
            )

        # Load samples
        if "samples" in data:
            for sample_data in data["samples"]:
                manifest.add_sample(
                    id=sample_data.get("id"),
                    organism=sample_data.get("organism"),
                    organism_part=sample_data.get("organism_part"),
                    condition=sample_data.get("condition"),
                    biological_replicate=sample_data.get("biological_replicate"),
                    technical_replicate=sample_data.get("technical_replicate"),
                    disease=sample_data.get("disease"),
                    cell_type=sample_data.get("cell_type"),
                )

        # Load mixtures
        if "mixtures" in data:
            for mixture_data in data["mixtures"]:
                manifest.add_mixture(
                    id=mixture_data.get("id"),
                    channels=mixture_data.get("channels", {}),
                    description=mixture_data.get("description"),
                )

        # Load runs
        if "runs" in data:
            for run_data in data["runs"]:
                manifest.add_run(
                    file=run_data.get("file"),
                    sample=run_data.get("sample"),
                    mixture=run_data.get("mixture"),
                    fraction=run_data.get("fraction"),
                    instrument=run_data.get("instrument"),
                    modification_profile=run_data.get("modification_profile"),
                )

        # Load modifications
        if "modifications" in data:
            for mod_data in data["modifications"]:
                # Filter out unknown fields and handle deprecated aliases
                filtered_data = {}

                # Map deprecated aliases to current field names
                alias_map = {
                    "accession": "ontology_id",
                    "term_spec": "term_specificity",
                }

                # Known valid fields for Modification dataclass
                valid_fields = {
                    "mode", "kind", "name", "ontology_id", "residues",
                    "term_specificity", "mass_shift", "profile", "id",
                    "max_occurrences", "required", "neutral_loss",
                    "localize_mass_shift", "label_mass_shift", "custom_mod_code",
                    "formula", "binary_group", "min_occurrences",
                    "distance_from_terminus"
                }

                for key, value in mod_data.items():
                    if key in alias_map:
                        # Handle deprecated alias
                        canonical_key = alias_map[key]
                        # Only use alias if canonical key not already present
                        if canonical_key not in mod_data:
                            filtered_data[canonical_key] = value
                    elif key in valid_fields:
                        filtered_data[key] = value
                    # Unknown fields are silently ignored

                manifest.add_modification(**filtered_data)

        return manifest
