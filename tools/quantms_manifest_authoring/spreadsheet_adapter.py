#!/usr/bin/env python3
"""
Spreadsheet adapter for translating between WizardState runs and spreadsheet rows.

This adapter provides a reusable contract for mapping between the authoritative
WizardState (list of run dicts) and flat spreadsheet rows that can be edited
and synchronized back.

Key principles:
- WizardState is the authoritative source (never modified by adapter except via explicit sync)
- Spreadsheet rows are ephemeral views that can be edited and synced back
- Column order is predictable for consistent UI rendering
- Required fields (especially 'file') are validated
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from manifest_core import ChannelBuilder


LFQ_LABELING_STRATEGY = "label free sample"


class RunFieldInfo:
    """Metadata about run fields for the adapter."""

    FIELD_METADATA = {
        "file": {
            "type": "str",
            "required": True,
            "description": "Path or URI to raw/mzML file",
        },
        "fraction": {
            "type": "int",
            "required": False,
            "description": "Fraction number",
        },
        "instrument": {
            "type": "str",
            "required": False,
            "description": "Instrument name",
        },
        "group_id": {
            "type": "str",
            "required": False,
            "description": "Authoring group identifier",
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        """Get all available field names."""
        return list(RunFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        """Get metadata for a specific field."""
        if field not in RunFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return RunFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        """Get list of required fields."""
        return [
            field
            for field, info in RunFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


class ModificationFieldInfo:
    """Metadata about modification fields for the adapter."""

    FIELD_METADATA = {
        "mode": {
            "type": "str",
            "required": True,
            "description": "Modification mode (fixed or variable)",
        },
        "kind": {
            "type": "str",
            "required": False,
            "description": "Modification source kind (ontology or custom)",
        },
        "name": {
            "type": "str",
            "required": False,
            "description": "Human-readable modification name",
        },
        "ontology_id": {
            "type": "str",
            "required": False,
            "description": "Ontology CURIE for ontology-backed modifications",
        },
        "residues": {
            "type": "str",
            "required": False,
            "description": "Target residues",
        },
        "term_specificity": {
            "type": "str",
            "required": False,
            "description": "Term specificity",
        },
        "mass_shift": {
            "type": "float",
            "required": False,
            "description": "Mass shift in Daltons",
        },
        "profile": {
            "type": "str",
            "required": False,
            "description": "Modification profile",
        },
        "id": {
            "type": "str",
            "required": False,
            "description": "Optional identifier",
        },
        "max_occurrences": {
            "type": "int",
            "required": False,
            "description": "Maximum occurrences",
        },
        "required": {
            "type": "bool",
            "required": False,
            "description": "Whether the modification is required",
        },
        "neutral_loss": {
            "type": "float",
            "required": False,
            "description": "Neutral loss",
        },
        "localize_mass_shift": {
            "type": "bool",
            "required": False,
            "description": "Whether to localize the mass shift",
        },
        "label_mass_shift": {
            "type": "float",
            "required": False,
            "description": "Label mass shift",
        },
        "custom_mod_code": {
            "type": "str",
            "required": False,
            "description": "Custom modification code",
        },
        "formula": {
            "type": "str",
            "required": False,
            "description": "Chemical formula",
        },
        "binary_group": {
            "type": "int",
            "required": False,
            "description": "Binary group",
        },
        "min_occurrences": {
            "type": "int",
            "required": False,
            "description": "Minimum occurrences",
        },
        "distance_from_terminus": {
            "type": "int",
            "required": False,
            "description": "Distance from terminus",
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        return list(ModificationFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        if field not in ModificationFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return ModificationFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        return [
            field
            for field, info in ModificationFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


class GroupFieldInfo:
    """Metadata about authoring group fields for the adapter."""

    FIELD_METADATA = {
        "id": {
            "type": "str",
            "required": True,
            "description": "Group identifier",
            "read_only": False,
        },
        "name": {
            "type": "str",
            "required": True,
            "description": "Group label",
            "read_only": False,
        },
        "kind": {
            "type": "str",
            "required": True,
            "description": "Group kind",
            "read_only": False,
        },
        "labeling_strategy": {
            "type": "str",
            "required": False,
            "description": "Labeling strategy or plex type",
            "read_only": False,
        },
        "channel_count": {
            "type": "int",
            "required": False,
            "description": "Derived channel count",
            "read_only": True,
        },
        "members": {
            "type": "str",
            "required": False,
            "description": "Run identifiers belonging to this group",
            "read_only": False,
        },
        "description": {
            "type": "str",
            "required": False,
            "description": "Optional group description",
            "read_only": False,
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        return list(GroupFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        if field not in GroupFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return GroupFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        return [
            field
            for field, info in GroupFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


@dataclass
class SpreadsheetRow:
    """Represents a single spreadsheet row corresponding to a run."""

    file: Optional[str] = None
    fraction: Optional[int] = None
    instrument: Optional[str] = None
    group_id: Optional[str] = None
    row_index: int = 0

    @classmethod
    def from_wizard_run(cls, run: Dict[str, Any], row_index: int = 0) -> "SpreadsheetRow":
        """
        Create a spreadsheet row from a wizard run dict.

        Args:
            run: Dictionary from WizardState.runs
            row_index: Index of this row (for reference)

        Returns:
            SpreadsheetRow instance
        """
        return cls(
            file=run.get("file"),
            fraction=run.get("fraction"),
            instrument=run.get("instrument"),
            group_id=run.get("group_id"),
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert row to dict, excluding None values.

        Returns:
            Dictionary suitable for wizard.update_run()
        """
        result = {}
        if self.file is not None:
            result["file"] = self.file
        if self.fraction is not None:
            result["fraction"] = self.fraction
        if self.instrument is not None:
            result["instrument"] = self.instrument
        if self.group_id is not None:
            result["group_id"] = self.group_id
        return result

    def update(self, **kwargs) -> None:
        """Update row fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        """
        Validate row against field constraints.

        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        if not self.file:
            raise ValueError("Required field 'file' is missing")

        # Type coercion and validation
        if self.fraction is not None:
            # Treat empty string as None
            if isinstance(self.fraction, str) and self.fraction.strip() == "":
                self.fraction = None
            elif isinstance(self.fraction, str):
                try:
                    self.fraction = int(self.fraction)
                except (ValueError, TypeError):
                    raise ValueError(f"Fraction must be an integer, got: {self.fraction}")

    def is_empty_optional_field(self, field: str) -> bool:
        """Check if an optional field is empty (None or empty string)."""
        value = getattr(self, field, None)
        return value is None or value == ""


@dataclass
class ModificationSpreadsheetRow:
    """Represents a single spreadsheet row corresponding to a modification."""

    mode: Optional[str] = None
    kind: Optional[str] = None
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
    row_index: int = 0

    @classmethod
    def from_wizard_modification(
        cls,
        modification: Dict[str, Any],
        row_index: int = 0,
    ) -> "ModificationSpreadsheetRow":
        return cls(
            mode=modification.get("mode"),
            kind=modification.get("kind"),
            name=modification.get("name"),
            ontology_id=modification.get("ontology_id"),
            residues=modification.get("residues"),
            term_specificity=modification.get("term_specificity"),
            mass_shift=modification.get("mass_shift"),
            profile=modification.get("profile"),
            id=modification.get("id"),
            max_occurrences=modification.get("max_occurrences"),
            required=modification.get("required"),
            neutral_loss=modification.get("neutral_loss"),
            localize_mass_shift=modification.get("localize_mass_shift"),
            label_mass_shift=modification.get("label_mass_shift"),
            custom_mod_code=modification.get("custom_mod_code"),
            formula=modification.get("formula"),
            binary_group=modification.get("binary_group"),
            min_occurrences=modification.get("min_occurrences"),
            distance_from_terminus=modification.get("distance_from_terminus"),
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        result = {}
        for field in ModificationFieldInfo.get_all_fields():
            value = getattr(self, field, None)
            if value is not None:
                result[field] = value
        return result

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        if not self.mode:
            raise ValueError("Required field 'mode' is missing")

        if isinstance(self.mass_shift, str):
            if self.mass_shift.strip() == "":
                self.mass_shift = None
            else:
                self.mass_shift = float(self.mass_shift)

        for field in ["max_occurrences", "binary_group", "min_occurrences", "distance_from_terminus"]:
            value = getattr(self, field)
            if isinstance(value, str):
                if value.strip() == "":
                    setattr(self, field, None)
                else:
                    setattr(self, field, int(value))

        for field in ["neutral_loss", "label_mass_shift"]:
            value = getattr(self, field)
            if isinstance(value, str):
                if value.strip() == "":
                    setattr(self, field, None)
                else:
                    setattr(self, field, float(value))


@dataclass
class GroupSpreadsheetRow:
    """Represents a single spreadsheet row corresponding to an authoring group."""

    id: Optional[str] = None
    name: Optional[str] = None
    kind: Optional[str] = None
    labeling_strategy: Optional[str] = None
    channel_count: Optional[int] = None
    members: Optional[str] = None
    description: Optional[str] = None
    row_index: int = 0

    @classmethod
    def from_wizard_group(cls, group: Dict[str, Any], row_index: int = 0) -> "GroupSpreadsheetRow":
        members = group.get("members", []) or []
        if isinstance(members, (list, tuple, set)):
            members_text = ", ".join(str(member) for member in members if member is not None)
        else:
            members_text = str(members)

        return cls(
            id=group.get("id"),
            name=group.get("name"),
            kind=group.get("kind"),
            labeling_strategy=group.get("labeling_strategy"),
            channel_count=group.get("channel_count"),
            members=members_text,
            description=group.get("description"),
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        if self.name is not None:
            result["name"] = self.name
        if self.kind is not None:
            result["kind"] = self.kind
        if self.labeling_strategy is not None:
            result["labeling_strategy"] = self.labeling_strategy
        if self.members is not None:
            members = [member.strip() for member in str(self.members).split(",") if member.strip()]
            result["members"] = members
        if self.description is not None:
            result["description"] = self.description
        return result

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Required field 'id' is missing")
        if not self.name:
            raise ValueError("Required field 'name' is missing")
        if not self.kind:
            raise ValueError("Required field 'kind' is missing")


@dataclass
class GroupChannelSpreadsheetRow:
    """Represents a single spreadsheet row for group-channel assignments."""

    id: Optional[str] = None
    channels: Dict[str, Optional[str]] = None
    row_index: int = 0

    def __post_init__(self):
        if self.channels is None:
            self.channels = {}

    @classmethod
    def from_wizard_group(
        cls,
        group: Dict[str, Any],
        channel_headers: List[str],
        row_index: int = 0,
    ) -> "GroupChannelSpreadsheetRow":
        channels: Dict[str, Optional[str]] = {}
        if channel_headers == ["sample_target"]:
            channels["sample_target"] = group.get("sample_target")
        else:
            assignments = group.get("channel_sample_assignments", {}) or {}
            for channel in channel_headers:
                channels[channel] = assignments.get(channel)

        return cls(
            id=group.get("id"),
            channels=channels,
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        if self.id is not None:
            result["id"] = self.id
        if self.channels:
            result["channels"] = dict(self.channels)
        return result

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Required field 'id' is missing")


class SpreadsheetAdapter:
    """
    Adapter for translating between WizardState and spreadsheet rows.

    Keeps WizardState as the authoritative source. The adapter converts the
    state to/from spreadsheet rows which can be edited and synced.
    """

    def __init__(self, wizard):
        """
        Initialize adapter with a wizard state.

        Args:
            wizard: WizardState instance to operate on
        """
        self.wizard = wizard

    def get_column_headers(self) -> List[str]:
        """
        Get column headers in predictable order (run-level fields only).

        Returns:
            List of field names representing columns
        """
        # Always put 'file' first, then others in consistent order
        return ["file", "fraction", "instrument", "group_id"]

    def get_column_headers_groups(self) -> List[str]:
        """
        Get column headers for authoring groups in predictable order.

        Returns:
            List of field names representing columns
        """
        return ["id", "name", "labeling_strategy", "description"]

    def get_column_headers_modifications(self) -> List[str]:
        """
        Get column headers for modifications in predictable order.

        Returns:
            List of field names representing visible columns
        """
        return [
            "mode",
            "kind",
            "name",
            "ontology_id",
            "residues",
            "term_specificity",
            "mass_shift",
            "profile",
        ]

    def get_field_info(self, field: str) -> Dict[str, Any]:
        """
        Get metadata for a field.

        Args:
            field: Field name (e.g., 'file', 'fraction', 'instrument')

        Returns:
            Dictionary with field metadata including 'type' and 'required'

        Raises:
            ValueError: If field is unknown
        """
        return RunFieldInfo.get_field_info(field)

    def get_group_field_info(self, field: str) -> Dict[str, Any]:
        """Get metadata for a group field."""
        return GroupFieldInfo.get_field_info(field)

    def get_column_headers_samples(self) -> List[str]:
        """
        Get column headers for samples in predictable order.

        Returns:
            List of field names representing columns
        """
        # Always put 'id' first, then others in consistent order
        return ["id", "organism", "organism_part", "condition", "biological_replicate", "technical_replicate", "disease", "cell_type"]

    def get_column_headers_mixtures(self) -> List[str]:
        """
        Get column headers for mixtures: id + channel columns.

        Returns:
            List of field names representing columns (id + all channel keys from current mixtures)
        """
        # Start with 'id'
        headers = ["id"]

        # Add all unique channel keys from current mixtures
        channel_keys = set()
        for mixture in self.wizard.mixtures:
            channel_keys.update(mixture.get("channels", {}).keys())

        # Sort channel keys for consistent order
        headers.extend(sorted(channel_keys))

        return headers

    def _normalize_group_channel_strategy(self, labeling_strategy: Optional[str]) -> Optional[str]:
        if labeling_strategy is None:
            return None

        normalized = str(labeling_strategy).strip()
        if not normalized:
            return None

        if normalized.casefold() == LFQ_LABELING_STRATEGY.casefold():
            return LFQ_LABELING_STRATEGY

        for strategy in ChannelBuilder.get_supported_plex_types():
            if strategy.casefold() == normalized.casefold():
                return strategy

        for kind in ("LFQ", "TMT", "iTRAQ", "SILAC"):
            if kind.casefold() == normalized.casefold():
                if kind == "LFQ":
                    return LFQ_LABELING_STRATEGY
                return self._default_strategy_for_kind(kind)

        return normalized

    def _default_strategy_for_kind(self, kind: str) -> Optional[str]:
        if kind == "LFQ":
            return LFQ_LABELING_STRATEGY
        for strategy in ChannelBuilder.get_supported_plex_types():
            if strategy.startswith(kind):
                return strategy
        return None

    def get_group_channel_headers(self, labeling_strategy: Optional[str]) -> List[str]:
        """Get column headers for a group-channel sheet."""
        normalized_strategy = self._normalize_group_channel_strategy(labeling_strategy)
        if normalized_strategy == LFQ_LABELING_STRATEGY:
            return ["id", "sample_target"]

        if not normalized_strategy:
            return ["id"]

        try:
            channels = ChannelBuilder(normalized_strategy).get_available_channels()
        except ValueError:
            channels = []

        return ["id", *channels]

    def wizard_group_channels_to_spreadsheet(
        self,
        labeling_strategy: Optional[str],
        group_id: Optional[str] = None,
    ) -> List[GroupChannelSpreadsheetRow]:
        """Convert groups for a labeling strategy into spreadsheet rows."""
        normalized_strategy = self._normalize_group_channel_strategy(labeling_strategy)
        rows: List[GroupChannelSpreadsheetRow] = []

        for idx, group in enumerate(self.wizard.groups):
            if group_id is not None and str(group.get("id") or "") != str(group_id):
                continue

            group_strategy = self._normalize_group_channel_strategy(group.get("labeling_strategy"))
            if not group_strategy:
                group_strategy = self._default_strategy_for_kind(str(group.get("kind") or ""))

            if normalized_strategy and group_strategy != normalized_strategy:
                continue

            channel_headers = self.get_group_channel_headers(group_strategy)
            row = GroupChannelSpreadsheetRow.from_wizard_group(group, channel_headers[1:], row_index=idx)
            rows.append(row)

        return rows

    def sync_group_channel_edits(
        self,
        rows: List[GroupChannelSpreadsheetRow],
        labeling_strategy: Optional[str],
        group_id: Optional[str] = None,
    ) -> None:
        """Synchronize group-channel spreadsheet rows back to WizardState."""
        normalized_strategy = self._normalize_group_channel_strategy(labeling_strategy)
        sample_ids = {sample["id"] for sample in self.wizard.samples}

        for row in rows:
            row.validate()

        for row in rows:
            group_index = self.wizard._get_group_index(row.id)
            group = self.wizard.groups[group_index]
            if group_id is not None and str(group.get("id") or "") != str(group_id):
                continue

            group_strategy = self._normalize_group_channel_strategy(group.get("labeling_strategy"))
            if not group_strategy:
                group_strategy = self._default_strategy_for_kind(str(group.get("kind") or ""))

            if normalized_strategy and group_strategy != normalized_strategy:
                continue

            if group_strategy == LFQ_LABELING_STRATEGY:
                sample_target = row.channels.get("sample_target")
                if sample_target is not None and str(sample_target).strip() and str(sample_target) not in sample_ids:
                    raise ValueError(f"Sample '{sample_target}' not found in samples")
                self.wizard.set_group_sample_target(row.id, sample_target if sample_target not in (None, "") else None)
                continue

            normalized_assignments: Dict[str, Optional[str]] = {}
            for channel, sample_id in row.channels.items():
                if sample_id is None or (isinstance(sample_id, str) and sample_id.strip() == ""):
                    normalized_assignments[channel] = None
                    continue
                if str(sample_id) not in sample_ids:
                    raise ValueError(f"Sample '{sample_id}' not found in samples")
                normalized_assignments[channel] = str(sample_id)

            self.wizard.set_group_channel_assignments(row.id, normalized_assignments)


    def wizard_to_spreadsheet(self) -> List[SpreadsheetRow]:
        """
        Convert WizardState.runs to spreadsheet rows.

        Returns:
            List of SpreadsheetRow instances (one per run)
        """
        rows = []
        for idx, run in enumerate(self.wizard.runs):
            row = SpreadsheetRow.from_wizard_run(run, row_index=idx)
            rows.append(row)
        return rows

    def wizard_groups_to_spreadsheet(self) -> List[GroupSpreadsheetRow]:
        """
        Convert WizardState.groups to spreadsheet rows.

        Returns:
            List of GroupSpreadsheetRow instances (one per group)
        """
        rows = []
        for idx, group in enumerate(self.wizard.groups):
            if hasattr(self.wizard, "ensure_group_labeling_metadata") and (group.get("labeling_strategy") or group.get("kind")):
                self.wizard.ensure_group_labeling_metadata(group)
            row = GroupSpreadsheetRow.from_wizard_group(group, row_index=idx)
            rows.append(row)
        return rows

    def wizard_modifications_to_spreadsheet(self) -> List[ModificationSpreadsheetRow]:
        """
        Convert WizardState.modifications to spreadsheet rows.

        Returns:
            List of ModificationSpreadsheetRow instances (one per modification)
        """
        rows = []
        for idx, modification in enumerate(self.wizard.modifications):
            row = ModificationSpreadsheetRow.from_wizard_modification(modification, row_index=idx)
            rows.append(row)
        return rows

    def spreadsheet_row_to_wizard_run(self, row: SpreadsheetRow) -> Dict[str, Any]:
        """
        Convert a spreadsheet row to a wizard run dict.

        Args:
            row: SpreadsheetRow to convert

        Returns:
            Dictionary suitable for WizardState
        """
        return row.to_dict()

    def spreadsheet_row_to_wizard_modification(self, row: ModificationSpreadsheetRow) -> Dict[str, Any]:
        """Convert a spreadsheet row to a wizard modification dict."""
        return row.to_dict()

    def spreadsheet_to_wizard(self, rows: List[SpreadsheetRow]) -> None:
        """
        Synchronize spreadsheet rows back to WizardState.

        This validates all rows and updates the wizard in-place.

        Args:
            rows: List of SpreadsheetRow instances to sync

        Raises:
            ValueError: If row count differs from wizard or validation fails
        """
        # Validate row count matches
        if len(rows) != len(self.wizard.runs):
            raise ValueError(
                f"row count mismatch: spreadsheet has {len(rows)} rows but wizard has {len(self.wizard.runs)} runs"
            )

        # Validate all rows
        for row in rows:
            row.validate()

        # Synchronize each row
        for idx, row in enumerate(rows):
            # Get the updated fields from the spreadsheet row
            updated_fields = {}
            group_id = str(row.group_id).strip() if row.group_id is not None else None
            if group_id == "":
                group_id = None

            for field in RunFieldInfo.get_all_fields():
                if field == "file":
                    # File is always required
                    updated_fields[field] = getattr(row, field)
                elif field == "group_id":
                    continue
                else:
                    # For optional fields, only include if not None/empty
                    value = getattr(row, field)
                    if value is not None and (not isinstance(value, str) or value.strip() != ""):
                        updated_fields[field] = value

            # Update the run in wizard (only with fields that have values)
            self.wizard.update_run(idx, **updated_fields)

            if group_id is not None:
                self.wizard.assign_run(idx, group_id=group_id, create_missing_group=True)
            elif "group_id" in self.wizard.runs[idx]:
                self.wizard.clear_run_field(idx, "group_id")

            # Remove fields that were explicitly cleared (None or empty string for optional fields)
            for field in RunFieldInfo.get_all_fields():
                if field not in {"file", "group_id"}:  # Never remove the required file field
                    value = getattr(row, field)
                    # If the field is None or empty string, remove it from wizard run
                    if value is None or (isinstance(value, str) and value.strip() == ""):
                        if field in self.wizard.runs[idx]:
                            # Use public API to remove fields that were previously present.
                            self.wizard.clear_run_field(idx, field)

    def sync_modification_edits(self, rows: List[ModificationSpreadsheetRow]) -> None:
        """
        Synchronize spreadsheet rows back to WizardState modifications.

        This validates all rows and updates the wizard modifications in-place.

        Args:
            rows: List of ModificationSpreadsheetRow instances to sync

        Raises:
            ValueError: If validation fails
        """
        for row in rows:
            row.validate()

        existing_profiles = self.wizard.get_modification_profiles()
        self.wizard.modifications = [row.to_dict() for row in rows]
        self.wizard.modification_profiles = []
        for profile in existing_profiles:
            self.wizard.register_modification_profile(profile)
        for modification in self.wizard.modifications:
            self.wizard.register_modification_profile(modification.get("profile"))

    def sync_group_edits(self, rows: List[GroupSpreadsheetRow]) -> None:
        """Synchronize group rows back to WizardState.

        Groups are editable in the Phase 2 authoring surface, so syncing
        validates and round-trips the worksheet rows back into WizardState.
        """
        if len(rows) != len(self.wizard.groups):
            raise ValueError(
                f"row count mismatch: spreadsheet has {len(rows)} rows but wizard has {len(self.wizard.groups)} groups"
            )

        for row_index, row in enumerate(rows):
            self.wizard.sync_group_sheet_row(
                row_index,
                id=row.id,
                name=row.name,
                labeling_strategy=row.labeling_strategy,
                description=row.description,
            )

    def get_row_by_index(self, index: int) -> Optional[SpreadsheetRow]:
        """
        Get a specific spreadsheet row by index.

        Args:
            index: Index of the row

        Returns:
            SpreadsheetRow or None if out of range
        """
        rows = self.wizard_to_spreadsheet()
        if 0 <= index < len(rows):
            return rows[index]
        return None

    def copy_field_down(
        self,
        field: str,
        from_row_index: int,
        to_row_index: Optional[int] = None,
    ) -> None:
        """
        Copy a field value down (fill-down) from one row to subsequent rows.

        This is groundwork for spreadsheet-style drag-copy behavior.
        The value from from_row_index is copied to all rows from from_row_index+1
        to to_row_index (inclusive). If to_row_index is None, copies to end of rows.

        Args:
            field: Field name to copy (must be a valid field)
            from_row_index: Starting row index (source of value)
            to_row_index: Ending row index (inclusive). If None, copies to last row.

        Raises:
            ValueError: If field is invalid, from_row_index is out of range, or range is invalid
        """
        # Validate field
        if field not in RunFieldInfo.get_all_fields():
            raise ValueError(
                f"Unknown field '{field}'. Valid fields: {RunFieldInfo.get_all_fields()}"
            )

        # Validate from_row_index
        if from_row_index < 0 or from_row_index >= len(self.wizard.runs):
            raise ValueError(
                f"from_row_index {from_row_index} out of range (0-{len(self.wizard.runs) - 1})"
            )

        # Default to_row_index to last row
        if to_row_index is None:
            to_row_index = len(self.wizard.runs) - 1

        # Validate to_row_index
        if to_row_index < from_row_index:
            raise ValueError(
                f"to_row_index {to_row_index} must be >= from_row_index {from_row_index}"
            )
        if to_row_index >= len(self.wizard.runs):
            raise ValueError(
                f"to_row_index {to_row_index} out of range (0-{len(self.wizard.runs) - 1})"
            )

        # Get the value from the source row
        source_run = self.wizard.runs[from_row_index]
        value_to_copy = source_run.get(field)

        # Copy the value to all target rows
        for idx in range(from_row_index + 1, to_row_index + 1):
            if value_to_copy is not None:
                self.wizard.update_run(idx, **{field: value_to_copy})
            else:
                # If source value is None, remove field from target if present
                self.wizard.clear_run_field(idx, field)

    def wizard_samples_to_spreadsheet(self) -> List["SampleSpreadsheetRow"]:
        """
        Convert WizardState.samples to spreadsheet rows.

        Returns:
            List of SampleSpreadsheetRow instances (one per sample)
        """
        rows = []
        for idx, sample in enumerate(self.wizard.samples):
            row = SampleSpreadsheetRow.from_wizard_sample(sample, row_index=idx)
            rows.append(row)
        return rows

    def spreadsheet_row_to_wizard_sample(self, row: "SampleSpreadsheetRow") -> Dict[str, Any]:
        """
        Convert a spreadsheet row to a wizard sample dict.

        Args:
            row: SampleSpreadsheetRow to convert

        Returns:
            Dictionary suitable for WizardState
        """
        return row.to_dict()

    def sync_sample_edits(self, rows: List["SampleSpreadsheetRow"]) -> None:
        """
        Synchronize spreadsheet rows back to WizardState samples.

        This validates all rows and updates the wizard samples in-place.

        Args:
            rows: List of SampleSpreadsheetRow instances to sync

        Raises:
            ValueError: If validation fails
        """
        # Validate all rows
        for row in rows:
            row.validate()

        # Replace wizard samples with synced rows
        self.wizard.samples = [row.to_dict() for row in rows]

    def wizard_mixtures_to_spreadsheet(self) -> List["MixtureSpreadsheetRow"]:
        """
        Convert WizardState.mixtures to spreadsheet rows.

        Returns:
            List of MixtureSpreadsheetRow instances (one per mixture)
        """
        rows = []
        for idx, mixture in enumerate(self.wizard.mixtures):
            row = MixtureSpreadsheetRow.from_wizard_mixture(mixture, row_index=idx)
            rows.append(row)
        return rows

    def spreadsheet_row_to_wizard_mixture(self, row: "MixtureSpreadsheetRow") -> Dict[str, Any]:
        """
        Convert a spreadsheet row to a wizard mixture dict.

        Args:
            row: MixtureSpreadsheetRow to convert

        Returns:
            Dictionary suitable for WizardState
        """
        return row.to_dict()

    def sync_mixture_edits(self, rows: List["MixtureSpreadsheetRow"]) -> None:
        """
        Synchronize spreadsheet rows back to WizardState mixtures.

        This validates all rows and all referenced samples exist, then updates the wizard.

        Args:
            rows: List of MixtureSpreadsheetRow instances to sync

        Raises:
            ValueError: If validation fails or referenced sample does not exist
        """
        # Validate all rows and sample references
        for row in rows:
            row.validate()
            # Validate that all referenced samples exist
            sample_ids = {s["id"] for s in self.wizard.samples}
            for channel, sample_id in row.channels.items():
                if sample_id not in sample_ids:
                    raise ValueError(
                        f"Sample '{sample_id}' referenced in channel '{channel}' not found in samples"
                    )

        # Replace wizard mixtures with synced rows
        self.wizard.mixtures = [row.to_dict() for row in rows]

    def get_assignment_headers_for_quantification(self, quantification_method: Optional[str]) -> List[str]:
        """
        Get assignment column headers based on quantification method.

        Args:
            quantification_method: "LFQ", "TMT", "iTRAQ", "SILAC", or None

        Returns:
            List of field names appropriate for the quantification method
        """
        # Determine if multiplexed (TMT, iTRAQ, SILAC)
        is_multiplexed = quantification_method in ("TMT", "iTRAQ", "SILAC")

        headers = ["run_file"]
        if is_multiplexed:
            headers.append("mixture")
        else:
            # LFQ or non-multiplexed (default)
            headers.append("sample")

        return headers

    def wizard_assignments_to_spreadsheet(self, quantification_method: Optional[str]) -> List["AssignmentSpreadsheetRow"]:
        """
        Convert WizardState.runs to assignment spreadsheet rows.

        Args:
            quantification_method: Quantification method to determine linkage type

        Returns:
            List of AssignmentSpreadsheetRow instances (one per run)
        """
        rows = []
        for idx, run in enumerate(self.wizard.runs):
            row = AssignmentSpreadsheetRow.from_wizard_run(
                run,
                row_index=idx,
                quantification_method=quantification_method
            )
            rows.append(row)
        return rows

    def sync_assignment_edits(
        self,
        rows: List["AssignmentSpreadsheetRow"],
        quantification_method: Optional[str]
    ) -> None:
        """
        Synchronize spreadsheet assignment rows back to WizardState.

        This validates all rows and updates the wizard runs in-place.

        Args:
            rows: List of AssignmentSpreadsheetRow instances to sync
            quantification_method: Quantification method for validation

        Raises:
            ValueError: If validation fails or referenced sample/mixture does not exist
        """
        # Determine if multiplexed
        is_multiplexed = quantification_method in ("TMT", "iTRAQ", "SILAC")

        # Validate references
        sample_ids = {s["id"] for s in self.wizard.samples}
        mixture_ids = {m["id"] for m in self.wizard.mixtures}

        for row in rows:
            row.validate()

            # Validate references exist
            if row.sample is not None and row.sample not in sample_ids:
                raise ValueError(f"Sample '{row.sample}' not found in samples")
            if row.mixture is not None and row.mixture not in mixture_ids:
                raise ValueError(f"Mixture '{row.mixture}' not found in mixtures")

        # Update wizard runs
        for idx, row in enumerate(rows):
            if row.sample is not None:
                self.wizard.update_run(idx, sample=row.sample)
                # For non-multiplexed, clear mixture field
                self.wizard.clear_run_field(idx, "mixture")
            elif row.mixture is not None:
                self.wizard.update_run(idx, mixture=row.mixture)
                # For multiplexed, clear sample field
                self.wizard.clear_run_field(idx, "sample")
            else:
                # Neither sample nor mixture set - clear both
                if "sample" in self.wizard.runs[idx]:
                    self.wizard.clear_run_field(idx, "sample")
                if "mixture" in self.wizard.runs[idx]:
                    self.wizard.clear_run_field(idx, "mixture")


class SampleFieldInfo:
    """Metadata about sample fields for the adapter."""

    FIELD_METADATA = {
        "id": {
            "type": "str",
            "required": True,
            "description": "Unique sample identifier",
        },
        "organism": {
            "type": "str",
            "required": False,
            "description": "Species (e.g., homo sapiens)",
        },
        "organism_part": {
            "type": "str",
            "required": False,
            "description": "Tissue/compartment (e.g., liver)",
        },
        "condition": {
            "type": "str",
            "required": False,
            "description": "Experimental condition",
        },
        "biological_replicate": {
            "type": "int",
            "required": False,
            "description": "Biological replicate number",
        },
        "technical_replicate": {
            "type": "int",
            "required": False,
            "description": "Technical replicate number",
        },
        "disease": {
            "type": "str",
            "required": False,
            "description": "Disease state",
        },
        "cell_type": {
            "type": "str",
            "required": False,
            "description": "Cell type",
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        """Get all available field names."""
        return list(SampleFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        """Get metadata for a specific field."""
        if field not in SampleFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return SampleFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        """Get list of required fields."""
        return [
            field
            for field, info in SampleFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


@dataclass
class SampleSpreadsheetRow:
    """Represents a single spreadsheet row corresponding to a sample."""

    id: Optional[str] = None
    organism: Optional[str] = None
    organism_part: Optional[str] = None
    condition: Optional[str] = None
    biological_replicate: Optional[int] = None
    technical_replicate: Optional[int] = None
    disease: Optional[str] = None
    cell_type: Optional[str] = None
    row_index: int = 0

    @classmethod
    def from_wizard_sample(cls, sample: Dict[str, Any], row_index: int = 0) -> "SampleSpreadsheetRow":
        """
        Create a spreadsheet row from a wizard sample dict.

        Args:
            sample: Dictionary from WizardState.samples
            row_index: Index of this row (for reference)

        Returns:
            SampleSpreadsheetRow instance
        """
        return cls(
            id=sample.get("id"),
            organism=sample.get("organism"),
            organism_part=sample.get("organism_part"),
            condition=sample.get("condition"),
            biological_replicate=sample.get("biological_replicate"),
            technical_replicate=sample.get("technical_replicate"),
            disease=sample.get("disease"),
            cell_type=sample.get("cell_type"),
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert row to dict, excluding None values.

        Returns:
            Dictionary suitable for wizard.add_sample() or samples list
        """
        result = {}
        if self.id is not None:
            result["id"] = self.id
        if self.organism is not None and (not isinstance(self.organism, str) or self.organism.strip() != ""):
            result["organism"] = self.organism
        if self.organism_part is not None and (not isinstance(self.organism_part, str) or self.organism_part.strip() != ""):
            result["organism_part"] = self.organism_part
        if self.condition is not None and (not isinstance(self.condition, str) or self.condition.strip() != ""):
            result["condition"] = self.condition
        if self.biological_replicate is not None:
            result["biological_replicate"] = self.biological_replicate
        if self.technical_replicate is not None:
            result["technical_replicate"] = self.technical_replicate
        if self.disease is not None and (not isinstance(self.disease, str) or self.disease.strip() != ""):
            result["disease"] = self.disease
        if self.cell_type is not None and (not isinstance(self.cell_type, str) or self.cell_type.strip() != ""):
            result["cell_type"] = self.cell_type
        return result

    def validate(self) -> None:
        """
        Validate row against field constraints.

        Raises:
            ValueError: If validation fails
        """
        # Check required fields
        if not self.id:
            raise ValueError("Sample ID is required")

        for field_name in ("biological_replicate", "technical_replicate"):
            value = getattr(self, field_name)
            if isinstance(value, str):
                if value.strip() == "":
                    setattr(self, field_name, None)
                    continue
                try:
                    setattr(self, field_name, int(value))
                except (TypeError, ValueError):
                    raise ValueError(f"{field_name} must be an integer")

    def update(self, **kwargs) -> None:
        """Update row fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


class MixtureFieldInfo:
    """Metadata about mixture fields for the adapter."""

    FIELD_METADATA = {
        "id": {
            "type": "str",
            "required": True,
            "description": "Unique mixture identifier",
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        """Get all available field names."""
        return list(MixtureFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        """Get metadata for a specific field."""
        if field not in MixtureFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return MixtureFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        """Get list of required fields."""
        return [
            field
            for field, info in MixtureFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


@dataclass
class MixtureSpreadsheetRow:
    """Represents a single spreadsheet row corresponding to a mixture."""

    id: Optional[str] = None
    channels: Dict[str, str] = None
    row_index: int = 0

    def __post_init__(self):
        """Initialize channels dict if not provided."""
        if self.channels is None:
            self.channels = {}

    @classmethod
    def from_wizard_mixture(cls, mixture: Dict[str, Any], row_index: int = 0) -> "MixtureSpreadsheetRow":
        """
        Create a spreadsheet row from a wizard mixture dict.

        Args:
            mixture: Dictionary from WizardState.mixtures
            row_index: Index of this row (for reference)

        Returns:
            MixtureSpreadsheetRow instance
        """
        return cls(
            id=mixture.get("id"),
            channels=mixture.get("channels", {}).copy(),
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert row to dict.

        Returns:
            Dictionary suitable for wizard.add_mixture() or mixtures list
        """
        result = {}
        if self.id is not None:
            result["id"] = self.id
        if self.channels:
            result["channels"] = self.channels.copy()
        return result

    def validate(self) -> None:
        """
        Validate row against field constraints.

        Raises:
            ValueError: If validation fails
        """
        # Mixture id is required
        if not self.id or (isinstance(self.id, str) and self.id.strip() == ""):
            raise ValueError("Mixture ID is required")
        # At least one channel is required
        if not self.channels:
            raise ValueError("At least one channel is required")

    def update(self, **kwargs) -> None:
        """Update row fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


class AssignmentFieldInfo:
    """Metadata about assignment fields for the adapter."""

    FIELD_METADATA = {
        "run_file": {
            "type": "str",
            "required": True,
            "read_only": True,
            "description": "Run file name (read-only reference)",
        },
        "sample": {
            "type": "str",
            "required": False,
            "description": "Sample ID (for LFQ)",
        },
        "mixture": {
            "type": "str",
            "required": False,
            "description": "Mixture ID (for multiplexed quantification)",
        },
    }

    @staticmethod
    def get_all_fields() -> List[str]:
        """Get all available field names."""
        return list(AssignmentFieldInfo.FIELD_METADATA.keys())

    @staticmethod
    def get_field_info(field: str) -> Dict[str, Any]:
        """Get metadata for a specific field."""
        if field not in AssignmentFieldInfo.FIELD_METADATA:
            raise ValueError(f"Unknown field: {field}")
        return AssignmentFieldInfo.FIELD_METADATA[field]

    @staticmethod
    def get_required_fields() -> List[str]:
        """Get list of required fields."""
        return [
            field
            for field, info in AssignmentFieldInfo.FIELD_METADATA.items()
            if info["required"]
        ]


@dataclass
class AssignmentSpreadsheetRow:
    """Represents a single spreadsheet row for run-to-sample/mixture assignment."""

    run_file: Optional[str] = None
    sample: Optional[str] = None
    mixture: Optional[str] = None
    row_index: int = 0

    @classmethod
    def from_wizard_run(
        cls,
        run: Dict[str, Any],
        row_index: int = 0,
        quantification_method: Optional[str] = None
    ) -> "AssignmentSpreadsheetRow":
        """
        Create an assignment row from a wizard run dict.

        Args:
            run: Dictionary from WizardState.runs
            row_index: Index of this row (for reference)
            quantification_method: Quantification method to determine linkage type

        Returns:
            AssignmentSpreadsheetRow instance
        """
        # Determine if multiplexed (TMT, iTRAQ, SILAC)
        is_multiplexed = quantification_method in ("TMT", "iTRAQ", "SILAC")

        return cls(
            run_file=run.get("file"),
            sample=run.get("sample") if not is_multiplexed else None,
            mixture=run.get("mixture") if is_multiplexed else None,
            row_index=row_index,
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert row to dict, excluding None values.

        Returns:
            Dictionary suitable for updating wizard run
        """
        result = {}
        if self.sample is not None:
            result["sample"] = self.sample
        if self.mixture is not None:
            result["mixture"] = self.mixture
        return result

    def validate(self) -> None:
        """
        Validate row against field constraints.

        Raises:
            ValueError: If validation fails
        """
        # run_file is required and must be present
        if not self.run_file:
            raise ValueError("Required field 'run_file' is missing")

        # sample and mixture are optional

    def update(self, **kwargs) -> None:
        """Update row fields."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
