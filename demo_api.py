"""
SupplyWatch Demo API — runs the full pipeline on demand and emails the brief.

POST /demo  {"email": "you@example.com"}
  → kicks off background task (scorer + LLM + email)
  → returns immediately with estimated wait time

GET /health → {"status": "ok"}
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import re
from pydantic import BaseModel

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="SupplyWatch Demo API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://supplywatch.netlify.app", "http://localhost"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class DemoRequest(BaseModel):
    email: str

    def valid_email(self) -> bool:
        return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/demo")
async def run_demo(payload: DemoRequest, background_tasks: BackgroundTasks):
    if not payload.valid_email():
        return {"status": "error", "message": "Invalid email address."}
    background_tasks.add_task(_pipeline, payload.email)
    return {
        "status": "processing",
        "message": f"Checking what {payload.email} may already be exposed to — results in ~60 seconds.",
    }


def _pipeline(email: str):
    try:
        log.info(f"[demo] Starting pipeline for {email}")

        from live_scorer import build_scorer_output
        minerals = build_scorer_output()
        log.info(f"[demo] Signals fetched: {[m['mineral'] for m in minerals]}")

        from reports.generator import ReportGenerator
        from datetime import date
        gen = ReportGenerator()
        markdown, eval_score = gen.generate_markdown(minerals)
        paths = gen.write_outputs(markdown, eval_score)
        log.info(f"[demo] Report generated: {eval_score}/20")

        md_text = paths["md"].read_text()
        report_date = paths["md"].stem

        from pipeline.email_sender import EmailSender
        EmailSender().send(md_text, report_date, to=email)
        log.info(f"[demo] Email sent to {email}")

    except Exception as e:
        log.error(f"[demo] Pipeline failed for {email}: {e}")
