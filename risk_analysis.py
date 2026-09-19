from datetime import date, time, datetime, timedelta
import math



def normalize_deadline(event: dict) -> datetime:
    due_date = event["due_date"]

    if isinstance(due_date, datetime):
        return due_date
    
    return datetime.combine(due_date, time.max)



def daily_overload_penalty(hours: float, comfortable_hours: float, penalty = lambda x: x ** 2) -> float:
    return penalty(max(0, hours - comfortable_hours))



def last_workday(event: dict, cutoff = time(20, 0)) -> date:
    deadline = normalize_deadline(event)
    day = deadline.date()

    if deadline.time() < cutoff:
        return day - timedelta(days=1)

    return day



def build_timeline(events: list, start_date: date, hours_by_weekday = (2, 2, 2, 2, 2, 2, 2)):
    groups_by_unit = {}

    for index, event in enumerate(events):
        last_day = (last_workday(event) - start_date).days
        event_units = math.ceil(event["est_hours"]*2)

        if last_day < 0:
            continue

        if event_units > 16:
            raise ValueError("Event duration longer than 8 hours")

        if event_units not in groups_by_unit:
            groups_by_unit[event_units] = []

        groups_by_unit[event_units].append({"event_index": index, "last_day": last_day})

    sorted_units = sorted(groups_by_unit)
    for group in groups_by_unit.values():
        group.sort(key=lambda task: task["last_day"])

    states = {(0,) * len(sorted_units): (0, 0)}
    active_range = max(group[-1]["last_day"] for group in groups_by_unit.values())
    backtrack = {}

    for current_day in range(active_range + 1):
        next_states = {}

        for state, score in states.items():
            pass
    






print(build_timeline([
    {"title": "Algebra", "est_hours": 2,
     "due_date": datetime(2026, 9, 19, 23, 55)},
    {"title": "Analysis", "est_hours": 1,
     "due_date": date(2026, 9, 18)},
    {"title": "Geometry", "est_hours": 2,
     "due_date": datetime(2026, 9, 17, 10, 0)},
    {"title": "Combinatorics", "est_hours": 1.2,
     "due_date": date(2026, 9, 20)},
], date(2026, 9, 16)))