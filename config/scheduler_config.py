"""
Scheduler Configuration

Pydantic models for scheduled jobs with JSON file persistence.
Jobs are stored in config/scheduled_jobs.json.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

def _resolve_jobs_file() -> Path:
    """Select scheduler job file based on deployment profile when available."""
    base_dir = Path(__file__).parent
    profile = os.getenv("DEPLOYMENT_PROFILE", "full").strip().lower()
    if profile:
        profile_path = base_dir / f"scheduled_jobs.{profile}.json"
        if profile_path.exists():
            return profile_path
    return base_dir / "scheduled_jobs.json"


# Default path for job persistence
JOBS_FILE = _resolve_jobs_file()


class JobTrigger(BaseModel):
    """Trigger configuration for a scheduled job."""
    type: str = Field(description="Trigger type: 'cron', 'interval', or 'date'")

    # Cron fields (type='cron')
    cron_expression: Optional[str] = Field(
        None,
        description="Cron expression: 'minute hour day month day_of_week' (e.g., '0 9 * * MON-FRI')"
    )

    # Interval fields (type='interval')
    interval_seconds: Optional[int] = Field(None, description="Interval in seconds")

    # Date fields (type='date')
    run_date: Optional[str] = Field(None, description="ISO format date for one-time execution")

    # Common
    timezone: str = Field("Europe/Zagreb", description="Timezone for the trigger")


class ScheduledJob(BaseModel):
    """A scheduled job that triggers an agent request."""
    id: str = Field(description="Unique job identifier")
    name: str = Field(description="Human-readable job name")
    agent_request: str = Field(description="Natural language request for the agent system")
    trigger: JobTrigger
    enabled: bool = Field(True, description="Whether the job is active")
    max_retries: int = Field(2, description="Max retry attempts on failure")
    description: Optional[str] = Field(None, description="Optional description")


class SchedulerConfig(BaseModel):
    """Root configuration containing all scheduled jobs."""
    jobs: List[ScheduledJob] = Field(default_factory=list)


def load_jobs(file_path: Path = JOBS_FILE) -> SchedulerConfig:
    """Load scheduled jobs from JSON file."""
    if not file_path.exists():
        logger.info(f"No jobs file found at {file_path}, starting with empty config")
        return SchedulerConfig()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        config = SchedulerConfig(**data)
        logger.info(f"Loaded {len(config.jobs)} scheduled jobs from {file_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load jobs from {file_path}: {e}")
        return SchedulerConfig()


def save_jobs(config: SchedulerConfig, file_path: Path = JOBS_FILE) -> None:
    """Save scheduled jobs to JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config.model_dump(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(config.jobs)} jobs to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save jobs to {file_path}: {e}")
        raise
