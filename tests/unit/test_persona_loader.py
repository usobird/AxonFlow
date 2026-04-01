"""Persona 目录加载 + PromptBuilder persona 注入 测试"""

import tempfile
from pathlib import Path

import pytest

from autoflow.config.loader import (
    _deep_merge,
    load_agent_config,
    load_agent_config_from_dir,
    load_all_agent_configs,
)
from autoflow.config.models import AgentConfig, ModelConfig, PersonaConfig
from autoflow.core.message import Message, MessageType
from autoflow.llm.prompt_builder import PromptBuilder


class TestPersonaLoading:
    def test_load_from_directory(self, tmp_path: Path):
        """从目录格式加载 agent 配置 + persona 文件"""
        agent_dir = tmp_path / "my-agent"
        agent_dir.mkdir()

        # config.yaml
        (agent_dir / "config.yaml").write_text(
            'agent:\n  id: my-agent\n  name: "测试"\n  role: "基础角色"\n',
            encoding="utf-8",
        )
        # soul.md
        (agent_dir / "soul.md").write_text("不说废话\n诚实守信", encoding="utf-8")
        # user.md
        (agent_dir / "user.md").write_text("用户是开发者", encoding="utf-8")
        # workflow.md
        (agent_dir / "workflow.md").write_text("先分析再编码", encoding="utf-8")

        config = load_agent_config_from_dir(agent_dir)
        assert config.id == "my-agent"
        assert config.persona.soul == "不说废话\n诚实守信"
        assert config.persona.user == "用户是开发者"
        assert config.persona.workflow == "先分析再编码"

    def test_load_from_directory_partial_persona(self, tmp_path: Path):
        """目录中只有部分 persona 文件也能正常加载"""
        agent_dir = tmp_path / "partial"
        agent_dir.mkdir()

        (agent_dir / "config.yaml").write_text(
            "agent:\n  id: partial\n  name: P\n",
            encoding="utf-8",
        )
        (agent_dir / "soul.md").write_text("有灵魂", encoding="utf-8")

        config = load_agent_config_from_dir(agent_dir)
        assert config.persona.soul == "有灵魂"
        assert config.persona.user is None
        assert config.persona.workflow is None

    def test_load_from_directory_no_persona(self, tmp_path: Path):
        """目录中没有任何 persona 文件"""
        agent_dir = tmp_path / "no-persona"
        agent_dir.mkdir()

        (agent_dir / "config.yaml").write_text(
            "agent:\n  id: no-persona\n  name: NP\n",
            encoding="utf-8",
        )

        config = load_agent_config_from_dir(agent_dir)
        assert config.persona.soul is None
        assert config.persona.user is None
        assert config.persona.workflow is None

    def test_mixed_format_loading(self, tmp_path: Path):
        """同时加载目录格式和单文件格式的 agents"""
        # 目录格式
        dir_agent = tmp_path / "agent-dir"
        dir_agent.mkdir()
        (dir_agent / "config.yaml").write_text(
            "agent:\n  id: dir-agent\n  name: Dir\n",
            encoding="utf-8",
        )
        (dir_agent / "soul.md").write_text("灵魂", encoding="utf-8")

        # 单文件格式
        (tmp_path / "file-agent.yaml").write_text(
            "agent:\n  id: file-agent\n  name: File\n  role: test\n",
            encoding="utf-8",
        )

        configs = load_all_agent_configs(tmp_path)
        assert len(configs) == 2
        ids = {c.id for c in configs}
        assert "dir-agent" in ids
        assert "file-agent" in ids

        dir_cfg = next(c for c in configs if c.id == "dir-agent")
        assert dir_cfg.persona.soul == "灵魂"

    def test_load_real_coder_directory(self):
        """加载实际的 config/agents/coder 目录"""
        coder_dir = Path("config/agents/coder")
        if not coder_dir.exists():
            pytest.skip("coder directory not found")

        config = load_agent_config_from_dir(coder_dir)
        assert config.id == "agent-coder"
        assert config.persona.soul is not None
        assert "废话" in config.persona.soul or "简洁" in config.persona.soul
        assert config.persona.user is not None
        assert config.persona.workflow is not None


class TestPromptBuilderPersona:
    def _make_message(self):
        return Message(
            sender="user",
            receiver="agent-test",
            type=MessageType.TASK_REQUEST,
            payload={"task": "test task"},
        )

    def test_persona_injected_before_role(self):
        config = AgentConfig(
            id="test",
            name="T",
            role="我是助手",
            persona=PersonaConfig(
                soul="不说废话",
                user="用户是开发者",
                workflow="先分析再编码",
            ),
        )
        messages = PromptBuilder.build(
            agent_config=config,
            incoming_message=self._make_message(),
        )
        system = messages[0]["content"]
        # persona 内容应在 role 之前
        soul_pos = system.find("不说废话")
        role_pos = system.find("我是助手")
        assert soul_pos < role_pos
        assert "用户是开发者" in system
        assert "先分析再编码" in system

    def test_no_persona_no_injection(self):
        config = AgentConfig(
            id="test",
            name="T",
            role="我是助手",
        )
        messages = PromptBuilder.build(
            agent_config=config,
            incoming_message=self._make_message(),
        )
        system = messages[0]["content"]
        assert "价值观" not in system
        assert "我是助手" in system

    def test_partial_persona(self):
        config = AgentConfig(
            id="test",
            name="T",
            role="helper",
            persona=PersonaConfig(soul="诚实"),
        )
        messages = PromptBuilder.build(
            agent_config=config,
            incoming_message=self._make_message(),
        )
        system = messages[0]["content"]
        assert "诚实" in system
        assert "用户档案" not in system  # user 未设置


class TestDeepMerge:
    def test_simple_merge(self):
        result = _deep_merge({"a": 1, "b": 2}, {"b": 3, "c": 4})
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        base = {"flow": {"entry": "a", "timeout": 3600}}
        override = {"flow": {"timeout": 7200}}
        result = _deep_merge(base, override)
        assert result == {"flow": {"entry": "a", "timeout": 7200}}

    def test_override_wins(self):
        result = _deep_merge({"x": [1, 2]}, {"x": [3]})
        assert result == {"x": [3]}
