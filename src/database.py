"""SQLite database operations module."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from contextlib import contextmanager


class Database:
    """SQLite database manager for tracking GitHub updates."""

    def __init__(self, db_path: str = "./data/tracker.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Repository tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS repos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT UNIQUE NOT NULL,
                    last_pr_id INTEGER DEFAULT 0,
                    last_release_id INTEGER DEFAULT 0,
                    last_run_time TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Summaries table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name TEXT NOT NULL,
                    summary_date TEXT NOT NULL,
                    summary_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    pr_count INTEGER DEFAULT 0,
                    release_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(repo_full_name, summary_date, summary_type)
                )
            """)

            # Processed items table (for deduplication)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processed_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_full_name TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    item_id INTEGER NOT NULL,
                    item_title TEXT,
                    item_url TEXT,
                    processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(repo_full_name, item_type, item_id)
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_summaries_repo_date
                ON summaries(repo_full_name, summary_date)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_items_repo
                ON processed_items(repo_full_name, item_type)
            """)

    def get_repo_state(self, full_name: str) -> Optional[dict]:
        """Get the current tracking state for a repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM repos WHERE full_name = ?",
                (full_name,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_repo_state(
        self,
        full_name: str,
        last_pr_id: Optional[int] = None,
        last_release_id: Optional[int] = None
    ):
        """Update the tracking state for a repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Check if repo exists
            cursor.execute(
                "SELECT id FROM repos WHERE full_name = ?",
                (full_name,)
            )
            exists = cursor.fetchone()

            now = datetime.now().isoformat()

            if exists:
                updates = ["last_run_time = ?"]
                params = [now]

                if last_pr_id is not None:
                    updates.append("last_pr_id = ?")
                    params.append(last_pr_id)

                if last_release_id is not None:
                    updates.append("last_release_id = ?")
                    params.append(last_release_id)

                params.append(full_name)
                cursor.execute(
                    f"UPDATE repos SET {', '.join(updates)} WHERE full_name = ?",
                    params
                )
            else:
                cursor.execute(
                    """INSERT INTO repos (full_name, last_pr_id, last_release_id, last_run_time)
                       VALUES (?, ?, ?, ?)""",
                    (full_name, last_pr_id or 0, last_release_id or 0, now)
                )

    def is_item_processed(self, full_name: str, item_type: str, item_id: int) -> bool:
        """Check if an item has already been processed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id FROM processed_items
                   WHERE repo_full_name = ? AND item_type = ? AND item_id = ?""",
                (full_name, item_type, item_id)
            )
            return cursor.fetchone() is not None

    def mark_item_processed(
        self,
        full_name: str,
        item_type: str,
        item_id: int,
        item_title: str = "",
        item_url: str = ""
    ):
        """Mark an item as processed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT OR IGNORE INTO processed_items
                   (repo_full_name, item_type, item_id, item_title, item_url)
                   VALUES (?, ?, ?, ?, ?)""",
                (full_name, item_type, item_id, item_title, item_url)
            )

    def save_summary(
        self,
        repo_full_name: str,
        summary_type: str,
        content: str,
        pr_count: int = 0,
        release_count: int = 0
    ):
        """Save an AI-generated summary."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            today = datetime.now().strftime("%Y-%m-%d")

            cursor.execute(
                """INSERT OR REPLACE INTO summaries
                   (repo_full_name, summary_date, summary_type, content, pr_count, release_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (repo_full_name, today, summary_type, content, pr_count, release_count)
            )

    def get_recent_summaries(self, repo_full_name: str, limit: int = 3) -> list[dict]:
        """Get recent summaries for a repository."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT * FROM summaries
                   WHERE repo_full_name = ?
                   ORDER BY summary_date DESC, created_at DESC
                   LIMIT ?""",
                (repo_full_name, limit)
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_summaries(
        self,
        repo_full_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> list[dict]:
        """Get all summaries with optional filters."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT * FROM summaries WHERE 1=1"
            params = []

            if repo_full_name:
                query += " AND repo_full_name = ?"
                params.append(repo_full_name)

            if start_date:
                query += " AND summary_date >= ?"
                params.append(start_date)

            if end_date:
                query += " AND summary_date <= ?"
                params.append(end_date)

            query += " ORDER BY summary_date DESC, created_at DESC"

            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_all_repos(self) -> list[str]:
        """Get all tracked repository names."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT repo_full_name FROM summaries ORDER BY repo_full_name")
            return [row["repo_full_name"] for row in cursor.fetchall()]

    def should_run(self, full_name: str, frequency: str) -> bool:
        """Check if tracking should run based on frequency setting."""
        state = self.get_repo_state(full_name)

        if not state or not state.get("last_run_time"):
            return True

        last_run = datetime.fromisoformat(state["last_run_time"])
        now = datetime.now()

        # Compare by calendar date, not elapsed time
        # This ensures a job scheduled for 9:00 daily runs even if
        # previous run finished at 9:03 (less than 24 hours ago)
        last_run_date = last_run.date()
        today = now.date()
        days_since_last_run = (today - last_run_date).days

        if frequency == "1d":
            return days_since_last_run >= 1
        elif frequency == "2d":
            return days_since_last_run >= 2
        elif frequency == "on_release":
            # For on_release, always check (the actual filtering happens in tracker)
            return True

        return days_since_last_run >= 1
