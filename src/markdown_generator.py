"""Markdown report generation module."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .github_tracker import RepoUpdates

logger = logging.getLogger(__name__)


class MarkdownGenerator:
    """Generate Markdown reports for repository updates."""

    def __init__(self, reports_dir: str = "./data/reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize repository name for use in filename."""
        return name.replace("/", "_").replace(" ", "_")

    def generate_report(
        self,
        repo_name: str,
        summary: str,
        updates: Optional[RepoUpdates] = None
    ) -> str:
        """Generate a Markdown report file."""
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = self._sanitize_filename(repo_name)
        filename = f"{safe_name}_{date_str}.md"
        filepath = self.reports_dir / filename

        # Build the report content
        content_parts = [
            f"# {repo_name} 更新报告",
            f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
        ]

        # Add statistics if updates available
        if updates:
            stats = []
            if updates.merged_prs:
                stats.append(f"已合并PR: {len(updates.merged_prs)}")
            if updates.open_prs:
                stats.append(f"新开放PR: {len(updates.open_prs)}")
            if updates.releases:
                stats.append(f"新版本: {len(updates.releases)}")

            if stats:
                content_parts.append(f"**本次统计**: {' | '.join(stats)}\n")

            if updates.keywords:
                content_parts.append(f"**关注关键词**: {', '.join(updates.keywords)}\n")

        content_parts.append("---\n")

        # Add the AI summary
        content_parts.append("## AI 总结\n")
        content_parts.append(summary)
        content_parts.append("\n---\n")

        # Add raw data section if updates available
        if updates:
            content_parts.append("## 原始数据\n")

            if updates.merged_prs:
                content_parts.append("### 已合并的 Pull Requests\n")
                for pr in updates.merged_prs:
                    labels = f" `{', '.join(pr.labels)}`" if pr.labels else ""
                    content_parts.append(f"- [#{pr.number} {pr.title}]({pr.url}){labels}")
                content_parts.append("")

            if updates.open_prs:
                content_parts.append("### 新开放的 Pull Requests\n")
                for pr in updates.open_prs:
                    labels = f" `{', '.join(pr.labels)}`" if pr.labels else ""
                    content_parts.append(f"- [#{pr.number} {pr.title}]({pr.url}){labels}")
                content_parts.append("")

            if updates.releases:
                content_parts.append("### 版本发布\n")
                for release in updates.releases:
                    prerelease = " *(预发布)*" if release.prerelease else ""
                    content_parts.append(f"- [{release.tag_name} - {release.name}]({release.url}){prerelease}")
                content_parts.append("")

        content = "\n".join(content_parts)

        # Write to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Generated report: {filepath}")
        return str(filepath)

    def generate_daily_digest(
        self,
        reports: list[tuple[str, str, Optional[RepoUpdates]]]
    ) -> str:
        """Generate a combined daily digest report."""
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"daily_digest_{date_str}.md"
        filepath = self.reports_dir / filename

        content_parts = [
            "# GitHub 追踪日报",
            f"\n生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            f"追踪项目数: {len(reports)}\n",
            "---\n",
            "## 目录\n"
        ]

        # Generate TOC
        for repo_name, _, _ in reports:
            anchor = repo_name.replace("/", "").replace(" ", "-").lower()
            content_parts.append(f"- [{repo_name}](#{anchor})")
        content_parts.append("\n---\n")

        # Generate content for each repo
        for repo_name, summary, updates in reports:
            content_parts.append(f"## {repo_name}\n")

            if updates:
                stats = []
                if updates.merged_prs:
                    stats.append(f"已合并PR: {len(updates.merged_prs)}")
                if updates.open_prs:
                    stats.append(f"新开放PR: {len(updates.open_prs)}")
                if updates.releases:
                    stats.append(f"新版本: {len(updates.releases)}")
                if stats:
                    content_parts.append(f"*{' | '.join(stats)}*\n")

            content_parts.append(summary)
            content_parts.append("\n---\n")

        content = "\n".join(content_parts)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Generated daily digest: {filepath}")
        return str(filepath)

    def list_reports(self, repo_name: Optional[str] = None) -> list[dict]:
        """List all generated reports."""
        reports = []

        for filepath in sorted(self.reports_dir.glob("*.md"), reverse=True):
            filename = filepath.name

            # Parse filename to extract info
            if filename.startswith("daily_digest_"):
                report_type = "digest"
                date_str = filename.replace("daily_digest_", "").replace(".md", "")
                report_repo = None
            else:
                report_type = "single"
                parts = filename.replace(".md", "").rsplit("_", 1)
                if len(parts) == 2:
                    report_repo = parts[0].replace("_", "/")
                    date_str = parts[1]
                else:
                    continue

            # Filter by repo if specified
            if repo_name and report_repo != repo_name:
                continue

            try:
                report_date = datetime.strptime(date_str, "%Y%m%d")
            except ValueError:
                continue

            reports.append({
                "filename": filename,
                "filepath": str(filepath),
                "type": report_type,
                "repo": report_repo,
                "date": report_date.strftime("%Y-%m-%d"),
                "size": filepath.stat().st_size
            })

        return reports
