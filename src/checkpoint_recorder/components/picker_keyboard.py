"""
Inline keyboard builder for the smart-metric-picker (FR22, FR24, FR25, FR27).

callback_data encoding (ADR-013, must fit within Telegram's 64-byte limit):
  pick:<metric_id_uuid>   — user selected an existing metric (41 bytes max)
  create:<typed_name>     — user confirmed creation of a new metric (≤64 bytes;
                            typed_name truncated at 57 chars if needed)
  showfits                — expand overflow to full match list (8 bytes)
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from checkpoint_recorder.db.models import Metric

_OVERFLOW_THRESHOLD = 4
_CREATE_PREFIX = "create:"
_CREATE_NAME_MAX = 64 - len(_CREATE_PREFIX)  # 57 chars


def build_picker_keyboard(
    metrics: list[Metric],
    overflow_threshold: int = _OVERFLOW_THRESHOLD,
) -> InlineKeyboardMarkup:
    """
    Build a metric-selection keyboard from an ordered metric list (FR22, FR24, FR25).

    If len(metrics) > overflow_threshold: show first overflow_threshold buttons
    plus a "Show all fits" button.
    Otherwise: show all metrics.
    Buttons are arranged in rows of 2.
    """
    display = metrics[:overflow_threshold] if len(metrics) > overflow_threshold else metrics
    buttons = [
        InlineKeyboardButton(text=m.name, callback_data=f"pick:{m.id}")
        for m in display
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    if len(metrics) > overflow_threshold:
        rows.append([
            InlineKeyboardButton(
                text=f"Show all fits ({len(metrics)})",
                callback_data="showfits",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_all_fits_keyboard(metrics: list[Metric]) -> InlineKeyboardMarkup:
    """
    Build a keyboard showing every metric in the list (FR25 overflow expansion).
    Replaces the overflow keyboard in-place when user taps "Show all fits".
    """
    buttons = [
        InlineKeyboardButton(text=m.name, callback_data=f"pick:{m.id}")
        for m in metrics
    ]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_create_keyboard(typed_name: str) -> InlineKeyboardMarkup:
    """
    Build a single-button keyboard for zero-match logging flow (FR27).
    typed_name is truncated to fit the 64-byte callback_data limit.
    The full name is preserved in ConversationState.state_data, not in callback_data.
    """
    safe_name = typed_name[:_CREATE_NAME_MAX]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f'Create "{typed_name[:30]}{"…" if len(typed_name) > 30 else ""}"',
            callback_data=f"{_CREATE_PREFIX}{safe_name}",
        )
    ]])


def build_zero_match_message(command_context: str) -> str:
    """Plain-text response for zero-match management commands (FR28)."""
    return "No matching metrics found."
