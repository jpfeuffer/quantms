#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "textual",
#   "nicegui",
#   "fastapi",
#   "uvicorn",
#   "pyyaml",
#   "click",
# ]
# ///
"""
quantms YAML Manifest Authoring Application

Provides command-line interface to choose between TUI (Textual) and GUI (NiceGUI)
for creating and editing quantms YAML manifests.
"""

import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

import click


@click.group()
def cli():
    """quantms YAML Manifest Authoring Tool"""
    pass


@cli.command()
def tui():
    """Launch the Terminal User Interface (TUI) using Textual"""
    click.echo("Starting TUI (Textual)...")
    from tui_textual import run_tui
    run_tui()


@cli.command()
@click.option(
    "--port",
    type=int,
    default=8080,
    help="Port for the web server (default: 8080)",
)
@click.option(
    "--host",
    type=str,
    default="127.0.0.1",
    help="Host for the web server (default: 127.0.0.1)",
)
def gui(port: int, host: str):
    """Launch the GUI using NiceGUI (web interface)"""
    click.echo(f"Starting GUI (NiceGUI) at http://{host}:{port}")
    from gui_nicegui import run_gui
    run_gui(port=port, host=host)


@cli.command()
def info():
    """Show information about supported multiplex types"""
    from manifest_core import ChannelBuilder

    click.echo("\nSupported Multiplex Types:\n")
    plex_types = ChannelBuilder.get_supported_plex_types()

    for plex_type in plex_types:
        try:
            builder = ChannelBuilder(plex_type)
            channels = builder.get_available_channels()
            click.echo(f"  {plex_type:15} ({len(channels):2} channels)")
        except Exception as e:
            click.echo(f"  {plex_type:15} (Error: {e})")

    click.echo("\nUsage:")
    click.echo("  quantms-manifest tui   - Launch Terminal UI")
    click.echo("  quantms-manifest gui   - Launch Web UI")


if __name__ == "__main__":
    cli()
