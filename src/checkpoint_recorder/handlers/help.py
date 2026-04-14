"""
Help handler — FR-19: Help Command.

Available to any user (registered or not); no state side-effects.
"""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")

_HELP_TEXT = (
    "<b>Available commands</b>\n\n"
    "<b>General</b>\n"
    "/help — Show this command reference\n"
    "/start — Start the bot and register your account\n"
    "/cancel — Cancel the current in-progress action\n\n"
    "<b>Data entry</b>\n"
    "Just send a free-text message to log a value, e.g. <code>weight 82.5</code>\n\n"
    "<b>Metrics</b>\n"
    "/metric_create &lt;name&gt; &lt;daily|weekly&gt; [unit] — Create a metric explicitly\n"
    "/metric_list — List all your metrics with activity status\n"
    "/metric_archive &lt;name&gt; — Archive a metric (pause tracking)\n"
    "/metric_reactivate &lt;name&gt; — Reactivate an archived metric\n"
    "/metric_delete &lt;name&gt; — Permanently delete a metric and all its data\n\n"
    "<b>Alerts</b>\n"
    "/alert_set &lt;metric&gt; &lt;above|below&gt; &lt;threshold&gt; — Set a threshold alert\n"
    "/alert_rearm &lt;alert_id&gt; — Re-arm a triggered alert\n\n"
    "<b>Charts</b>\n"
    "/chart &lt;metric&gt; [days] — Generate a time-series chart for a metric\n\n"
    "<b>Deferred entries</b>\n"
    "/deferred_list — List entries that could not be automatically categorised\n"
    "/deferred_categorize &lt;id&gt; &lt;metric&gt; — Assign a deferred entry to a metric\n\n"
    "<b>Account</b>\n"
    "/account_delete — Request account deletion (72-hour grace period applies)\n"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Return a formatted list of all available commands (FR-19)."""
    await message.answer(_HELP_TEXT)
