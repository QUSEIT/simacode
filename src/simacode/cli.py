"""
Command-line interface for SimaCode.

This module provides the main entry point for the SimaCode CLI application,
handling command parsing, configuration loading, and application initialization.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.traceback import install

from .config import Config
from .logging_config import setup_logging

# Install rich traceback handler for better error display
install(show_locals=True)

console = Console()


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to configuration file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging",
)
@click.option(
    "--version",
    is_flag=True,
    help="Show version and exit",
)
@click.pass_context
def main(
    ctx: click.Context,
    config: Optional[Path] = None,
    verbose: bool = False,
    version: bool = False,
) -> None:
    """
    SimaCode: A modern AI programming assistant with intelligent ReAct mechanisms.
    
    SimaCode combines natural language understanding with practical programming
    capabilities through a sophisticated ReAct (Reasoning and Acting) framework.
    """
    if version:
        from . import __version__
        console.print(f"SimaCode version {__version__}")
        return
    
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Load configuration
    try:
        config_obj = Config.load(config_path=config)
        ctx.obj["config"] = config_obj
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        sys.exit(1)
    
    # Setup logging
    log_level = "DEBUG" if verbose else config_obj.logging.level
    setup_logging(level=log_level, config=config_obj.logging)


@main.command()
@click.option(
    "--check",
    is_flag=True,
    help="Check configuration validity without starting",
)
@click.pass_context
def config(ctx: click.Context, check: bool) -> None:
    """Configuration management commands."""
    config_obj = ctx.obj["config"]
    
    if check:
        try:
            config_obj.validate()
            console.print("[green]Configuration is valid[/green]")
        except Exception as e:
            console.print(f"[red]Configuration error: {e}[/red]")
            sys.exit(1)
    else:
        console.print("[bold]Current Configuration:[/bold]")
        console.print(config_obj.model_dump_json(indent=2))


@main.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a new SimaCode project."""
    config_obj = ctx.obj["config"]
    
    # Create default directories
    project_root = Path.cwd()
    directories = [
        project_root / ".simacode",
        project_root / ".simacode" / "sessions",
        project_root / ".simacode" / "logs",
        project_root / ".simacode" / "cache",
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]Created directory: {directory}[/green]")
    
    # Create project configuration
    config_path = project_root / ".simacode" / "config.yaml"
    if not config_path.exists():
        config_obj.save_to_file(config_path)
        console.print(f"[green]Created project configuration: {config_path}[/green]")
    
    console.print("[bold green]Project initialized successfully![/bold green]")


@main.command()
@click.argument("message", required=False)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Start interactive mode",
)
@click.pass_context
def chat(ctx: click.Context, message: Optional[str], interactive: bool) -> None:
    """Start a chat session with the AI assistant."""
    config_obj = ctx.obj["config"]
    
    if not interactive and not message:
        console.print("[yellow]No message provided. Use --interactive for interactive mode.[/yellow]")
        return
    
    # Placeholder for chat functionality
    console.print("[yellow]Chat functionality will be implemented in Phase 2[/yellow]")
    
    if message:
        console.print(f"[blue]You: {message}[/blue]")
        console.print("[green]AI: Chat functionality coming soon...[/green]")


if __name__ == "__main__":
    main()