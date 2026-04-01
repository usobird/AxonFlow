"""智能体管理 CLI 子命令"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

agent_app = typer.Typer(no_args_is_help=True)
console = Console()


@agent_app.command("list")
def list_agents(
    config_dir: str = typer.Option("config", "--config-dir", "-c", help="配置目录路径"),
) -> None:
    """列出所有已配置的智能体"""
    from autoflow.config.loader import load_all_agent_configs

    agents_dir = Path(config_dir) / "agents"
    agents = load_all_agent_configs(agents_dir)

    if not agents:
        console.print("[yellow]未找到任何智能体配置[/yellow]")
        raise typer.Exit()

    table = Table(title="已配置的智能体")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="blue")
    table.add_column("Model", style="yellow")
    table.add_column("Tools", style="magenta")
    table.add_column("Memory", style="white")

    for a in agents:
        model_str = f"{a.model.provider}/{a.model.name}"
        tools_str = ", ".join(a.tools) if a.tools else "-"
        memory_str = "on" if a.memory.enabled else "off"
        table.add_row(a.id, a.name, a.agent_type, model_str, tools_str, memory_str)

    console.print(table)


@agent_app.command("show")
def show_agent(
    agent_id: str = typer.Argument(help="智能体 ID"),
    config_dir: str = typer.Option("config", "--config-dir", "-c", help="配置目录路径"),
) -> None:
    """显示指定智能体的详细信息"""
    from autoflow.config.loader import load_all_agent_configs

    agents_dir = Path(config_dir) / "agents"
    agents = load_all_agent_configs(agents_dir)

    # 按 ID 查找目标智能体
    matched = [a for a in agents if a.id == agent_id]
    if not matched:
        console.print(f"[red]未找到 ID 为 '{agent_id}' 的智能体[/red]")
        raise typer.Exit(code=1)

    agent = matched[0]

    # 基本信息表
    info_table = Table(title=f"智能体详情 — {agent.name}", show_header=False)
    info_table.add_column("Field", style="bold cyan", width=16)
    info_table.add_column("Value")

    info_table.add_row("ID", agent.id)
    info_table.add_row("Name", agent.name)
    info_table.add_row("Role", agent.role)
    info_table.add_row("Type", agent.agent_type)
    info_table.add_row("Class Path", agent.class_path or "-")
    info_table.add_row("Model", f"{agent.model.provider}/{agent.model.name}")
    info_table.add_row("Temperature", str(agent.model.temperature))
    info_table.add_row("Max Tokens", str(agent.model.max_tokens))
    info_table.add_row("Tools", ", ".join(agent.tools) if agent.tools else "-")
    info_table.add_row("Can Request", ", ".join(agent.can_request) if agent.can_request else "-")
    info_table.add_row("Max Concurrent", str(agent.max_concurrent))
    info_table.add_row("Retry Limit", str(agent.retry_limit))

    # 记忆配置
    mem = agent.memory
    info_table.add_row("Memory Enabled", str(mem.enabled))
    info_table.add_row("Memory Backend", mem.backend)
    info_table.add_row("Memory Scopes", ", ".join(mem.scopes) if mem.scopes else "-")
    info_table.add_row("Memory Max Records", str(mem.max_records))
    info_table.add_row("Memory TTL", str(mem.default_ttl) if mem.default_ttl else "-")

    # 自定义参数
    if agent.parameters:
        import json

        info_table.add_row("Parameters", json.dumps(agent.parameters, ensure_ascii=False))
    else:
        info_table.add_row("Parameters", "-")

    console.print(info_table)


@agent_app.command("validate")
def validate_agents(
    config_dir: str = typer.Option("config", "--config-dir", "-c", help="配置目录路径"),
) -> None:
    """校验所有智能体配置文件"""
    from autoflow.config.loader import load_agent_config

    agents_dir = Path(config_dir) / "agents"

    if not agents_dir.exists():
        console.print(f"[red]配置目录不存在: {agents_dir}[/red]")
        raise typer.Exit(code=1)

    # 收集所有 yaml / yml 文件
    yaml_files = sorted(agents_dir.glob("*.yaml")) + sorted(agents_dir.glob("*.yml"))
    if not yaml_files:
        console.print("[yellow]未找到任何配置文件[/yellow]")
        raise typer.Exit()

    errors: list[tuple[str, str]] = []
    ok_count = 0

    for f in yaml_files:
        try:
            load_agent_config(f)
            ok_count += 1
            console.print(f"  [green]✓[/green] {f.name}")
        except Exception as e:
            errors.append((f.name, str(e)))
            console.print(f"  [red]✗[/red] {f.name}: {e}")

    # 汇总
    console.print()
    if errors:
        console.print(f"[red]校验完成: {ok_count} 个通过, {len(errors)} 个失败[/red]")
        raise typer.Exit(code=1)
    else:
        console.print(f"[green]校验完成: 全部 {ok_count} 个配置有效[/green]")


@agent_app.command("types")
def list_types() -> None:
    """列出所有已注册的智能体类型"""
    from autoflow.core.agent import _AGENT_TYPE_REGISTRY

    table = Table(title="已注册的智能体类型")
    table.add_column("Type Name", style="cyan")
    table.add_column("Class", style="green")

    for type_name, cls in _AGENT_TYPE_REGISTRY.items():
        table.add_row(type_name, f"{cls.__module__}.{cls.__name__}")

    console.print(table)
