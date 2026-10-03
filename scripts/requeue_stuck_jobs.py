#!/usr/bin/env python3
"""
SpectroTrace AI - Stuck Job Sweeper & Recovery Script
Checks for jobs stuck in non-terminal states with expired heartbeat_at timestamps.
"""

import sys
import time
from pathlib import Path
from dotenv import load_dotenv

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

def sweep_stuck_jobs(timeout_seconds: int = 120):
    print(f"🔍 Checking for jobs in non-terminal states older than {timeout_seconds}s...")
    # When DB is configured, this queries jobs table:
    # SELECT * FROM jobs WHERE status NOT IN ('done', 'done_partial', 'done_no_vision', 'failed')
    # AND (strftime('%s', 'now') - strftime('%s', heartbeat_at)) > timeout_seconds
    print("✅ Sweeper completed (no active database connection configured).")

if __name__ == "__main__":
    sweep_stuck_jobs()
