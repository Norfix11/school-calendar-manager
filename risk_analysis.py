from datetime import date, time, datetime, timedelta
from itertools import product
from heapq import heappush, heappop
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



def relaxed_remaining_score(current_day: int, state: tuple, groups_by_unit: dict,
                            sorted_units: list, allowance_by_day: list) -> tuple:
    remaining_events = []

    for i, unit in enumerate(sorted_units):
        group = groups_by_unit[unit]

        for event in group[state[i]:]:
            remaining_events.append((event["last_day"], unit))

    remaining_events.sort()

    assigned_units = [0] * len(allowance_by_day)
    daily_offers = []
    iterating_day = current_day

    total_penalty = 0
    total_ew_cost = 0

    for last_day, unit in remaining_events:

        while iterating_day <= last_day:
            allowance = allowance_by_day[iterating_day]
            heappush(daily_offers, (
                daily_overload_penalty(0.5, allowance) - daily_overload_penalty(0, allowance), iterating_day
            ))
            iterating_day += 1

        for _ in range(unit):
            penalty_cost, day = heappop(daily_offers)

            total_penalty += penalty_cost
            total_ew_cost += day
            assigned_units[day] += 1

            hours = assigned_units[day] / 2
            allowance = allowance_by_day[day]
            heappush(daily_offers, (
                daily_overload_penalty(hours + 0.5, allowance) - daily_overload_penalty(hours, allowance), day
            ))

    return total_penalty, total_ew_cost



def greedy_benchmark_score(groups_by_unit: dict, sorted_units: list,
                           allowance_by_day: list) -> tuple[tuple, list]:
    sorted_events = []

    for unit_index, unit in enumerate(sorted_units):
        for event in groups_by_unit[unit]:
            sorted_events.append((event["last_day"], unit, unit_index))

    sorted_events.sort()

    plan = [[0] * len(sorted_units) for _ in range(len(allowance_by_day))] 
    assigned_units = [0] * len(allowance_by_day)
    total_penalty = 0
    total_ew_cost = 0

    for last_day, unit, unit_index in sorted_events:
        best_offer = None

        for current_day in range(last_day + 1):
            allowance = allowance_by_day[current_day]
            penalty = (
                daily_overload_penalty((assigned_units[current_day] + unit) / 2, allowance) 
                - daily_overload_penalty(assigned_units[current_day] / 2, allowance)
            )
            offer = (penalty, current_day)
            
            if best_offer is None or offer < best_offer:
                best_offer = offer

        penalty, chosen_day = best_offer
        assigned_units[chosen_day] += unit
        total_penalty += penalty
        total_ew_cost += chosen_day * unit
        plan[chosen_day][unit_index] += 1

    return (total_penalty, total_ew_cost), [tuple(day) for day in plan]



def build_timeline(events: list, start_date: date, hours_by_weekday = (1, 3, 3, 2, 3, 1, 2)) -> dict:
    groups_by_unit = {}
    event_count = 0

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
        event_count += 1

    if not groups_by_unit:
        return {}
    
    sorted_units = sorted(groups_by_unit)
    for group in groups_by_unit.values():
        group.sort(key=lambda event: event["last_day"])

    last_day_index = max(group[-1]["last_day"] for group in groups_by_unit.values())
    allowance_by_day = []

    for current_day in range(last_day_index + 1):
        planning_date = start_date + timedelta(days=current_day)
        allowance_by_day.append(hours_by_weekday[planning_date.weekday()])


    best_score, best_plan = greedy_benchmark_score(groups_by_unit, sorted_units, allowance_by_day)
    best_seen = {}
    current_plan = []

    def state_space_DFS(current_day: int, remaining_events: int, state: tuple, score: tuple) -> None:
        nonlocal best_score, best_plan

        if (current_day, state) not in best_seen or score < best_seen[(current_day, state)]:
            best_seen[(current_day, state)] = score
        else:
            return
        
        if remaining_events == 0:
            if score < best_score:
                best_score = score
                best_plan = current_plan.copy()
            return

        relaxed_penalty, relaxed_ew_cost = relaxed_remaining_score(current_day, state, groups_by_unit, sorted_units, allowance_by_day)
        relaxed_score = (score[0] + relaxed_penalty, score[1] + relaxed_ew_cost)

        if relaxed_score >= best_score:
            return


        new_by_unit = []

        for i, unit in enumerate(sorted_units):
            group = groups_by_unit[unit]
            required = sum(event["last_day"] <= current_day for event in group)

            min_new = max(0, required - state[i])
            max_new = len(group) - state[i]
            new_by_unit.append(range(min_new, max_new + 1))

        for allocation in product(*new_by_unit):
            units_today = 0
            events_today = 0

            for i, count in enumerate(allocation):
                events_today += count
                units_today += count * sorted_units[i]

            total_penalty = score[0] + daily_overload_penalty(units_today/2, allowance_by_day[current_day])
            total_ew_cost = score[1] + current_day*units_today
            new_score = (total_penalty, total_ew_cost)
            new_state = tuple(state[i] + allocation[i] for i in range(len(sorted_units)))

            current_plan.append(allocation)
            state_space_DFS(current_day + 1, remaining_events - events_today, new_state, new_score)
            current_plan.pop()


    state_space_DFS(0, event_count, (0,) * len(sorted_units), (0, 0))


    timeline = {}
    assigned = [0] * len(sorted_units)

    for current_day, allocation in enumerate(best_plan):
        events_today = []

        for i, unit in enumerate(sorted_units):
            group = groups_by_unit[unit]
            start = assigned[i]
            end = start + allocation[i]

            for event in group[start:end]:
                events_today.append(events[event["event_index"]])

            assigned[i] = end

        planning_date = start_date + timedelta(days=current_day)
        timeline[planning_date] = events_today

    return timeline

    

if __name__ == "__main__":
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

    print(build_timeline([{"title": "Algebra", "est_hours": 2,
            "due_date": datetime(2026, 9, 19, 23, 55)}], date(2026, 9, 16)))
