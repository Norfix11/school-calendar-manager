import json
import math
from datetime import date, datetime
from pathlib import Path



def prepare_event(event: dict, default_est_hours = 2.0, hours_by_subject = None) -> dict:
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
    serialized_events = []

    for event in combined_events:
        serialized_events.append(dict(event, due_date = event["due_date"].isoformat()))

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(serialized_events, file, ensure_ascii = False, indent=4)

    print(f"Created {output_file.rsplit('/', 1)[-1]}")


def load_events(default_est_hours = 2.0, hours_by_subject = None, input_file = "data/sample_deadlines.json"):
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
    events_by_key = {}
    
    for event in saved_events:
        key = (event["subject"], event["title"])
        events_by_key[key] = prepare_event(event, default_est_hours, hours_by_subject)

    for event in new_events:
        key = (event["subject"], event["title"])
        
        if key in events_by_key:
            saved_event = events_by_key[key]
            updated_event = dict(saved_event, **event)
            
            for field in ("est_hours", "actual_hours", "completed"):
                updated_event[field] = saved_event[field]
            events_by_key[key] = updated_event
        else:
            events_by_key[key] = prepare_event(event, default_est_hours, hours_by_subject)

    return list(events_by_key.values())


def set_estimated_hours(event: dict, hours: float) -> None:
    event["est_hours"] = hours


def complete_event(event: dict, actual_hours: float) -> None:
    event["actual_hours"] = actual_hours
    event["completed"] = True


def reopen_event(event: dict) -> None:
    event["completed"] = False
    event["actual_hours"] = None