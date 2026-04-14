#!/usr/bin/env python3
"""
Tests for channel-to-sample assignment logic.

UI-agnostic tests that validate the core assignment building mechanism
used by the TUI for multiplex mixture authoring.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from manifest_core import ChannelBuilder, ManifestState


class TestChannelAssignmentBuilder:
    """Tests for building channel-to-sample assignments."""

    def test_build_empty_assignments_for_plex_type(self):
        """Test building empty assignments structure for a plex type."""
        builder = TestChannelAssignmentHelper()

        assignments = builder.build_empty_assignments("TMT6")

        # Should have all 6 TMT channels
        assert len(assignments) == 6
        assert "TMT126" in assignments
        assert "TMT127N" in assignments
        assert "TMT129N" in assignments

        # All values should be empty/None initially
        for value in assignments.values():
            assert value is None or value == ""

    def test_build_empty_assignments_for_different_plex_types(self):
        """Test building assignments for different plex types."""
        builder = TestChannelAssignmentHelper()

        # Test TMT2
        assignments_tmt2 = builder.build_empty_assignments("TMT2")
        assert len(assignments_tmt2) == 2

        # Test TMT10
        assignments_tmt10 = builder.build_empty_assignments("TMT10")
        assert len(assignments_tmt10) == 10

        # Test iTRAQ4
        assignments_itraq = builder.build_empty_assignments("iTRAQ4")
        assert len(assignments_itraq) == 4

    def test_set_channel_assignment(self):
        """Test setting a sample to a channel."""
        builder = TestChannelAssignmentHelper()
        assignments = builder.build_empty_assignments("TMT6")

        builder.set_assignment(assignments, "TMT126", "sample_1")

        assert assignments["TMT126"] == "sample_1"
        # Other channels should still be empty
        assert assignments["TMT127N"] == ""

    def test_get_all_assignments_from_dict(self):
        """Test reading all assignments from an assignment dict."""
        builder = TestChannelAssignmentHelper()
        assignments = builder.build_empty_assignments("TMT6")

        builder.set_assignment(assignments, "TMT126", "sample_1")
        builder.set_assignment(assignments, "TMT127N", "sample_2")
        builder.set_assignment(assignments, "TMT127C", "sample_3")

        result = builder.get_assignments(assignments)

        assert result["TMT126"] == "sample_1"
        assert result["TMT127N"] == "sample_2"
        assert result["TMT127C"] == "sample_3"
        # Unset channels should not be in result
        assert "TMT128N" not in result or result.get("TMT128N") == ""

    def test_validate_assignments_partial_allowed(self):
        """Test that validation passes with partial channel assignments (at least 1)."""
        builder = TestChannelAssignmentHelper()
        assignments = builder.build_empty_assignments("TMT6")

        # Only assign 3 of 6 channels
        builder.set_assignment(assignments, "TMT126", "sample_1")
        builder.set_assignment(assignments, "TMT127N", "sample_2")
        builder.set_assignment(assignments, "TMT127C", "sample_3")

        is_valid, errors = builder.validate_assignments(assignments)

        # Partial assignments should be valid
        assert is_valid
        assert len(errors) == 0

    def test_validate_assignments_requires_at_least_one(self):
        """Test that validation fails if no channels are assigned."""
        builder = TestChannelAssignmentHelper()
        assignments = builder.build_empty_assignments("TMT6")

        # Don't assign any channels
        is_valid, errors = builder.validate_assignments(assignments)

        assert not is_valid
        assert len(errors) > 0

    def test_validate_assignments_all_assigned(self):
        """Test that validation passes when all channels are assigned (also valid)."""
        builder = TestChannelAssignmentHelper()
        assignments = builder.build_empty_assignments("TMT6")

        # Assign all 6 channels
        for idx, channel in enumerate(builder.get_channels("TMT6")):
            builder.set_assignment(assignments, channel, f"sample_{idx}")

        is_valid, errors = builder.validate_assignments(assignments)

        assert is_valid
        assert len(errors) == 0

    def test_integration_with_manifest_add_mixture(self):
        """Test that assignments work correctly with ManifestState.add_mixture."""
        manifest = ManifestState()

        # Add samples
        for i in range(1, 7):
            manifest.add_sample(id=f"sample_{i}")

        # Build and validate assignments
        builder = TestChannelAssignmentHelper()
        assignments = builder.build_empty_assignments("TMT6")

        channels = builder.get_channels("TMT6")
        for idx, channel in enumerate(channels):
            builder.set_assignment(assignments, channel, f"sample_{idx + 1}")

        # Use assignments to create mixture
        assignments_dict = builder.get_assignments(assignments)
        manifest.add_mixture(id="plex_1", channels=assignments_dict)

        # Verify
        mixture = manifest.mixtures[0]
        assert mixture.channels["TMT126"] == "sample_1"
        assert mixture.channels["TMT129N"] == "sample_6"


class TestChannelAssignmentHelper:
    """Helper class that provides UI-agnostic channel assignment operations."""

    @staticmethod
    def build_empty_assignments(plex_type: str) -> dict:
        """Build an empty assignment dict for a plex type with all channels as empty strings."""
        builder = ChannelBuilder(plex_type)
        channels = builder.get_available_channels()
        return {channel: "" for channel in channels}

    @staticmethod
    def get_channels(plex_type: str) -> list:
        """Get list of channels for a plex type."""
        builder = ChannelBuilder(plex_type)
        return builder.get_available_channels()

    @staticmethod
    def set_assignment(assignments: dict, channel: str, sample_id: str) -> None:
        """Set a channel-to-sample assignment."""
        if channel not in assignments:
            raise ValueError(f"Unknown channel: {channel}")
        assignments[channel] = sample_id

    @staticmethod
    def get_assignments(assignments: dict) -> dict:
        """Get only non-empty assignments."""
        return {k: v for k, v in assignments.items() if v and v.strip()}

    @staticmethod
    def validate_assignments(assignments: dict) -> tuple:
        """
        Validate that at least one channel has an assignment (schema requires minProperties: 1).

        Returns (is_valid, error_messages) tuple.
        """
        errors = []
        assigned_channels = [ch for ch, val in assignments.items() if val and val.strip()]

        if not assigned_channels:
            errors.append("At least one channel must be assigned a sample")
            return False, errors

        return True, []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
