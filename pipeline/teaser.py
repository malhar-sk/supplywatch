"""
Formats the SupplyWatch markdown report for Substack and Reddit.

Substack → 60-second bite: headline + per-mineral bullets + one action + CTA
Reddit   → full 4-section report for depth, indexability, and AI discoverability
"""

from __future__ import annotations

import re

WAITLIST_URL = "https://supplywatch.netlify.app"

REDDIT_TARGETS = [
    "supplychain",
    "manufacturing",
    "scarcity",
    "commodities",
]


# ── Shared helpers ────────────────────────────────────────────────────────────

def _extract_section(md: str, heading: str) -> str:
    match = re.search(rf"## {heading}\n(.*?)(?=\n## |\Z)", md, re.DOTALL)
    return match.group(1).strip() if match else ""


def _first_sentence(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return parts[0] if parts else text[:200]


def _first_action(md: str) -> str:
    actions = _extract_section(md, "Recommended Actions")
    for line in actions.splitlines():
        m = re.match(r"^\d+\.\s+(.+)", line.strip())
        if m:
            # Strip bold markers but keep the text inside them
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", m.group(1)).strip()
            return _first_sentence(text)
    return ""


def _mineral_bullets(md: str) -> list[str]:
    """
    One tight sentence per mineral from the What Moved section.
    Returns e.g. ["**Gallium (Ga)** — China expanded export controls…", ...]
    """
    what_moved = _extract_section(md, "What Moved")
    # Split on ### mineral headings
    blocks = re.split(r"\n(?=### )", what_moved)
    bullets = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        heading = lines[0].lstrip("#").strip()
        body = " ".join(l.strip() for l in lines[1:] if l.strip())
        sentence = _first_sentence(body)
        if heading and sentence:
            bullets.append(f"**{heading}** — {sentence}")
    return bullets[:3]


# ── Substack (60-second bite) ─────────────────────────────────────────────────

def email_subject(md: str, report_date: str) -> str:
    """~7-word email subject: top mineral + short date."""
    from datetime import datetime
    what_moved = _extract_section(md, "What Moved")
    m = re.search(r"### ([A-Za-z]+)", what_moved)
    mineral = m.group(1) if m else "Critical minerals"
    try:
        short_date = datetime.strptime(report_date, "%Y-%m-%d").strftime("%b %-d")
    except Exception:
        short_date = report_date
    return f"{mineral}: what you may have missed | {short_date}"


def substack_title(md: str, report_date: str) -> str:
    summary = _extract_section(md, "Executive Summary")
    return f"SupplyWatch — {report_date}: {_first_sentence(summary)}"


def substack_subtitle(md: str) -> str:
    summary = _extract_section(md, "Executive Summary")
    sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
    return sentences[1] if len(sentences) > 1 else ""


def substack_body_html(md: str, report_date: str) -> str:
    """
    Tight HTML for Substack's email body.
    Reads in ~60 seconds. Full report lives on Reddit + the waitlist page.
    """
    summary = _extract_section(md, "Executive Summary")
    bullets = _mineral_bullets(md)
    action = _first_action(md)

    lines = [
        f'<p><strong>Week ending {report_date}</strong></p>',
        f'<p>{summary}</p>',
    ]

    if bullets:
        lines.append("<p><strong>What moved this week:</strong></p><ul>")
        for b in bullets:
            b_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", b)
            lines.append(f"<li>{b_html}</li>")
        lines.append("</ul>")

    if action:
        lines.append(
            f"<p><strong>One action for today:</strong><br>{action}</p>"
        )

    lines += [
        f'<p><a href="{WAITLIST_URL}">See what else you may be exposed to →</a></p>',
        "<hr>",
        "<p><em>SupplyWatch flags critical mineral exposure before it hits your BOM. "
        "Free during beta — forward to your procurement team.</em></p>",
    ]

    return "\n".join(lines)


# ── Reddit (full report) ──────────────────────────────────────────────────────

def reddit_title(md: str, report_date: str) -> str:
    summary = _extract_section(md, "Executive Summary")
    return f"SupplyWatch Weekly Brief ({report_date}): {_first_sentence(summary)}"


def reddit_body(md: str, report_date: str, substack_url: str = "") -> str:
    """
    Full 4-section report in Reddit markdown.
    ### subheadings → **bold** for old-Reddit compatibility.
    Named entities, specific numbers, trade routes left intact for indexability.
    """
    link = substack_url or WAITLIST_URL
    reddit_md = re.sub(r"^### (.+)$", r"**\1**", md, flags=re.MULTILINE)
    footer = (
        "\n\n---\n"
        f"*SupplyWatch flags critical mineral exposure before it hits your BOM — free weekly, for procurement teams. "
        f"Track it: {link}*"
    )
    return reddit_md + footer
