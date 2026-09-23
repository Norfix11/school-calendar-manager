from datetime import date, time, datetime, timedelta
from itertools import product
from heapq import heappush, heappop
import math
import numpy as np
from scipy.stats import gamma
from scipy.signal import fftconvolve
from bisect import bisect_left



def analyze_events(events: list, start_date: date, hours_by_weekday = (1, 3, 3, 2, 3, 1, 2),
                   forecast_end = None, history_start = None, breaks = None,
                   est_hours_override = None, daily_step_hours = 0.1, weekly_step_hours = 0.25) -> dict:
    hours_by_subject = {}
    unfinished_events = []

    for event in events:
        if event.get("completed_at") is not None:
            subject = event["subject"]

            if subject not in hours_by_subject:
                hours_by_subject[subject] = []
            hours_by_subject[subject].append(event["actual_hours"])

        else:
            unfinished_events.append(event)

    planning_events = []
    for event in unfinished_events:

        if event["subject"] in hours_by_subject:
            past_hours = hours_by_subject[event["subject"]]
        else:
            past_hours = []

        estimate = estimate_event_duration(event["est_hours"], past_hours)

        planning_event = event.copy()
        planning_event["est_hours"] = estimate["expected_hours"]
        planning_event["distribution"] = estimate["distribution"]

        planning_events.append(planning_event)

    timeline = build_timeline(planning_events, start_date, hours_by_weekday)

    daily_risk = {}
    for date, assigned_events in timeline.items():
        distributions = []

        for event in assigned_events:
            distributions.append(event["distribution"])

        allowance = hours_by_weekday[date.weekday()]
        daily_risk[date] = daily_overload_probability(distributions, allowance, daily_step_hours)


    predictions = []
    weekly_risk = {}
    if forecast_end is not None:

        predictions = predict_events(events, start_date, forecast_end, history_start, breaks)
        distribution_by_subject = {}

        for prediction in predictions:
            subject = prediction["subject"]

            if subject not in distribution_by_subject:

                if est_hours_override is not None and subject in est_hours_override:
                    est_hours = est_hours_override[subject]
                else:
                    total_est_hours = 0
                    count = 0
                    for event in events:
                        if event["subject"] == subject and event.get("est_hours") is not None:
                            total_est_hours += event["est_hours"]
                            count += 1
                    if count == 0:
                        raise ValueError(f"No initial duration estimate for subject: {subject}")
                    
                    est_hours = total_est_hours / count

                past_hours = hours_by_subject.get(subject, [])
                estimate = estimate_event_duration(est_hours, past_hours)
                distribution_by_subject[subject] = {"distribution": estimate["distribution"], "expected_hours": estimate["expected_hours"]}

            prediction["distribution"] = distribution_by_subject[subject]["distribution"]
            prediction["expected_hours"] = distribution_by_subject[subject]["expected_hours"]

        weekly_risk = weekly_workload_risk(planning_events, predictions, start_date,
                                          forecast_end, hours_by_weekday, weekly_step_hours)

    return {"timeline": timeline, "daily_risk": daily_risk,
            "predictions": predictions, "weekly_risk": weekly_risk}


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


def daily_overload_probability(distributions: list, allowance: float, step_hours = 0.1) -> float:
    grid_array = workload_grid(allowance, step_hours)

    total_probabilities = np.zeros(len(grid_array))
    total_probabilities[0] = 1.0

    for distribution in distributions:
        event_probabilities = event_duration_probabilities(distribution, grid_array)
        total_probabilities = convolve_workload_probabilities(total_probabilities, event_probabilities)

    return overload_from_probabilities(total_probabilities)


def workload_grid(allowance: float, step_hours = 0.1) -> np.ndarray:
    interval_count = math.ceil(allowance / step_hours)
    return np.linspace(0, allowance, interval_count + 1)


def event_duration_probabilities(distribution, grid: np.ndarray) -> np.ndarray:
    cumulative_probabilities = distribution.cdf(grid)
    return np.maximum(np.diff(cumulative_probabilities, prepend=0.0), 0.0)


def convolve_workload_probabilities(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    #both arrays must describe the same grid
    if len(first) != len(second):
        raise ValueError("Workload arrays must use the same grid")
    combined = fftconvolve(first, second)[:len(first)]
    return np.maximum(combined, 0.0)


def overload_from_probabilities(probabilities: np.ndarray) -> float:
    overload_probability = 1 - float(probabilities.sum())
    return max(0.0, min(1.0, overload_probability))


def predicted_workload_probabilities(distribution, centers_by_event_count: dict, matched_centers: int,
                                     occurrence_probability: float, grid: np.ndarray) -> np.ndarray:

    event_probabilities = event_duration_probabilities(distribution, grid)
    total_probabilities = np.zeros(len(grid))
    total_probabilities[0] = 1.0

    predicted_probabilities = np.zeros(len(grid))
    predicted_probabilities[0] = 1 - occurrence_probability

    for event_count in range(1, max(centers_by_event_count) + 1):
        total_probabilities = convolve_workload_probabilities(total_probabilities, event_probabilities)

        count_probability = centers_by_event_count.get(event_count, 0) / matched_centers
        predicted_probabilities += occurrence_probability * count_probability * total_probabilities

    return predicted_probabilities


def weekly_workload_risk(planning_events: list, predictions: list, start_date: date, forecast_end: date, 
                         hours_by_weekday: tuple, step_hours = 0.25) -> dict:
    weekly_risk = {}
    week_start = start_date - timedelta(days=start_date.weekday())

    while week_start <= forecast_end:
        period_start = max(week_start, start_date)
        period_end = min(week_start + timedelta(days=6), forecast_end)
        allowance = sum(hours_by_weekday[period_start.weekday() : period_end.weekday() + 1])

        grid = workload_grid(allowance, step_hours)
        known_probabilities = np.zeros(len(grid))
        known_probabilities[0] = 1.0
        known_hours = 0.0
        
        for event in planning_events:
            deadline = event["due_date"]

            if isinstance(deadline, datetime):
                date = deadline.date() 
            else: date = deadline

            if period_start <= date <= period_end:
                distribution = event["distribution"]
                event_probabilities = event_duration_probabilities(distribution, grid)
                known_probabilities = convolve_workload_probabilities(known_probabilities, event_probabilities)
                known_hours += event["est_hours"]

        forecast_probabilities = known_probabilities.copy()
        forecast_hours = known_hours

        for prediction in predictions:
            if period_start <= prediction["predicted_deadline"] <= period_end:
                distribution = prediction["distribution"]
                centers_by_event_count = prediction["centers_by_event_count"]
                occurrence = prediction["occurrence_probability"]
                probabilities = predicted_workload_probabilities(distribution, centers_by_event_count, prediction["matched_centers"], occurrence, grid)
                forecast_probabilities = convolve_workload_probabilities(forecast_probabilities, probabilities)

                expected_count = prediction["expected_event_count"]
                expected_hours = prediction["expected_hours"]
                forecast_hours += (occurrence * expected_count * expected_hours)

        weekly_risk[week_start] = {"period_start": period_start,
                                   "period_end": period_end,
                                   "allowance": allowance,
                                   "known_hours": known_hours,
                                   "forecast_hours": forecast_hours,
                                   "known_overload_probability": overload_from_probabilities(known_probabilities),
                                   "forecast_overload_probability": overload_from_probabilities(forecast_probabilities)}
        
        week_start += timedelta(days=7)

    return weekly_risk


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
        if breaks is None:
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

        if history_start is not None:
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
                centers_by_event_count = {}

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
                            event_count = clusters[closest_date]
                            matched_events += event_count

                            if event_count not in centers_by_event_count:
                                centers_by_event_count[event_count] = 0
                            centers_by_event_count[event_count] += 1
                            
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

                if best_score is None or score > best_score:
                    best_score = score
                    best_schedule = {"period_days": period,
                                    "phase_date": earliest_candidate_date + timedelta(days=phase),
                                    "fit": fit,
                                    "matched_centers": matched_centers,
                                    "evaluated_centers": evaluated_centers,
                                    "unmatched_dates": unmatched_dates,
                                    "matched_events": matched_events,
                                    "centers_by_event_count": centers_by_event_count}

        if best_schedule is None or best_schedule["fit"] < minimum_fit:
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
                                "centers_by_event_count": best_schedule["centers_by_event_count"].copy(),
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
    pass