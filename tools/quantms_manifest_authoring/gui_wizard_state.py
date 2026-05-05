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

from enum import Enum, auto
import re
from typing import Optional, Dict, List, Any
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from manifest_core import ManifestState, Run, Sample, Mixture, Experiment


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
        self.runs: List[Dict[str, Any]] = []
        self.samples: List[Dict[str, Any]] = []
        self.mixtures: List[Dict[str, Any]] = []
        self.modifications: List[Dict[str, Any]] = []
        self.modification_profiles: List[str] = []
        self.active_modification_profile: Optional[str] = None
        self.experiment: Optional[Dict[str, Any]] = None
        self._experiment_settings_saved = False
        self._active_editor: Optional[Any] = None

    def get_current_step(self) -> WizardStep:
        """Get the current wizard step."""
        steps = WizardStep.ordered_steps()
        return steps[self.current_step_index]

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

    def add_run(
        self,
        file: str,
        sample: Optional[str] = None,
        mixture: Optional[str] = None,
        fraction: Optional[int] = None,
        instrument: Optional[str] = None,
        modification_profile: Optional[str] = None,
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

        run = {
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

        self.runs.append(run)

    def add_modification(self, **kwargs) -> None:
        """Add a modification definition to the wizard state."""
        if "mode" not in kwargs or not kwargs["mode"]:
            raise ValueError("Modification mode is required")
        self.modifications.append(kwargs.copy())
        profile = (kwargs.get("profile") or "").strip()
        if profile:
            self.register_modification_profile(profile)

    def register_modification_profile(self, profile: str) -> None:
        """Register a modification profile so it survives rerenders."""
        profile_name = (profile or "").strip()
        if not profile_name:
            return
        if profile_name not in self.modification_profiles:
            self.modification_profiles.append(profile_name)

    def set_active_modification_profile(self, profile: Optional[str]) -> None:
        """Set the currently active modification profile."""
        profile_name = (profile or "").strip() if profile else None
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
        if not id:
            raise ValueError("Sample ID is required")

        sample = {"id": id}
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

        # Add all runs
        for run in self.runs:
            manifest.add_run(
                file=run["file"],
                sample=run.get("sample"),
                mixture=run.get("mixture"),
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
        for mixture in self.mixtures:
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
