from datetime import date, time, datetime, timedelta



def normalize_deadline(event):
    due_date = event["due_date"]

    if isinstance(due_date, datetime):
        return due_date
    
    return datetime.combine(due_date, time.max)



def cumulative_workload(events: list) -> list:
    sorted_events = sorted(events, key = normalize_deadline)

    hours_by_deadline = []
    cumulative = 0

    for event in sorted_events:
        deadline = normalize_deadline(event)
        cumulative += event["est_hours"]

        if not hours_by_deadline or deadline != hours_by_deadline[-1]["deadline"]:
            hours_by_deadline.append({"deadline": deadline})

        hours_by_deadline[-1]["cumulative_hours"] = cumulative

    return hours_by_deadline



def daily_overload_penalty(hours: float, comfortable_hours: float, penalty = lambda x: x ** 2) -> float:
    return penalty(max(0, hours - comfortable_hours))



def last_workday(event, cutoff = time(20, 0)) -> date:
    deadline = normalize_deadline(event)
    day = deadline.date()

    if deadline.time() < cutoff:
        return day - timedelta(days=1)

    return day



def build_timeline(events, start_date, hours_by_weekday):
    pass