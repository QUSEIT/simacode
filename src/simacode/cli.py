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
from .services.react_service import ReActService

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
@click.option(
    "--react",
    "-r",
    is_flag=True,
    help="Use ReAct engine for intelligent task planning and execution",
)
@click.option(
    "--session-id",
    "-s",
    type=str,
    help="Continue existing session",
)
@click.pass_context
def chat(ctx: click.Context, message: Optional[str], interactive: bool, react: bool, session_id: Optional[str]) -> None:
    """Start a chat session with the AI assistant."""
    config_obj = ctx.obj["config"]
    
    if not interactive and not message:
        console.print("[yellow]No message provided. Use --interactive for interactive mode.[/yellow]")
        return
    
    asyncio.run(_run_chat(ctx, message, interactive, react, session_id))


async def _run_chat(ctx: click.Context, message: Optional[str], interactive: bool, react: bool, session_id: Optional[str]) -> None:
    """Run the chat functionality."""
    config_obj = ctx.obj["config"]
    
    try:
        if react:
            # Use ReAct service for intelligent task planning and execution
            await _handle_react_mode(config_obj, message, interactive, session_id)
        else:
            # Use traditional conversation mode
            await _handle_traditional_mode(config_obj, message, interactive)
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")


async def _handle_react_mode(config_obj: Config, message: Optional[str], interactive: bool, session_id: Optional[str]) -> None:
    """Handle ReAct mode for intelligent task planning and execution."""
    # Initialize ReAct service
    react_service = ReActService(config_obj)
    
    try:
        await react_service.start()
        console.print("[bold green]🤖 ReAct Engine Activated[/bold green]")
        console.print("[dim]Intelligent task planning and execution enabled[/dim]\n")
        
        if not interactive and message:
            # Single message mode with ReAct
            await _handle_single_react_message(react_service, message, session_id)
        elif interactive:
            # Interactive ReAct mode
            await _handle_interactive_react_mode(react_service, session_id)
        
    finally:
        await react_service.stop()


async def _handle_single_react_message(react_service: ReActService, message: str, session_id: Optional[str]) -> None:
    """Handle a single message through ReAct engine."""
    console.print(f"[bold blue]Processing:[/bold blue] {message}")
    console.print()
    
    try:
        async for update in react_service.process_user_request(message, session_id):
            _display_react_update(update)
            
    except Exception as e:
        console.print(f"[red]ReAct processing failed: {e}[/red]")


async def _handle_interactive_react_mode(react_service: ReActService, initial_session_id: Optional[str]) -> None:
    """Handle interactive ReAct mode."""
    console.print("[bold green]Starting interactive ReAct mode...[/bold green]")
    console.print("[dim]Type 'quit' or 'exit' to end, 'help' for commands[/dim]\n")
    
    current_session_id = initial_session_id
    consecutive_errors = 0
    max_consecutive_errors = 3
    
    while True:
        try:
            # Get user input
            try:
                user_input = click.prompt("You", type=str)
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Chat interrupted. Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"\n[red]Input error: {e}[/red]")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    console.print(f"[red]Too many consecutive input errors ({consecutive_errors}). Exiting.[/red]")
                    break
                continue
            
            # Reset error counter on successful input
            consecutive_errors = 0
            
            # Handle empty input
            if not user_input.strip():
                console.print("[yellow]Please enter a command or message.[/yellow]")
                continue
            
            # Handle exit commands
            if user_input.lower() in ['quit', 'exit', 'q']:
                console.print("[yellow]Goodbye![/yellow]")
                break
            
            # Handle help commands
            if user_input.lower() in ['help', '?']:
                _show_react_help()
                continue
            
            # Handle session commands
            if user_input.lower().startswith('sessions'):
                try:
                    await _handle_session_commands(react_service, user_input)
                except Exception as e:
                    console.print(f"[red]Session command error: {e}[/red]")
                continue
            
            # Handle status commands
            if user_input.lower().startswith('status'):
                try:
                    await _show_service_status(react_service)
                except Exception as e:
                    console.print(f"[red]Status command error: {e}[/red]")
                continue
            
            # Process input through ReAct
            console.print(f"\n[bold blue]🧠 Reasoning & Planning:[/bold blue] {user_input}")
            console.print()
            
            try:
                async for update in react_service.process_user_request(user_input, current_session_id):
                    _display_react_update(update)
                    
                    # Update current session ID
                    if update.get("session_id"):
                        current_session_id = update["session_id"]
                        
            except Exception as e:
                console.print(f"[red]Processing error: {e}[/red]")
                console.print("[dim]Please try again or type 'help' for assistance.[/dim]")
            
            console.print()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Chat interrupted. Goodbye![/yellow]")
            break
        except EOFError:
            console.print("\n[yellow]End of input. Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Unexpected error: {e}[/red]")
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                console.print(f"[red]Too many consecutive errors ({consecutive_errors}). Exiting for safety.[/red]")
                break
            console.print("[dim]Please try again or type 'quit' to exit.[/dim]")


def _display_react_update(update: dict) -> None:
    """Display a ReAct update in a formatted way."""
    update_type = update.get("type", "unknown")
    content = update.get("content", "")
    
    if update_type == "status_update":
        console.print(f"[cyan]ℹ️  {content}[/cyan]")
    
    elif update_type == "task_plan":
        console.print(f"[green]📋 Task Plan Created[/green]")
        tasks = update.get("tasks", [])
        for i, task in enumerate(tasks):
            console.print(f"  {i+1}. {task.get('description', 'Unknown task')}")
    
    elif update_type == "tool_progress":
        result_type = update.get("result_type", "info")
        if result_type == "error":
            console.print(f"    [red]❌ {content}[/red]")
        elif result_type == "success":
            console.print(f"    [green]✅ {content}[/green]")
        else:
            console.print(f"    [dim]⚙️  {content}[/dim]")
    
    elif update_type == "task_result":
        task_status = update.get("status", "unknown")
        if task_status == "completed":
            console.print(f"[green]✅ {content}[/green]")
        else:
            console.print(f"[yellow]⚠️  {content}[/yellow]")
    
    elif update_type == "final_result":
        console.print(f"\n[bold green]🎉 {content}[/bold green]")
        summary = update.get("summary", {})
        if summary:
            console.print(f"[dim]Tasks: {summary.get('successful_tasks', 0)}/{summary.get('total_tasks', 0)} successful[/dim]")
    
    elif update_type == "error":
        console.print(f"[red]❌ Error: {content}[/red]")
    
    elif update_type == "overall_assessment":
        console.print(f"[blue]📊 Assessment: {content}[/blue]")
    
    else:
        console.print(f"[dim]{content}[/dim]")


def _show_react_help():
    """Show ReAct mode help."""
    console.print("\n[bold]ReAct Mode Commands:[/bold]")
    console.print("  [dim]quit/exit/q     - Exit ReAct mode[/dim]")
    console.print("  [dim]help/?          - Show this help[/dim]")
    console.print("  [dim]sessions list   - List available sessions[/dim]")
    console.print("  [dim]sessions info   - Show current session info[/dim]")
    console.print("  [dim]status          - Show service status[/dim]")
    console.print("  [dim]<your request>  - Process through ReAct engine[/dim]")
    console.print()


async def _handle_session_commands(react_service: ReActService, command: str):
    """Handle session-related commands."""
    parts = command.split()
    if len(parts) < 2:
        console.print("[yellow]Usage: sessions <list|info> [session_id][/yellow]")
        return
    
    subcommand = parts[1].lower()
    
    if subcommand == "list":
        sessions = await react_service.list_sessions(limit=10)
        if sessions:
            console.print("\n[bold]Recent Sessions:[/bold]")
            for session in sessions:
                console.print(f"  {session['id'][:8]}... - {session['user_input'][:50]}... ({session['state']})")
        else:
            console.print("[dim]No sessions found[/dim]")
    
    elif subcommand == "info":
        session_id = parts[2] if len(parts) > 2 else None
        if not session_id:
            console.print("[yellow]Please provide session ID[/yellow]")
            return
        
        session_info = await react_service.get_session_info(session_id)
        if session_info:
            console.print(f"\n[bold]Session {session_id[:8]}...:[/bold]")
            console.print(f"  Input: {session_info.get('user_input', 'N/A')}")
            console.print(f"  State: {session_info.get('state', 'N/A')}")
            console.print(f"  Tasks: {len(session_info.get('tasks', []))}")
            console.print(f"  Created: {session_info.get('created_at', 'N/A')}")
        else:
            console.print(f"[red]Session not found: {session_id}[/red]")


async def _show_service_status(react_service: ReActService):
    """Show ReAct service status."""
    status = await react_service.get_service_status()
    
    console.print("\n[bold]ReAct Service Status:[/bold]")
    console.print(f"  Running: {status.get('service_running', False)}")
    console.print(f"  AI Client: {status.get('ai_client_type', 'Unknown')}")
    console.print(f"  Execution Mode: {status.get('execution_mode', 'Unknown')}")
    console.print(f"  Available Tools: {len(status.get('available_tools', []))}")
    
    session_stats = status.get('session_statistics', {})
    if session_stats:
        console.print(f"  Active Sessions: {session_stats.get('active_sessions', 0)}")
        console.print(f"  Total Sessions: {session_stats.get('total_sessions', 0)}")


async def _handle_traditional_mode(config_obj: Config, message: Optional[str], interactive: bool) -> None:
    """Handle traditional conversation mode."""
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
    consecutive_errors = 0
    max_consecutive_errors = 3
    
    while True:
        try:
            # Get user input
            try:
                user_input = click.prompt("You", type=str)
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]Chat interrupted. Goodbye![/yellow]")
                break
            except Exception as e:
                console.print(f"\n[red]Input error: {e}[/red]")
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    console.print(f"[red]Too many consecutive input errors ({consecutive_errors}). Exiting.[/red]")
                    break
                continue
            
            # Reset error counter on successful input
            consecutive_errors = 0
            
            # Handle empty input
            if not user_input.strip():
                console.print("[yellow]Please enter a message.[/yellow]")
                continue
            
            # Handle exit commands
            if user_input.lower() in ['quit', 'exit', 'q']:
                console.print("[yellow]Goodbye![/yellow]")
                break
            
            # Handle clear commands
            if user_input.lower() in ['clear', 'reset']:
                conversation.clear_messages()
                console.print("[yellow]Conversation cleared.[/yellow]")
                continue
            
            # Handle help commands
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
            
            try:
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
            except Exception as e:
                console.print(f"\n[red]AI response error: {e}[/red]")
                console.print("[dim]Please try again or type 'help' for assistance.[/dim]")
            
            console.print()
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Chat interrupted. Goodbye![/yellow]")
            break
        except EOFError:
            console.print("\n[yellow]End of input. Goodbye![/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Unexpected error: {e}[/red]")
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                console.print(f"[red]Too many consecutive errors ({consecutive_errors}). Exiting for safety.[/red]")
                break
            console.print("[dim]Please try again or type 'quit' to exit.[/dim]")


if __name__ == "__main__":
    main()