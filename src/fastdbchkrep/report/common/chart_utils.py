"""Common helpers for time-series charts in reports.

This module centralizes time label normalization and x-axis rendering so that
MySQL and Oracle editable HTML charts have consistent, readable time axes.
"""
from __future__ import annotations

import math
import re
from typing import List, Tuple, Optional


def normalize_time_label(s: str) -> str:
    """Normalize various time strings to HH:MM.

    Supports SAR-like outputs such as:
    - '08时10分01秒' or '08时10分' -> '08:10'
    - '08:10:01' or '08:10' -> '08:10'
    - '08:10:01 AM' -> '08:10'
    Returns original string if no HH:MM can be detected.
    """
    if not s:
        return s
    text = str(s).strip()

    # Chinese patterns like 08时10分01秒 / 08时10分
    text = re.sub(r"\b(\d{1,2})时(\d{2})分(\d{2})秒\b", r"\1:\2", text)
    text = re.sub(r"\b(\d{1,2})时(\d{2})分\b", r"\1:\2", text)

    # Remove AM/PM and localized markers that don't affect minute-level display
    text = re.sub(r"\b(AM|PM|am|pm|上午|下午)\b", "", text)

    # Standard HH:MM[:SS] patterns
    m = re.search(r"\b(\d{1,2}):(\d{2})", text)
    if m:
        hh = int(m.group(1))
        mm = m.group(2)
        return f"{hh:02d}:{mm}"
    return text


def apply_time_axis(ax, times: List[str], max_labels: Optional[int] = 12, rotation: int = 45, fontsize: int = 10) -> Tuple[List[int], int]:
    """Apply readable, evenly-spaced ticks for a categorical time axis.

    - Converts the time labels to positional indices for plotting.
    - Chooses a step to keep at most `max_labels` ticks visible.
    - Sets rotated, right-aligned labels to avoid overlap.

    Returns (x_indices, step).
    """
    n = len(times)
    x = list(range(n))
    if n == 0:
        return x, 1
    # Show all labels if max_labels is None or larger than the number of points
    if max_labels is None or max_labels >= n:
        step = 1
    else:
        step = max(1, math.ceil(n / float(max_labels)))
    show_idx = list(range(0, n, step))
    ax.set_xticks(show_idx)
    ax.set_xticklabels([times[i] for i in show_idx], rotation=rotation, ha="right", fontsize=fontsize)
    return x, step


def align_twinx_xlim(ax_left, ax_right) -> None:
    """Keep twinx() right axis aligned with the left axis x-limits."""
    try:
        ax_right.set_xlim(ax_left.get_xlim())
    except Exception:
        pass
