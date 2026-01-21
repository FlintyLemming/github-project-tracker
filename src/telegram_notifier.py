"""Telegram notification module."""

import asyncio
import logging
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

    def _escape_markdown(self, text: str) -> str:
        """Escape special characters for MarkdownV2."""
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

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

    def send_message(self, message: str, use_markdown: bool = True) -> bool:
        """Send a message via Telegram (synchronous wrapper)."""
        parse_mode = ParseMode.MARKDOWN if use_markdown else None

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(self._send_message_async(message, parse_mode))

    def send_update(self, repo_name: str, summary: str) -> bool:
        """Send a repository update notification."""
        header = f"📦 *{repo_name}* 更新\n\n"
        message = header + summary
        return self.send_message(message)

    def send_digest(self, digest: str, repo_count: int) -> bool:
        """Send a combined digest notification."""
        header = f"📊 *GitHub 追踪日报* ({repo_count}个项目)\n\n"
        message = header + digest
        return self.send_message(message)

    def send_error(self, error_message: str) -> bool:
        """Send an error notification."""
        message = f"⚠️ *GitHub追踪助手错误*\n\n{error_message}"
        return self.send_message(message)

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
