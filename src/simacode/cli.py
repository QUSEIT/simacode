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
from .ai.factory import AIClientFactory
from .ai.conversation import ConversationManager

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
    
    asyncio.run(_run_chat(ctx, message, interactive))


async def _run_chat(ctx: click.Context, message: Optional[str], interactive: bool) -> None:
    """Run the chat functionality."""
    config_obj = ctx.obj["config"]
    
    try:
        # Create AI client
        ai_client = AIClientFactory.create_client(config_obj.ai.model_dump())
        
        # Create conversation manager
        sessions_dir = Path.cwd() / ".simacode" / "sessions"
        conversation_manager = ConversationManager(sessions_dir)
        
        if not interactive and message:
            # Single message mode
            await _handle_single_message(ai_client, conversation_manager, message)
        elif interactive:
            # Interactive mode
            await _handle_interactive_mode(ai_client, conversation_manager)
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")


async def _handle_single_message(ai_client, conversation_manager, message: str) -> None:
    """Handle a single message."""
    conversation = conversation_manager.get_current_conversation()
    
    # Add user message
    conversation.add_user_message(message)
    
    # Get AI response
    messages = conversation.get_messages()
    response = await ai_client.chat(messages)
    
    # Add AI response to conversation
    conversation.add_assistant_message(response.content)
    
    # Save conversation
    conversation_manager.save_all_conversations()
    
    # Display response
    console.print(f"\n[bold blue]AI:[/bold blue] {response.content}\n")


async def _handle_interactive_mode(ai_client, conversation_manager) -> None:
    """Handle interactive chat mode."""
    console.print("[bold green]Starting interactive chat mode...[/bold green]")
    console.print("[dim]Type 'quit' or 'exit' to end the conversation[/dim]\n")
    
    conversation = conversation_manager.get_current_conversation()
    
    while True:
        try:
            # Get user input
            user_input = click.prompt("You", type=str)
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                console.print("[yellow]Goodbye![/yellow]")
                break
            
            if user_input.lower() in ['clear', 'reset']:
                conversation.clear_messages()
                console.print("[yellow]Conversation cleared.[/yellow]")
                continue
            
            if user_input.lower() in ['help', '?']:
                console.print("\n[dim]Commands:[/dim]")
                console.print("  [dim]quit/exit/q - Exit chat[/dim]")
                console.print("  [dim]clear/reset - Clear conversation[/dim]")
                console.print("  [dim]help/? - Show this help[/dim]\n")
                continue
            
            # Add user message
            conversation.add_user_message(user_input)
            
            # Get AI response with streaming
            messages = conversation.get_messages()
            
            console.print("[bold blue]AI:[/bold blue] ", end="")
            
            # Use streaming for better UX
            response_content = ""
            async for chunk in ai_client.chat_stream(messages):
                response_content += chunk
                console.print(chunk, end="")
            
            console.print()  # New line after response
            
            # Add AI response to conversation
            conversation.add_assistant_message(response_content)
            
            # Save conversation
            conversation_manager.save_all_conversations()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Chat interrupted. Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()