"""
quantms YAML Manifest Authoring Module

Provides core classes and utilities for creating and editing quantms YAML manifests,
with two user interfaces:
  - TUI: Terminal UI using Textual
  - GUI: Web UI using NiceGUI

The module includes:
  - ManifestState: In-memory representation of manifest state
  - Channel builders for multiplex types (TMT, iTRAQ, SILAC)
  - YAML serialization/deserialization
  - Validation integration
"""

from .manifest_core import (
    ManifestState,
    Sample,
    Mixture,
    Run,
    Modification,
    Experiment,
    Metadata,
    ChannelBuilder,
    validate_manifest,
)

__version__ = "0.1.0"
__all__ = [
    "ManifestState",
    "Sample",
    "Mixture",
    "Run",
    "Modification",
    "Experiment",
    "Metadata",
    "ChannelBuilder",
    "validate_manifest",
]
