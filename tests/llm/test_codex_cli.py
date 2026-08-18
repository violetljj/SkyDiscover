import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skydiscover.config import Config, LLMModelConfig, apply_overrides
from skydiscover.llm.codex_cli import CodexCliLLM, is_codex_cli_model
from skydiscover.llm.llm_pool import LLMPool
from skydiscover.search.default_discovery_controller import (
    DiscoveryController,
    DiscoveryControllerInput,
)


def _event_stream(text: str) -> bytes:
    events = [
        {"type": "thread.started", "thread_id": "test"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": text}},
        {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
    ]
    return ("\n".join(json.dumps(event) for event in events) + "\n").encode()


def _make_llm() -> CodexCliLLM:
    config = LLMModelConfig(
        name="codex-cli/gpt-test",
        timeout=20,
        retries=0,
        reasoning_effort="medium",
    )
    with (
        patch.object(CodexCliLLM, "_resolve_executable", return_value="codex-test"),
        patch.object(CodexCliLLM, "_verify_executable", return_value="codex-cli 1.2.3"),
    ):
        return CodexCliLLM(config)


def test_provider_detection():
    assert is_codex_cli_model("codex-cli/gpt-5")
    assert is_codex_cli_model("CODEX-CLI/gpt-5")
    assert not is_codex_cli_model("gpt-5")


def test_config_preserves_provider_prefix_without_api_key():
    config = Config.from_dict({"llm": {"models": [{"name": "codex-cli/gpt-test"}]}})
    model = config.llm.models[0]
    assert model.name == "codex-cli/gpt-test"
    assert model.api_base is None
    assert model.api_key is None


def test_cli_model_override_needs_no_api_base():
    config = Config()
    config.llm.codex_executable = "/opt/codex"
    apply_overrides(config, model="codex-cli/gpt-test")
    assert config.llm.models[0].name == "codex-cli/gpt-test"
    assert config.llm.models[0].api_base is None
    assert config.llm.models[0].codex_executable == "/opt/codex"


def test_pool_routes_codex_models_to_codex_backend():
    config = LLMModelConfig(name="codex-cli/gpt-test")
    fake = object()
    with patch("skydiscover.llm.llm_pool.CodexCliLLM", return_value=fake) as init:
        pool = LLMPool([config])
    assert pool.models == [fake]
    init.assert_called_once_with(config)


def test_codex_cli_rejects_nested_agentic_mode():
    config = Config.from_dict(
        {
            "llm": {"models": [{"name": "codex-cli/gpt-test"}]},
            "agentic": {"enabled": True},
        }
    )
    controller_input = DiscoveryControllerInput(
        config=config,
        evaluation_file="unused.py",
        database=MagicMock(),
    )
    with pytest.raises(ValueError, match="cannot be combined"):
        DiscoveryController(controller_input)


@pytest.mark.asyncio
async def test_generate_runs_isolated_jsonl_codex_exec():
    llm = _make_llm()
    process = MagicMock()
    process.returncode = 0
    process.communicate = AsyncMock(return_value=(_event_stream("candidate"), b"diagnostic"))

    with patch(
        "skydiscover.llm.codex_cli.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ) as spawn:
        response = await llm.generate("system", [{"role": "user", "content": "task"}])

    assert response.text == "candidate"
    assert response.metadata["llm_provider"] == "codex-cli"
    assert response.metadata["codex_thread_id"] == "test"
    assert response.metadata["codex_usage"]["input_tokens"] == 1
    command = spawn.call_args.args
    assert command[:3] == ("codex-test", "exec", "--json")
    assert "--ephemeral" in command
    assert ("--sandbox", "read-only") == command[
        command.index("--sandbox") : command.index("--sandbox") + 2
    ]
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert "--skip-git-repo-check" in command
    assert command[-1] == "-"
    prompt = process.communicate.call_args.args[0].decode()
    assert "<skydiscover_system>" in prompt
    assert "Do not inspect the filesystem" in prompt


@pytest.mark.asyncio
async def test_nonzero_exit_fails_closed():
    llm = _make_llm()
    process = MagicMock()
    process.returncode = 7
    process.communicate = AsyncMock(return_value=(b"", b"login failed"))

    with patch(
        "skydiscover.llm.codex_cli.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ):
        with pytest.raises(RuntimeError, match="exited with code 7"):
            await llm.generate("system", [{"role": "user", "content": "task"}])


@pytest.mark.asyncio
async def test_timeout_kills_codex_process():
    llm = _make_llm()
    process = MagicMock()
    process.returncode = None
    process.kill = MagicMock()
    process.wait = AsyncMock(return_value=0)

    async def slow_communicate(_prompt):
        await asyncio.sleep(60)

    process.communicate = slow_communicate
    with patch(
        "skydiscover.llm.codex_cli.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=process),
    ):
        with pytest.raises(TimeoutError, match="timed out"):
            await llm.generate(
                "system",
                [{"role": "user", "content": "task"}],
                timeout=0.001,
            )

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()


def test_failed_event_fails_closed():
    output = json.dumps({"type": "turn.failed", "error": {"message": "bad"}})
    with pytest.raises(RuntimeError, match="failed turn"):
        CodexCliLLM._parse_jsonl(output)


def test_invalid_jsonl_fails_closed():
    with pytest.raises(RuntimeError, match="invalid JSONL"):
        CodexCliLLM._parse_jsonl("not-json")


def test_version_check_requires_authenticated_cli():
    version = MagicMock(returncode=0, stdout="codex-cli 1.2.3", stderr="")
    auth = MagicMock(returncode=0, stdout="", stderr="Not logged in")
    with patch("skydiscover.llm.codex_cli.subprocess.run", side_effect=[version, auth]):
        with pytest.raises(RuntimeError, match="not authenticated"):
            CodexCliLLM._verify_executable("codex-test")


def test_non_text_content_is_rejected():
    with pytest.raises(ValueError, match="text message content only"):
        CodexCliLLM._build_prompt(
            "system",
            [{"role": "user", "content": [{"type": "image_url", "url": "x"}]}],
            None,
        )
