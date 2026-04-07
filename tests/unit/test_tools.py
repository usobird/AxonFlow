"""工具系统测试"""

import pytest

from axonflow.tools.base import ToolRegistry
from axonflow.tools.file_ops import FileReadTool, FileWriteTool
from axonflow.tools.shell_exec import ShellExecTool


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = ShellExecTool()
        registry.register(tool)

        assert registry.get("shell_exec") is tool
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(ShellExecTool())
        registry.register(FileReadTool())
        registry.register(FileWriteTool())

        names = registry.list_tools()
        assert "shell_exec" in names
        assert "file_read" in names
        assert "file_write" in names

    def test_get_schemas(self):
        registry = ToolRegistry()
        registry.register(ShellExecTool())
        registry.register(FileReadTool())

        schemas = registry.get_schemas(["shell_exec", "file_read"])
        assert len(schemas) == 2
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "shell_exec"


class TestShellExecTool:
    @pytest.mark.asyncio
    async def test_echo_command(self):
        tool = ShellExecTool()
        result = await tool.execute(command="echo hello")
        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_failing_command(self):
        tool = ShellExecTool()
        result = await tool.execute(command="false")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_timeout(self):
        tool = ShellExecTool()
        result = await tool.execute(command="sleep 10", timeout=1)
        assert result.success is False
        assert "timed out" in result.error


class TestFileTools:
    @pytest.mark.asyncio
    async def test_write_and_read(self, tmp_path):
        write_tool = FileWriteTool()
        read_tool = FileReadTool()

        test_file = str(tmp_path / "test.txt")
        content = "Hello, AutoFlow!"

        # 写入
        write_result = await write_tool.execute(path=test_file, content=content)
        assert write_result.success is True

        # 读取
        read_result = await read_tool.execute(path=test_file)
        assert read_result.success is True
        assert read_result.output == content

    @pytest.mark.asyncio
    async def test_read_nonexistent(self):
        tool = FileReadTool()
        result = await tool.execute(path="/nonexistent/file.txt")
        assert result.success is False
        assert "not found" in result.error.lower()
