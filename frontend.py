"""Local web interface using the existing analysis and storage functions."""

from __future__ import annotations

import copy
import json
import math
import secrets
import sys
import tempfile
import threading
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from calendar_export import build_backup_ics, sync_to_apple_calendar
from event_storage import complete_event, load_events, merge_events, reopen_event, save_events
from risk_analysis import analyze_events, last_workday


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DEMO_START = date(2026, 9, 24)
DEMOS = {
    "demo_01_learning.json": "Learning & weekly recurrence",
    "demo_02_deadline_crunch.json": "Deadline crunch",
    "demo_03_mixed_patterns.json": "Mixed patterns & a holiday",
    "demo_04_large_benchmark.json": "Large benchmark · 396 tasks",
}


def positive_number(value: object, label: str, allow_zero: bool = False) -> float:
    """Validates a numeric input before passing it to the existing functions."""
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number.") from error
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        raise ValueError(f"{label} must be finite and {'nonnegative' if allow_zero else 'positive'}.")
    return number


def parse_deadline(value: str) -> date | datetime:
    """Parses a date or local datetime without a timezone offset."""
    if not isinstance(value, str):
        raise ValueError("A deadline must be a date or a date and time.")
    result = datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)
    if isinstance(result, datetime) and result.tzinfo is not None:
        raise ValueError("Use a local deadline without a timezone offset.")
    return result


def validate_events(events: list) -> None:
    """Validates imported events before replacing the current workspace."""
    keys = set()
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Each task must be an object.")
        for field in ("subject", "title"):
            if not isinstance(event.get(field), str) or not event[field].strip():
                raise ValueError(f"Each task needs a nonempty {field}.")
        key = (event["subject"], event["title"])
        if key in keys:
            raise ValueError(f"Duplicate task in the same subject: {event['title']}")
        keys.add(key)
        parse_deadline(event["due_date"].isoformat())
        positive_number(event["est_hours"], "Estimated hours")
        if not isinstance(event.get("completed"), bool):
            raise ValueError("Completed must be true or false.")
        if event["completed"]:
            positive_number(event.get("actual_hours"), "Actual hours", allow_zero=True)
        if not isinstance(event.get("description", ""), str):
            raise ValueError("Task description must be text.")


def public_events(events: list) -> list:
    """Returns event fields that can be sent to the browser as JSON."""
    return [
        {
            "id": i,
            "title": event["title"],
            "subject": event["subject"],
            "due_date": event["due_date"].isoformat(),
            "est_hours": event["est_hours"],
            "actual_hours": event.get("actual_hours"),
            "completed": event.get("completed", False),
            "description": event.get("description", ""),
        }
        for i, event in enumerate(events)
    ]


def public_report(report: dict, events: list, start: date, allowances: tuple) -> dict:
    """Converts analysis results into display data without distribution objects."""
    days = []
    for day, tasks in report["timeline"].items():
        if tasks:
            days.append({
                "day": day.isoformat(),
                "allowance": allowances[day.weekday()],
                "risk": report["daily_risk"][day],
                "expected_hours": sum(task["est_hours"] for task in tasks),
                "planned_hours": sum(math.ceil(task["est_hours"] * 2) / 2 for task in tasks),
                "tasks": public_events(tasks),
            })
    predictions = []
    for prediction in report["predictions"]:
        predictions.append({
            "subject": prediction["subject"],
            "deadline": prediction["predicted_deadline"].isoformat(),
            "probability": prediction["occurrence_probability"],
            "count": prediction["expected_event_count"],
            "hours_per_task": prediction["expected_hours"],
            "period": prediction["period_days"],
            "window": [day.isoformat() for day in prediction["date_window"]],
        })
    weeks = [
        {key: value.isoformat() if isinstance(value, date) else value for key, value in week.items()}
        for week in report["weekly_risk"].values()
    ]
    overdue = [e for e in events if not e["completed"] and last_workday(e) < start]
    return {"days": days, "weeks": weeks, "predictions": predictions, "overdue": public_events(overdue)}


class Application:
    """Keeps working data in memory and runs analysis outside HTTP requests."""

    def __init__(self, data_dir: Path = DATA) -> None:
        """Initializes an empty workspace. Files are opened when requested."""
        self.data_dir = data_dir.resolve()
        self.lock = threading.RLock()
        self.events = []
        self.filename = None
        self.dirty = False
        self.revision = 0
        self.job = {"status": "idle"}
        self.token = secrets.token_urlsafe(32)

    def file_path(self, name: str) -> Path:
        """Restricts file access to JSON files directly inside the data folder."""
        if not isinstance(name, str) or Path(name).name != name or not name.endswith(".json"):
            raise ValueError("Use a JSON filename without a folder path.")
        path = (self.data_dir / name).resolve()
        if path.parent != self.data_dir:
            raise ValueError("The file must be inside the data folder.")
        return path

    def state(self) -> dict:
        """Returns current tasks, file information and available datasets."""
        with self.lock:
            return {
                "files": [{"name": p.name, "label": DEMOS.get(p.name, p.stem.replace("_", " "))}
                          for p in sorted(self.data_dir.glob("*.json"))],
                "filename": self.filename,
                "dirty": self.dirty,
                "events": public_events(self.events),
                "revision": self.revision,
                "today": date.today().isoformat(),
                "apple_calendar_available": sys.platform == "darwin",
            }

    def open_file(self, name: str, merge: bool = False) -> dict:
        """Opens a dataset or merges it into the workspace without saving changes."""
        events = load_events(input_file=str(self.file_path(name)))
        validate_events(events)
        with self.lock:
            self.events = merge_events(self.events, events) if merge else events
            self.filename = self.filename if merge else name
            self.dirty = merge
            self.revision += 1
            result = self.state()
            if not merge and name in DEMOS:
                result["demo_start"] = DEMO_START.isoformat()
                result["demo_breaks"] = "2026-10-05,2026-10-11" if name == "demo_03_mixed_patterns.json" else ""
            return result

    def update_task(self, payload: dict) -> dict:
        """Updates a task using the existing completion and reopening functions."""
        with self.lock:
            index = payload.get("id")
            if index is not None and (type(index) is not int or not 0 <= index < len(self.events)):
                raise ValueError("Select a valid task.")
            event = self.events[index].copy() if index is not None else {}
            event.update({
                "title": payload["title"].strip(),
                "subject": payload["subject"].strip(),
                "due_date": parse_deadline(payload["due_date"]),
                "description": payload.get("description", ""),
                "est_hours": positive_number(payload["est_hours"], "Estimated hours"),
            })
            if payload.get("completed"):
                complete_event(event, positive_number(payload.get("actual_hours"), "Actual hours", True))
            else:
                reopen_event(event)
            updated = self.events.copy()
            if index is None:
                updated.append(event)
            else:
                updated[index] = event
            validate_events(updated)
            self.events = updated
            self.dirty = True
            self.revision += 1
            return self.state()

    def save(self, name: str) -> dict:
        """Saves the workspace while keeping demo datasets as reusable templates."""
        path = self.file_path(name)
        if name in DEMOS:
            raise ValueError("Save a copy under a different name to keep the demo reusable.")
        with self.lock:
            validate_events(self.events)
            save_events(self.events, str(path))
            self.filename = name
            self.dirty = False
            return self.state()

    def analyze(self, payload: dict) -> dict:
        """Analyzes a snapshot of the workspace. Later edits invalidate its results."""
        start = date.fromisoformat(payload["start"])
        end = date.fromisoformat(payload["end"])
        if end < start:
            raise ValueError("Forecast end must be on or after the planning start.")
        allowances = tuple(positive_number(h, "Weekday allowance", True) for h in payload["allowances"])
        if len(allowances) != 7:
            raise ValueError("Enter all seven weekday allowances.")
        breaks = []
        for line in payload.get("breaks", "").splitlines():
            if line.strip():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) != 2:
                    raise ValueError("Write each break as YYYY-MM-DD,YYYY-MM-DD.")
                first, last = map(date.fromisoformat, parts)
                if first > last:
                    raise ValueError("A break cannot end before it starts.")
                breaks.append((first, last))
        with self.lock:
            if self.job["status"] == "running":
                raise ValueError("An analysis is already running. Please wait for it to finish.")
            events = copy.deepcopy(self.events)
            validate_events(events)
            revision = self.revision
            self.job = {"status": "running", "revision": revision}

        def work() -> None:
            """Runs analysis in the background and returns serializable results."""
            try:
                result = analyze_events(events, start, allowances, forecast_end=end, breaks=breaks)
                result = public_report(result, events, start, allowances)
                json.dumps(result, allow_nan=False)
                job = {"status": "done", "revision": revision, "report": result}
            except Exception as error:
                job = {"status": "error", "revision": revision, "error": f"{type(error).__name__}: {error}"}
            with self.lock:
                self.job = job

        threading.Thread(target=work, daemon=True).start()
        return {"status": "running"}

    def export(self, unfinished_only: bool) -> bytes:
        """Creates a temporary ICS export without overwriting the project calendar."""
        with self.lock:
            events = copy.deepcopy(self.events)
        if unfinished_only:
            events = [event for event in events if not event["completed"]]
        for event in events:
            event.setdefault("description", "")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "deadlines.ics"
            build_backup_ics(events, str(path))
            return path.read_bytes()

    def sync_calendar(self, unfinished_only: bool, confirmed: bool) -> dict:
        """Runs the existing Apple Calendar replacement only after explicit confirmation."""
        if sys.platform != "darwin":
            raise ValueError("Direct Apple Calendar sync requires running this application on macOS. Use ICS export here.")
        if confirmed is not True:
            raise ValueError("Confirm replacement of the Homework Deadlines calendar first.")
        with self.lock:
            if self.job["status"] == "running":
                raise ValueError("Wait for the current operation to finish.")
            events = copy.deepcopy(self.events)
            if unfinished_only:
                events = [event for event in events if not event["completed"]]
            validate_events(events)
            for event in events:
                event.setdefault("description", "")
                # The existing exporter inserts these fields directly into AppleScript strings.
                if any(character in event[field] for field in ("title", "description")
                       for character in ('"', "\\", "\n", "\r")):
                    raise ValueError("The current Apple exporter cannot handle quotes, backslashes or line breaks in titles or notes. Use ICS export for these tasks.")
            self.job = {"status": "running", "kind": "sync"}

        def work() -> None:
            """Reports completion or failure without blocking other browser requests."""
            try:
                sync_to_apple_calendar(events)
                job = {"status": "done", "kind": "sync", "count": len(events)}
            except Exception as error:
                job = {
                    "status": "error",
                    "kind": "sync",
                    "error": f"Apple Calendar sync failed; the calendar may be partially updated. {type(error).__name__}: {error}",
                }
            with self.lock:
                self.job = job

        threading.Thread(target=work, daemon=True).start()
        return {"status": "running"}

    def refresh(self, sources: dict) -> dict:
        """Fetches selected sources in the background and merges their events into memory."""
        selected = {name: url.strip() for name, url in sources.items() if url.strip()}
        if not selected or any(name not in ("nt", "rr", "owl", "recodex") for name in selected):
            raise ValueError("Select at least one supported source.")
        if any(urlsplit(url).scheme not in ("http", "https") for url in selected.values()):
            raise ValueError("Source addresses must start with http:// or https://.")
        with self.lock:
            if self.job["status"] == "running":
                raise ValueError("Wait for the current analysis or refresh to finish.")
            self.job = {"status": "running", "kind": "refresh"}

        def work() -> None:
            """Keeps fetched events separate until all selected sources have succeeded."""
            from deadline_sources import (
                extract_deadlines_nt, extract_deadlines_owl,
                extract_deadlines_recodex, extract_deadlines_rr, get_html,
            )

            try:
                events = []
                for name, url in selected.items():
                    if name in ("nt", "rr"):
                        html, address = get_html(url)
                        extractor = extract_deadlines_nt if name == "nt" else extract_deadlines_rr
                        events.extend(extractor(html, address))
                    elif name == "owl":
                        events.extend(extract_deadlines_owl(url))
                    else:
                        events.extend(extract_deadlines_recodex(url))
                with self.lock:
                    updated = merge_events(self.events, events)
                    validate_events(updated)
                    self.events = updated
                    self.dirty = True
                    self.revision += 1
                    self.job = {"status": "done", "kind": "refresh", "count": len(events)}
            except Exception as error:
                with self.lock:
                    self.job = {"status": "error", "error": f"{type(error).__name__}: {error}"}

        threading.Thread(target=work, daemon=True).start()
        return {"status": "running"}


def make_handler(app: Application) -> type[BaseHTTPRequestHandler]:
    """Creates request handlers for the local application server."""

    class Handler(BaseHTTPRequestHandler):
        """Serves the interface and its JSON API."""

        def log_message(self, format: str, *args: object) -> None:
            """Suppresses routine access logs from repeated status requests."""
            pass

        def send_content(self, body: bytes, content_type: str, status: int = 200) -> None:
            """Sends a response without browser caching."""
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, value: dict, status: int = 200) -> None:
            """Sends a JSON response or an error message."""
            self.send_content(json.dumps(value, allow_nan=False).encode(), "application/json", status)

        def local_request(self) -> bool:
            """Rejects requests using a different host address."""
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self) -> None:
            """Serves the interface. Data requests require a token in a POST request."""
            if not self.local_request():
                self.send_json({"error": "Local access only."}, 403)
                return
            if urlsplit(self.path).path != "/":
                self.send_json({"error": "Not found."}, 404)
                return
            html = (ROOT / "frontend.html").read_text(encoding="utf-8")
            self.send_content(html.replace("__API_TOKEN__", app.token).encode(), "text/html; charset=utf-8")

        def do_POST(self) -> None:
            """Handles an action and reports errors without stopping the server."""
            if not self.local_request() or self.headers.get("X-App-Token") != app.token:
                self.send_json({"error": "Reload the local application page."}, 403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 <= size <= 1_000_000:
                    raise ValueError("Request is too large.")
                payload = json.loads(self.rfile.read(size) or b"{}")
                route = urlsplit(self.path).path
                if route == "/api/state":
                    result = app.state()
                elif route == "/api/open":
                    result = app.open_file(payload["name"], payload.get("merge", False))
                elif route == "/api/task":
                    result = app.update_task(payload)
                elif route == "/api/save":
                    result = app.save(payload["name"])
                elif route == "/api/analyze":
                    result = app.analyze(payload)
                elif route == "/api/refresh":
                    result = app.refresh(payload)
                elif route == "/api/sync":
                    result = app.sync_calendar(
                        payload.get("unfinished_only", True), payload.get("confirmed", False)
                    )
                elif route == "/api/result":
                    with app.lock:
                        result = app.job.copy()
                elif route == "/api/export":
                    self.send_content(app.export(payload.get("unfinished_only", True)), "text/calendar")
                    return
                else:
                    self.send_json({"error": "Not found."}, 404)
                    return
                self.send_json(result)
            except Exception as error:
                self.send_json({"error": f"{type(error).__name__}: {error}"}, 400)

    return Handler


def launch(port: int = 0, open_browser: bool = True) -> None:
    """Starts the local interface and keeps serving until Ctrl+C."""
    app = Application()
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"School Calendar Manager: {url}\nKeep this terminal open. Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
