"""目录树浏览工具"""

from __future__ import annotations

from pathlib import Path

from axonflow.tools.base import Tool, ToolResult

_MAX_ENTRIES = 500


def _format_size(size_bytes: int) -> str:
    """将字节数转换为人类可读的大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _build_tree(
    dir_path: Path,
    prefix: str,
    max_depth: int,
    current_depth: int,
    show_hidden: bool,
    show_size: bool,
    entries_count: list[int],
) -> list[str]:
    """递归构建目录树的各行"""
    if current_depth > max_depth:
        return []
    if entries_count[0] >= _MAX_ENTRIES:
        return ["... (output truncated, too many entries)"]

    try:
        children = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return [f"{prefix}[permission denied]"]

    if not show_hidden:
        children = [c for c in children if not c.name.startswith(".")]

    lines: list[str] = []
    for i, child in enumerate(children):
        if entries_count[0] >= _MAX_ENTRIES:
            lines.append(f"{prefix}... (output truncated, too many entries)")
            break

        is_last = i == len(children) - 1
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        entries_count[0] += 1

        if child.is_dir():
            lines.append(f"{prefix}{connector}{child.name}/")
            subtree = _build_tree(
                child,
                prefix + extension,
                max_depth,
                current_depth + 1,
                show_hidden,
                show_size,
                entries_count,
            )
            lines.extend(subtree)
        else:
            size_suffix = ""
            if show_size:
                try:
                    size_suffix = f" ({_format_size(child.stat().st_size)})"
                except OSError:
                    size_suffix = " (?)"
            lines.append(f"{prefix}{connector}{child.name}{size_suffix}")

    return lines


class DirectoryTreeTool(Tool):
    """以树状格式展示目录结构"""

    name = "directory_tree"
    description = "以 ASCII 树状图展示目录结构，类似 tree 命令"
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "要浏览的目录路径",
            },
            "max_depth": {
                "type": "integer",
                "description": "最大递归深度，默认 3",
                "default": 3,
            },
            "show_hidden": {
                "type": "boolean",
                "description": "是否显示隐藏文件/目录，默认 false",
                "default": False,
            },
            "show_size": {
                "type": "boolean",
                "description": "是否显示文件大小，默认 false",
                "default": False,
            },
        },
        "required": ["path"],
    }

    async def execute(
        self,
        path: str,
        max_depth: int = 3,
        show_hidden: bool = False,
        show_size: bool = False,
        **_kwargs,
    ) -> ToolResult:
        dir_path = Path(path)

        if not dir_path.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")
        if not dir_path.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {path}")

        # entries_count is a mutable list so recursive calls can share it
        entries_count: list[int] = [0]

        lines = [f"{dir_path.name}/"]
        tree_lines = _build_tree(
            dir_path,
            prefix="",
            max_depth=max_depth,
            current_depth=1,
            show_hidden=show_hidden,
            show_size=show_size,
            entries_count=entries_count,
        )
        lines.extend(tree_lines)

        return ToolResult(success=True, output="\n".join(lines))
