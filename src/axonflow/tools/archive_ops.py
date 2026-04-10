"""归档压缩/解压工具，支持 tar.gz 和 zip 格式"""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from axonflow.tools.base import Tool, ToolResult

# 解压条目数上限（zip bomb 防护）
_MAX_ENTRIES = 10000


def _detect_format(archive_path: str) -> str | None:
    """根据文件扩展名推断归档格式"""
    lower = archive_path.lower()
    if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
        return "tar.gz"
    if lower.endswith(".zip"):
        return "zip"
    return None


class ArchiveOpsTool(Tool):
    """归档压缩、解压与内容列举"""

    name = "archive_ops"
    description = "创建或解压 tar.gz/zip 归档文件，也可列出归档内容"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["compress", "decompress", "list"],
                "description": "操作类型：compress 压缩、decompress 解压、list 列出内容",
            },
            "archive_path": {
                "type": "string",
                "description": "归档文件路径",
            },
            "source_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要压缩的文件或目录列表（compress 时使用）",
            },
            "destination": {
                "type": "string",
                "description": "解压目标目录（decompress 时使用，默认与归档同目录）",
            },
            "format": {
                "type": "string",
                "enum": ["tar.gz", "zip"],
                "description": "归档格式，默认根据扩展名自动检测",
            },
        },
        "required": ["action", "archive_path"],
    }

    async def execute(
        self,
        action: str,
        archive_path: str,
        source_paths: list[str] | None = None,
        destination: str | None = None,
        format: str | None = None,  # noqa: A002
        **_kwargs,
    ) -> ToolResult:
        fmt = format or _detect_format(archive_path)
        if fmt is None:
            return ToolResult(
                success=False,
                error="Cannot detect archive format from extension. Please specify 'format'.",
            )

        try:
            if action == "compress":
                return self._compress(archive_path, source_paths, fmt)
            if action == "decompress":
                return self._decompress(archive_path, destination, fmt)
            if action == "list":
                return self._list(archive_path, fmt)
            return ToolResult(success=False, error=f"Unknown action: {action}")
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"File not found: {e}")
        except PermissionError as e:
            return ToolResult(success=False, error=f"Permission denied: {e}")
        except (tarfile.TarError, zipfile.BadZipFile) as e:
            return ToolResult(success=False, error=f"Invalid archive: {e}")

    # ------------------------------------------------------------------
    # compress
    # ------------------------------------------------------------------

    @staticmethod
    def _compress(archive_path: str, source_paths: list[str] | None, fmt: str) -> ToolResult:
        if not source_paths:
            return ToolResult(
                success=False,
                error="Parameter 'source_paths' is required for action 'compress'",
            )

        # 校验所有源路径存在
        resolved: list[Path] = []
        for sp in source_paths:
            p = Path(sp)
            if not p.exists():
                return ToolResult(success=False, error=f"Source path not found: {sp}")
            resolved.append(p)

        out = Path(archive_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "tar.gz":
            with tarfile.open(archive_path, "w:gz") as tar:
                for p in resolved:
                    tar.add(str(p), arcname=p.name)
        else:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in resolved:
                    if p.is_dir():
                        for child in p.rglob("*"):
                            if child.is_file():
                                zf.write(str(child), arcname=str(child.relative_to(p.parent)))
                    else:
                        zf.write(str(p), arcname=p.name)

        return ToolResult(success=True, output=f"Archive created: {archive_path}")

    # ------------------------------------------------------------------
    # decompress
    # ------------------------------------------------------------------

    @staticmethod
    def _decompress(archive_path: str, destination: str | None, fmt: str) -> ToolResult:
        ap = Path(archive_path)
        if not ap.exists():
            return ToolResult(success=False, error=f"Archive not found: {archive_path}")

        dest = Path(destination) if destination else ap.parent
        dest.mkdir(parents=True, exist_ok=True)

        if fmt == "tar.gz":
            with tarfile.open(archive_path, "r:gz") as tar:
                members = tar.getmembers()
                if len(members) > _MAX_ENTRIES:
                    return ToolResult(
                        success=False,
                        error=f"Archive contains {len(members)} entries (limit: {_MAX_ENTRIES}). "
                        "Refusing to decompress for safety.",
                    )
                tar.extractall(path=str(dest))  # noqa: S202
        else:
            with zipfile.ZipFile(archive_path, "r") as zf:
                entries = zf.namelist()
                if len(entries) > _MAX_ENTRIES:
                    return ToolResult(
                        success=False,
                        error=f"Archive contains {len(entries)} entries (limit: {_MAX_ENTRIES}). "
                        "Refusing to decompress for safety.",
                    )
                zf.extractall(path=str(dest))

        return ToolResult(success=True, output=f"Extracted to: {dest}")

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    @staticmethod
    def _list(archive_path: str, fmt: str) -> ToolResult:
        ap = Path(archive_path)
        if not ap.exists():
            return ToolResult(success=False, error=f"Archive not found: {archive_path}")

        if fmt == "tar.gz":
            with tarfile.open(archive_path, "r:gz") as tar:
                names = tar.getnames()
        else:
            with zipfile.ZipFile(archive_path, "r") as zf:
                names = zf.namelist()

        return ToolResult(success=True, output="\n".join(names))
