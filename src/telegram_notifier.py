"""Telegram notification module."""

import asyncio
import logging
import re
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from .config import TelegramConfig, ProxyConfig

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram bot for sending update notifications."""

    def __init__(self, config: TelegramConfig, proxy: Optional[ProxyConfig] = None):
        self.config = config
        self.bot: Optional[Bot] = None

        if config.enabled and config.bot_token:
            # Configure proxy if enabled
            if proxy and proxy.enabled and proxy.proxy_url:
                logger.info(f"Telegram bot using proxy: {proxy.proxy_url}")
                request = HTTPXRequest(proxy=proxy.proxy_url)
                self.bot = Bot(token=config.bot_token, request=request)
            else:
                self.bot = Bot(token=config.bot_token)

    def _truncate_message(self, message: str, max_length: int = 4096) -> str:
        """Truncate message to Telegram's maximum length."""
        if len(message) <= max_length:
            return message

        truncated = message[:max_length - 100]
        last_newline = truncated.rfind("\n")
        if last_newline > max_length - 500:
            truncated = truncated[:last_newline]

        return truncated + "\n\n...(内容已截断)"

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    def _markdown_to_telegram_html(self, text: str) -> str:
        """Convert Markdown to Telegram-compatible HTML."""
        # First, protect code blocks from other transformations
        code_blocks = []
        def save_code_block(match):
            code_blocks.append(match.group(1))
            return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

        # Save code blocks
        text = re.sub(r'```[\w]*\n?(.*?)```', save_code_block, text, flags=re.DOTALL)

        # Save inline code
        inline_codes = []
        def save_inline_code(match):
            inline_codes.append(match.group(1))
            return f"__INLINE_CODE_{len(inline_codes) - 1}__"

        text = re.sub(r'`([^`]+)`', save_inline_code, text)

        # Escape HTML characters (but not in saved code blocks)
        text = self._escape_html(text)

        # Convert headers to bold
        text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

        # Convert bold: **text** or __text__
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__(.+?)__(?!_)', r'<b>\1</b>', text)

        # Convert italic: *text* or _text_
        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
        text = re.sub(r'(?<!_)_(?!_)(.+?)(?<!_)_(?!_)', r'<i>\1</i>', text)

        # Convert links: [text](url)
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

        # Convert list items
        text = re.sub(r'^[\-\*]\s+', '• ', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s+', '• ', text, flags=re.MULTILINE)

        # Convert nested list items (with indentation)
        text = re.sub(r'^(\s+)[\-\*]\s+', r'\1◦ ', text, flags=re.MULTILINE)

        # Remove horizontal rules
        text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)

        # Restore code blocks
        for i, code in enumerate(code_blocks):
            escaped_code = self._escape_html(code.strip())
            text = text.replace(f"__CODE_BLOCK_{i}__", f"<pre>{escaped_code}</pre>")

        # Restore inline code
        for i, code in enumerate(inline_codes):
            escaped_code = self._escape_html(code)
            text = text.replace(f"__INLINE_CODE_{i}__", f"<code>{escaped_code}</code>")

        # Clean up extra blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    async def _send_message_async(self, message: str, parse_mode: Optional[str] = None) -> bool:
        """Send message asynchronously."""
        if not self.bot or not self.config.enabled:
            logger.warning("Telegram notifications are disabled")
            return False

        try:
            truncated = self._truncate_message(message)
            await self.bot.send_message(
                chat_id=self.config.chat_id,
                text=truncated,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            logger.info("Telegram message sent successfully")
            return True
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")
            # Try without parse mode if markdown fails
            if parse_mode:
                try:
                    await self.bot.send_message(
                        chat_id=self.config.chat_id,
                        text=truncated,
                        disable_web_page_preview=True
                    )
                    logger.info("Telegram message sent successfully (plain text)")
                    return True
                except TelegramError as e2:
                    logger.error(f"Failed to send plain text message: {e2}")
            return False

    def _send_html(self, html_message: str) -> bool:
        """Send HTML message (synchronous wrapper)."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._send_message_async(html_message, ParseMode.HTML))

    def send_message(self, message: str) -> bool:
        """Send a Markdown message, converting to HTML for Telegram."""
        html_message = self._markdown_to_telegram_html(message)
        return self._send_html(html_message)

    def send_update(self, repo_name: str, summary: str) -> bool:
        """Send a repository update notification."""
        header = f"📦 <b>{repo_name}</b> 更新\n\n"
        content = self._markdown_to_telegram_html(summary)
        return self._send_html(header + content)

    def send_digest(self, digest: str, repo_count: int) -> bool:
        """Send a combined digest notification."""
        header = f"📊 <b>GitHub 追踪日报</b> ({repo_count}个项目)\n\n"
        content = self._markdown_to_telegram_html(digest)
        return self._send_html(header + content)

    def send_error(self, error_message: str) -> bool:
        """Send an error notification."""
        escaped = self._escape_html(error_message)
        message = f"⚠️ <b>GitHub追踪助手错误</b>\n\n{escaped}"
        return self._send_html(message)

    def test_connection(self) -> bool:
        """Test the Telegram bot connection."""
        if not self.bot:
            return False

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _test():
            try:
                me = await self.bot.get_me()
                logger.info(f"Telegram bot connected: @{me.username}")
                return True
            except TelegramError as e:
                logger.error(f"Telegram connection test failed: {e}")
                return False

        return loop.run_until_complete(_test())
