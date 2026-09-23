import json
import math
from datetime import date, datetime
from pathlib import Path



def prepare_event(event: dict, default_est_hours = 2.0, hours_by_subject = None) -> dict:
    """Normalizes event for further use and returns it. Sets initial
    estimated hours given by hours_by_subject, or default_est_hours if not given."""

    event = event.copy()
    subject = event.get("subject")

    if event.get("est_hours") is None:
        if hours_by_subject is not None and subject in hours_by_subject:
            event["est_hours"] = hours_by_subject[subject]
        else:
            event["est_hours"] = default_est_hours

    event.setdefault("actual_hours", None)
    event.setdefault("completed", False)
    return event


def save_events(combined_events: list, output_file = "data/sample_deadlines.json"):
    """Saves combined_events into a .json output_file directory for history and backup.
    Creates the file if it does not exist, sample_deadlines.json by default."""

    serialized_events = []

    for event in combined_events:
        serialized_events.append(dict(event, due_date = event["due_date"].isoformat()))

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(serialized_events, file, ensure_ascii = False, indent=4)

    print(f"Created {output_file.rsplit('/', 1)[-1]}")


def load_events(default_est_hours = 2.0, hours_by_subject = None, input_file = "data/sample_deadlines.json"):
    """Returns a list of event dictionaries obtained from a .json input_file directory,
    sample_deadlines.json by default. Retains datetime and date information in due_date.
    Sets initial estimated hours given by hours_by_subject, or default_est_hours if not given."""

    combined_events = []

    with open(input_file, "r", encoding="utf-8") as file:
        serialized_events = json.load(file)

    for event in serialized_events:
        if "T" in event["due_date"]:
            event["due_date"] = datetime.fromisoformat(event["due_date"])
        else:
            event["due_date"] = date.fromisoformat(event["due_date"])
        combined_events.append(prepare_event(event, default_est_hours, hours_by_subject))

    return combined_events


def merge_events(saved_events: list, new_events: list, default_est_hours = 2.0, hours_by_subject = None):
    """Returns a list of event dictionaries by merging saved_events and new_events lists.
    Events are differentiated by (subject, title), events with equal (subject, title) keep
    new data, except for keys est_hours, actual_hours, completed which retain historical data.
    Sets initial estimated hours given by hours_by_subject, or default_est_hours if not given."""

    events_by_key = {}
    
    for event in saved_events:
        # Only events matching both subject and title are equal
        key = (event["subject"], event["title"])
        events_by_key[key] = prepare_event(event, default_est_hours, hours_by_subject)

    for event in new_events:
        key = (event["subject"], event["title"])

        # Saved events already contain this event
        if key in events_by_key:
            saved_event = events_by_key[key]
            updated_event = dict(saved_event, **event)  # Merges dictionaries giving event priority

            # Saved event gets priority on history keys
            for field in ("est_hours", "actual_hours", "completed"):
                updated_event[field] = saved_event[field]
            events_by_key[key] = updated_event
        else:
            events_by_key[key] = prepare_event(event, default_est_hours, hours_by_subject)

    return list(events_by_key.values())


def set_estimated_hours(event: dict, hours: float) -> None:
    """Manually overwrites est_hours key for given event with given hours."""

    event["est_hours"] = hours


def complete_event(event: dict, actual_hours: float) -> None:
    """Manually sets actual_hours key to given actual_hours
    and sets completed to True for a given event."""

    event["actual_hours"] = actual_hours
    event["completed"] = True


def reopen_event(event: dict) -> None:
    """Manually sets actual_hours to None
    and sets completed to False for a given event."""

    event["completed"] = False
    event["actual_hours"] = None