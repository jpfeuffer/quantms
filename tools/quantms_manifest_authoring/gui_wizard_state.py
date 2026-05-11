#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "pyyaml",
# ]
# ///
"""
Wizard state management for quantms manifest authoring.

Provides WizardStep enum and WizardState class for managing the sequential,
non-skippable wizard workflow for YAML manifest creation. This module has
no UI dependencies and can be imported and tested independently.
"""

from copy import deepcopy
from enum import Enum, auto
import re
from typing import Optional, Dict, List, Any
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from manifest_core import ManifestState, Run, Sample, Mixture, Experiment, ChannelBuilder


GROUP_KIND_OPTIONS = ["LFQ", "TMT", "iTRAQ", "SILAC"]
LFQ_LABELING_STRATEGY = "label free sample"
MAIN_FLOW_PAGE_LABELS = [
    "Runs + Modifications + Experiment",
    "Group Details",
    "Review",
]
_UNSET = object()


class WizardStep(Enum):
    """Enumeration of wizard steps in order."""
    RUNS = auto()
    SAMPLES = auto()
    MIXTURES = auto()
    EXPERIMENT = auto()
    ASSIGNMENTS = auto()
    REVIEW = auto()

    @classmethod
    def ordered_steps(cls) -> List["WizardStep"]:
        """Get steps in order."""
        return [cls.RUNS, cls.SAMPLES, cls.MIXTURES, cls.EXPERIMENT, cls.ASSIGNMENTS, cls.REVIEW]

    def get_index(self) -> int:
        """Get the index of this step (0-based)."""
        return self.ordered_steps().index(self)


class WizardState:
    """
    Manages wizard state for sequential manifest authoring.

    Ensures runs are entered first, enforces sequential step progression,
    and defers validation until the review step.
    """

    def __init__(self):
        """Initialize wizard state."""
        self.current_step_index = 0
        self.active_group_id: Optional[str] = None
        self.runs: List[Dict[str, Any]] = []
        self.samples: List[Dict[str, Any]] = []
        self.mixtures: List[Dict[str, Any]] = []
        self.groups: List[Dict[str, Any]] = []
        self.modifications: List[Dict[str, Any]] = []
        self.modification_profiles: List[str] = []
        self.active_modification_profile: Optional[str] = None
        self._pending_modification_draft: Dict[str, Any] = {}
        self.experiment: Optional[Dict[str, Any]] = None
        self._experiment_settings_saved = False
        self._active_editor: Optional[Any] = None
        self._run_counter = 0

    def get_current_step(self) -> WizardStep:
        """Get the current wizard step."""
        steps = WizardStep.ordered_steps()
        return steps[self.current_step_index]

    def get_main_flow_page_index(self) -> int:
        """Map the legacy step index to the three visible authoring pages."""
        if self.current_step_index <= WizardStep.RUNS.get_index():
            return 0
        if self.current_step_index < WizardStep.REVIEW.get_index():
            return 1
        return 2

    @classmethod
    def get_main_flow_page_labels(cls) -> List[str]:
        """Return the visible page labels for the revised main wizard flow."""
        return MAIN_FLOW_PAGE_LABELS.copy()

    def set_current_step_index(self, index: int) -> None:
        """
        Set the current step by index.

        Enforces sequential progression - cannot skip ahead.

        Args:
            index: Step index to set (0-based)

        Raises:
            ValueError: If trying to skip steps or go out of bounds
        """
        steps = WizardStep.ordered_steps()

        if index < 0 or index >= len(steps):
            raise ValueError(f"Step index {index} out of range")

        # Can only move forward sequentially or go back
        if index > self.current_step_index:
            # Moving forward - can only advance one step at a time
            if index != self.current_step_index + 1:
                raise ValueError(f"Cannot skip steps: currently at {self.current_step_index}, cannot jump to {index}")

            # If advancing to next step, validate prerequisites
            current_step = self.get_current_step()
            if current_step == WizardStep.RUNS:
                if not self.runs:
                    raise ValueError("At least one run is required before advancing past the RUNS step")
            elif current_step == WizardStep.EXPERIMENT:
                if not self._experiment_settings_saved:
                    raise ValueError("Experiment settings must be saved before advancing to the review step")

        if index != self.current_step_index:
            self.clear_active_group()

        self.current_step_index = index

    def set_active_editor(self, editor: Optional[Any]) -> None:
        """
        Register an active editor for pre-navigation flush.

        Args:
            editor: The editor instance to flush before navigation, or None to clear
        """
        self._active_editor = editor

    def get_active_editor(self) -> Optional[Any]:
        """
        Get the currently registered active editor.

        Returns:
            The active editor instance, or None if no editor is registered
        """
        return self._active_editor

    def next_step(self) -> None:
        """
        Advance to the next step.

        Raises:
            ValueError: If already at the last step or prerequisites not met
        """
        # Flush active editor before stepping
        self._flush_active_editor()

        steps = WizardStep.ordered_steps()
        if self.current_step_index >= len(steps) - 1:
            raise ValueError("Cannot advance past the last step (REVIEW)")

        self.set_current_step_index(self.current_step_index + 1)

    def previous_step(self) -> None:
        """
        Go back to the previous step.

        Raises:
            ValueError: If already at the first step
        """
        # Flush active editor before stepping
        self._flush_active_editor()

        if self.current_step_index <= 0:
            raise ValueError("Cannot go back from the first step (RUNS)")

        self.clear_active_group()
        self.current_step_index -= 1

    def _flush_active_editor(self) -> None:
        """
        Internal: Flush pending edits from the active editor if registered.

        NOTE: In the async migration, this is now a no-op since the real flush
        happens in the async button handlers (gui_nicegui.py) which await the
        flush_pending_edits coroutine before calling next_step()/previous_step().

        This method is kept for backward compatibility but is not used in the
        new async flow.
        """
        # The async button handlers in gui_nicegui.py handle the flush directly
        # by awaiting flush_pending_edits() before calling next_step/previous_step
        pass

    @staticmethod
    def _infer_fraction_from_file_name(file: str) -> Optional[int]:
        """Infer a fraction number from a run filename when it follows a supported pattern."""
        file_name = re.split(r"[\\/]", str(file or ""))[-1]
        file_stem = Path(file_name).stem

        for pattern in (
            r"(?i)fraction(\d+)",
            r"(?i)frac(\d+)",
            r"(?i)(?:^|[^A-Za-z])f(\d+)",
        ):
            match = re.search(pattern, file_stem)
            if match:
                return int(match.group(1))

        return None

    @staticmethod
    def _infer_group_id_from_file_name(file: str) -> Optional[str]:
        """Infer a group seed from the basename after removing supported fraction markers."""
        file_name = re.split(r"[\\/]", str(file or ""))[-1]
        file_stem = Path(file_name).stem

        normalized_stem = file_stem
        fraction_marker_found = False
        for pattern in (
            r"(?i)fraction(\d+)",
            r"(?i)frac(\d+)",
            r"(?i)(?:^|[^A-Za-z])f(\d+)",
        ):
            updated_stem, replacements = re.subn(pattern, "", normalized_stem)
            if replacements:
                fraction_marker_found = True
                normalized_stem = updated_stem

        if not fraction_marker_found:
            return None

        normalized_stem = re.sub(r"[\s._-]+", " ", normalized_stem).strip()
        normalized_stem = re.sub(r"\s+", " ", normalized_stem)
        return normalized_stem or None

    def _ensure_group_exists(
        self,
        group_id: str,
        *,
        kind: str = "manual",
        labeling_strategy: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> None:
        """Create a group record if it does not already exist."""
        if not group_id:
            return

        if any(group.get("id") == group_id for group in self.groups):
            return

        self.add_group(
            id=group_id,
            name=name or group_id,
            kind=kind,
            labeling_strategy=labeling_strategy,
            description=description,
        )

    def get_allowed_group_kinds(self) -> List[str]:
        """Return the allowed group kind options for the current experiment state."""
        quantification_method = self.experiment.get("quantification_method") if self.experiment else None
        if quantification_method:
            normalized_method = str(quantification_method).strip()
            for allowed_kind in GROUP_KIND_OPTIONS:
                if allowed_kind.casefold() == normalized_method.casefold():
                    return [allowed_kind]
        return GROUP_KIND_OPTIONS.copy()

    def get_allowed_labeling_strategies(self, kind: Optional[str] = None) -> List[str]:
        """Return supported labeling strategies for a group kind or for all currently allowed kinds."""
        if kind is not None:
            normalized_kind = self._normalize_group_kind(kind)
            if normalized_kind == "LFQ":
                return [LFQ_LABELING_STRATEGY]
            if normalized_kind in {"TMT", "iTRAQ", "SILAC"}:
                return [
                    plex_type
                    for plex_type in ChannelBuilder.get_supported_plex_types()
                    if plex_type.startswith(normalized_kind)
                ]
            return []

        strategies: List[str] = []
        for allowed_kind in self.get_allowed_group_kinds():
            for strategy in self.get_allowed_labeling_strategies(allowed_kind):
                if strategy not in strategies:
                    strategies.append(strategy)
        return strategies

    def set_active_group_id(self, group_id: Optional[str]) -> None:
        """Set the currently open group detail page."""
        if group_id is None:
            self.active_group_id = None
            return

        self._get_group_index(group_id)
        self.active_group_id = group_id

    def get_active_group_id(self) -> Optional[str]:
        """Return the group currently shown in the detail flow, if any."""
        return self.active_group_id

    def clear_active_group(self) -> None:
        """Close the active group detail flow."""
        self.active_group_id = None

    def get_active_group(self) -> Optional[Dict[str, Any]]:
        """Return a defensive copy of the group currently shown in the detail flow."""
        if not self.active_group_id:
            return None

        try:
            group_index = self._get_group_index(self.active_group_id)
        except ValueError:
            self.active_group_id = None
            return None

        return deepcopy(self.groups[group_index])

    def set_group_sample_target(self, group_id: str, sample_id: Optional[str]) -> None:
        """Store the LFQ sample target for an authoring group."""
        group_index = self._get_group_index(group_id)
        if sample_id is None:
            self.groups[group_index].pop("sample_target", None)
            return

        sample_ids = {sample["id"] for sample in self.samples}
        if sample_id not in sample_ids:
            raise ValueError(f"Sample '{sample_id}' not found in samples")

        self.groups[group_index]["sample_target"] = sample_id

    def get_group_sample_target(self, group_id: str) -> Optional[str]:
        """Get the stored LFQ sample target for a group."""
        group_index = self._get_group_index(group_id)
        return self.groups[group_index].get("sample_target")

    def set_group_channel_assignments(self, group_id: str, channel_assignments: Dict[str, Optional[str]]) -> None:
        """Store channel-to-sample assignments for a multiplexed group."""
        group_index = self._get_group_index(group_id)
        normalized_assignments: Dict[str, Optional[str]] = {}
        sample_ids = {sample["id"] for sample in self.samples}

        for channel, sample_id in channel_assignments.items():
            if sample_id is None:
                normalized_assignments[str(channel)] = None
                continue

            sample_text = str(sample_id).strip()
            if not sample_text:
                normalized_assignments[str(channel)] = None
                continue

            if sample_text not in sample_ids:
                raise ValueError(f"Sample '{sample_text}' not found in samples")

            normalized_assignments[str(channel)] = sample_text

        self.groups[group_index]["channel_sample_assignments"] = normalized_assignments

    def get_group_channel_assignments(self, group_id: str) -> Dict[str, Optional[str]]:
        """Get the stored channel-to-sample assignments for a group."""
        group_index = self._get_group_index(group_id)
        return dict(self.groups[group_index].get("channel_sample_assignments", {}))

    def get_group_channel_sheet_strategies(self) -> List[str]:
        """Return the distinct labeling strategies currently present in authoring groups."""
        strategies: List[str] = []
        for group in self.groups:
            strategy = self._normalize_labeling_strategy(group.get("labeling_strategy"))
            if not strategy:
                strategy = self.get_default_labeling_strategy(group.get("kind"))
            if strategy and strategy not in strategies:
                strategies.append(strategy)
        return strategies

    def get_group_ids_for_labeling_strategy(self, labeling_strategy: Optional[str]) -> List[str]:
        """Return the group ids that use a specific labeling strategy."""
        normalized_strategy = self._normalize_labeling_strategy(labeling_strategy)
        if not normalized_strategy:
            return []

        group_ids: List[str] = []
        for group in self.groups:
            group_strategy = self._normalize_labeling_strategy(group.get("labeling_strategy"))
            if not group_strategy:
                group_strategy = self.get_default_labeling_strategy(group.get("kind"))
            if group_strategy == normalized_strategy:
                group_ids.append(str(group.get("id") or ""))
        return [group_id for group_id in group_ids if group_id]

    def get_default_labeling_strategy(self, kind: Optional[str]) -> Optional[str]:
        """Get the first supported labeling strategy for a kind, if any."""
        strategies = self.get_allowed_labeling_strategies(kind)
        return strategies[0] if strategies else None

    def get_labeling_strategy_channel_count(self, labeling_strategy: Optional[str]) -> Optional[int]:
        """Derive the number of channels from a labeling strategy."""
        normalized_strategy = self._normalize_labeling_strategy(labeling_strategy)
        if not normalized_strategy:
            return None
        if normalized_strategy == LFQ_LABELING_STRATEGY:
            return 1

        try:
            return len(ChannelBuilder(normalized_strategy).get_available_channels())
        except ValueError:
            return None

    @staticmethod
    def _derive_group_kind_from_labeling_strategy(labeling_strategy: Any) -> Optional[str]:
        """Derive the canonical group kind from a labeling strategy."""
        if labeling_strategy is None:
            return None

        normalized_strategy = str(labeling_strategy).strip()
        if not normalized_strategy:
            return None

        if normalized_strategy.casefold() == LFQ_LABELING_STRATEGY.casefold():
            return "LFQ"

        for group_kind in ("TMT", "iTRAQ", "SILAC"):
            if normalized_strategy.casefold().startswith(group_kind.casefold()):
                return group_kind

        return None

    def _normalize_labeling_strategy(self, labeling_strategy: Any) -> Optional[str]:
        """Normalize a labeling strategy using the runtime ChannelBuilder catalog."""
        if labeling_strategy is None:
            return None

        normalized_strategy = str(labeling_strategy).strip()
        if not normalized_strategy:
            return None

        for allowed_strategy in self.get_allowed_labeling_strategies():
            if allowed_strategy.casefold() == normalized_strategy.casefold():
                return allowed_strategy

        if normalized_strategy.casefold() == LFQ_LABELING_STRATEGY.casefold():
            return LFQ_LABELING_STRATEGY

        return None

    def _resolve_group_labeling_metadata(
        self,
        kind: Any = _UNSET,
        *,
        labeling_strategy: Any = _UNSET,
        existing_group: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve the supported labeling strategy and derived channel count for a group."""
        if labeling_strategy is not _UNSET:
            candidate_strategy = labeling_strategy
        elif kind is not _UNSET and kind is not None:
            normalized_kind = self._normalize_group_kind(kind)
            if normalized_kind is None:
                raise ValueError(f"Group kind '{kind}' is not allowed")
            candidate_strategy = self.get_default_labeling_strategy(normalized_kind)
        else:
            candidate_strategy = existing_group.get("labeling_strategy") if existing_group else None
            if not candidate_strategy and existing_group:
                candidate_strategy = self.get_default_labeling_strategy(existing_group.get("kind"))

        normalized_strategy = self._normalize_labeling_strategy(candidate_strategy)
        if not normalized_strategy:
            allowed_strategies = self.get_allowed_labeling_strategies()
            allowed_text = ", ".join(allowed_strategies) if allowed_strategies else "none"
            raise ValueError(
                f"Labeling strategy '{candidate_strategy}' is not allowed. Allowed options: {allowed_text}"
            )

        derived_kind = self._derive_group_kind_from_labeling_strategy(normalized_strategy)
        if derived_kind is None:
            raise ValueError(f"Labeling strategy '{normalized_strategy}' is not supported")

        allowed_kinds = self.get_allowed_group_kinds()
        if derived_kind not in allowed_kinds:
            allowed_strategies = self.get_allowed_labeling_strategies()
            allowed_text = ", ".join(allowed_strategies) if allowed_strategies else "none"
            raise ValueError(
                f"Labeling strategy '{normalized_strategy}' is not allowed. Allowed options: {allowed_text}"
            )

        if kind is not _UNSET and kind is not None:
            normalized_kind = self._normalize_group_kind(kind)
            if normalized_kind is None:
                raise ValueError(f"Group kind '{kind}' is not allowed")
            if normalized_kind != derived_kind:
                raise ValueError(
                    f"Group kind '{kind}' does not match labeling strategy '{normalized_strategy}'"
                )

        channel_count = self.get_labeling_strategy_channel_count(normalized_strategy)
        metadata: Dict[str, Any] = {
            "kind": derived_kind,
            "labeling_strategy": normalized_strategy,
        }
        if channel_count is not None:
            metadata["channel_count"] = channel_count
        return metadata

    def ensure_group_labeling_metadata(
        self,
        group: Dict[str, Any],
        *,
        kind: Any = _UNSET,
        labeling_strategy: Any = _UNSET,
    ) -> None:
        """Backfill or normalize a group's labeling strategy metadata in-place."""
        metadata = self._resolve_group_labeling_metadata(
            kind,
            labeling_strategy=labeling_strategy,
            existing_group=group,
        )

        group.update(metadata)

    def _normalize_group_kind(self, kind: Any) -> Optional[str]:
        """Normalize a canonical group kind value to its expected casing."""
        if kind is None:
            return None

        normalized_kind = str(kind).strip()
        if not normalized_kind:
            return None

        for allowed_kind in GROUP_KIND_OPTIONS:
            if allowed_kind.casefold() == normalized_kind.casefold():
                return allowed_kind

        return None

    def normalize_group_kind(self, kind: Any) -> Optional[str]:
        """Public wrapper for normalizing a group kind value."""
        return self._normalize_group_kind(kind)

    def _get_run_index_by_id(self, run_id: str) -> int:
        """Return the index of a run by its internal identifier."""
        for index, run in enumerate(self.runs):
            if run.get("id") == run_id:
                return index
        raise ValueError(f"Run '{run_id}' not found in runs")

    @staticmethod
    def _normalize_optional_group_text(value: Any) -> Optional[str]:
        """Normalize optional text fields used by spreadsheet-authored group rows."""
        if value is None:
            return None

        normalized = str(value).strip()
        return normalized or None

    def _ensure_unique_group_id(self, group_id: str, *, exclude_index: Optional[int] = None) -> None:
        """Ensure a group identifier is unique within the current wizard state."""
        for index, group in enumerate(self.groups):
            if exclude_index is not None and index == exclude_index:
                continue
            if group.get("id") == group_id:
                raise ValueError(f"Group '{group_id}' already exists")

    def _ensure_unique_sample_id(self, sample_id: str, *, exclude_index: Optional[int] = None) -> None:
        """Ensure a sample identifier is unique within the current wizard state."""
        for index, sample in enumerate(self.samples):
            if exclude_index is not None and index == exclude_index:
                continue
            if sample.get("id") == sample_id:
                raise ValueError(f"Sample '{sample_id}' already exists")

    def rename_group(self, old_id: str, new_id: Any) -> None:
        """Rename a group identifier and cascade the change into run assignments."""
        normalized_new_id = self._normalize_optional_group_text(new_id)
        if not normalized_new_id:
            raise ValueError("Group ID is required")

        group_index = self._get_group_index(old_id)
        current_group = self.groups[group_index]
        if current_group.get("id") == normalized_new_id:
            return

        self._ensure_unique_group_id(normalized_new_id, exclude_index=group_index)
        current_group["id"] = normalized_new_id

        for run in self.runs:
            if run.get("group_id") == old_id:
                run["group_id"] = normalized_new_id

        if self.active_group_id == old_id:
            self.active_group_id = normalized_new_id

    def sync_group_sheet_row(
        self,
        row_index: int,
        *,
        id: Any = _UNSET,
        name: Any = _UNSET,
        labeling_strategy: Any = _UNSET,
        description: Any = _UNSET,
    ) -> None:
        """Apply a Groups-sheet row edit without requiring the row to be complete yet."""
        if row_index < 0 or row_index > len(self.groups):
            raise ValueError(f"Row index {row_index} out of range")

        if row_index == len(self.groups):
            self.groups.append({"members": []})

        group = self.groups[row_index]
        group.setdefault("members", [])

        if id is not _UNSET:
            normalized_id = self._normalize_optional_group_text(id)
            current_id = group.get("id")
            if current_id:
                if not normalized_id:
                    raise ValueError("Group ID is required")
                if normalized_id != current_id:
                    self.rename_group(current_id, normalized_id)
                    group = self.groups[row_index]
            elif normalized_id:
                self._ensure_unique_group_id(normalized_id, exclude_index=row_index)
                group["id"] = normalized_id

        if name is not _UNSET:
            normalized_name = self._normalize_optional_group_text(name)
            if normalized_name is None:
                group.pop("name", None)
            else:
                group["name"] = normalized_name

        if description is not _UNSET:
            normalized_description = self._normalize_optional_group_text(description)
            if normalized_description is None:
                group.pop("description", None)
            else:
                group["description"] = normalized_description

        if labeling_strategy is not _UNSET:
            normalized_strategy = self._normalize_optional_group_text(labeling_strategy)
            if normalized_strategy is None:
                group.pop("labeling_strategy", None)
                group.pop("kind", None)
                group.pop("channel_count", None)
            else:
                self.ensure_group_labeling_metadata(group, labeling_strategy=normalized_strategy)

        has_visible_values = any(
            self._normalize_optional_group_text(group.get(field))
            for field in ("id", "name", "labeling_strategy", "description")
        )
        has_linked_state = bool(group.get("members")) or bool(group.get("sample_target")) or bool(group.get("channel_sample_assignments"))
        if not has_visible_values and not has_linked_state:
            removed_group = self.groups.pop(row_index)
            removed_group_id = removed_group.get("id")
            if removed_group_id and self.active_group_id == removed_group_id:
                self.active_group_id = None

    def validate_groups_for_runs_step(self) -> None:
        """Validate that all authored groups are complete before leaving the Runs page."""
        seen_ids: set[str] = set()

        for row_index, group in enumerate(self.groups):
            group_id = self._normalize_optional_group_text(group.get("id"))
            group_name = self._normalize_optional_group_text(group.get("name"))
            group_strategy = self._normalize_optional_group_text(group.get("labeling_strategy"))

            missing_fields: list[str] = []
            if not group_id:
                missing_fields.append("id")
            if not group_name:
                missing_fields.append("name")
            if not group_strategy:
                missing_fields.append("labeling_strategy")

            if missing_fields:
                missing_text = ", ".join(missing_fields)
                raise ValueError(f"Group row {row_index + 1} is incomplete: missing {missing_text}")

            normalized_group_id = str(group_id)
            if normalized_group_id in seen_ids:
                raise ValueError(f"Group '{normalized_group_id}' already exists")
            seen_ids.add(normalized_group_id)

            group["id"] = normalized_group_id
            group["name"] = group_name
            self.ensure_group_labeling_metadata(group, labeling_strategy=group_strategy)

    def update_group(
        self,
        group_id: str,
        *,
        name: Any = _UNSET,
        kind: Any = _UNSET,
        labeling_strategy: Any = _UNSET,
        members: Any = _UNSET,
        description: Any = _UNSET,
    ) -> None:
        """Update an existing authoring group and keep run membership in sync."""
        group_index = self._get_group_index(group_id)
        group = self.groups[group_index]

        if name is not _UNSET:
            normalized_name = str(name).strip() if name is not None else ""
            if not normalized_name:
                raise ValueError("Group name is required")
            group["name"] = normalized_name

        if kind is not _UNSET:
            normalized_kind = str(kind).strip() if kind is not None else ""
            if not normalized_kind:
                raise ValueError("Group kind is required")

        self.ensure_group_labeling_metadata(
            group,
            kind=kind if kind is not _UNSET else _UNSET,
            labeling_strategy=labeling_strategy,
        )

        if description is not _UNSET:
            normalized_description = str(description).strip() if description is not None else ""
            if normalized_description:
                group["description"] = normalized_description
            else:
                group.pop("description", None)

        if members is not _UNSET:
            if members is None:
                member_ids: List[str] = []
            elif isinstance(members, str):
                member_ids = [member.strip() for member in members.split(",") if member.strip()]
            else:
                member_ids = []
                for member in members:
                    member_text = str(member).strip()
                    if member_text:
                        member_ids.append(member_text)

            deduped_member_ids: List[str] = []
            for member_id in member_ids:
                if member_id not in deduped_member_ids:
                    deduped_member_ids.append(member_id)

            for member_id in deduped_member_ids:
                self._get_run_index_by_id(member_id)

            current_members = list(group.get("members", []))
            for member_id in deduped_member_ids:
                run_index = self._get_run_index_by_id(member_id)
                self._assign_run_group(run_index, group_id)

            for member_id in current_members:
                if member_id not in deduped_member_ids:
                    run_index = self._get_run_index_by_id(member_id)
                    if self.runs[run_index].get("group_id") == group_id:
                        self.clear_run_field(run_index, "group_id")

            group["members"] = deduped_member_ids

    def seed_runs_from_filenames(self, force: bool = False) -> int:
        """Assign ungrouped runs to filename-derived groups when a fraction marker is present."""
        seeded_count = 0
        for run_index, run in enumerate(self.runs):
            if run.get("group_id"):
                continue
            if run.get("group_assignment_cleared") and not force:
                continue

            file_name = run.get("file")
            if file_name is None:
                continue

            group_id = self._infer_group_id_from_file_name(file_name)
            if not group_id:
                continue

            self._ensure_group_exists(
                group_id,
                kind=self.get_allowed_group_kinds()[0],
                labeling_strategy=self.get_default_labeling_strategy(self.get_allowed_group_kinds()[0]),
                name=group_id,
                description="Auto-created from matching filename fraction markers",
            )
            self._assign_run_group(run_index, group_id)
            run.pop("group_assignment_cleared", None)
            seeded_count += 1

        return seeded_count

    def _next_run_id(self) -> str:
        """Generate a stable internal run identifier for wizard-only relationships."""
        self._run_counter += 1
        return f"run_{self._run_counter}"

    def _get_group_index(self, group_id: str) -> int:
        """Return the index of a group by id."""
        for index, group in enumerate(self.groups):
            if group.get("id") == group_id:
                return index
        raise ValueError(f"Group '{group_id}' not found in groups")

    def _remove_run_from_group_members(self, run_id: str, group_id: Optional[str]) -> None:
        """Remove a run reference from a group's members list if present."""
        if not group_id:
            return

        group_index = self._get_group_index(group_id)
        members = self.groups[group_index].setdefault("members", [])
        if run_id in members:
            members.remove(run_id)

    def _assign_run_group(self, run_index: int, group_id: Optional[str]) -> None:
        """Keep run and group membership in sync for wizard-only authoring groups."""
        run = self.runs[run_index]
        run_id = run["id"]
        previous_group_id = run.get("group_id")

        if previous_group_id and previous_group_id != group_id:
            self._remove_run_from_group_members(run_id, previous_group_id)

        if group_id is None:
            run.pop("group_id", None)
            return

        group_index = self._get_group_index(group_id)
        members = self.groups[group_index].setdefault("members", [])
        if run_id not in members:
            members.append(run_id)
        run["group_id"] = group_id
        run.pop("group_assignment_cleared", None)

    def _get_group_projection(self, group_id: str) -> Dict[str, Any]:
        """Return the exported projection for a group-backed run."""
        group_index = self._get_group_index(group_id)
        group = self.groups[group_index]

        projected_run: Dict[str, Any] = {}
        sample_target = group.get("sample_target")
        if sample_target:
            projected_run["sample"] = sample_target

        channel_assignments = {
            str(channel): sample_id
            for channel, sample_id in group.get("channel_sample_assignments", {}).items()
            if sample_id
        }
        if channel_assignments:
            projected_run["mixture"] = group["id"]

        if projected_run.get("mixture"):
            projected_run["mixture_definition"] = {
                "id": group["id"],
                "channels": channel_assignments,
            }

        return projected_run

    def add_run(
        self,
        file: str,
        sample: Optional[str] = None,
        mixture: Optional[str] = None,
        fraction: Optional[int] = None,
        instrument: Optional[str] = None,
        modification_profile: Optional[str] = None,
        group_id: Optional[str] = None,
    ) -> None:
        """
        Add a raw/mzML file run.

        Args:
            file: Path or URI to raw/mzML file (required)
            sample: Sample ID this run belongs to (for LFQ samples)
            mixture: Mixture ID this run belongs to (for labeled samples)
            fraction: Fraction number (for fractionated samples)
            instrument: Instrument used (optional)
        """
        if not file:
            raise ValueError("File path is required")

        if fraction is None:
            fraction = self._infer_fraction_from_file_name(file)

        run_id = self._next_run_id()

        run: Dict[str, Any] = {
            "id": run_id,
            "file": file,
        }
        if sample is not None:
            run["sample"] = sample
        if mixture is not None:
            run["mixture"] = mixture
        if fraction is not None:
            run["fraction"] = fraction
        if instrument is not None:
            run["instrument"] = instrument
        if modification_profile is not None:
            run["modification_profile"] = modification_profile
        if group_id is not None:
            run["group_id"] = group_id

        self.runs.append(run)

        if group_id is not None:
            default_kind = self.get_allowed_group_kinds()[0]
            self._ensure_group_exists(
                group_id,
                kind=default_kind,
                labeling_strategy=self.get_default_labeling_strategy(default_kind),
            )
            self._assign_run_group(len(self.runs) - 1, group_id)

    def add_group(
        self,
        id: str,
        name: str,
        kind: Optional[str] = None,
        group_type: Optional[str] = None,
        description: Optional[str] = None,
        labeling_strategy: Any = _UNSET,
    ) -> None:
        """Add an authoring-level group for runs without changing manifest export."""
        if not id:
            raise ValueError("Group ID is required")
        if not name:
            raise ValueError("Group name is required")
        self._ensure_unique_group_id(id)

        group = {
            "id": id,
            "name": name,
            "members": [],
        }
        if description:
            group["description"] = description

        effective_kind = kind if kind is not None else group_type
        self.ensure_group_labeling_metadata(
            group,
            kind=effective_kind if effective_kind is not None else _UNSET,
            labeling_strategy=labeling_strategy if labeling_strategy is not _UNSET else _UNSET,
        )

        self.groups.append(group)

    def get_available_groups(self) -> List[Dict[str, Any]]:
        """Get list of all authoring groups added so far."""
        return [
            {**group, "members": list(group.get("members", []))}
            for group in self.groups
        ]

    def add_modification(self, **kwargs) -> None:
        """Add a modification definition to the wizard state."""
        if "mode" not in kwargs or not kwargs["mode"]:
            raise ValueError("Modification mode is required")
        self.modifications.append(kwargs.copy())
        profile = (kwargs.get("profile") or "").strip()
        if profile:
            self.register_modification_profile(profile)

    def normalize_modification_profile_name(self, profile: Any) -> Optional[str]:
        """Normalize a profile name for storage and comparisons."""
        profile_name = re.sub(r"\s+", " ", str(profile or "")).strip()
        return profile_name or None

    def find_modification_profile_name(self, profile: Any) -> Optional[str]:
        """Find a registered profile using case-insensitive matching."""
        profile_name = self.normalize_modification_profile_name(profile)
        if not profile_name:
            return None

        for existing in self.modification_profiles:
            if existing.casefold() == profile_name.casefold():
                return existing
        return None

    def register_modification_profile(self, profile: str) -> None:
        """Register a modification profile so it survives rerenders."""
        profile_name = self.normalize_modification_profile_name(profile)
        if not profile_name:
            return
        if self.find_modification_profile_name(profile_name) is None:
            self.modification_profiles.append(profile_name)

    def rename_modification_profile(self, current: str, new_name: str) -> None:
        """Rename a profile and update all wizard state references."""
        current_name = self.find_modification_profile_name(current)
        if current_name is None:
            raise ValueError(f"Profile '{current}' not found")

        normalized_new_name = self.normalize_modification_profile_name(new_name)
        if not normalized_new_name:
            raise ValueError("Profile name cannot be empty")

        existing_name = self.find_modification_profile_name(normalized_new_name)
        if existing_name is not None and existing_name != current_name:
            raise ValueError(f"Profile '{existing_name}' already exists")

        profile_index = self.modification_profiles.index(current_name)
        self.modification_profiles[profile_index] = normalized_new_name

        if self.active_modification_profile == current_name:
            self.active_modification_profile = normalized_new_name

        for modification in self.modifications:
            if modification.get("profile") == current_name:
                modification["profile"] = normalized_new_name

        for run in self.runs:
            if run.get("modification_profile") == current_name:
                run["modification_profile"] = normalized_new_name

        if self._pending_modification_draft.get("profile") == current_name:
            self._pending_modification_draft["profile"] = normalized_new_name

    def get_pending_modification_draft(self) -> Dict[str, Any]:
        """Return a defensive copy of the pending modification draft."""
        return deepcopy(self._pending_modification_draft)

    def update_pending_modification_draft(self, **kwargs: Any) -> None:
        """Update the transient modification draft used by the Runs step."""
        for key, value in kwargs.items():
            if key == "profile":
                normalized_profile = self.normalize_modification_profile_name(value)
                if normalized_profile:
                    self.register_modification_profile(normalized_profile)
                    self._pending_modification_draft[key] = normalized_profile
                else:
                    self._pending_modification_draft.pop(key, None)
                continue

            self._pending_modification_draft[key] = deepcopy(value)

    def clear_pending_modification_draft(self) -> None:
        """Clear the transient modification draft state."""
        self._pending_modification_draft = {}

    def set_active_modification_profile(self, profile: Optional[str]) -> None:
        """Set the currently active modification profile."""
        profile_name = self.normalize_modification_profile_name(profile) if profile else None
        self.active_modification_profile = profile_name
        if profile_name:
            self.register_modification_profile(profile_name)

    def get_modification_profiles(self) -> List[str]:
        """Return known modification profiles in insertion order."""
        if not self.modification_profiles and self.modifications:
            self.modification_profiles = []
            for modification in self.modifications:
                profile_name = (modification.get("profile") or "").strip()
                if profile_name and profile_name not in self.modification_profiles:
                    self.modification_profiles.append(profile_name)
        return self.modification_profiles.copy()

    def get_available_runs(self) -> List[Dict[str, Any]]:
        """Get list of all runs added so far."""
        return self.runs.copy()

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
        """
        Add a biological sample.

        Args:
            id: Unique sample identifier (required)
            organism: Species (e.g., "homo sapiens")
            organism_part: Tissue/compartment (e.g., "liver")
            condition: Experimental condition (e.g., "treated")
            biological_replicate: Replicate number
            technical_replicate: Technical replicate number
            disease: Disease state
            cell_type: Cell type
        """
        normalized_id = str(id).strip() if id is not None else ""
        if not normalized_id:
            raise ValueError("Sample ID is required")

        self._ensure_unique_sample_id(normalized_id)

        sample: Dict[str, Any] = {"id": normalized_id}
        if organism:
            sample["organism"] = organism
        if organism_part:
            sample["organism_part"] = organism_part
        if condition:
            sample["condition"] = condition
        if biological_replicate is not None:
            sample["biological_replicate"] = biological_replicate
        if technical_replicate is not None:
            sample["technical_replicate"] = technical_replicate
        if disease:
            sample["disease"] = disease
        if cell_type:
            sample["cell_type"] = cell_type

        self.samples.append(sample)

    def get_available_samples(self) -> List[Dict[str, Any]]:
        """Get list of all samples added so far."""
        return self.samples.copy()

    def add_mixture(
        self,
        id: str,
        channels: Dict[str, str],
        description: Optional[str] = None,
    ) -> None:
        """
        Add a multiplex mixture (for TMT, iTRAQ, SILAC, etc.).

        Channels map from label (e.g., "TMT126") to sample ID.
        All referenced samples must already exist.

        Args:
            id: Unique mixture identifier
            channels: Mapping of channel label to sample ID
            description: Optional description of the mixture

        Raises:
            ValueError: If referenced sample does not exist
        """
        if not id:
            raise ValueError("Mixture ID is required")
        if not channels:
            raise ValueError("At least one channel assignment is required")

        # Validate that all referenced samples exist
        sample_ids = {s["id"] for s in self.samples}
        for channel, sample_id in channels.items():
            if sample_id not in sample_ids:
                raise ValueError(
                    f"Sample '{sample_id}' referenced in channel '{channel}' not found in samples"
                )

        mixture = {
            "id": id,
            "channels": channels.copy(),
        }
        if description:
            mixture["description"] = description

        self.mixtures.append(mixture)

    def get_available_mixtures(self) -> List[Dict[str, Any]]:
        """Get list of all mixtures added so far."""
        return self.mixtures.copy()

    def assign_run(
        self,
        run_index: int,
        sample: Optional[str] = None,
        mixture: Optional[str] = None,
        fraction: Optional[int] = None,
        instrument: Optional[str] = None,
        group_id: Optional[str] = None,
        create_missing_group: bool = True,
    ) -> None:
        """
        Assign run metadata (sample, mixture, fraction, instrument) with validation.

        This is called during the ASSIGNMENTS step to link runs to samples/mixtures
        and specify instrument and fraction details.

        Args:
            run_index: Index of the run to assign
            sample: Sample ID this run belongs to (for LFQ samples)
            mixture: Mixture ID this run belongs to (for labeled samples)
            fraction: Fraction number (for fractionated samples)
            instrument: Instrument used for this run

        Raises:
            IndexError: If run_index is out of range
            ValueError: If referenced sample or mixture does not exist
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")

        # Validate references
        if sample is not None:
            sample_ids = {s["id"] for s in self.samples}
            if sample not in sample_ids:
                raise ValueError(f"Sample '{sample}' not found in samples")

        if mixture is not None:
            mixture_ids = {m["id"] for m in self.mixtures}
            if mixture not in mixture_ids:
                raise ValueError(f"Mixture '{mixture}' not found in mixtures")

        if group_id is not None and create_missing_group:
            default_kind = self.get_allowed_group_kinds()[0]
            self._ensure_group_exists(
                group_id,
                kind=default_kind,
                labeling_strategy=self.get_default_labeling_strategy(default_kind),
            )

        # Update run with assignment
        run = self.runs[run_index]
        if sample is not None:
            run["sample"] = sample
        if mixture is not None:
            run["mixture"] = mixture
        if fraction is not None:
            run["fraction"] = fraction
        if instrument is not None:
            run["instrument"] = instrument
        if group_id is not None or "group_id" in run:
            self._assign_run_group(run_index, group_id)

    def get_run_assignment(self, run_index: int) -> Dict[str, Any]:
        """
        Get the assignment details for a specific run.

        Args:
            run_index: Index of the run to retrieve

        Returns:
            Dictionary containing the run's assignment (file, sample, mixture, etc.)

        Raises:
            IndexError: If run_index is out of range
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")
        return self.runs[run_index].copy()


    def set_experiment(
        self,
        acquisition_method: str,
        enzyme: str,
        quantification_method: Optional[str] = None,
        dissociation_method: Optional[str] = None,
        precursor_mass_tolerance: Optional[str] = None,
        fragment_mass_tolerance: Optional[str] = None,
    ) -> None:
        """
        Set experiment-level parameters that apply to all runs.

        Args:
            acquisition_method: "DDA" or "DIA" (required)
            enzyme: Proteolytic enzyme (required)
            quantification_method: "LFQ", "TMT", "iTRAQ", "SILAC", or None
            dissociation_method: Explicit dissociation method (e.g., "HCD") - never inferred
            precursor_mass_tolerance: Tolerance spec (e.g., "10 ppm")
            fragment_mass_tolerance: Tolerance spec (e.g., "0.02 Da")
        """
        if not acquisition_method:
            raise ValueError("Acquisition method is required")
        if not enzyme:
            raise ValueError("Enzyme is required")

        self.experiment = {
            "acquisition_method": acquisition_method,
            "enzyme": enzyme,
        }
        if quantification_method:
            self.experiment["quantification_method"] = quantification_method
        if dissociation_method:
            self.experiment["dissociation_method"] = dissociation_method
        if precursor_mass_tolerance:
            self.experiment["precursor_mass_tolerance"] = precursor_mass_tolerance
        if fragment_mass_tolerance:
            self.experiment["fragment_mass_tolerance"] = fragment_mass_tolerance

        # Mark that experiment settings have been saved
        self._experiment_settings_saved = True

    def update_run(self, run_index: int, **kwargs) -> None:
        """
        Update properties of a run in the wizard state.

        Args:
            run_index: Index of the run to update
            **kwargs: Properties to update (file, sample, mixture, fraction, instrument)

        Raises:
            IndexError: If run_index is out of range
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")

        if "group_id" in kwargs:
            self.assign_run(run_index, group_id=kwargs["group_id"])
            kwargs = {key: value for key, value in kwargs.items() if key != "group_id"}

        for key, value in kwargs.items():
            self.runs[run_index][key] = value

    def clear_run_field(self, run_index: int, field: str) -> None:
        """
        Remove a specific field from a run.

        This respects encapsulation by providing an explicit public API
        for field removal. Use for clearing optional fields that were previously set.

        Args:
            run_index: Index of the run to modify
            field: Field name to remove (should not be 'file')

        Raises:
            IndexError: If run_index is out of range
            ValueError: If trying to remove the required 'file' field
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")

        if field == "file":
            raise ValueError("Cannot remove required field 'file'")

        if field == "group_id":
            run = self.runs[run_index]
            self._remove_run_from_group_members(run["id"], run.get("group_id"))
            run.pop("group_id", None)
            run["group_assignment_cleared"] = True
            return

        if field in self.runs[run_index]:
            del self.runs[run_index][field]

    def remove_run(self, run_index: int) -> None:
        """
        Remove a run from the wizard state.

        Args:
            run_index: Index of the run to remove

        Raises:
            IndexError: If run_index is out of range
        """
        if run_index < 0 or run_index >= len(self.runs):
            raise IndexError(f"Run index {run_index} out of range")

        run = self.runs[run_index]
        self._remove_run_from_group_members(run["id"], run.get("group_id"))
        del self.runs[run_index]

    def update_sample(self, sample_index: int, **kwargs) -> None:
        """
        Update properties of a sample in the wizard state.

        Args:
            sample_index: Index of the sample to update
            **kwargs: Properties to update (organism, organism_part, condition, etc.)

        Raises:
            IndexError: If sample_index is out of range
        """
        if sample_index < 0 or sample_index >= len(self.samples):
            raise IndexError(f"Sample index {sample_index} out of range")

        for key, value in kwargs.items():
            self.samples[sample_index][key] = value

    def remove_sample(self, sample_index: int) -> None:
        """
        Remove a sample from the wizard state.

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
        Update properties of a mixture in the wizard state.

        Args:
            mixture_index: Index of the mixture to update
            **kwargs: Properties to update (id, channels, description)

        Raises:
            IndexError: If mixture_index is out of range
        """
        if mixture_index < 0 or mixture_index >= len(self.mixtures):
            raise IndexError(f"Mixture index {mixture_index} out of range")

        for key, value in kwargs.items():
            self.mixtures[mixture_index][key] = value

    def remove_mixture(self, mixture_index: int) -> None:
        """
        Remove a mixture from the wizard state.

        Args:
            mixture_index: Index of the mixture to remove

        Raises:
            IndexError: If mixture_index is out of range
        """
        if mixture_index < 0 or mixture_index >= len(self.mixtures):
            raise IndexError(f"Mixture index {mixture_index} out of range")
        del self.mixtures[mixture_index]

    def to_manifest_state(self) -> ManifestState:
        """
        Convert wizard state to a complete ManifestState object.

        This is called in the REVIEW step to generate the final manifest
        that can be validated and saved.

        Returns:
            ManifestState object ready for validation and serialization
        """
        manifest = ManifestState()

        projected_mixtures: Dict[str, Dict[str, Any]] = {
            mixture["id"]: {
                "id": mixture["id"],
                "channels": mixture["channels"].copy(),
                **({"description": mixture["description"]} if mixture.get("description") else {}),
            }
            for mixture in self.mixtures
        }

        # Add all runs
        for run in self.runs:
            projected_sample = run.get("sample")
            projected_mixture = run.get("mixture")

            group_id = run.get("group_id")
            if group_id:
                group_projection = self._get_group_projection(group_id)
                projected_sample = group_projection.get("sample")
                projected_mixture = group_projection.get("mixture")

                mixture_definition = group_projection.get("mixture_definition")
                if mixture_definition:
                    projected_mixtures[mixture_definition["id"]] = mixture_definition

            manifest.add_run(
                file=run["file"],
                sample=projected_sample,
                mixture=projected_mixture,
                fraction=run.get("fraction"),
                instrument=run.get("instrument"),
                modification_profile=run.get("modification_profile"),
            )

        # Add all samples
        for sample in self.samples:
            manifest.add_sample(
                id=sample["id"],
                organism=sample.get("organism"),
                organism_part=sample.get("organism_part"),
                condition=sample.get("condition"),
                biological_replicate=sample.get("biological_replicate"),
                technical_replicate=sample.get("technical_replicate"),
                disease=sample.get("disease"),
                cell_type=sample.get("cell_type"),
            )

        # Add all mixtures
        for mixture in projected_mixtures.values():
            manifest.add_mixture(
                id=mixture["id"],
                channels=mixture["channels"],
                description=mixture.get("description"),
            )

        # Add all modifications
        for modification in self.modifications:
            manifest.add_modification(**modification)

        # Set experiment
        if self.experiment:
            manifest.set_experiment(
                acquisition_method=self.experiment["acquisition_method"],
                enzyme=self.experiment["enzyme"],
                quantification_method=self.experiment.get("quantification_method"),
                dissociation_method=self.experiment.get("dissociation_method"),
                precursor_mass_tolerance=self.experiment.get("precursor_mass_tolerance"),
                fragment_mass_tolerance=self.experiment.get("fragment_mass_tolerance"),
            )

        return manifest
