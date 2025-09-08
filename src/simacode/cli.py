"""
Command-line interface for SimaCode.

This module provides the main entry point for the SimaCode CLI application,
handling command parsing, configuration loading, and application initialization.
"""

import asyncio
import sys
import logging
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.traceback import install

from .config import Config
from .logging_config import setup_logging
from .core.service import SimaCodeService, ChatRequest, ReActRequest
from .cli_mcp import mcp_group

# Install rich traceback handler for better error display
install(show_locals=True)

console = Console()
logger = logging.getLogger(__name__)

# Global service instance to prevent repeated initialization in CLI
_global_simacode_service: Optional[SimaCodeService] = None
_service_init_lock = asyncio.Lock()


@click.group(invoke_without_command=True)
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
        ctx.exit(0)
    
    # If no command is provided, show help
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        ctx.exit(0)
    
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
@click.option(
    "--scope",
    type=str,
    help="🎯 Set context scope (e.g., 'ticmaker')",
)
@click.pass_context
def chat(ctx: click.Context, message: Optional[str], interactive: bool, react: bool, session_id: Optional[str], scope: Optional[str]) -> None:
    """Start a chat session with the AI assistant."""
    config_obj = ctx.obj["config"]
    
    if not interactive and not message:
        console.print("[yellow]No message provided. Use --interactive for interactive mode.[/yellow]")
        return
    
    # 🎯 构建context信息支持作用域
    context = {}
    if scope == "ticmaker":
        context["scope"] = "ticmaker"
        context["ticmaker_processing"] = True
        context["cli_mode"] = True
        context["trigger_ticmaker_tool"] = True
        console.print("[bold green]🎯 TICMaker模式已启用[/bold green]")
    elif scope:
        context["scope"] = scope
    
    asyncio.run(_run_chat(ctx, message, interactive, react, session_id, context))


async def _get_or_create_service(config_obj) -> SimaCodeService:
    """Get or create a global SimaCodeService instance to prevent repeated initialization."""
    global _global_simacode_service
    
    async with _service_init_lock:
        if _global_simacode_service is None:
            logger.info("Initializing global SimaCodeService instance for CLI")
            _global_simacode_service = SimaCodeService(config_obj, api_mode=False)
        return _global_simacode_service

async def _run_chat(ctx: click.Context, message: Optional[str], interactive: bool, react: bool, session_id: Optional[str], context: dict = None) -> None:
    """Run the chat functionality using unified SimaCodeService with context support."""
    config_obj = ctx.obj["config"]
    
    try:
        # Use global service instance to prevent repeated MCP initialization
        simacode_service = await _get_or_create_service(config_obj)
        
        if react:
            # Use ReAct mode for intelligent task planning and execution
            await _handle_react_mode(simacode_service, message, interactive, session_id, context)
        else:
            # Use traditional conversation mode
            await _handle_chat_mode(simacode_service, message, interactive, session_id, context)
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")


async def _handle_react_mode(simacode_service: SimaCodeService, message: Optional[str], interactive: bool, session_id: Optional[str], context: dict = None) -> None:
    """Handle ReAct mode for intelligent task planning and execution."""
    console.print("[bold green]🤖 ReAct Engine Activated[/bold green]")
    console.print("[dim]Intelligent task planning and execution enabled[/dim]\n")
    
    try:
        if not interactive and message:
            # Single message mode with ReAct - use streaming for better UX
            request = ReActRequest(task=message, session_id=session_id, context=context or {})
            
            console.print(f"[bold yellow]🔄 Processing:[/bold yellow] {message}\n")
            
            final_result = None
            step_count = 0
            
            async for update in await simacode_service.process_react(request, stream=True):
                step_count += 1
                update_type = update.get("type", "unknown")
                content = update.get("content", "")
                
                if update_type == "status_update":
                    console.print(f"[dim]• {content}[/dim]")
                elif update_type == "confirmation_request":
                    # CLI模式下确认请求现在在engine内部同步处理，这里只显示信息
                    await _handle_confirmation_request(update, simacode_service)
                elif update_type == "confirmation_timeout":
                    console.print(f"[red]⏰ {content}[/red]")
                elif update_type == "task_replanned":
                    console.print(f"[blue]🔄 {content}[/blue]")
                elif update_type == "confirmation_skipped":
                    console.print(f"[bold green]⚡ {content}[/bold green]")
                elif update_type == "conversational_response":
                    # 对话性回复，直接显示内容，不显示额外标识
                    console.print(f"[white]{content}[/white]")
                    final_result = content
                elif update_type == "sub_task_result" or update_type == "final_result":
                    final_result = content
                    console.print(f"[bold green]✅ {content}[/bold green]")
                elif update_type == "error":
                    console.print(f"[red]❌ {content}[/red]")
                elif update_type == "tool_execution":
                    console.print(f"[blue]🔧 {content}[/blue]")
                else:
                    console.print(f"[cyan]{content}[/cyan]")
            
            if final_result:
                console.print(f"\n[bold blue]Task Result:[/bold blue]\n{final_result}")
            
            console.print(f"\n[dim]Execution steps: {step_count}[/dim]")
        else:
            # Interactive ReAct mode
            console.print("Type 'exit' or 'quit' to end the session.\n")
            
            while True:
                try:
                    user_input = console.input("[bold blue]ReAct>[/bold blue] ")
                    if user_input.lower() in ['exit', 'quit', 'q']:
                        break
                    
                    if user_input.strip():
                        request = ReActRequest(task=user_input, session_id=session_id, context=context or {})
                        
                        console.print(f"[bold yellow]🔄 Processing:[/bold yellow] {user_input}\n")
                        
                        final_result = None
                        step_count = 0
                        current_session_id = session_id
                        
                        async for update in await simacode_service.process_react(request, stream=True):
                            step_count += 1
                            update_type = update.get("type", "unknown")
                            content = update.get("content", "")
                            
                            # Update session ID if provided
                            if update.get("session_id"):
                                current_session_id = update["session_id"]
                            
                            if update_type == "status_update":
                                console.print(f"[dim]• {content}[/dim]")
                            elif update_type == "confirmation_request":
                                # CLI模式下确认请求现在在engine内部同步处理，这里只显示信息
                                await _handle_confirmation_request(update, simacode_service)
                            elif update_type == "confirmation_timeout":
                                console.print(f"[red]⏰ {content}[/red]")
                            elif update_type == "task_replanned":
                                console.print(f"[blue]🔄 {content}[/blue]")
                            elif update_type == "confirmation_skipped":
                                console.print(f"[bold green]⚡ {content}[/bold green]")
                            elif update_type == "conversational_response":
                                # 对话性回复，直接显示内容，不显示额外标识
                                console.print(f"[white]{content}[/white]")
                                final_result = content
                            elif update_type == "sub_task_result" or update_type == "final_result":
                                final_result = content
                                console.print(f"[bold green]✅ {content}[/bold green]")
                            elif update_type == "error":
                                console.print(f"[red]❌ {content}[/red]")
                            elif update_type == "tool_execution":
                                console.print(f"[blue]🔧 {content}[/blue]")
                            elif update_type == "reasoning":
                                console.print(f"[magenta]🤔 {content}[/magenta]")
                            elif update_type == "planning":
                                console.print(f"[yellow]📋 {content}[/yellow]")
                            else:
                                console.print(f"[cyan]{content}[/cyan]")
                        
                        session_id = current_session_id  # Update session_id for next iteration
                        
                        if final_result:
                            console.print(f"\n[bold green]Result:[/bold green]\n{final_result}\n")
                        else:
                            console.print(f"\n[dim]Completed {step_count} processing steps[/dim]\n")
                            
                except KeyboardInterrupt:
                    console.print("\n[yellow]Interrupted by user[/yellow]")
                    break
                except EOFError:
                    break
                    
    except Exception as e:
        console.print(f"[red]ReAct mode error: {e}[/red]")


async def _handle_confirmation_request(update: dict, simacode_service: SimaCodeService):
    """处理确认请求 - 简化版，实际确认逻辑在engine.py中"""
    
    tasks_summary = update.get("tasks_summary", {})
    session_id = update.get("session_id")
    confirmation_round = update.get("confirmation_round", 1)
    
    # 显示任务计划头部信息
    round_info = f" (第{confirmation_round}轮)" if confirmation_round > 1 else ""
    console.print(f"\n[bold yellow]📋 任务执行计划确认{round_info}[/bold yellow]")
    console.print(f"会话ID: {session_id}")
    console.print(f"计划任务数: {tasks_summary.get('total_tasks', 0)}")
    console.print(f"风险等级: {tasks_summary.get('risk_level', 'unknown')}")
    
    if confirmation_round > 1:
        console.print(f"[dim]※ 这是根据您的修改建议重新规划的任务计划[/dim]")
    console.print()
    
    # 注意：实际的确认界面交互逻辑现在在engine.py的handle_cli_confirmation方法中处理
    # 这里只是显示头部信息，具体的用户交互会在engine的CLI模式分支中处理


async def _handle_chat_mode(simacode_service: SimaCodeService, message: Optional[str], interactive: bool, session_id: Optional[str], context: dict = None) -> None:
    """Handle traditional chat mode."""
    console.print("[bold green]💬 Chat Mode Activated[/bold green]")
    console.print("[dim]Direct AI conversation enabled[/dim]\n")
    
    try:
        if not interactive and message:
            # 🎯 根据context决定是否强制ReAct模式
            force_mode = None if (context and context.get("trigger_ticmaker_tool")) else "chat"
            
            request = ChatRequest(
                message=message, 
                session_id=session_id, 
                force_mode=force_mode,
                context=context or {}  # 🎯 传递context
            )
            response = await simacode_service.process_chat(request)
            
            if response.error:
                console.print(f"[red]Error: {response.error}[/red]")
            else:
                console.print(f"[bold green]Assistant:[/bold green]\n{response.content}")
        else:
            # Interactive chat mode
            console.print("Type 'exit' or 'quit' to end the session.\n")
            
            while True:
                try:
                    user_input = console.input("[bold blue]You>[/bold blue] ")
                    if user_input.lower() in ['exit', 'quit', 'q']:
                        break
                    
                    if user_input.strip():
                        # 🎯 根据context决定是否强制ReAct模式
                        force_mode = None if (context and context.get("trigger_ticmaker_tool")) else "chat"
                        
                        request = ChatRequest(
                            message=user_input, 
                            session_id=session_id, 
                            force_mode=force_mode,
                            context=context or {}  # 🎯 传递context
                        )
                        response = await simacode_service.process_chat(request)
                        session_id = response.session_id  # Update session_id
                        
                        if response.error:
                            console.print(f"[red]Error: {response.error}[/red]")
                        else:
                            console.print(f"\n[bold green]Assistant:[/bold green]\n{response.content}\n")
                            
                except KeyboardInterrupt:
                    console.print("\n[yellow]Interrupted by user[/yellow]")
                    break
                except EOFError:
                    break
                    
    except Exception as e:
        console.print(f"[red]Chat mode error: {e}[/red]")


# Add serve command for API mode
@main.command()
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind the server to",
)
@click.option(
    "--port",
    default=8000,
    help="Port to bind the server to",
)
@click.option(
    "--workers",
    default=1,
    help="Number of worker processes",
)
@click.option(
    "--reload",
    is_flag=True,
    help="Enable auto-reload for development",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable DEBUG logging for HTTP requests/responses",
)
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, workers: int, reload: bool, debug: bool) -> None:
    """Start SimaCode in API service mode."""
    config_obj = ctx.obj["config"]
    
    # 如果启用了debug选项，覆盖配置中的日志级别
    if debug:
        config_obj.logging.level = "DEBUG"
        console.print("[bold yellow]🐛 DEBUG mode enabled - HTTP requests/responses will be logged[/bold yellow]")
    
    console.print("[bold green]🚀 Starting SimaCode API Server[/bold green]")
    console.print(f"[dim]Host: {host}:{port}[/dim]")
    console.print(f"[dim]Workers: {workers}[/dim]")
    console.print(f"[dim]Reload: {reload}[/dim]")
    console.print(f"[dim]Debug: {debug}[/dim]\n")
    
    try:
        # Import here to avoid circular imports and optional dependency
        import uvicorn
        from .api.app import create_app
        
        # Create FastAPI app with config
        app = create_app(config_obj)
        
        # 设置 uvicorn 日志级别
        uvicorn_log_level = "debug" if debug else "info"
        
        # Run the server
        uvicorn.run(
            app,
            host=host,
            port=port,
            workers=workers if not reload else 1,  # uvicorn doesn't support workers with reload
            reload=reload,
            log_level=uvicorn_log_level
        )
        
    except ImportError:
        console.print("[red]FastAPI and uvicorn are required for API mode.[/red]")
        console.print("[yellow]Install with: pip install 'simacode[api]'[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Failed to start server: {e}[/red]")
        sys.exit(1)


# Add MCP command group to main CLI
main.add_command(mcp_group)


if __name__ == "__main__":
    main()