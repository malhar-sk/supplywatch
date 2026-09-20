"""Telegram push — designed, deliberately deferred this semester.

The report lists an "optional Telegram morning push" as part of the
delivery layer. No test is claimed for it in Chapter 3.2, and a live bot
integration (token management, webhook reliability) is pure integration
risk with no bearing on this semester's non-negotiables. Rather than
silently omit it, this stub makes the deferred integration point explicit
and logged, so it is honestly "designed but deferred," not quietly absent.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def send_telegram_push(message: str) -> None:
    """Would-send stub. Logs what a real integration would push and returns.

    Swapping this for a real python-telegram-bot call is the entire
    integration surface for the Final Year increment — this function's
    signature is the seam that call would slot into.
    """
    log.info("[telegram-stub] would send: %s", message)
