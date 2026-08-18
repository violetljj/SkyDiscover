"""Codex CLI backend using saved Codex/ChatGPT authentication."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from skydiscover.config import LLMModelConfig
from skydiscover.execution_budget import BudgetExceeded, active_budget
from skydiscover.llm.base import LLMInterface, LLMResponse

logger = logging.getLogger("skydiscover.llm")

_CODEX_PROVIDER_PREFIX = "codex-cli/"
_VERSION_CACHE: Dict[str, str] = {}


def is_codex_cli_model(model_name: Optional[str]) -> bool:
    """Return whether *model_name* selects the Codex CLI provider."""
    return bool(model_name and model_name.lower().startswith(_CODEX_PROVIDER_PREFIX))


class CodexCliLLM(LLMInterface):
    """Generate candidates through ``codex exec`` without an API key.

    Each call runs in an empty temporary directory with a read-only sandbox.
    The evaluator and repository are not exposed as the Codex working directory;
    all candidate context must arrive through the prompt assembled by SkyDiscover.
    """

    def __init__(self, model_cfg: LLMModelConfig):
        if not is_codex_cli_model(model_cfg.name):
            raise ValueError("CodexCliLLM requires a model named codex-cli/<model>")

        self.model = model_cfg.name.split("/", 1)[1]
        if not self.model:
            raise ValueError("Codex CLI model name cannot be empty")

        self.timeout = model_cfg.timeout if model_cfg.timeout is not None else 600
        self.retries = model_cfg.retries if model_cfg.retries is not None else 0
        self.retry_delay = model_cfg.retry_delay if model_cfg.retry_delay is not None else 2
        self.reasoning_effort = model_cfg.reasoning_effort
        self.executable = self._resolve_executable(model_cfg.codex_executable)
        self.version = self._verify_executable(self.executable)
        logger.debug("Codex CLI LLM: model=%s, version=%s", self.model, self.version)

    @staticmethod
    def _resolve_executable(configured: Optional[str]) -> str:
        requested = configured or os.environ.get("SKYDISCOVER_CODEX_EXECUTABLE")
        candidates: List[Path] = []
        if requested:
            candidates.append(Path(os.path.expandvars(os.path.expanduser(requested))))
        else:
            if os.name == "nt":
                candidates.append(Path.home() / ".codex" / ".sandbox-bin" / "codex.exe")
            discovered = shutil.which("codex")
            if discovered:
                candidates.append(Path(discovered))

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate.resolve())

        searched = ", ".join(str(path) for path in candidates) or "PATH"
        raise FileNotFoundError(
            "No executable Codex CLI was found. Set llm.codex_executable or "
            f"SKYDISCOVER_CODEX_EXECUTABLE. Searched: {searched}"
        )

    @staticmethod
    def _verify_executable(executable: str) -> str:
        cached = _VERSION_CACHE.get(executable)
        if cached:
            return cached

        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                check=False,
                timeout=15,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Codex CLI is not executable: {executable}: {exc}") from exc

        output = " ".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode != 0 or not re.search(r"\bcodex(?:-cli)?\b", output, re.IGNORECASE):
            raise RuntimeError(
                f"Codex CLI version check failed for {executable}: "
                f"exit={result.returncode}, output={output[-1000:]!r}"
            )
        if "unknown" in output.lower():
            raise RuntimeError(f"Codex CLI returned an unknown version: {output!r}")

        try:
            auth = subprocess.run(
                [executable, "login", "status"],
                capture_output=True,
                check=False,
                timeout=15,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Codex CLI login check failed: {executable}: {exc}") from exc
        auth_output = " ".join(part.strip() for part in (auth.stdout, auth.stderr) if part.strip())
        auth_output_lower = auth_output.lower()
        if (
            auth.returncode != 0
            or "not logged in" in auth_output_lower
            or "logged in" not in auth_output_lower
        ):
            raise RuntimeError(
                "Codex CLI is not authenticated. Run 'codex login' first. "
                f"Status output: {auth_output[-1000:]!r}"
            )

        _VERSION_CACHE[executable] = output
        return output

    async def generate(
        self, system_message: str, messages: List[Dict[str, Any]], **kwargs
    ) -> LLMResponse:
        if kwargs.get("image_output"):
            raise ValueError("The Codex CLI provider does not support image generation")

        prompt = self._build_prompt(system_message, messages, kwargs.get("response_format"))
        retries = kwargs.get("retries", self.retries)
        retry_delay = kwargs.get("retry_delay", self.retry_delay)
        timeout = kwargs.get("timeout", self.timeout)

        last_error: Optional[Exception] = None
        for attempt in range(retries + 1):
            ledger = active_budget()
            event_id = (
                ledger.start_generation(provider="codex-cli", model=self.model, attempt=attempt + 1)
                if ledger
                else None
            )
            try:
                text, run_metadata = await self._run_once(
                    prompt, timeout, kwargs.get("response_format")
                )
                if ledger is not None and event_id is not None:
                    ledger.finish_generation(event_id, metadata=run_metadata)
                metadata = {
                    "llm_provider": "codex-cli",
                    "llm_model": self.model,
                    "codex_cli_version": self.version,
                    "codex_executable": self.executable,
                    **run_metadata,
                }
                return LLMResponse(text=text, metadata=metadata)
            except BudgetExceeded:
                raise
            except Exception as exc:
                if ledger is not None and event_id is not None:
                    ledger.finish_generation(event_id, error=f"{type(exc).__name__}: {exc}")
                last_error = exc
                if attempt >= retries:
                    raise
                logger.warning(
                    "Codex CLI error attempt %d/%d: %s; retrying...",
                    attempt + 1,
                    retries + 1,
                    exc,
                )
                await asyncio.sleep(retry_delay)

        raise RuntimeError("Codex CLI generation failed") from last_error

    async def _run_once(
        self, prompt: str, timeout: float, response_format: Any
    ) -> tuple[str, Dict[str, Any]]:
        with tempfile.TemporaryDirectory(prefix="skydiscover-codex-") as temp_dir:
            command = [
                self.executable,
                "exec",
                "--json",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--ignore-user-config",
                "--ignore-rules",
                "--color",
                "never",
                "--skip-git-repo-check",
                "--cd",
                temp_dir,
                "--model",
                self.model,
            ]
            if self.reasoning_effort:
                command.extend(["--config", f'model_reasoning_effort="{self.reasoning_effort}"'])

            schema = self._json_schema(response_format)
            if schema is not None:
                schema_path = Path(temp_dir) / "output-schema.json"
                schema_path.write_text(json.dumps(schema), encoding="utf-8")
                command.extend(["--output-schema", str(schema_path)])

            command.append("-")
            process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(prompt.encode("utf-8")), timeout=timeout
                )
            except asyncio.TimeoutError:
                await self._stop_process(process)
                raise TimeoutError(f"Codex CLI generation timed out after {timeout} seconds")
            except asyncio.CancelledError:
                await self._stop_process(process)
                raise

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")
        if process.returncode != 0:
            raise RuntimeError(
                f"Codex CLI exited with code {process.returncode}: {stderr_text[-4000:]}"
            )
        if stderr_text.strip():
            logger.debug("Codex CLI stderr: %s", stderr_text[-4000:])
        return self._parse_jsonl(stdout_text)

    @staticmethod
    async def _stop_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.kill()
        except ProcessLookupError:
            return
        await process.wait()

    @staticmethod
    def _json_schema(response_format: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
            return None
        json_schema = response_format.get("json_schema")
        if not isinstance(json_schema, dict):
            return None
        schema = json_schema.get("schema")
        return schema if isinstance(schema, dict) else None

    @staticmethod
    def _parse_jsonl(output: str) -> tuple[str, Dict[str, Any]]:
        final_messages: List[str] = []
        errors: List[str] = []
        metadata: Dict[str, Any] = {}
        for line_number, line in enumerate(output.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Codex CLI emitted invalid JSONL on line {line_number}: {line[:500]!r}"
                ) from exc

            event_type = event.get("type")
            if event_type == "thread.started" and event.get("thread_id"):
                metadata["codex_thread_id"] = event["thread_id"]
            elif event_type == "item.completed":
                item = event.get("item") or {}
                if item.get("type") == "agent_message" and isinstance(item.get("text"), str):
                    final_messages.append(item["text"])
            elif event_type == "turn.completed" and isinstance(event.get("usage"), dict):
                metadata["codex_usage"] = event["usage"]
            elif event_type in {"error", "turn.failed"}:
                errors.append(json.dumps(event, ensure_ascii=False)[:2000])

        if errors:
            raise RuntimeError(f"Codex CLI reported a failed turn: {errors[-1]}")
        if not final_messages or not final_messages[-1].strip():
            raise RuntimeError("Codex CLI completed without a final agent message")
        return final_messages[-1], metadata

    @classmethod
    def _build_prompt(
        cls,
        system_message: str,
        messages: List[Dict[str, Any]],
        response_format: Any,
    ) -> str:
        sections = [
            "You are the candidate-generation backend for SkyDiscover.",
            "Do not inspect the filesystem, invoke tools, or modify files. Work only from this prompt.",
            "Follow the SkyDiscover system instructions and return only the requested candidate response.",
            f"\n<skydiscover_system>\n{system_message or ''}\n</skydiscover_system>",
        ]
        for message in messages:
            role = str(message.get("role", "user"))
            content = cls._content_to_text(message.get("content", ""))
            sections.append(
                f"\n<skydiscover_message role={json.dumps(role)}>\n"
                f"{content}\n</skydiscover_message>"
            )
        if isinstance(response_format, dict) and response_format.get("type") == "json_object":
            sections.append("\nReturn a valid JSON object and no surrounding prose.")
        return "\n".join(sections)

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if not isinstance(item, dict) or item.get("type") not in {"text", "input_text"}:
                    raise ValueError("The Codex CLI provider accepts text message content only")
                text = item.get("text")
                if not isinstance(text, str):
                    raise ValueError("Codex CLI text content must be a string")
                parts.append(text)
            return "\n".join(parts)
        raise ValueError("The Codex CLI provider accepts text message content only")
