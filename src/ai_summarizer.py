"""AI summarization module."""

import logging
from typing import Optional

from openai import OpenAI

from .config import AIConfig
from .database import Database
from .github_tracker import RepoUpdates, PRInfo, ReleaseInfo

logger = logging.getLogger(__name__)


class AISummarizer:
    """AI-powered update summarizer."""

    def __init__(self, config: AIConfig, db: Optional[Database] = None):
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
        self.model = config.model
        self.db = db or Database()

    def _format_pr_list(self, prs: list[PRInfo], pr_type: str) -> str:
        """Format a list of PRs for the prompt."""
        if not prs:
            return f"无{pr_type}\n"

        lines = [f"### {pr_type} ({len(prs)}个)\n"]
        for pr in prs:
            labels_str = f" [{', '.join(pr.labels)}]" if pr.labels else ""
            body_preview = pr.body[:200] + "..." if len(pr.body) > 200 else pr.body
            body_preview = body_preview.replace("\n", " ").strip()
            lines.append(f"- **#{pr.number}** {pr.title}{labels_str}")
            lines.append(f"  URL: {pr.url}")
            if body_preview:
                lines.append(f"  描述: {body_preview}")
            lines.append("")
        return "\n".join(lines)

    def _format_release_list(self, releases: list[ReleaseInfo]) -> str:
        """Format a list of releases for the prompt."""
        if not releases:
            return "无新版本发布\n"

        lines = ["### 新版本发布\n"]
        for release in releases:
            prerelease_tag = " (预发布)" if release.prerelease else ""
            body_preview = release.body[:300] + "..." if len(release.body) > 300 else release.body
            body_preview = body_preview.replace("\n", " ").strip()
            lines.append(f"- **{release.tag_name}** {release.name}{prerelease_tag}")
            lines.append(f"  URL: {release.url}")
            if body_preview:
                lines.append(f"  更新内容: {body_preview}")
            lines.append("")
        return "\n".join(lines)

    def _get_history_context(self, repo_name: str) -> str:
        """Get compressed history from recent summaries."""
        recent_summaries = self.db.get_recent_summaries(repo_name, limit=3)

        if not recent_summaries:
            return ""

        summaries_text = "\n\n---\n\n".join([
            f"[{s['summary_date']}]\n{s['content']}"
            for s in recent_summaries
        ])

        return f"""
## 历史回顾
以下是该项目最近3次的更新总结，请在总结时考虑这些背景信息，帮助用户理解项目的发展脉络：

{summaries_text}

请将以上历史记录压缩为100字以内的极简回顾，作为本次总结的开头。
"""

    def summarize(self, updates: RepoUpdates) -> Optional[str]:
        """Generate AI summary for repository updates."""
        if not updates.open_prs and not updates.merged_prs and not updates.releases:
            return None

        # Build the content section
        content_parts = []

        if updates.merged_prs:
            content_parts.append(self._format_pr_list(updates.merged_prs, "已合并的PR"))

        if updates.open_prs:
            content_parts.append(self._format_pr_list(updates.open_prs, "新开放的PR"))

        if updates.releases:
            content_parts.append(self._format_release_list(updates.releases))

        updates_content = "\n".join(content_parts)

        # Build keywords emphasis
        keywords_instruction = ""
        if updates.keywords:
            keywords_str = "、".join(updates.keywords)
            keywords_instruction = f"\n**重点关注**: 请特别关注包含以下关键词的更新: {keywords_str}\n"

        # Get history context
        history_context = self._get_history_context(updates.repo_name)

        # Build the full prompt
        prompt = f"""你是一个专业的技术文档助手，负责总结 GitHub 项目的更新动态。

## 项目
{updates.repo_name}
{keywords_instruction}
{history_context}

## 本次更新内容

{updates_content}

## 总结要求

请用中文生成一份结构清晰的更新总结，包含以下部分：

1. **历史回顾**（如有历史记录）：100字以内的极简回顾
2. **重要更新**：突出最重要的变化（新功能、重大修复、breaking changes等）
3. **PR概览**：
   - 已合并PR的主要改动
   - 新开放PR的关注点
4. **版本发布**（如有）：新版本的核心变化
5. **技术趋势**：从更新中观察到的项目发展方向

请保持总结简洁专业，使用Markdown格式，突出关键信息。对于PR和Release，请保留原始链接。
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的技术文档助手，擅长总结GitHub项目更新。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )

            summary = response.choices[0].message.content
            logger.info(f"Generated summary for {updates.repo_name}")
            return summary

        except Exception as e:
            logger.error(f"Failed to generate summary for {updates.repo_name}: {e}")
            return None

    def generate_digest(self, summaries: list[str], repo_names: list[str]) -> Optional[str]:
        """Generate a combined digest from multiple repository summaries."""
        if not summaries:
            return None

        combined = "\n\n---\n\n".join([
            f"## {name}\n\n{summary}"
            for name, summary in zip(repo_names, summaries)
        ])

        prompt = f"""以下是多个GitHub项目的更新总结，请生成一份综合摘要：

{combined}

请用中文生成一份简洁的综合摘要（300字以内），突出所有项目中最重要的更新。
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的技术文档助手。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=500
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"Failed to generate digest: {e}")
            return None
