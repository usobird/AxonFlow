"""Optional LangSmith reporting for AxonFlow LLM spans."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class LangSmithRun:
    client: Any
    run_id: str
    trace_id: str


class LangSmithReporter:
    """Best-effort LangSmith client that never blocks an agent result on telemetry."""

    def __init__(
        self,
        settings_resolver: Callable[[], dict[str, Any]] | None,
        credential_resolver: Callable[[str], dict[str, str]] | None,
    ) -> None:
        self._settings_resolver = settings_resolver
        self._credential_resolver = credential_resolver

    async def start(
        self,
        span: dict[str, Any],
        inputs: dict[str, Any],
        parent: LangSmithRun | None = None,
    ) -> LangSmithRun | None:
        settings = self._settings()
        if settings is None:
            return None
        try:
            credential = self._credential_resolver(settings["langsmith_credential_id"])
            from langsmith import Client

            kwargs: dict[str, Any] = {"api_key": credential["secret"]}
            if settings.get("langsmith_endpoint"):
                kwargs["api_url"] = settings["langsmith_endpoint"]
            client = Client(**kwargs)
            await asyncio.to_thread(
                client.create_run,
                id=span["id"],
                name=f"agent:{span.get('agent_id') or 'llm'}",
                run_type="llm",
                inputs=inputs,
                project_name=settings["langsmith_project"],
                extra={"metadata": span.get("metadata", {})},
                trace_id=parent.trace_id if parent else span["id"],
                parent_run_id=parent.run_id if parent else None,
            )
            return LangSmithRun(
                client=client,
                run_id=span["id"],
                trace_id=parent.trace_id if parent else span["id"],
            )
        except Exception as exc:
            logger.warning("langsmith.start_failed", error=str(exc))
            return None

    async def start_workflow(
        self,
        trace_id: str,
        workflow_id: str,
        input_data: str,
    ) -> LangSmithRun | None:
        settings = self._settings()
        if settings is None:
            return None
        try:
            credential = self._credential_resolver(settings["langsmith_credential_id"])
            from langsmith import Client

            kwargs: dict[str, Any] = {"api_key": credential["secret"]}
            if settings.get("langsmith_endpoint"):
                kwargs["api_url"] = settings["langsmith_endpoint"]
            client = Client(**kwargs)
            content_policy = settings.get("content_policy", "masked_content")
            inputs = (
                {"input": input_data}
                if content_policy == "full_content"
                else {"input_length": len(input_data)}
                if content_policy == "masked_content"
                else {}
            )
            await asyncio.to_thread(
                client.create_run,
                id=trace_id,
                name=f"workflow:{workflow_id}",
                run_type="chain",
                inputs=inputs,
                project_name=settings["langsmith_project"],
                trace_id=trace_id,
                extra={
                    "metadata": {
                        "workflow_id": workflow_id,
                        "content_policy": content_policy,
                    }
                },
            )
            return LangSmithRun(client=client, run_id=trace_id, trace_id=trace_id)
        except Exception as exc:
            logger.warning("langsmith.workflow_start_failed", error=str(exc))
            return None

    async def finish(
        self,
        run: LangSmithRun | None,
        outputs: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if run is None:
            return
        try:
            kwargs: dict[str, Any] = {"outputs": outputs or {}}
            if error:
                kwargs["error"] = error
            await asyncio.to_thread(run.client.update_run, run.run_id, **kwargs)
        except Exception as exc:
            logger.warning("langsmith.finish_failed", error=str(exc))

    def _settings(self) -> dict[str, Any] | None:
        if self._settings_resolver is None or self._credential_resolver is None:
            return None
        settings = self._settings_resolver()
        if not settings.get("langsmith_enabled") or not settings.get("langsmith_credential_id"):
            return None
        return settings
