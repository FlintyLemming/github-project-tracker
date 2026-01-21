"""GitHub API interaction module."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from github import Github, GithubException
from github.PullRequest import PullRequest
from github.GitRelease import GitRelease

from .config import RepoConfig
from .database import Database

logger = logging.getLogger(__name__)


@dataclass
class PRInfo:
    """Pull request information."""
    id: int
    number: int
    title: str
    url: str
    state: str
    merged: bool
    body: str
    created_at: datetime
    updated_at: datetime
    labels: list[str]


@dataclass
class ReleaseInfo:
    """Release information."""
    id: int
    tag_name: str
    name: str
    url: str
    body: str
    published_at: datetime
    prerelease: bool


@dataclass
class RepoUpdates:
    """Collected updates for a repository."""
    repo_name: str
    open_prs: list[PRInfo]
    merged_prs: list[PRInfo]
    releases: list[ReleaseInfo]
    keywords: list[str]


class GitHubTracker:
    """GitHub repository tracker."""

    def __init__(self, token: Optional[str] = None, db: Optional[Database] = None):
        self.github = Github(token) if token else Github()
        self.db = db or Database()

    def _convert_pr(self, pr: PullRequest) -> PRInfo:
        """Convert GitHub PR object to PRInfo."""
        return PRInfo(
            id=pr.id,
            number=pr.number,
            title=pr.title,
            url=pr.html_url,
            state=pr.state,
            merged=pr.merged if pr.state == "closed" else False,
            body=pr.body or "",
            created_at=pr.created_at,
            updated_at=pr.updated_at,
            labels=[label.name for label in pr.labels]
        )

    def _convert_release(self, release: GitRelease) -> ReleaseInfo:
        """Convert GitHub Release object to ReleaseInfo."""
        return ReleaseInfo(
            id=release.id,
            tag_name=release.tag_name,
            name=release.title or release.tag_name,
            url=release.html_url,
            body=release.body or "",
            published_at=release.published_at or release.created_at,
            prerelease=release.prerelease
        )

    def fetch_updates(self, repo_config: RepoConfig) -> Optional[RepoUpdates]:
        """Fetch new updates for a repository based on configuration."""
        full_name = repo_config.full_name
        logger.info(f"Fetching updates for {full_name}")

        try:
            repo = self.github.get_repo(full_name)
        except GithubException as e:
            logger.error(f"Failed to access repository {full_name}: {e}")
            return None

        state = self.db.get_repo_state(full_name)
        last_pr_id = state.get("last_pr_id", 0) if state else 0
        last_release_id = state.get("last_release_id", 0) if state else 0

        open_prs: list[PRInfo] = []
        merged_prs: list[PRInfo] = []
        releases: list[ReleaseInfo] = []

        # Fetch based on tracking level
        if repo_config.level in ["all", "merged_and_release"]:
            # Fetch merged PRs
            try:
                prs = repo.get_pulls(state="closed", sort="updated", direction="desc")
                count = 0
                for pr in prs:
                    if count >= 50:
                        break
                    count += 1
                    if pr.merged and pr.id > last_pr_id:
                        if not self.db.is_item_processed(full_name, "pr", pr.id):
                            merged_prs.append(self._convert_pr(pr))
            except GithubException as e:
                logger.warning(f"Failed to fetch merged PRs for {full_name}: {e}")

        if repo_config.level == "all":
            # Fetch open PRs
            try:
                prs = repo.get_pulls(state="open", sort="updated", direction="desc")
                count = 0
                for pr in prs:
                    if count >= 30:
                        break
                    count += 1
                    if pr.id > last_pr_id:
                        if not self.db.is_item_processed(full_name, "pr_open", pr.id):
                            open_prs.append(self._convert_pr(pr))
            except GithubException as e:
                logger.warning(f"Failed to fetch open PRs for {full_name}: {e}")

        # Fetch releases (all levels track releases)
        try:
            repo_releases = repo.get_releases()
            count = 0
            for release in repo_releases:
                if count >= 10:
                    break
                count += 1
                if release.id > last_release_id:
                    if not self.db.is_item_processed(full_name, "release", release.id):
                        releases.append(self._convert_release(release))
        except (GithubException, Exception) as e:
            logger.warning(f"Failed to fetch releases for {full_name}: {e}")

        # Check if we have any updates
        if not open_prs and not merged_prs and not releases:
            logger.info(f"No new updates for {full_name}")
            return None

        return RepoUpdates(
            repo_name=full_name,
            open_prs=open_prs,
            merged_prs=merged_prs,
            releases=releases,
            keywords=repo_config.keywords
        )

    def mark_processed(self, updates: RepoUpdates):
        """Mark all items in updates as processed."""
        full_name = updates.repo_name

        max_pr_id = 0
        max_release_id = 0

        for pr in updates.open_prs:
            self.db.mark_item_processed(
                full_name, "pr_open", pr.id, pr.title, pr.url
            )
            max_pr_id = max(max_pr_id, pr.id)

        for pr in updates.merged_prs:
            self.db.mark_item_processed(
                full_name, "pr", pr.id, pr.title, pr.url
            )
            max_pr_id = max(max_pr_id, pr.id)

        for release in updates.releases:
            self.db.mark_item_processed(
                full_name, "release", release.id, release.name, release.url
            )
            max_release_id = max(max_release_id, release.id)

        # Update repo state
        self.db.update_repo_state(
            full_name,
            last_pr_id=max_pr_id if max_pr_id > 0 else None,
            last_release_id=max_release_id if max_release_id > 0 else None
        )

    def get_rate_limit_info(self) -> dict:
        """Get current GitHub API rate limit information."""
        rate_limit = self.github.get_rate_limit()
        core = rate_limit.core
        return {
            "limit": core.limit,
            "remaining": core.remaining,
            "reset_time": core.reset.isoformat()
        }
