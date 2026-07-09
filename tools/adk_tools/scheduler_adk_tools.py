"""
Scheduler ADK Tools

ADK-compatible tools for managing scheduled/recurring agent tasks.
Uses the SchedulerInterface from interfaces/scheduler_interface.py.

Tools:
- scheduler_add_job: Add a new scheduled job
- scheduler_list_jobs: List all scheduled jobs
- scheduler_remove_job: Remove a scheduled job
- scheduler_pause_job: Pause a job
- scheduler_resume_job: Resume a paused job
"""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton scheduler instance. Registered ONLY by the CLI path
# (main.py initialize_agents(start_scheduler=True)); web/RPi deployments run
# jobs in a separate process (run_scheduler.py), so there these tools have no
# instance and must say so honestly instead of "restart the system".
_scheduler_instance = None

_SCHEDULER_UNAVAILABLE = (
    "Scheduler is not running in this process. Recurring jobs are managed by "
    "the CLI (python main.py) or the scheduler daemon (python run_scheduler.py) "
    "— tell the user to add/manage the job there."
)


def set_scheduler_instance(scheduler):
    """Set the global scheduler instance (called by main.py during init)."""
    global _scheduler_instance
    _scheduler_instance = scheduler
    logger.info("Scheduler instance registered with ADK tools")


def get_scheduler_instance():
    """Get the global scheduler instance."""
    return _scheduler_instance


async def scheduler_add_job(
    name: str,
    agent_request: str,
    trigger_type: str,
    cron_expression: Optional[str] = None,
    interval_seconds: Optional[int] = None,
    run_date: Optional[str] = None,
    timezone: str = "Europe/Zagreb",
    max_retries: int = 2,
    job_id: Optional[str] = None
) -> dict:
    """
    Add a new scheduled job that executes an agent request on a schedule.

    The agent_request is natural language - the same text a user would type in the CLI.
    The Smart Orchestrator will route it to the appropriate agent when triggered.

    Args:
        name: Human-readable job name (e.g., "Weekly Sales Report")
        agent_request: Natural language request for agents (e.g., "Send weekly sales report to team@company.com")
        trigger_type: Type of trigger - "cron", "interval", or "date"
        cron_expression: Cron expression for cron triggers (format: "minute hour day month day_of_week")
                        Examples: "0 9 * * MON-FRI" (weekdays 9am), "0 8 * * MON" (Mondays 8am),
                        "*/30 * * * *" (every 30 min), "0 0 1 * *" (1st of month midnight)
        interval_seconds: Interval in seconds for interval triggers (e.g., 3600 for hourly)
        run_date: ISO datetime for one-time date triggers (e.g., "2026-03-10 14:00:00")
        timezone: Timezone for the schedule (default: Europe/Zagreb)
        max_retries: Max retry attempts on failure (default: 2)
        job_id: Optional custom job ID (auto-generated if not provided)

    Returns:
        Dictionary with job details and confirmation
    """
    scheduler = get_scheduler_instance()
    if scheduler is None:
        return {"error": _SCHEDULER_UNAVAILABLE}

    from config.scheduler_config import ScheduledJob, JobTrigger

    if not job_id:
        job_id = f"job-{uuid.uuid4().hex[:8]}"

    try:
        trigger = JobTrigger(
            type=trigger_type,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            run_date=run_date,
            timezone=timezone
        )

        job = ScheduledJob(
            id=job_id,
            name=name,
            agent_request=agent_request,
            trigger=trigger,
            enabled=True,
            max_retries=max_retries
        )

        scheduler.add_job(job)

        # Get next run time
        ap_job = scheduler.scheduler.get_job(job_id)
        next_run = str(ap_job.next_run_time) if ap_job and ap_job.next_run_time else "N/A"

        trigger_desc = cron_expression or f"every {interval_seconds}s" or run_date
        return {
            "status": "success",
            "job_id": job_id,
            "name": name,
            "agent_request": agent_request,
            "trigger": f"{trigger_type}: {trigger_desc}",
            "timezone": timezone,
            "next_run": next_run,
            "message": f"Job '{name}' scheduled successfully. Next run: {next_run}"
        }

    except Exception as e:
        logger.error(f"Failed to add job: {e}")
        return {"error": str(e)}


async def scheduler_list_jobs() -> dict:
    """
    List all scheduled jobs with their current status.

    Returns:
        Dictionary with list of all jobs, their triggers, next run times, and last execution status.
    """
    scheduler = get_scheduler_instance()
    if scheduler is None:
        return {"error": _SCHEDULER_UNAVAILABLE, "jobs": []}

    jobs = scheduler.list_jobs()
    return {
        "total_jobs": len(jobs),
        "jobs": jobs,
        "scheduler_running": scheduler.scheduler.running
    }


async def scheduler_remove_job(job_id: str) -> dict:
    """
    Remove a scheduled job by its ID.

    Args:
        job_id: The ID of the job to remove

    Returns:
        Dictionary with removal confirmation
    """
    scheduler = get_scheduler_instance()
    if scheduler is None:
        return {"error": _SCHEDULER_UNAVAILABLE}

    if scheduler.remove_job(job_id):
        return {"status": "success", "message": f"Job '{job_id}' removed successfully."}
    else:
        return {"error": f"Job '{job_id}' not found."}


async def scheduler_pause_job(job_id: str) -> dict:
    """
    Pause a scheduled job. The job will not execute until resumed.

    Args:
        job_id: The ID of the job to pause

    Returns:
        Dictionary with pause confirmation
    """
    scheduler = get_scheduler_instance()
    if scheduler is None:
        return {"error": _SCHEDULER_UNAVAILABLE}

    if scheduler.pause_job(job_id):
        return {"status": "success", "message": f"Job '{job_id}' paused."}
    else:
        return {"error": f"Failed to pause job '{job_id}'."}


async def scheduler_resume_job(job_id: str) -> dict:
    """
    Resume a paused scheduled job.

    Args:
        job_id: The ID of the job to resume

    Returns:
        Dictionary with resume confirmation
    """
    scheduler = get_scheduler_instance()
    if scheduler is None:
        return {"error": _SCHEDULER_UNAVAILABLE}

    if scheduler.resume_job(job_id):
        return {"status": "success", "message": f"Job '{job_id}' resumed."}
    else:
        return {"error": f"Failed to resume job '{job_id}'."}


def get_scheduler_adk_tools() -> list:
    """
    Get all scheduler ADK tools as a list of async functions.

    Returns:
        List of tool functions for use with ADK agents
    """
    tools = [
        scheduler_add_job,
        scheduler_list_jobs,
        scheduler_remove_job,
        scheduler_pause_job,
        scheduler_resume_job
    ]
    logger.info(f"Scheduler ADK tools loaded: {len(tools)} tools")
    return tools
