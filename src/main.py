"""Main entry point for GitHub AI Tracker."""

import argparse
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config, RepoConfig
from .database import Database
from .github_tracker import GitHubTracker
from .ai_summarizer import AISummarizer
from .telegram_notifier import TelegramNotifier
from .markdown_generator import MarkdownGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("tracker.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)


class GitHubAITracker:
    """Main tracker application."""

    def __init__(self, config_path: str = "config.json"):
        self.config = Config.load(config_path)
        self.db = Database(f"{self.config.data_dir}/tracker.db")
        self.tracker = GitHubTracker(self.config.github_token, self.db)
        self.summarizer = AISummarizer(self.config.ai, self.db)
        self.notifier = TelegramNotifier(self.config.telegram)
        self.markdown = MarkdownGenerator(self.config.reports_dir)

        # Ensure directories exist
        Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.config.reports_dir).mkdir(parents=True, exist_ok=True)

    def process_repo(self, repo_config: RepoConfig) -> tuple[str, str, bool]:
        """Process a single repository."""
        full_name = repo_config.full_name
        logger.info(f"Processing repository: {full_name}")

        # Check if should run based on frequency
        if not self.db.should_run(full_name, repo_config.frequency):
            logger.info(f"Skipping {full_name} - not yet due for update")
            return full_name, "", False

        # Fetch updates
        updates = self.tracker.fetch_updates(repo_config)
        if not updates:
            logger.info(f"No new updates for {full_name}")
            return full_name, "", False

        # Generate summary
        summary = self.summarizer.summarize(updates)
        if not summary:
            logger.warning(f"Failed to generate summary for {full_name}")
            return full_name, "", False

        # Save summary to database
        self.db.save_summary(
            full_name,
            "daily",
            summary,
            pr_count=len(updates.merged_prs) + len(updates.open_prs),
            release_count=len(updates.releases)
        )

        # Generate Markdown report
        self.markdown.generate_report(full_name, summary, updates)

        # Mark items as processed
        self.tracker.mark_processed(updates)

        # Send Telegram notification if enabled
        if repo_config.enable_tg and self.config.telegram.enabled:
            self.notifier.send_update(full_name, summary)

        logger.info(f"Successfully processed {full_name}")
        return full_name, summary, True

    def run_tracking(self):
        """Run tracking for all configured repositories."""
        logger.info("Starting tracking run...")
        start_time = datetime.now()

        results = []
        successful = 0
        failed = 0

        for repo_config in self.config.repos:
            try:
                full_name, summary, processed = self.process_repo(repo_config)
                if processed:
                    results.append((full_name, summary, None))
                    successful += 1
            except Exception as e:
                logger.error(f"Error processing {repo_config.full_name}: {e}")
                failed += 1

        # Generate daily digest if we have results
        if results:
            self.markdown.generate_daily_digest(results)

            # Send digest notification if Telegram is enabled
            if self.config.telegram.enabled and successful > 0:
                digest = self.summarizer.generate_digest(
                    [r[1] for r in results],
                    [r[0] for r in results]
                )
                if digest:
                    self.notifier.send_digest(digest, successful)

        elapsed = datetime.now() - start_time
        logger.info(
            f"Tracking run completed. "
            f"Processed: {successful}, Failed: {failed}, "
            f"Time: {elapsed.total_seconds():.1f}s"
        )

        # Log rate limit info
        try:
            rate_info = self.tracker.get_rate_limit_info()
            logger.info(
                f"GitHub API rate limit: {rate_info['remaining']}/{rate_info['limit']} "
                f"(resets at {rate_info['reset_time']})"
            )
        except Exception:
            pass

    def run_single(self, repo_name: str):
        """Run tracking for a single repository."""
        repo_config = self.config.get_repo_by_name(repo_name)
        if not repo_config:
            logger.error(f"Repository not found in config: {repo_name}")
            return

        self.process_repo(repo_config)


def create_scheduler(tracker: GitHubAITracker, schedule: str = "0 9 * * *"):
    """Create and configure the scheduler."""
    scheduler = BlockingScheduler()

    # Parse schedule (default: daily at 9:00 AM)
    scheduler.add_job(
        tracker.run_tracking,
        CronTrigger.from_crontab(schedule),
        id="github_tracking",
        name="GitHub Tracking Job",
        misfire_grace_time=3600
    )

    return scheduler


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="GitHub AI Tracker")
    parser.add_argument(
        "--config", "-c",
        default="config.json",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run tracking once and exit"
    )
    parser.add_argument(
        "--repo",
        help="Process a single repository (format: owner/name)"
    )
    parser.add_argument(
        "--schedule",
        default="0 9 * * *",
        help="Cron schedule for tracking (default: '0 9 * * *' = daily at 9:00 AM)"
    )

    args = parser.parse_args()

    try:
        tracker = GitHubAITracker(args.config)
        logger.info("GitHub AI Tracker initialized")

        if args.repo:
            # Process single repository
            tracker.run_single(args.repo)
        elif args.run_once:
            # Run once and exit
            tracker.run_tracking()
        else:
            # Start scheduler
            scheduler = create_scheduler(tracker, args.schedule)

            # Handle shutdown signals
            def signal_handler(signum, frame):
                logger.info("Received shutdown signal, stopping scheduler...")
                scheduler.shutdown(wait=False)
                sys.exit(0)

            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            logger.info(f"Starting scheduler with schedule: {args.schedule}")
            logger.info("Press Ctrl+C to stop")

            # Run initial tracking
            tracker.run_tracking()

            # Start scheduler
            scheduler.start()

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
