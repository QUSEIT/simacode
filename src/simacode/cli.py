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
from rich.progress import Progress, TaskID, BarColumn, TextColumn, TimeRemainingColumn, SpinnerColumn
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich import box
import time

from .config import Config
from .logging_config import setup_logging
from .core.service import SimaCodeService, ChatRequest, ReActRequest
from .cli_mcp import mcp_group
from .mcp.async_integration import get_global_task_manager, TaskType, TaskStatus

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


async def _show_async_task_progress(task_manager, task_id: str, task_name: str) -> None:
    """显示异步任务的富文本进度。"""
    console.print(f"[bold green]🔄 Detected long-running task, switching to async mode...[/bold green]")
    console.print(f"[dim]🚀 Task submitted: {task_id}[/dim]\n")

    # 创建进度显示
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
        transient=False
    )

    task_progress_id = progress.add_task(f"[green]Processing: {task_name}", total=100)

    messages = []
    start_time = time.time()

    with progress:
        try:
            async for progress_data in task_manager.get_task_progress_stream(task_id):
                progress_type = progress_data.get("type", "progress")
                message = progress_data.get("message", "")
                progress_value = progress_data.get("progress")

                # 更新进度条
                if progress_value is not None:
                    progress.update(task_progress_id, completed=progress_value)

                # 显示状态消息
                if progress_type == "started":
                    console.print("[dim]📈 Task started...[/dim]")
                    progress.update(task_progress_id, description="[blue]Starting task...")

                elif progress_type == "progress":
                    if message:
                        stage = progress_data.get("stage", "Processing")
                        console.print(f"[dim]📈 {stage}: {message}[/dim]")
                        progress.update(task_progress_id, description=f"[blue]{stage}...")

                elif progress_type == "final_result":
                    progress.update(task_progress_id, completed=100)
                    progress.update(task_progress_id, description="[green]✅ Completed")

                    result = progress_data.get("result", {})
                    if isinstance(result, dict):
                        if result.get("status"):
                            console.print(f"[bold green]✅ {result['status']}[/bold green]")
                        if result.get("task"):
                            console.print(f"[green]Task: {result['task']}[/green]")

                    # 显示执行摘要
                    elapsed_time = time.time() - start_time
                    execution_time = progress_data.get("execution_time", elapsed_time)

                    summary_table = Table(show_header=False, box=box.ROUNDED, width=60)
                    summary_table.add_column("Field", style="bold cyan")
                    summary_table.add_column("Value", style="white")

                    summary_table.add_row("Task ID", task_id)
                    summary_table.add_row("Execution Time", f"{execution_time:.2f}s")
                    summary_table.add_row("Status", "[green]Completed Successfully[/green]")

                    summary_panel = Panel(
                        summary_table,
                        title="📊 Task Summary",
                        title_align="left"
                    )

                    console.print("\n")
                    console.print(summary_panel)
                    break

                elif progress_type == "error":
                    progress.update(task_progress_id, description="[red]❌ Failed")
                    error_msg = progress_data.get("error", message)
                    console.print(f"[red]❌ Error: {error_msg}[/red]")
                    break

                elif progress_type == "cancelled":
                    progress.update(task_progress_id, description="[yellow]🚫 Cancelled")
                    console.print(f"[yellow]🚫 Task was cancelled[/yellow]")
                    break

        except Exception as e:
            console.print(f"[red]❌ Progress monitoring error: {str(e)}[/red]")


async def _handle_react_mode(simacode_service: SimaCodeService, message: Optional[str], interactive: bool, session_id: Optional[str], context: dict = None) -> None:
    """Handle ReAct mode for intelligent task planning and execution."""
    console.print("[bold green]🤖 ReAct Engine Activated[/bold green]")
    console.print("[dim]Intelligent task planning and execution enabled[/dim]\n")
    
    try:
        if not interactive and message:
            # Single message mode with ReAct - check if async processing is needed
            request = ReActRequest(task=message, session_id=session_id, context=context or {})

            # 检测是否需要异步处理
            try:
                requires_async = await simacode_service._requires_async_execution(request)

                if requires_async:
                    # 异步模式：提交任务并显示进度
                    task_manager = get_global_task_manager()
                    task_id = await task_manager.submit_task(TaskType.REACT, request)

                    # 显示富文本进度
                    await _show_async_task_progress(task_manager, task_id, message)
                    return

            except Exception as e:
                # 如果异步检测失败，回退到同步模式
                console.print(f"[yellow]⚠️ Async detection failed, using sync mode: {str(e)}[/yellow]")

            # 同步模式：原有的流式处理
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

                        # 检测是否需要异步处理（交互式模式下也支持）
                        try:
                            requires_async = await simacode_service._requires_async_execution(request)

                            if requires_async:
                                # 异步模式：提交任务并显示进度
                                task_manager = get_global_task_manager()
                                task_id = await task_manager.submit_task(TaskType.REACT, request)

                                # 显示富文本进度
                                await _show_async_task_progress(task_manager, task_id, user_input)
                                continue  # 继续下一次交互

                        except Exception as e:
                            # 如果异步检测失败，回退到同步模式
                            console.print(f"[yellow]⚠️ Async detection failed, using sync mode: {str(e)}[/yellow]")

                        # 同步模式：原有的流式处理
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
        # Import here to avoid circular imports
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
        
    except Exception as e:
        console.print(f"[red]Failed to start server: {e}[/red]")
        sys.exit(1)


# Task management commands
@click.group(name="task")
def task_group():
    """Manage async tasks."""
    pass


@task_group.command("list")
@click.pass_context
def list_tasks(ctx: click.Context) -> None:
    """List all active async tasks."""
    asyncio.run(_list_tasks_async(ctx))


async def _list_tasks_async(ctx: click.Context) -> None:
    """Async implementation of list tasks."""
    try:
        task_manager = get_global_task_manager()
        stats = task_manager.get_stats()

        if stats["active_tasks"] == 0:
            console.print("[dim]No active tasks[/dim]")
            return

        # Create tasks table
        table = Table(title="Active Async Tasks")
        table.add_column("Task ID", style="cyan")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="green")
        table.add_column("Created", style="dim")

        for task_id, task in task_manager.active_tasks.items():
            created_time = time.strftime("%H:%M:%S", time.localtime(task.created_at))
            status_color = {
                "pending": "yellow",
                "running": "blue",
                "completed": "green",
                "failed": "red",
                "cancelled": "orange1"
            }.get(task.status.value, "white")

            table.add_row(
                task_id,
                task.task_type.value,
                f"[{status_color}]{task.status.value}[/{status_color}]",
                created_time
            )

        console.print(table)

        # Show summary
        summary_panel = Panel(
            f"Total: {stats['active_tasks']} tasks\\n" +
            "\\n".join([f"{status}: {count}" for status, count in stats["task_breakdown"].items()]),
            title="📊 Summary"
        )
        console.print("\\n")
        console.print(summary_panel)

    except Exception as e:
        console.print(f"[red]Error listing tasks: {e}[/red]")


@task_group.command("status")
@click.argument("task_id")
@click.pass_context
def task_status(ctx: click.Context, task_id: str) -> None:
    """Get detailed status of a specific task."""
    asyncio.run(_task_status_async(ctx, task_id))


async def _task_status_async(ctx: click.Context, task_id: str) -> None:
    """Async implementation of task status."""
    try:
        task_manager = get_global_task_manager()
        task = await task_manager.get_task_status(task_id)

        if not task:
            console.print(f"[red]Task {task_id} not found[/red]")
            return

        # Create status table
        status_table = Table(show_header=False, box=box.ROUNDED)
        status_table.add_column("Field", style="bold cyan")
        status_table.add_column("Value", style="white")

        status_table.add_row("Task ID", task.task_id)
        status_table.add_row("Type", task.task_type.value)
        status_table.add_row("Status", f"[{task.status.value}]{task.status.value}[/{task.status.value}]")

        if task.created_at:
            created_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.created_at))
            status_table.add_row("Created", created_time)

        if task.started_at:
            started_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.started_at))
            status_table.add_row("Started", started_time)

        if task.completed_at:
            completed_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.completed_at))
            status_table.add_row("Completed", completed_time)

            # Calculate duration
            duration = task.completed_at - (task.started_at or task.created_at)
            status_table.add_row("Duration", f"{duration:.2f}s")

        if task.error:
            status_table.add_row("Error", f"[red]{task.error}[/red]")

        if task.metadata:
            status_table.add_row("Metadata", str(task.metadata))

        status_panel = Panel(
            status_table,
            title=f"📋 Task {task_id} Status"
        )
        console.print(status_panel)

    except Exception as e:
        console.print(f"[red]Error getting task status: {e}[/red]")


@task_group.command("cancel")
@click.argument("task_id")
@click.pass_context
def cancel_task_cli(ctx: click.Context, task_id: str) -> None:
    """Cancel a running task."""
    asyncio.run(_cancel_task_async(ctx, task_id))


async def _cancel_task_async(ctx: click.Context, task_id: str) -> None:
    """Async implementation of cancel task."""
    try:
        task_manager = get_global_task_manager()
        success = await task_manager.cancel_task(task_id)

        if success:
            console.print(f"[green]✅ Task {task_id} cancelled successfully[/green]")
        else:
            console.print(f"[red]❌ Failed to cancel task {task_id} (not found or already completed)[/red]")

    except Exception as e:
        console.print(f"[red]Error cancelling task: {e}[/red]")


@task_group.command("restart")
@click.argument("task_id")
@click.pass_context
def restart_task_cli(ctx: click.Context, task_id: str) -> None:
    """Restart a failed or cancelled task."""
    asyncio.run(_restart_task_async(ctx, task_id))


async def _restart_task_async(ctx: click.Context, task_id: str) -> None:
    """Async implementation of restart task."""
    try:
        task_manager = get_global_task_manager()

        # Check original task status first
        original_task = await task_manager.get_task_status(task_id)
        if not original_task:
            console.print(f"[red]❌ Task {task_id} not found[/red]")
            return

        if original_task.status not in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
            console.print(f"[yellow]⚠️ Task {task_id} cannot be restarted (status: {original_task.status.value})[/yellow]")
            console.print("[dim]Only failed or cancelled tasks can be restarted[/dim]")
            return

        # Restart the task
        new_task_id = await task_manager.restart_task(task_id)

        if new_task_id:
            console.print(f"[green]✅ Task {task_id} restarted successfully[/green]")
            console.print(f"[dim]New task ID: {new_task_id}[/dim]")

            # Offer to monitor the new task
            if console.input("[bold blue]Monitor the restarted task? (y/N):[/bold blue] ").lower() in ['y', 'yes']:
                console.print(f"[dim]Monitoring new task: {new_task_id}[/dim]\n")
                await _show_async_task_progress(task_manager, new_task_id, f"Restarted Task {task_id}")
        else:
            console.print(f"[red]❌ Failed to restart task {task_id}[/red]")

    except Exception as e:
        console.print(f"[red]Error restarting task: {e}[/red]")


@task_group.command("monitor")
@click.argument("task_id")
@click.pass_context
def monitor_task(ctx: click.Context, task_id: str) -> None:
    """Monitor a task's progress in real-time."""
    asyncio.run(_monitor_task_async(ctx, task_id))


async def _monitor_task_async(ctx: click.Context, task_id: str) -> None:
    """Async implementation of monitor task."""
    try:
        task_manager = get_global_task_manager()
        task = await task_manager.get_task_status(task_id)

        if not task:
            console.print(f"[red]Task {task_id} not found[/red]")
            return

        console.print(f"[bold green]🔍 Monitoring task: {task_id}[/bold green]")
        console.print(f"[dim]Press Ctrl+C to stop monitoring[/dim]\\n")

        # Use the existing progress display function
        await _show_async_task_progress(task_manager, task_id, f"Task {task_id}")

    except KeyboardInterrupt:
        console.print("\\n[yellow]Monitoring stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error monitoring task: {e}[/red]")


# Add command groups to main CLI
main.add_command(task_group)
main.add_command(mcp_group)


if __name__ == "__main__":
    main()