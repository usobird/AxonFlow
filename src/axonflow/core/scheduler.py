"""Cron 定时调度器"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from croniter import croniter

import structlog

logger = structlog.get_logger()


@dataclass
class ScheduledJob:
    """定时任务"""

    workflow_id: str
    cron_expr: str
    input_data: str
    is_running: bool = False
    last_run: datetime | None = None
    _cron: croniter = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._cron = croniter(self.cron_expr, datetime.now(timezone.utc))

    def should_run(self, now: datetime) -> bool:
        """判断当前时间是否应该触发"""
        if self.is_running:
            return False
        next_time = croniter(self.cron_expr, self.last_run or datetime.min.replace(tzinfo=timezone.utc)).get_next(datetime)
        return now >= next_time


class Scheduler:
    """定时任务调度器"""

    def __init__(self) -> None:
        self._jobs: list[ScheduledJob] = []
        self._running = False
        self._run_callback = None  # 由 Engine 注入，实际执行工作流的回调

    def set_run_callback(self, callback) -> None:
        """设置工作流执行回调

        callback 签名: async def run(workflow_id: str, input_data: str) -> None
        """
        self._run_callback = callback

    def add_job(self, workflow_id: str, cron_expr: str, input_data: str = "") -> None:
        """添加定时任务"""
        job = ScheduledJob(
            workflow_id=workflow_id,
            cron_expr=cron_expr,
            input_data=input_data,
        )
        self._jobs.append(job)
        logger.info(
            "scheduler.job_added",
            workflow_id=workflow_id,
            cron=cron_expr,
        )

    async def start(self) -> None:
        """启动调度循环"""
        self._running = True
        logger.info("scheduler.started", jobs=len(self._jobs))

        while self._running:
            now = datetime.now(timezone.utc)
            for job in self._jobs:
                if job.should_run(now):
                    asyncio.create_task(self._execute_job(job))
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """停止调度器"""
        self._running = False
        logger.info("scheduler.stopped")

    async def _execute_job(self, job: ScheduledJob) -> None:
        """执行定时任务"""
        job.is_running = True
        logger.info(
            "scheduler.job_running",
            workflow_id=job.workflow_id,
        )
        try:
            if self._run_callback:
                await self._run_callback(job.workflow_id, job.input_data)
            else:
                logger.warning("scheduler.no_callback")
        except Exception as e:
            logger.error(
                "scheduler.job_failed",
                workflow_id=job.workflow_id,
                error=str(e),
            )
        finally:
            job.is_running = False
            job.last_run = datetime.now(timezone.utc)
