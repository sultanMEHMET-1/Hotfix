"""Readable console output without changing telemetry or workflow data."""

import logging
import json
import os
import re

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PICTOGRAPHS = re.compile(
    "[\U0001F000-\U0001FAFF\u2300-\u23FF\u25A0-\u27BF\u2B00-\u2BFF"
    "\uFE0E\uFE0F\u200D\u20E3]"
)
COLORS = {"FAST": "cyan", "BROKEN": "yellow", "AGENT": "blue",
          "PATCH": "magenta", "VERIFY": "cyan", "CANARY": "cyan",
          "HEALED": "green", "FAILED": "red", "ROLLBACK": "yellow",
          "COOLDOWN": "yellow"}


def clean(text):
    return PICTOGRAPHS.sub("", ANSI.sub("", str(text))).replace("\u2014", "-").strip()


class TerminalHandler(RichHandler):
    def emit(self, record):
        message = clean(record.getMessage())
        if not message:
            return
        if self.level > logging.DEBUG and record.levelno < logging.WARNING:
            if record.name.startswith(("httpx", "httpcore", "bubus", "cdp_use", "google_genai", "google.genai")):
                return
            if record.name.startswith("browser_use") and not re.match(
                r"(?:Step \d+|Typed\b|Clicked\b|Navigated\b|Task completed successfully)", message
            ):
                return
        super().emit(record)

    def render_message(self, record, message):
        phase = getattr(record, "phase", None)
        if not phase:
            phase = "AGENT" if record.name.startswith("browser_use") else record.name.rsplit(".", 1)[-1]
        phase = clean(phase).upper()
        output = Text(f"{phase:<10} ", style=COLORS.get(phase, "dim"))
        output.append(clean(message))
        return output


def configure_logging():
    """Install once, before importing Browser Use, and preserve non-console handlers."""
    level = logging.DEBUG if os.getenv("MENDER_LOG_LEVEL", "INFO").upper() == "DEBUG" else logging.INFO
    root = logging.getLogger()
    handler = next((item for item in root.handlers if isinstance(item, TerminalHandler)), None)
    if handler is None:
        handler = TerminalHandler(
            console=Console(stderr=True, emoji=False, markup=False, highlight=False),
            show_path=False, markup=False, rich_tracebacks=False, log_time_format="%H:%M:%S",
        )
        root.addHandler(handler)
    handler.setLevel(level)
    root.setLevel(level)
    # Browser Use skips its own setup when the root already has a handler.
    # Also normalize console handlers if a dependency was imported earlier.
    loggers = [root, *[logger for name, logger in logging.root.manager.loggerDict.items()
                      if name.startswith(("browser_use", "bubus", "cdp_use", "uvicorn"))
                      and isinstance(logger, logging.Logger)]]
    for logger in loggers:
        for existing in list(logger.handlers):
            if type(existing) is logging.StreamHandler:
                logger.removeHandler(existing)
        if logger is not root:
            logger.propagate = True
    return handler.console


def show_result(payload, version, console=None):
    console = console or configure_logging()
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    rows = [("Status", payload["status"].upper()),
            ("Latency", f"{payload['execution_time_ms'] / 1000:.2f} s"),
            ("Selector version", str(version))]
    diff = payload.get("diff")
    if diff:
        rows.extend([("Old selector", diff["old_selector"]), ("New selector", diff["new_selector"])])
    if payload.get("error"):
        rows.append(("Error", payload["error"]["message"]))
    if payload.get("data"):
        rows.append(("Output", json.dumps(payload["data"], ensure_ascii=False, sort_keys=True)))
    rows.append(("Trace", payload["trace_id"]))
    for label, value in rows:
        table.add_row(Text(label), Text(clean(value)))
    success = payload["status"] != "failed"
    console.print(Panel(table, title="Recovery verified" if success else "Recovery failed",
                        border_style="green" if success else "red", expand=False))
