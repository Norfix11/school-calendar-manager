from datetime import date, time, datetime, timedelta
from itertools import product
from heapq import heappush, heappop
import math
import numpy as np
from scipy.stats import gamma
from scipy.signal import fftconvolve
from bisect import bisect_left



def estimate_event_duration(est_hours: float, past_hours: list, initial_weight = 2.0,
                           relative_deviation = 0.5, interval_probability = 0.9) -> dict:

    total_weight = initial_weight + len(past_hours)
    expected_hours = (initial_weight * est_hours + math.fsum(past_hours)) / total_weight

    initial_variance = (relative_deviation * est_hours) ** 2
    weighted_variance = initial_weight * (initial_variance + (est_hours - expected_hours) ** 2)
    weighted_variance += math.fsum((hours - expected_hours) ** 2 for hours in past_hours)
    variance = weighted_variance / total_weight

    shape = expected_hours ** 2 / variance
    scale = variance / expected_hours
    distribution = gamma(a=shape, scale=scale)

    tail_probability = (1 - interval_probability) / 2
    lower = float(distribution.ppf(tail_probability))
    upper = float(distribution.ppf(1 - tail_probability))

    return {"expected_hours": expected_hours, "deviation_hours": math.sqrt(variance), "prediction_interval": (lower, upper),
            "interval_probability": interval_probability, "shape": shape, "scale": scale, "distribution": distribution}


def daily_overload_probability(distributions: list, allowance: float,
                               step_hours = 0.1) -> float:
    if not distributions:
        return 0.0
    if allowance == 0:
        return 1.0

    interval_count = math.ceil(allowance / step_hours)
    grid_array = np.linspace(0, allowance, interval_count + 1)

    total_probabilities = np.array([1.0])

    for distribution in distributions:
        cumulative_probabilities = distribution.cdf(grid_array)
        event_probabilities = np.diff(cumulative_probabilities, prepend = 0.0)

        total_probabilities = fftconvolve(total_probabilities, event_probabilities)

        #cutting unnecessary information
        total_probabilities = total_probabilities[:interval_count + 1]
        total_probabilities = np.maximum(total_probabilities, 0.0)

    overload_probability = 1 - float(total_probabilities.sum())
    return max(0.0, min(1.0, overload_probability))


def predict_events(
    events: list,
    forecast_start: date,
    forecast_end: date,
    history_start = None,
    breaks = None,
    date_tolerance = 1,
    minimum_probability = 0.5,
    minimum_fit = 0.6,
    match_weight_function = lambda distance, tolerance: 1 - distance / (tolerance + 1)) -> list:
    
    if not isinstance(date_tolerance, int) or not 0 <= date_tolerance <= 2:
        raise ValueError("date_tolerance must be an integer from zero to two")

    if forecast_end < forecast_start:
        return []


    def is_during_break(date):
        if not breaks:
            return False
        
        return any(start <= date <= end for start, end in breaks)


    clusters_by_subject = {}
    for event in events:
        deadline = event["due_date"]

        if isinstance(deadline, datetime):
            date = deadline.date()
        else: 
            date = deadline

        if event["subject"] not in clusters_by_subject:
            clusters_by_subject[event["subject"]] = {}
        clusters = clusters_by_subject[event["subject"]]

        if date not in clusters:
            clusters[date] = 0
        clusters[date] += 1

    predictions = []
    tolerance = timedelta(days=date_tolerance)

    for subject, clusters in clusters_by_subject.items():

        date_history = [date for date in clusters if date < forecast_start
                    and (history_start is None or date >= history_start)
                    and not is_during_break(date)]
        if not date_history:
            continue
        date_history.sort()

        if history_start:
            earliest_candidate_date = history_start - tolerance
        else:
            earliest_candidate_date = date_history[0] - tolerance


        best_schedule = None
        best_score = None
        
        for period in (7, 14):

            for phase in range(period):
                matched_centers = 0
                unmatched_centers = 0
                matched_events = 0
                matched_weight = 0
                total_shift = 0

                center = earliest_candidate_date + timedelta(days=phase)

                while center - tolerance < forecast_start:

                    if not is_during_break(center):
                        pos = bisect_left(date_history, center)

                        candidates = []
                        if pos > 0:
                            candidates.append(date_history[pos - 1])

                        if pos < len(date_history):
                            candidates.append(date_history[pos])

                        closest_date = min(candidates, key=lambda date: abs((date - center).days))
                        closest_distance = abs((closest_date - center).days)

                        #windows cannot overlap
                        if closest_distance <= date_tolerance:
                            matched_centers += 1
                            matched_events += clusters[closest_date]
                            total_shift += closest_distance
                            matched_weight += match_weight_function(closest_distance, date_tolerance)

                        elif center - tolerance >= earliest_candidate_date + tolerance and center + tolerance < forecast_start:
                            unmatched_centers += 1

                    center += timedelta(days=period)

                unmatched_dates = len(date_history) - matched_centers
                evaluated_centers = matched_centers + unmatched_centers

                if matched_centers < 2:
                    continue

                fit = matched_weight / (evaluated_centers + unmatched_dates)
                score = (fit, matched_centers, -total_shift, -period)

                if not best_score or score > best_score:
                    best_score = score
                    best_schedule = {
                        "period_days": period,
                        "phase_date": earliest_candidate_date + timedelta(days=phase),
                        "fit": fit,
                        "matched_centers": matched_centers,
                        "evaluated_centers": evaluated_centers,
                        "unmatched_dates": unmatched_dates,
                        "matched_events": matched_events,
                    }

        if not best_schedule or best_schedule["fit"] < minimum_fit:
            continue

        matched_centers = best_schedule["matched_centers"]
        evaluated_centers = best_schedule["evaluated_centers"]

        probability = (matched_centers + 1) / (evaluated_centers + 2)
        if probability < minimum_probability:
            continue

        expected_count = best_schedule["matched_events"] / matched_centers

        period = best_schedule["period_days"]
        phase_date = best_schedule["phase_date"]
        periods_to_forecast = math.ceil((forecast_start - phase_date).days / period)
        first_prediction = phase_date + timedelta(days=periods_to_forecast * period)

        for i in range(0, (forecast_end - first_prediction).days + 1, period):
            center = first_prediction + timedelta(days=i)

            if is_during_break(center):
                continue

            deadline_exists = False
            for date in clusters:
                if abs((center - date).days) <= date_tolerance:
                    deadline_exists = True
                    break

            if deadline_exists:
                continue

            predictions.append({"subject": subject,
                                "predicted_deadline": center,
                                "date_window": (center - tolerance, center + tolerance),
                                "occurrence_probability": probability,
                                "expected_event_count": expected_count,
                                "period_days": period,
                                "fit": best_schedule["fit"],
                                "matched_centers": matched_centers,
                                "evaluated_centers": evaluated_centers,
                                "unmatched_dates": best_schedule["unmatched_dates"]})

    return sorted(predictions, key=lambda prediction: (prediction["predicted_deadline"], prediction["subject"]))



def normalize_deadline(event: dict) -> datetime:
    due_date = event["due_date"]

    if isinstance(due_date, datetime):
        return due_date
    
    return datetime.combine(due_date, time.max)


def daily_overload_penalty(hours: float, allowance: float, penalty = lambda x: x ** 2) -> float:
    return penalty(max(0, hours - allowance))


def last_workday(event: dict, cutoff = time(20, 0)) -> date:
    deadline = normalize_deadline(event)
    date = deadline.date()

    if deadline.time() < cutoff:
        return date - timedelta(days=1)

    return date


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
            penalty_cost, date = heappop(daily_offers)

            total_penalty += penalty_cost
            total_ew_cost += date
            assigned_units[date] += 1

            hours = assigned_units[date] / 2
            allowance = allowance_by_day[date]
            heappush(daily_offers, (
                daily_overload_penalty(hours + 0.5, allowance) - daily_overload_penalty(hours, allowance), date
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

    return (total_penalty, total_ew_cost), [tuple(date) for date in plan]


def build_timeline(events: list, start_date: date, hours_by_weekday = (1, 3, 3, 2, 3, 1, 2)) -> dict:
    groups_by_unit = {}
    event_count = 0

    for index, event in enumerate(events):
        last_day = (last_workday(event) - start_date).days
        event_units = math.ceil(event["est_hours"]*2)

        if last_day < 0:
            continue

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
