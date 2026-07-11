"""
Scheduler Interface for Google Workspace ADK System

Provides APScheduler-based recurring/scheduled task execution.
Jobs are defined as natural language agent requests and executed
through the Smart Orchestrator pipeline.

Usage:
    python run_scheduler.py
"""

import os
import logging
import asyncio
import time
from typing import Optional, Dict, List

from dotenv import load_dotenv
load_dotenv()

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from .base_interface import BaseInterface
from config.scheduler_config import (
    ScheduledJob, JobTrigger, SchedulerConfig,
    load_jobs, save_jobs
)

logger = logging.getLogger(__name__)


class SchedulerInterface(BaseInterface):
    """
    Scheduler interface that executes agent requests on a schedule.

    Extends BaseInterface to reuse the WorkspaceADKSystem and
    RunnerHelper for executing tasks through the Smart Orchestrator.
    """

    def __init__(self):
        """Initialize scheduler interface."""
        super().__init__(session_prefix="scheduler")

        self.scheduler = AsyncIOScheduler(timezone="Europe/Zagreb")
        self.config: SchedulerConfig = SchedulerConfig()
        self.job_results: Dict[str, dict] = {}

        logger.info("SchedulerInterface initialized")

    def _build_trigger(self, trigger: JobTrigger):
        """Build APScheduler trigger from JobTrigger config."""
        if trigger.type == "cron":
            if not trigger.cron_expression:
                raise ValueError("cron_expression required for cron trigger")
            parts = trigger.cron_expression.split()
            if len(parts) != 5:
                raise ValueError(f"Invalid cron expression: '{trigger.cron_expression}' (need 5 fields: min hour day month dow)")
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4],
                timezone=trigger.timezone
            )
        elif trigger.type == "interval":
            if not trigger.interval_seconds:
                raise ValueError("interval_seconds required for interval trigger")
            return IntervalTrigger(
                seconds=trigger.interval_seconds,
                timezone=trigger.timezone
            )
        elif trigger.type == "date":
            if not trigger.run_date:
                raise ValueError("run_date required for date trigger")
            return DateTrigger(
                run_date=trigger.run_date,
                timezone=trigger.timezone
            )
        else:
            raise ValueError(f"Unknown trigger type: {trigger.type}")

    async def _deliver_to_telegram(self, text: str) -> bool:
        """Push a job result to the authorized Telegram chat, if configured."""
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if not token or not chat_id:
            logger.info("[SCHEDULER] No Telegram token/chat configured for delivery")
            return False
        from telegram import Bot

        bot = Bot(token=token)
        # Telegram hard limit is 4096 chars per message
        for start in range(0, len(text), 4000):
            await bot.send_message(chat_id=chat_id, text=text[start:start + 4000])
        return True

    async def _execute_briefing_job(self, job_config: ScheduledJob) -> None:
        """Deterministic daily-briefing job — no orchestrator, no NL replay."""
        job_id = job_config.id
        start_time = time.time()
        try:
            from config.user_context import get_default_user_context
            from services.daily_briefing import get_daily_briefing

            text = await get_daily_briefing(
                get_default_user_context(channel="scheduler")
            )
            delivered = await self._deliver_to_telegram(text)
            self.job_results[job_id] = {
                "status": "SUCCESS",
                "result_preview": text[:200],
                "delivered": delivered,
                "elapsed": round(time.time() - start_time, 1),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "attempt": 1,
            }
            logger.info(f"[SCHEDULER] Briefing job '{job_id}' done (delivered={delivered})")
        except Exception as e:
            self.job_results[job_id] = {
                "status": "FAILED",
                "error": str(e)[:200],
                "elapsed": round(time.time() - start_time, 1),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "attempt": 1,
            }
            logger.error(f"[SCHEDULER] Briefing job '{job_id}' failed: {e}")

    async def _execute_job(self, job_config: ScheduledJob) -> None:
        """
        Execute a scheduled job through the agent pipeline.

        This is called by APScheduler when a job triggers.
        """
        job_id = job_config.id

        if getattr(job_config, "action_type", "nl") == "briefing":
            await self._execute_briefing_job(job_config)
            return

        logger.info(f"[SCHEDULER] Executing job '{job_id}': {job_config.agent_request}")

        start_time = time.time()
        attempt = 0
        max_attempts = job_config.max_retries + 1

        while attempt < max_attempts:
            attempt += 1
            try:
                if self.system is None:
                    self.initialize_system()

                # Create/get RunnerHelper for this job's session
                from agents.adk_agents.runner_utils import RunnerHelper
                helper = RunnerHelper(
                    agent=self.system.orchestrator,
                    session_id=f"scheduler-{job_id}",
                    user_id="system:scheduler",
                    app_name="agents"
                )

                result = await helper.run(job_config.agent_request)
                elapsed = time.time() - start_time

                self.job_results[job_id] = {
                    "status": "SUCCESS",
                    "result_preview": result[:200] if result else "",
                    "elapsed": round(elapsed, 1),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "attempt": attempt
                }

                logger.info(f"[SCHEDULER] Job '{job_id}' completed in {elapsed:.1f}s (attempt {attempt})")
                logger.info(f"[SCHEDULER] Result preview: {result[:200] if result else 'empty'}")
                return

            except Exception as e:
                elapsed = time.time() - start_time
                error_str = str(e)
                logger.error(f"[SCHEDULER] Job '{job_id}' failed (attempt {attempt}/{max_attempts}): {e}")

                if attempt < max_attempts:
                    # Retry with backoff for rate limits
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                        wait = 60 * attempt
                        logger.info(f"[SCHEDULER] Rate limited, waiting {wait}s before retry...")
                        await asyncio.sleep(wait)
                    else:
                        await asyncio.sleep(5)
                else:
                    self.job_results[job_id] = {
                        "status": "FAILED",
                        "error": error_str[:200],
                        "elapsed": round(elapsed, 1),
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "attempt": attempt
                    }

    def add_job(self, job: ScheduledJob) -> str:
        """
        Add a scheduled job.

        Args:
            job: ScheduledJob configuration

        Returns:
            Job ID
        """
        trigger = self._build_trigger(job.trigger)

        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=job.id,
            name=job.name,
            args=[job],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )

        # Save to config
        existing_ids = {j.id for j in self.config.jobs}
        if job.id not in existing_ids:
            self.config.jobs.append(job)
        else:
            self.config.jobs = [j if j.id != job.id else job for j in self.config.jobs]

        save_jobs(self.config)
        logger.info(f"[SCHEDULER] Added job '{job.id}': {job.name} ({job.trigger.type})")
        return job.id

    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job."""
        try:
            self.scheduler.remove_job(job_id)
        except Exception:
            pass

        original_len = len(self.config.jobs)
        self.config.jobs = [j for j in self.config.jobs if j.id != job_id]

        if len(self.config.jobs) < original_len:
            save_jobs(self.config)
            logger.info(f"[SCHEDULER] Removed job '{job_id}'")
            return True
        return False

    def pause_job(self, job_id: str) -> bool:
        """Pause a scheduled job."""
        try:
            self.scheduler.pause_job(job_id)
            for job in self.config.jobs:
                if job.id == job_id:
                    job.enabled = False
            save_jobs(self.config)
            logger.info(f"[SCHEDULER] Paused job '{job_id}'")
            return True
        except Exception as e:
            logger.error(f"Failed to pause job '{job_id}': {e}")
            return False

    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job."""
        try:
            self.scheduler.resume_job(job_id)
            for job in self.config.jobs:
                if job.id == job_id:
                    job.enabled = True
            save_jobs(self.config)
            logger.info(f"[SCHEDULER] Resumed job '{job_id}'")
            return True
        except Exception as e:
            logger.error(f"Failed to resume job '{job_id}': {e}")
            return False

    def list_jobs(self) -> List[dict]:
        """List all scheduled jobs with their status."""
        jobs_info = []
        for job in self.config.jobs:
            ap_job = self.scheduler.get_job(job.id)
            next_run = str(ap_job.next_run_time) if ap_job and ap_job.next_run_time else "N/A"
            last_result = self.job_results.get(job.id, {})

            jobs_info.append({
                "id": job.id,
                "name": job.name,
                "request": job.agent_request[:60] + "..." if len(job.agent_request) > 60 else job.agent_request,
                "trigger": f"{job.trigger.type}: {self._describe_trigger(job.trigger)}",
                "enabled": job.enabled,
                "next_run": next_run,
                "last_status": last_result.get("status", "Never run"),
                "last_run": last_result.get("timestamp", "N/A")
            })
        return jobs_info

    @staticmethod
    def _describe_trigger(trigger) -> str:
        """Human-readable trigger description.

        The old one-liner rendered date jobs as "Nones": interval_seconds is
        None so f'{None}s' -> "Nones" (truthy) and run_date never showed.
        """
        if trigger.cron_expression:
            return trigger.cron_expression
        if trigger.interval_seconds is not None:
            return f"{trigger.interval_seconds}s"
        if trigger.run_date:
            return str(trigger.run_date)
        return "?"

    def _load_saved_jobs(self) -> None:
        """Load and register jobs from persistent storage."""
        self.config = load_jobs()

        for job in self.config.jobs:
            if not job.enabled:
                logger.info(f"[SCHEDULER] Skipping disabled job '{job.id}'")
                continue

            try:
                trigger = self._build_trigger(job.trigger)
                self.scheduler.add_job(
                    self._execute_job,
                    trigger=trigger,
                    id=job.id,
                    name=job.name,
                    args=[job],
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=300,
                )
                logger.info(f"[SCHEDULER] Loaded job '{job.id}': {job.name}")
            except Exception as e:
                logger.error(f"[SCHEDULER] Failed to load job '{job.id}': {e}")

    async def start(self) -> None:
        """Start the scheduler interface."""
        logger.info("Starting Scheduler interface...")

        # Initialize agent system
        self.initialize_system()

        # Load saved jobs
        self._load_saved_jobs()

        # Start scheduler
        self.scheduler.start()
        logger.info(f"[SCHEDULER] Started with {len(self.config.jobs)} jobs")

    async def stop(self) -> None:
        """Stop the scheduler interface."""
        logger.info("Stopping Scheduler interface...")
        self.scheduler.shutdown(wait=False)
        save_jobs(self.config)
        logger.info("Scheduler stopped, jobs saved")

    def format_response(self, response: str) -> str:
        """Format response (passthrough for scheduler)."""
        return response
