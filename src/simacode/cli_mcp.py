"""
MCP Tool CLI Integration for SimaCode

This module provides command-line interface commands for managing and executing
MCP (Model Context Protocol) tools through the SimaCode CLI.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax

from .mcp.integration import SimaCodeToolRegistry, initialize_mcp_integration
from .mcp.config import MCPConfigManager
from .tools.base import ToolResult, ToolResultType

console = Console()


@click.group(name="mcp")
def mcp_group():
    """MCP (Model Context Protocol) tool management and execution."""
    pass


@mcp_group.command()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=Path),
    help="Path to MCP configuration file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed initialization information",
)
def init(config: Optional[Path], verbose: bool) -> None:
    """Initialize MCP integration with servers."""
    
    with console.status("[bold green]Initializing MCP integration..."):
        try:
            success = asyncio.run(_initialize_mcp(config, verbose))
            
            if success:
                console.print("✅ [bold green]MCP integration initialized successfully![/bold green]")
            else:
                console.print("❌ [bold red]Failed to initialize MCP integration[/bold red]")
                
        except Exception as e:
            console.print(f"❌ [bold red]Error initializing MCP: {str(e)}[/bold red]")


@mcp_group.command()
@click.option(
    "--category",
    "-c",
    type=str,
    help="Filter tools by category (e.g., file, web, data)",
)
@click.option(
    "--server",
    "-s", 
    type=str,
    help="Filter tools by server name",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["table", "json", "simple"]),
    default="table",
    help="Output format",
)
def list(category: Optional[str], server: Optional[str], format: str) -> None:
    """List all available MCP tools."""
    
    try:
        asyncio.run(_list_tools_async(category, server, format))
    except Exception as e:
        console.print(f"❌ [bold red]Error listing tools: {str(e)}[/bold red]")


async def _list_tools_async(category: Optional[str], server: Optional[str], format: str) -> None:
    """Async implementation of list tools."""
    try:
        registry = SimaCodeToolRegistry()
        tools = await registry.list_tools()
        
        if not tools:
            console.print("[yellow]No tools available. Initialize MCP first with 'simacode mcp init'[/yellow]")
            return
        
        # Filter tools if needed
        filtered_tools = tools
        if category:
            filtered_tools = registry.list_tools_by_category(category)
        
        if server:
            # Filter by server (tools with server prefix)
            filtered_tools = [t for t in filtered_tools if server in t]
        
        if format == "json":
            await _output_tools_json_async(registry, filtered_tools)
        elif format == "simple":
            _output_tools_simple(filtered_tools)
        else:
            await _output_tools_table_async(registry, filtered_tools)
            
    except Exception as e:
        console.print(f"❌ [bold red]Error listing tools: {str(e)}[/bold red]")


@mcp_group.command()
@click.argument("tool_name")
@click.option(
    "--params",
    "-p",
    type=str,
    help="Tool parameters as JSON string",
)
@click.option(
    "--param",
    multiple=True,
    help="Individual parameter as key=value (can be used multiple times)",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Interactive parameter input",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be executed without running",
)
def run(tool_name: str, params: Optional[str], param: tuple, interactive: bool, dry_run: bool) -> None:
    """Execute an MCP tool with parameters."""
    
    try:
        # Prepare parameters
        tool_params = {}
        
        if params:
            try:
                tool_params = json.loads(params)
            except json.JSONDecodeError as e:
                console.print(f"❌ [red]Invalid JSON parameters: {str(e)}[/red]")
                return
        
        # Add individual parameters
        for p in param:
            if "=" not in p:
                console.print(f"❌ [red]Invalid parameter format: {p}. Use key=value[/red]")
                return
            key, value = p.split("=", 1)
            tool_params[key] = value
        
        # Interactive parameter input
        if interactive:
            tool_params = _get_interactive_params(tool_name, tool_params)
        
        if dry_run:
            _show_dry_run(tool_name, tool_params)
            return
        
        # Execute tool
        asyncio.run(_execute_tool(tool_name, tool_params))
        
    except Exception as e:
        console.print(f"❌ [bold red]Error executing tool: {str(e)}[/bold red]")


@mcp_group.command()
@click.argument("query")
@click.option(
    "--fuzzy",
    "-f",
    is_flag=True,
    help="Enable fuzzy matching",
)
@click.option(
    "--limit",
    "-l",
    type=int,
    default=10,
    help="Maximum number of results",
)
def search(query: str, fuzzy: bool, limit: int) -> None:
    """Search for tools by name or description."""
    
    try:
        registry = SimaCodeToolRegistry()
        results = registry.search_tools(query, fuzzy=fuzzy)
        
        if not results:
            console.print(f"[yellow]No tools found matching '{query}'[/yellow]")
            return
        
        # Limit results
        results = results[:limit]
        
        table = Table(title=f"Search Results for '{query}'")
        table.add_column("Tool Name", style="cyan")
        table.add_column("Score", style="magenta")
        table.add_column("Type", style="green")
        table.add_column("Description", style="white")
        
        for result in results:
            table.add_row(
                result["tool_name"],
                str(result["score"]),
                result.get("type", "unknown"),
                result.get("description", "No description")[:60] + "..."
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"❌ [bold red]Error searching tools: {str(e)}[/bold red]")


@mcp_group.command()
@click.argument("tool_name")
def info(tool_name: str) -> None:
    """Show detailed information about a specific tool."""
    
    try:
        asyncio.run(_info_tool_async(tool_name))
    except Exception as e:
        console.print(f"❌ [bold red]Error getting tool info: {str(e)}[/bold red]")


async def _info_tool_async(tool_name: str) -> None:
    """Async implementation of info command."""
    try:
        registry = SimaCodeToolRegistry()
        tool_info = await registry.get_tool_info(tool_name)
        
        if not tool_info:
            console.print(f"❌ [red]Tool '{tool_name}' not found[/red]")
            return
        
        # Create info panel
        tool_display_name = tool_info.get('wrapper_name', tool_info.get('name', tool_name))
        info_content = f"""
[bold]Name:[/bold] {tool_display_name}
[bold]Type:[/bold] {tool_info.get('type', 'unknown')}
[bold]Description:[/bold] {tool_info.get('server_description', tool_info.get('description', 'No description'))}
"""
        
        if tool_info.get('type') == 'mcp':
            info_content += f"""
[bold]Server:[/bold] {tool_info.get('server_name', 'unknown')}
[bold]Namespace:[/bold] {tool_info.get('namespace', 'none')}
[bold]Original Tool:[/bold] {tool_info.get('mcp_tool_name', 'unknown')}
[bold]Health Status:[/bold] {'✅ Healthy' if tool_info.get('is_healthy', False) else '❌ Unhealthy'}
[bold]Total Executions:[/bold] {tool_info.get('execution_stats', {}).get('total_executions', 0)}
"""
        
        panel = Panel(info_content, title=f"Tool Information: {tool_name}", expand=False)
        console.print(panel)
        
        # Show input schema if available
        if 'input_schema' in tool_info:
            schema_json = json.dumps(tool_info['input_schema'], indent=2)
            syntax = Syntax(schema_json, "json", theme="monokai", line_numbers=True)
            console.print("\n[bold]Input Schema:[/bold]")
            console.print(syntax)
        
    except Exception as e:
        console.print(f"❌ [bold red]Error getting tool info: {str(e)}[/bold red]")


@mcp_group.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force cleanup without confirmation",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed cleanup information",
)
def deinit(force: bool, verbose: bool) -> None:
    """Deinitialize MCP integration and cleanup resources."""
    
    try:
        if not force:
            # Ask for confirmation
            import click
            if not click.confirm("This will shut down all MCP servers and clear tool registrations. Continue?"):
                console.print("[yellow]Deinitialize cancelled[/yellow]")
                return
        
        asyncio.run(_deinitialize_mcp(verbose))
        
    except Exception as e:
        console.print(f"❌ [bold red]Error during MCP deinitialize: {str(e)}[/bold red]")


async def _deinitialize_mcp(verbose: bool) -> None:
    """Async implementation of MCP deinitialize."""
    
    with console.status("[bold red]Deinitializing MCP integration..."):
        try:
            registry = SimaCodeToolRegistry()
            
            if verbose:
                console.print("🔍 [bold]Checking MCP status...[/bold]")
            
            # Check if MCP is currently initialized
            if not registry.mcp_enabled and not registry.state_manager.is_initialized():
                console.print("[yellow]MCP integration is not initialized[/yellow]")
                return
            
            # Get current statistics before shutdown
            if registry.mcp_enabled:
                stats = registry.get_registry_stats()
                tools_count = stats.get('mcp_tools', 0)
                servers_count = stats.get('mcp_servers', 0)
                
                if verbose:
                    console.print(f"📊 Found {tools_count} MCP tools from {servers_count} servers")
            else:
                tools_count = 0
                servers_count = 0
                if verbose:
                    console.print("📊 MCP integration was previously initialized but not currently active")
            
            # Shutdown MCP integration
            if verbose:
                console.print("🛑 [bold]Shutting down MCP servers...[/bold]")
            
            await registry.shutdown_mcp()
            
            if verbose:
                console.print("🧹 [bold]Clearing initialization state...[/bold]")
            
            # Ensure state is cleared
            registry.state_manager.clear_initialization_state()
            
            console.print("✅ [bold green]MCP integration deinitialized successfully![/bold green]")
            
            if tools_count > 0 or servers_count > 0:
                console.print(f"📋 Cleaned up {tools_count} tools from {servers_count} servers")
            
            console.print("💡 [dim]Use 'simacode mcp init' to reinitialize MCP integration[/dim]")
            
        except Exception as e:
            console.print(f"❌ [bold red]Failed to deinitialize MCP: {str(e)}[/bold red]")
            if verbose:
                import traceback
                console.print(f"[dim]Error details: {traceback.format_exc()}[/dim]")


@mcp_group.command()
def status() -> None:
    """Show MCP system status and statistics."""
    
    try:
        registry = SimaCodeToolRegistry()
        stats = registry.get_registry_stats()
        
        # Create status table
        table = Table(title="MCP System Status")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Count", style="magenta")
        
        table.add_row("MCP Integration", "✅ Enabled" if stats["mcp_enabled"] else "❌ Disabled", "")
        table.add_row("Built-in Tools", "✅ Available", str(stats["builtin_tools"]))
        table.add_row("MCP Tools", "✅ Available" if stats["mcp_enabled"] else "❌ N/A", str(stats.get("mcp_tools", 0)))
        table.add_row("Total Tools", "✅ Available", str(stats["total_tools"]))
        
        if stats["mcp_enabled"]:
            table.add_row("MCP Servers", "✅ Connected", str(stats.get("mcp_servers", 0)))
            table.add_row("Namespaces", "✅ Active", str(stats.get("mcp_namespaces", 0)))
        
        console.print(table)
        
        # Show detailed MCP stats if available
        if stats["mcp_enabled"] and "mcp_stats" in stats:
            mcp_stats = stats["mcp_stats"]
            console.print(f"\n[bold]MCP Details:[/bold]")
            console.print(f"  • Currently registered: {mcp_stats.get('currently_registered', 0)}")
            console.print(f"  • Healthy tools: {mcp_stats.get('healthy_tools', 0)}")
            console.print(f"  • Total registrations: {mcp_stats.get('total_registered', 0)}")
            console.print(f"  • Successful registrations: {mcp_stats.get('successful_registrations', 0)}")
        
    except Exception as e:
        console.print(f"❌ [bold red]Error getting status: {str(e)}[/bold red]")


# Helper functions

async def _initialize_mcp(config_path: Optional[Path], verbose: bool) -> bool:
    """Initialize MCP integration."""
    
    if verbose:
        console.print(f"🔧 Configuration path: {config_path or 'default'}")
    
    try:
        success = await initialize_mcp_integration(config_path)
        
        if verbose and success:
            registry = SimaCodeToolRegistry()
            stats = registry.get_registry_stats()
            console.print(f"📊 Initialized with {stats['total_tools']} tools")
            
        return success
        
    except Exception as e:
        if verbose:
            console.print(f"❌ Initialization error: {str(e)}")
        raise


async def _output_tools_table_async(registry: SimaCodeToolRegistry, tools: List[str]) -> None:
    """Output tools in table format (async version)."""
    
    if not tools:
        console.print("[yellow]No tools found[/yellow]")
        return
    
    table = Table(title="Available Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Version", style="magenta")
    table.add_column("Description", style="white")
    
    for tool_name in tools:
        tool_info = await registry.get_tool_info(tool_name)
        if tool_info:
            table.add_row(
                tool_name,
                tool_info.get("type", "unknown"),
                tool_info.get("version", "unknown"),
                tool_info.get("description", "No description")[:50] + "..."
            )
    
    console.print(table)


def _output_tools_table(registry: SimaCodeToolRegistry, tools: List[str]) -> None:
    """Output tools in table format (legacy sync version)."""
    
    if not tools:
        console.print("[yellow]No tools found[/yellow]")
        return
    
    table = Table(title="Available Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Version", style="magenta")
    table.add_column("Description", style="white")
    
    for tool_name in tools:
        # For sync version, we can't get full tool info from MCP tools
        table.add_row(
            tool_name,
            "unknown",
            "unknown", 
            "Tool information requires async access"
        )
    
    console.print(table)


async def _output_tools_json_async(registry: SimaCodeToolRegistry, tools: List[str]) -> None:
    """Output tools in JSON format (async version)."""
    
    tools_data = []
    for tool_name in tools:
        tool_info = await registry.get_tool_info(tool_name)
        if tool_info:
            tools_data.append(tool_info)
    
    console.print(json.dumps(tools_data, indent=2))


def _output_tools_json(registry: SimaCodeToolRegistry, tools: List[str]) -> None:
    """Output tools in JSON format (legacy sync version)."""
    
    tools_data = []
    for tool_name in tools:
        # For sync version, we provide basic tool info only
        tools_data.append({
            "name": tool_name,
            "type": "unknown",
            "description": "Tool information requires async access"
        })
    
    console.print(json.dumps(tools_data, indent=2))


def _output_tools_simple(tools: List[str]) -> None:
    """Output tools in simple format."""
    for tool in tools:
        console.print(tool)


def _get_interactive_params(tool_name: str, existing_params: Dict[str, Any]) -> Dict[str, Any]:
    """Get parameters interactively."""
    
    console.print(f"\n[bold]Interactive parameter input for: {tool_name}[/bold]")
    console.print("[dim]Press Enter to skip optional parameters, Ctrl+C to cancel[/dim]\n")
    
    params = existing_params.copy()
    
    try:
        # Get tool info to show schema
        registry = SimaCodeToolRegistry()
        tool_info = registry.get_tool_info(tool_name)
        
        if tool_info and 'input_schema' in tool_info:
            schema = tool_info['input_schema']
            properties = schema.get('properties', {})
            required = schema.get('required', [])
            
            for prop_name, prop_info in properties.items():
                if prop_name in params:
                    console.print(f"[green]{prop_name}[/green] (already set): {params[prop_name]}")
                    continue
                
                is_required = prop_name in required
                prompt_text = f"{prop_name}"
                
                if 'description' in prop_info:
                    prompt_text += f" ({prop_info['description']})"
                
                if is_required:
                    prompt_text += " [required]"
                else:
                    prompt_text += " [optional]"
                
                prompt_text += ": "
                
                value = input(prompt_text)
                
                if value or is_required:
                    # Try to convert to appropriate type
                    prop_type = prop_info.get('type', 'string')
                    if prop_type == 'integer':
                        try:
                            params[prop_name] = int(value)
                        except ValueError:
                            console.print(f"[yellow]Warning: '{value}' is not a valid integer, using as string[/yellow]")
                            params[prop_name] = value
                    elif prop_type == 'number':
                        try:
                            params[prop_name] = float(value)
                        except ValueError:
                            console.print(f"[yellow]Warning: '{value}' is not a valid number, using as string[/yellow]")
                            params[prop_name] = value
                    elif prop_type == 'boolean':
                        params[prop_name] = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        params[prop_name] = value
        else:
            # Fallback: ask for generic parameters
            console.print("[yellow]No schema available, using generic parameter input[/yellow]")
            while True:
                param_name = input("Parameter name (empty to finish): ")
                if not param_name:
                    break
                param_value = input(f"Value for {param_name}: ")
                params[param_name] = param_value
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Parameter input cancelled[/yellow]")
        return existing_params
    
    return params


def _show_dry_run(tool_name: str, params: Dict[str, Any]) -> None:
    """Show what would be executed in dry run mode."""
    
    panel_content = f"""
[bold]Tool:[/bold] {tool_name}
[bold]Parameters:[/bold]
{json.dumps(params, indent=2)}

[bold green]This is a dry run - no actual execution will occur[/bold green]
"""
    
    panel = Panel(panel_content, title="Dry Run", expand=False)
    console.print(panel)


async def _execute_tool(tool_name: str, params: Dict[str, Any]) -> None:
    """Execute a tool with given parameters."""
    
    console.print(f"🚀 [bold]Executing tool: {tool_name}[/bold]")
    
    if params:
        console.print(f"📋 [bold]Parameters:[/bold]")
        for key, value in params.items():
            console.print(f"   • {key}: {value}")
    
    # Get registry and let it auto-initialize MCP if needed
    registry = SimaCodeToolRegistry()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Executing...", total=None)
        
        try:
            results = []
            async for result in registry.execute_tool(tool_name, params):
                results.append(result)
                
                # Update progress description based on result type
                if result.type == ToolResultType.PROGRESS:
                    progress.update(task, description=f"Progress: {result.content}")
                elif result.type == ToolResultType.INFO:
                    progress.update(task, description=f"Info: {result.content}")
            
            # Remove task if it still exists
            try:
                progress.remove_task(task)
            except KeyError:
                pass  # Task already removed or doesn't exist
            
            # Display results
            _display_tool_results(tool_name, results)
            
        except Exception as e:
            # Remove task if it still exists
            try:
                progress.remove_task(task)  
            except KeyError:
                pass  # Task already removed or doesn't exist
            console.print(f"❌ [bold red]Execution failed: {str(e)}[/bold red]")


def _display_tool_results(tool_name: str, results: List[ToolResult]) -> None:
    """Display tool execution results."""
    
    if not results:
        console.print("[yellow]No results returned[/yellow]")
        return
    
    console.print(f"\n📄 [bold]Results from {tool_name}:[/bold]\n")
    
    for i, result in enumerate(results, 1):
        # Determine style based on result type
        if result.type == ToolResultType.SUCCESS:
            style = "green"
            icon = "✅"
        elif result.type == ToolResultType.ERROR:
            style = "red"
            icon = "❌"
        elif result.type == ToolResultType.WARNING:
            style = "yellow"
            icon = "⚠️"
        elif result.type == ToolResultType.INFO:
            style = "blue"
            icon = "ℹ️"
        else:
            style = "white"
            icon = "📝"
        
        # Show result
        result_type_str = result.type.value if hasattr(result.type, 'value') else str(result.type)
        console.print(f"{icon} [bold {style}]{result_type_str.upper()}[/bold {style}]: {result.content}")
        
        # Show metadata if available
        if result.metadata:
            console.print(f"   [dim]Metadata: {json.dumps(result.metadata, indent=2)}[/dim]")
        
        if i < len(results):
            console.print()  # Add spacing between results