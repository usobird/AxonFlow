"""Comprehensive tests for the 10 new AxonFlow tools."""

from __future__ import annotations

import json
import os
import signal

import pytest

from axonflow.tools.archive_ops import ArchiveOpsTool
from axonflow.tools.directory_tree import DirectoryTreeTool
from axonflow.tools.env_vars import EnvVarsTool
from axonflow.tools.file_patch import FilePatchTool
from axonflow.tools.json_query import JsonQueryTool
from axonflow.tools.process_manager import ProcessManagerTool, _managed_processes
from axonflow.tools.python_eval import PythonEvalTool
from axonflow.tools.text_search import TextSearchTool
from axonflow.tools.web_scrape import WebScrapeTool
from axonflow.tools.web_search import WebSearchTool


# ======================================================================
# 1. TextSearchTool
# ======================================================================


class TestTextSearchTool:
    @pytest.mark.asyncio
    async def test_search_in_file(self, tmp_path):
        """Search for a known pattern inside a single file."""
        f = tmp_path / "sample.txt"
        f.write_text("line one\nfoo bar baz\nline three\n")

        tool = TextSearchTool()
        result = await tool.execute(pattern="bar", path=str(f))

        assert result.success is True
        matches = json.loads(result.output)
        assert len(matches) == 1
        assert matches[0]["line_number"] == 2
        assert matches[0]["match"] == "bar"
        assert "foo bar baz" in matches[0]["line_content"]

    @pytest.mark.asyncio
    async def test_search_in_directory(self, tmp_path):
        """Recursive search across multiple files in a directory."""
        (tmp_path / "a.txt").write_text("hello world\n")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("hello again\n")

        tool = TextSearchTool()
        result = await tool.execute(pattern="hello", path=str(tmp_path), recursive=True)

        assert result.success is True
        matches = json.loads(result.output)
        assert len(matches) == 2
        matched_files = {m["file"] for m in matches}
        assert str(tmp_path / "a.txt") in matched_files
        assert str(sub / "b.txt") in matched_files

    @pytest.mark.asyncio
    async def test_regex_pattern(self, tmp_path):
        """Search using a regex pattern with digit matching."""
        f = tmp_path / "nums.txt"
        f.write_text("no numbers here\nabc 42 def\nxyz\n")

        tool = TextSearchTool()
        result = await tool.execute(pattern=r"\d+", path=str(f))

        assert result.success is True
        matches = json.loads(result.output)
        assert len(matches) == 1
        assert matches[0]["match"] == "42"
        assert matches[0]["line_number"] == 2

    @pytest.mark.asyncio
    async def test_no_results(self, tmp_path):
        """Search for a pattern that does not exist in the file."""
        f = tmp_path / "empty_match.txt"
        f.write_text("nothing interesting\n")

        tool = TextSearchTool()
        result = await tool.execute(pattern="ZZZZNOTFOUND", path=str(f))

        assert result.success is True
        matches = json.loads(result.output)
        assert matches == []


# ======================================================================
# 2. PythonEvalTool
# ======================================================================


class TestPythonEvalTool:
    @pytest.mark.asyncio
    async def test_simple_expression(self):
        """Execute a trivial print statement and verify output."""
        tool = PythonEvalTool()
        result = await tool.execute(code="print(2+2)")

        assert result.success is True
        assert "4" in result.output

    @pytest.mark.asyncio
    async def test_syntax_error(self):
        """Execute invalid Python code and verify failure."""
        tool = PythonEvalTool()
        result = await tool.execute(code="if if if")

        assert result.success is False
        assert result.error is not None
        assert "SyntaxError" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self):
        """Execute long-running code with a short timeout."""
        tool = PythonEvalTool()
        result = await tool.execute(
            code="import time; time.sleep(30)",
            timeout=2,
        )

        assert result.success is False
        assert "timed out" in result.error.lower()


# ======================================================================
# 3. JsonQueryTool
# ======================================================================


class TestJsonQueryTool:
    @pytest.mark.asyncio
    async def test_simple_query(self):
        """Query a nested JSON object with a dot-path expression."""
        tool = JsonQueryTool()
        result = await tool.execute(
            data='{"a": {"b": 1}}',
            expression="a.b",
        )

        assert result.success is True
        assert json.loads(result.output) == 1

    @pytest.mark.asyncio
    async def test_array_query(self):
        """Query an array of objects using a JMESPath wildcard."""
        data = json.dumps(
            [
                {"name": "Alice", "age": 30},
                {"name": "Bob", "age": 25},
            ]
        )
        tool = JsonQueryTool()
        result = await tool.execute(data=data, expression="[*].name")

        assert result.success is True
        assert json.loads(result.output) == ["Alice", "Bob"]

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        """Pass non-JSON data and expect a parse error."""
        tool = JsonQueryTool()
        result = await tool.execute(data="not json at all {{{", expression="a")

        assert result.success is False
        assert "Invalid JSON" in result.error

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        """Pass a syntactically invalid JMESPath expression."""
        tool = JsonQueryTool()
        result = await tool.execute(data='{"a":1}', expression="[invalid!!")

        assert result.success is False
        assert "Invalid JMESPath" in result.error


# ======================================================================
# 4. DirectoryTreeTool
# ======================================================================


class TestDirectoryTreeTool:
    @pytest.mark.asyncio
    async def test_basic_tree(self, tmp_path):
        """Verify tree output contains created file and directory names."""
        (tmp_path / "file_a.txt").write_text("a")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "file_b.txt").write_text("b")

        tool = DirectoryTreeTool()
        result = await tool.execute(path=str(tmp_path))

        assert result.success is True
        assert "file_a.txt" in result.output
        assert "subdir" in result.output
        assert "file_b.txt" in result.output

    @pytest.mark.asyncio
    async def test_max_depth(self, tmp_path):
        """Depth=1 should show top-level entries but not nested children."""
        sub = tmp_path / "level1"
        sub.mkdir()
        deep = sub / "level2"
        deep.mkdir()
        (deep / "deep_file.txt").write_text("deep")

        tool = DirectoryTreeTool()
        result = await tool.execute(path=str(tmp_path), max_depth=1)

        assert result.success is True
        assert "level1" in result.output
        # level2 contents should not appear at depth=1
        assert "deep_file.txt" not in result.output

    @pytest.mark.asyncio
    async def test_show_size(self, tmp_path):
        """With show_size=True, output should contain size indicators."""
        f = tmp_path / "sized.txt"
        f.write_text("x" * 100)

        tool = DirectoryTreeTool()
        result = await tool.execute(path=str(tmp_path), show_size=True)

        assert result.success is True
        # The size formatter appends " B" or " KB" etc.
        assert " B)" in result.output or " KB)" in result.output


# ======================================================================
# 5. FilePatchTool
# ======================================================================


class TestFilePatchTool:
    @pytest.mark.asyncio
    async def test_search_replace(self, tmp_path):
        """Replace a known string in a file."""
        f = tmp_path / "patch_me.txt"
        f.write_text("hello world\n")

        tool = FilePatchTool()
        result = await tool.execute(
            path=str(f),
            mode="search_replace",
            search="hello",
            replace="goodbye",
        )

        assert result.success is True
        assert f.read_text() == "goodbye world\n"
        # The output is a unified diff
        assert "goodbye" in result.output

    @pytest.mark.asyncio
    async def test_line_range(self, tmp_path):
        """Replace a specific line range in a file."""
        f = tmp_path / "lines.txt"
        f.write_text("line1\nline2\nline3\nline4\n")

        tool = FilePatchTool()
        result = await tool.execute(
            path=str(f),
            mode="line_range",
            start_line=2,
            end_line=3,
            content="REPLACED",
        )

        assert result.success is True
        contents = f.read_text()
        assert "REPLACED" in contents
        assert "line2" not in contents
        assert "line3" not in contents
        # Surrounding lines should be preserved
        assert "line1" in contents
        assert "line4" in contents

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """Patching a non-existent file should fail."""
        tool = FilePatchTool()
        result = await tool.execute(
            path="/nonexistent/path/no_file.txt",
            mode="search_replace",
            search="a",
            replace="b",
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_search_not_found(self, tmp_path):
        """Searching for a string that doesn't exist should fail."""
        f = tmp_path / "no_match.txt"
        f.write_text("some content\n")

        tool = FilePatchTool()
        result = await tool.execute(
            path=str(f),
            mode="search_replace",
            search="DOES_NOT_EXIST",
            replace="anything",
        )

        assert result.success is False
        assert "not found" in result.error.lower()


# ======================================================================
# 6. EnvVarsTool
# ======================================================================


class TestEnvVarsTool:
    @pytest.mark.asyncio
    async def test_get_existing(self, monkeypatch):
        """Get an environment variable that exists."""
        monkeypatch.setenv("AXONFLOW_TEST_VAR", "hello")

        tool = EnvVarsTool()
        result = await tool.execute(action="get", name="AXONFLOW_TEST_VAR")

        assert result.success is True
        assert result.output == "hello"

    @pytest.mark.asyncio
    async def test_get_missing(self, monkeypatch):
        """Get an environment variable that does not exist."""
        monkeypatch.delenv("AXONFLOW_MISSING_VAR", raising=False)

        tool = EnvVarsTool()
        result = await tool.execute(action="get", name="AXONFLOW_MISSING_VAR")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_list_with_prefix(self, monkeypatch):
        """List variables filtered by a prefix."""
        monkeypatch.setenv("AXONFLOW_TEST_X", "1")

        tool = EnvVarsTool()
        result = await tool.execute(action="list", prefix="AXONFLOW_TEST")

        assert result.success is True
        assert "AXONFLOW_TEST_X" in result.output

    @pytest.mark.asyncio
    async def test_sensitive_var_redacted(self, monkeypatch):
        """Variables matching sensitive patterns should be redacted."""
        monkeypatch.setenv("AXONFLOW_TEST_SECRET", "mysecret")

        tool = EnvVarsTool()
        result = await tool.execute(action="get", name="AXONFLOW_TEST_SECRET")

        assert result.success is True
        assert result.output == "[REDACTED]"
        assert "mysecret" not in (result.output or "")


# ======================================================================
# 7. ArchiveOpsTool
# ======================================================================


class TestArchiveOpsTool:
    @pytest.mark.asyncio
    async def test_compress_and_decompress_zip(self, tmp_path):
        """Round-trip: create files -> compress to zip -> decompress -> verify."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("aaa")
        (src / "b.txt").write_text("bbb")

        archive = str(tmp_path / "out.zip")
        dest = tmp_path / "extracted"
        dest.mkdir()

        tool = ArchiveOpsTool()

        # Compress
        result = await tool.execute(
            action="compress",
            archive_path=archive,
            source_paths=[str(src / "a.txt"), str(src / "b.txt")],
            format="zip",
        )
        assert result.success is True

        # Decompress
        result = await tool.execute(
            action="decompress",
            archive_path=archive,
            destination=str(dest),
        )
        assert result.success is True

        # Verify extracted files exist and have correct content
        assert (dest / "a.txt").read_text() == "aaa"
        assert (dest / "b.txt").read_text() == "bbb"

    @pytest.mark.asyncio
    async def test_compress_and_decompress_tar(self, tmp_path):
        """Round-trip with tar.gz format."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "c.txt").write_text("ccc")

        archive = str(tmp_path / "out.tar.gz")
        dest = tmp_path / "extracted"
        dest.mkdir()

        tool = ArchiveOpsTool()

        result = await tool.execute(
            action="compress",
            archive_path=archive,
            source_paths=[str(src / "c.txt")],
            format="tar.gz",
        )
        assert result.success is True

        result = await tool.execute(
            action="decompress",
            archive_path=archive,
            destination=str(dest),
        )
        assert result.success is True
        assert (dest / "c.txt").read_text() == "ccc"

    @pytest.mark.asyncio
    async def test_list_archive(self, tmp_path):
        """List the contents of a zip archive."""
        src = tmp_path / "src"
        src.mkdir()
        (src / "x.txt").write_text("xxx")
        (src / "y.txt").write_text("yyy")

        archive = str(tmp_path / "listing.zip")
        tool = ArchiveOpsTool()

        await tool.execute(
            action="compress",
            archive_path=archive,
            source_paths=[str(src / "x.txt"), str(src / "y.txt")],
            format="zip",
        )

        result = await tool.execute(action="list", archive_path=archive)
        assert result.success is True
        assert "x.txt" in result.output
        assert "y.txt" in result.output

    @pytest.mark.asyncio
    async def test_invalid_archive(self, tmp_path):
        """Decompressing a non-existent file should fail."""
        tool = ArchiveOpsTool()
        result = await tool.execute(
            action="decompress",
            archive_path=str(tmp_path / "no_such_file.zip"),
        )

        assert result.success is False
        assert "not found" in result.error.lower()


# ======================================================================
# 8. ProcessManagerTool
# ======================================================================


class TestProcessManagerTool:
    """Tests for starting, listing, stopping, and querying processes.

    Each test that starts a process is responsible for cleaning it up.
    We also clear the module-level ``_managed_processes`` registry
    after every test to avoid cross-test pollution.
    """

    @pytest.fixture(autouse=True)
    def _cleanup_managed(self):
        """Clean up any leftover managed processes after each test."""
        yield
        for pid in list(_managed_processes.keys()):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        _managed_processes.clear()

    @pytest.mark.asyncio
    async def test_start_and_list(self):
        """Start a background process and verify it appears in the list."""
        tool = ProcessManagerTool()

        start_result = await tool.execute(action="start", command="sleep 60")
        assert start_result.success is True

        start_info = json.loads(start_result.output)
        pid = start_info["pid"]
        assert isinstance(pid, int)

        list_result = await tool.execute(action="list")
        assert list_result.success is True

        entries = json.loads(list_result.output)
        pids = [e["pid"] for e in entries]
        assert pid in pids

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """Start a process, stop it, and verify it is no longer running."""
        tool = ProcessManagerTool()

        start_result = await tool.execute(action="start", command="sleep 60")
        pid = json.loads(start_result.output)["pid"]

        stop_result = await tool.execute(action="stop", pid=pid)
        assert stop_result.success is True

        # After stopping, the pid should be removed from the registry
        assert pid not in _managed_processes

    @pytest.mark.asyncio
    async def test_status(self):
        """Start a process and check its status."""
        tool = ProcessManagerTool()

        start_result = await tool.execute(action="start", command="sleep 60")
        pid = json.loads(start_result.output)["pid"]

        status_result = await tool.execute(action="status", pid=pid)
        assert status_result.success is True

        status_info = json.loads(status_result.output)
        assert status_info["pid"] == pid
        assert status_info["status"] == "running"

    @pytest.mark.asyncio
    async def test_stop_nonexistent(self):
        """Stopping a PID that is not managed should fail."""
        tool = ProcessManagerTool()
        result = await tool.execute(action="stop", pid=999999999)

        assert result.success is False
        assert "not managed" in result.error.lower()


# ======================================================================
# 9. WebSearchTool
# ======================================================================


class TestWebSearchTool:
    def test_schema(self):
        """Verify the tool exposes the expected name and parameter schema."""
        tool = WebSearchTool()

        assert tool.name == "web_search"
        assert "query" in tool.parameters["properties"]
        assert "max_results" in tool.parameters["properties"]
        assert "query" in tool.parameters["required"]

        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_search"


# ======================================================================
# 10. WebScrapeTool
# ======================================================================


class TestWebScrapeTool:
    def test_schema(self):
        """Verify the tool exposes the expected name and parameter schema."""
        tool = WebScrapeTool()

        assert tool.name == "web_scrape"
        assert "url" in tool.parameters["properties"]
        assert "max_length" in tool.parameters["properties"]
        assert "url" in tool.parameters["required"]

        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_scrape"

    @pytest.mark.asyncio
    async def test_invalid_url(self):
        """Passing a non-HTTP URL should fail immediately."""
        tool = WebScrapeTool()
        result = await tool.execute(url="ftp://example.com/file")

        assert result.success is False
        assert "Invalid URL" in result.error
