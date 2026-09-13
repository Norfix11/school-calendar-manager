import json
from datetime import date, datetime


def save_events(combined_events: list, output_file = "data/sample_deadlines.json"):
    serialized_events = []

    for event in combined_events:
        serialized_events.append(dict(event, due_date = event["due_date"].isoformat()))

    with open(output_file, "w") as file:
        json.dump(serialized_events, file, ensure_ascii = False, indent=4)

    print(f"Created {output_file.rsplit('/', 1)[-1]}")


def load_events(input_file = "data/sample_deadlines.json"):
    combined_events = []

    with open(input_file, "r") as file:
        serialized_events = json.load(file)

    for event in serialized_events:
        if "T" in event["due_date"]:
            combined_events.append(dict(event, due_date = datetime.fromisoformat(event["due_date"])))
        else:
            combined_events.append(dict(event, due_date = date.fromisoformat(event["due_date"])))

    return combined_events


def merge_events(saved_events: list, new_events: list):
    events_by_title = {event["title"]: event for event in saved_events + new_events}

    return list(events_by_title.values())