from datetime import date, time, datetime, timedelta
from itertools import product
from heapq import heappush, heappop
import math
import numpy as np
from scipy.stats import gamma
from scipy.signal import fftconvolve
from bisect import bisect_left



def analyze_events(events: list, start_date: date, hours_by_weekday: tuple,
                   forecast_end = None, history_start = None, breaks = None,
                   est_hours_override = None, daily_step_hours = 0.1, weekly_step_hours = 0.1) -> dict:
    """Main analysis function connecting event duration estimation, scheduling and risk prediction.
    Completed events provide historical hours used to update expected event durations. Schedules
    unfinished events with these updated estimates and uses their Gamma duration distributions
    to calculate daily overload probabilities. Predicts recurring future deadlines if forecast_end
    is given, and combines with known events into weekly expected workload and overload risk."""

    hours_by_subject = {}
    unfinished_events = []

    # Separates completed events from unfinished events
    for event in events:
        if event.get("completed"):
            subject = event["subject"]

            if subject not in hours_by_subject:
                hours_by_subject[subject] = []
            hours_by_subject[subject].append(event["actual_hours"])

        else:
            unfinished_events.append(event)

    planning_events = []

    # Creates planning copies so original event estimates stay unchanged
    # Estimates duration of scheduled events based on initial given estimate and historical hours
    for event in unfinished_events:

        if event["subject"] in hours_by_subject:
            past_hours = hours_by_subject[event["subject"]]
        else:
            past_hours = []

        # Updated duration is a weighted mean:
        # E[hours] = (initial_weight * initial_estimate + sum(past_hours)) / total_weight
        # Distribution stores Gamma distribution based on given initial and past data
        estimate = estimate_event_duration(event["est_hours"], past_hours)

        planning_event = event.copy()
        planning_event["est_hours"] = estimate["expected_hours"]
        planning_event["distribution"] = estimate["distribution"]

        planning_events.append(planning_event)

    # Builds an exact timeline, works with the updated estimates
    timeline = build_timeline(planning_events, start_date, hours_by_weekday)

    daily_risk = {}
    # Calculates overload risk for a timeline date
    for date, assigned_events in timeline.items():
        distributions = []

        for event in assigned_events:
            distributions.append(event["distribution"])

        allowance = hours_by_weekday[date.weekday()]
        daily_risk[date] = daily_overload_probability(distributions, allowance, daily_step_hours)


    predictions = []
    weekly_risk = {}

    # Forecasting is optional, needs given forecast_end to initialise
    if forecast_end is not None:

        # Predicts recurring tasks based on original event history, does not predict task duration
        predictions = predict_events(events, start_date, forecast_end, history_start, breaks)
        distribution_by_subject = {}

        for prediction in predictions:
            subject = prediction["subject"]

            # Same subject can have multiple future predictions, calculates its duration model only once
            if subject not in distribution_by_subject:

                # Manual subject estimate has priority, otherwise uses mean of original event estimates
                # as initial event duration estimate
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

                # Estimating subject duration from historical hours, after choosing the initial estimate
                past_hours = hours_by_subject.get(subject, [])
                estimate = estimate_event_duration(est_hours, past_hours)
                distribution_by_subject[subject] = {"distribution": estimate["distribution"], "expected_hours": estimate["expected_hours"]}

            # Stores duration information in prediction needed by weekly risk
            prediction["distribution"] = distribution_by_subject[subject]["distribution"]
            prediction["expected_hours"] = distribution_by_subject[subject]["expected_hours"]

        # Calculates weekly workload and overload risks for the given period based on actual and predicted deadlines
        # Does not build an explicit timeline, when events will be assigned is not known
        weekly_risk = weekly_workload_risk(planning_events, predictions, start_date,
                                          forecast_end, hours_by_weekday, weekly_step_hours)

    return {"timeline": timeline, "daily_risk": daily_risk,
            "predictions": predictions, "weekly_risk": weekly_risk}


def estimate_event_duration(est_hours: float, past_hours: list, initial_weight = 2.0,
                           relative_deviation = 0.5, interval_probability = 0.9) -> dict:
    """Returns updated expected duration and uncertainty from initial est_hours and completed history.
    The initial estimate produces initial_weight historical observations, so little history cannot
    immediately replace it. Mean and variance are calculated from this data and converted into 
    Gamma distribution parameters. Gamma is used because event duration is positive and can have
    a right tail. Also returns standard deviation and a central prediction interval."""

    if est_hours <= 0:
        raise ValueError("Initial estimated hours must be greater than zero")
    
    # Calculates smoothed mean, initial_weight determines number of artificial est_hours long events
    total_weight = initial_weight + len(past_hours)
    expected_hours = (initial_weight * est_hours + math.fsum(past_hours)) / total_weight

    # Initial standard deviation calculated as given relative_deviation * est_hours,
    # variance is then standard deviation squared
    initial_variance = (relative_deviation * est_hours) ** 2

    # Calculates numerator of variance calculation, that is sum of squared distances from expected_hours mean
    # Initial variance represents average of squared distances from est_hours initial mean, where exact distances
    # are unknown. Mean shift variance formula: variance + (mean difference)^2 gives variance of initial data with 
    # respect to new expected_hours mean. Multiplying by initial weight converts variance to sum of squared distances.
    weighted_variance = initial_weight * (initial_variance + (est_hours - expected_hours) ** 2)
    # Adds sum of squared distances of past_hours and new expected_hours mean, giving the correct numerator and devides.
    weighted_variance += math.fsum((hours - expected_hours) ** 2 for hours in past_hours)
    variance = weighted_variance / total_weight

    # For Gamma(shape, scale):
    # mean = shape * scale and variance = shape * scale^2
    # Solving for shape and scale with known mean and variance gives:
    # shape = mean^2 / variance, scale = variance / mean
    shape = expected_hours ** 2 / variance
    scale = variance / expected_hours
    distribution = gamma(a=shape, scale=scale)

    # For a 90% interval, remaining 10% is split into 5% in each tail
    # lower = 5th percentile and upper = 95th percentile
    tail_probability = (1 - interval_probability) / 2
    lower = float(distribution.ppf(tail_probability))
    upper = float(distribution.ppf(1 - tail_probability))

    return {"expected_hours": expected_hours, "deviation_hours": math.sqrt(variance), "prediction_interval": (lower, upper),
            "interval_probability": interval_probability, "shape": shape, "scale": scale, "distribution": distribution}


def daily_overload_probability(distributions: list, allowance: float, step_hours = 0.1) -> float:
    """Returns probability that total duration of all given independent events exceeds allowance.
    Converts each continuous Gamma distribution into a grid conatining probabilities of the
    event duration landing in that section of the grid. Convolution then gives such probabilites
    of the sum X1 + X2 + ... + Xn through events. Only probabilities up to allowance are stored, 
    therefore overload probability is 1 - P(total workload <= allowance)."""

    grid_array = workload_grid(allowance, step_hours)

    # Before adding any events total workload is zero with probability 1
    total_probabilities = np.zeros(len(grid_array))
    total_probabilities[0] = 1.0

    for distribution in distributions:
        event_probabilities = event_duration_probabilities(distribution, grid_array)

        # If A and B are independent workloads, convolution calculates grid probabilities of A + B:
        # P(A + B = k) = sum_i P(A = i) * P(B = k - i)
        total_probabilities = convolve_workload_probabilities(total_probabilities, event_probabilities)

    return overload_from_probabilities(total_probabilities)


def workload_grid(allowance: float, step_hours = 0.1) -> np.ndarray:
    """Returns workload grid from zero to allowance. Number of intervals is ceil(allowance / step_hours),
    so continuous hours can later be represented by finite probability buckets instead of 
    infinitely many possible duration values."""

    interval_count = math.ceil(allowance / step_hours)
    return np.linspace(0, allowance, interval_count + 1)


def event_duration_probabilities(distribution, grid: np.ndarray) -> np.ndarray:
    """Converts a continuous duration distribution into probabilities for grid intervals.
    If f is the probability density and F its cumulative distribution function:
        P(a < duration <= b) = ∫_a^b f(x) dx = F(b) - F(a).
    For i >= 1, each bucket stores the integral between grid[i - 1] and grid[i].
    Bucket 0 stores F(0), which is zero for our Gamma duration distribution."""

    cumulative_probabilities = distribution.cdf(grid)

    # bucket[i] = F(grid[i]) - F(grid[i - 1])
    return np.maximum(np.diff(cumulative_probabilities, prepend=0.0), 0.0)


def convolve_workload_probabilities(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Convolves two independent workload probability arrays into probability array of their sum.
    Discrete convolution uses P(X + Y = k) = sum_i P(X = i) * P(Y = k - i).
    Cuts the result to original grid length, so all probability corresponding to workload above
    allowance is intentionally removed and later interpreted as overload probability."""

    # Both arrays must describe the same grid
    if len(first) != len(second):
        raise ValueError("Workload arrays must use the same grid")
    # Keeps only workload up to allowance, removed probability represents exceeding it
    combined = fftconvolve(first, second)[:len(first)]
    return np.maximum(combined, 0.0)


def overload_from_probabilities(probabilities: np.ndarray) -> float:
    """Returns probability of workload exceeding represented allowance.
    Stored buckets contain P(workload <= allowance), so complement gives
    P(overload) = 1 - P(workload <= allowance)."""

    overload_probability = 1 - float(probabilities.sum())
    return max(0.0, min(1.0, overload_probability))


def predicted_workload_probabilities(distribution, centers_by_event_count: dict, matched_centers: int,
                                     occurrence_probability: float, grid: np.ndarray) -> np.ndarray:
    """Returns workload distribution of one predicted recurrence.
    Final distribution combines three uncertainties: whether recurrence happens, how many events
    appear if it happens, and how long these events take. For every possible event count k, duration
    distribution of k events is weighted by P(recurrence) * P(count = k | recurrence). Places 
    probability 1 - P(recurrence) directly into zero-workload bucket."""

    event_probabilities = event_duration_probabilities(distribution, grid)
    # Reused convolution starts at zero events and adds one event on every loop
    total_probabilities = np.zeros(len(grid))
    total_probabilities[0] = 1.0

    predicted_probabilities = np.zeros(len(grid))

    # P(no recurrence) = 1 - P(recurrence), and no recurrence contributes exactly zero workload
    predicted_probabilities[0] = 1 - occurrence_probability

    # All possible event counts contribute to the distribution, count_probability = 0 for higher than max
    for event_count in range(1, max(centers_by_event_count) + 1):
        # After this convolution total_probabilities describes a distribution from exactly event_count events
        total_probabilities = convolve_workload_probabilities(total_probabilities, event_probabilities)

        # Conditional probability from matched historical centers:
        # P(count = k | recurrence) = centers_with_k_events / matched_centers
        count_probability = centers_by_event_count.get(event_count, 0) / matched_centers

        # P(recurrence AND count=k AND workload bucket)
        # = P(recurrence) * P(count=k | recurrence) * P(workload bucket | k events)
        predicted_probabilities += occurrence_probability * count_probability * total_probabilities

    return predicted_probabilities


def weekly_workload_risk(planning_events: list, predictions: list, start_date: date, forecast_end: date, 
                         hours_by_weekday: tuple, step_hours = 0.1) -> dict:
    """Returns known and forecast workload information for every week in requested period.
    Known workload uses unfinished events. Forecast workload starts from the same known distribution and convolves
    predicted recurrence distributions into it. Expected hours are calculated separately from probability grids
    so cutting excess probabilities at weekly allowance does not reduce the expected workload value."""

    weekly_risk = {}
    # Dictionary keys stay Mondays even when first analyzed week starts later
    week_start = start_date - timedelta(days=start_date.weekday())

    while week_start <= forecast_end:
        # First and last week may contain only part of a full week
        period_start = max(week_start, start_date)
        period_end = min(week_start + timedelta(days=6), forecast_end)
        # Whole grid represents total weekly allowance, date information is intentionally lost
        allowance = sum(hours_by_weekday[period_start.weekday() : period_end.weekday() + 1])

        grid = workload_grid(allowance, step_hours)

        # Distribution and expected hours of already known unfinished events in this week
        known_probabilities = np.zeros(len(grid))
        known_probabilities[0] = 1.0
        known_hours = 0.0
        
        for event in planning_events:
            deadline = event["due_date"]

            if isinstance(deadline, datetime):
                date = deadline.date() 
            else: date = deadline

            # Convolves event into weekly grid, if it falls in the observed period
            if period_start <= date <= period_end:
                distribution = event["distribution"]
                event_probabilities = event_duration_probabilities(distribution, grid)
                known_probabilities = convolve_workload_probabilities(known_probabilities, event_probabilities)
                known_hours += event["est_hours"]

        # Forecast starts from known workload and adds every predicted recurrence in this week
        forecast_probabilities = known_probabilities.copy()
        forecast_hours = known_hours

        # Convolves recurrence probabilities into weekly grid, if it falls in the observed period
        for prediction in predictions:
            if period_start <= prediction["predicted_deadline"] <= period_end:
                distribution = prediction["distribution"]
                centers_by_event_count = prediction["centers_by_event_count"]
                occurrence = prediction["occurrence_probability"]
                probabilities = predicted_workload_probabilities(distribution, centers_by_event_count, prediction["matched_centers"], occurrence, grid)
                forecast_probabilities = convolve_workload_probabilities(forecast_probabilities, probabilities)

                # Expected predicted workload follows E[workload]:
                # P(recurrence) * E[event count | recurrence] * E[hours per event]
                # Full estimates are used because probability grid is cut at allowance
                expected_count = prediction["expected_event_count"]
                expected_hours = prediction["expected_hours"]
                forecast_hours += (occurrence * expected_count * expected_hours)

        # Calculates overload probability from distributions and appends, along with relevant data
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
    """Predicts future recurring deadlines separately for every subject.
    First groups historical deadlines of same subject into clusters. Tests every weekly and
    biweekly phase as a possible recurrence. Matches closest historical dates inside given
    date_tolerance to expected recurrence centers and further matches receive lower weight
    as given by match_weight_function. Best model is selected by fit, number of matches, 
    total shift and shorter period. Hit rate is smoothed into occurrence probability and 
    matched cluster sizes are used as an estimate to how many events usually appear.
    Extends the accepted model through all of forecast period."""

    
    if not isinstance(date_tolerance, int) or not 0 <= date_tolerance <= 2:
        raise ValueError("date_tolerance must be an integer from zero to two")

    if forecast_end < forecast_start:
        return []


    def is_during_break(date):
        """Checks whether date belongs to any interval in breaks."""
        if breaks is None:
            return False
        
        return any(start <= date <= end for start, end in breaks)


    # Clusters equal subject deadlines on the same date, cluster value is number of events
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

    # Fits one independent recurrence model for every subject
    for subject, clusters in clusters_by_subject.items():

        # Only historical dates before forecasting influence model selection
        date_history = [date for date in clusters if date < forecast_start
                    and (history_start is None or date >= history_start)
                    and not is_during_break(date)]
        if not date_history:
            continue
        # Sorts date history
        date_history.sort()

        if history_start is not None:
            earliest_candidate_date = history_start - tolerance
        else:
            earliest_candidate_date = date_history[0] - tolerance


        best_schedule = None
        best_score = None
        
        # Tests weekly and biweekly recurrence with every possible phase
        for period in (7, 14):

            for phase in range(period):
                matched_centers = 0
                unmatched_centers = 0
                matched_events = 0
                matched_weight = 0
                total_shift = 0
                centers_by_event_count = {}

                # Iterates over all centers, i.e. recurrence dates expected with current period and phase
                center = earliest_candidate_date + timedelta(days=phase)

                while center - tolerance < forecast_start:

                    if not is_during_break(center):
                        # Closest date in sorted date history to center is one of the adjecent
                        pos = bisect_left(date_history, center)

                        candidates = []
                        if pos > 0:
                            candidates.append(date_history[pos - 1])

                        if pos < len(date_history):
                            candidates.append(date_history[pos])

                        # Stores closest date and its distance from center
                        closest_date = min(candidates, key=lambda date: abs((date - center).days))
                        closest_distance = abs((closest_date - center).days)

                        # Tolerance windows of radius at most 2 cannot overlap because periods are at least seven days
                        # Stores matched center data if date is in tolerance window
                        if closest_distance <= date_tolerance:
                            matched_centers += 1
                            event_count = clusters[closest_date]
                            matched_events += event_count

                            if event_count not in centers_by_event_count:
                                centers_by_event_count[event_count] = 0
                            centers_by_event_count[event_count] += 1
                            
                            total_shift += closest_distance
                            # Default weight function = 1 - distance / (tolerance + 1)
                            # With tolerance 1: exact match has weight 1, one-day shift has weight 0.5
                            matched_weight += match_weight_function(closest_distance, date_tolerance)

                        # If no match happens and the whole window is within history checked, count no match
                        elif center - tolerance >= earliest_candidate_date + tolerance and center + tolerance < forecast_start:
                            unmatched_centers += 1

                    center += timedelta(days=period)

                # Unmatched dates penalize for real deadlines unexplained by this recurrence model
                unmatched_dates = len(date_history) - matched_centers
                evaluated_centers = matched_centers + unmatched_centers

                # Skip this recurrence model if not enough supporting data
                if matched_centers < 2:
                    continue

                # Greater fit with higher weighted matches, but penalizes both missing expected centers
                # and historical deadlines which recurrence model does not explain
                # fit = weighted number of matches / (all evaluated centers + unmatched historical dates)
                fit = matched_weight / (evaluated_centers + unmatched_dates)

                # Lexicographic score prefers fit, then more matches, less shifting and shorter period
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

        # If no tested recurrence pattern is strong enough, skip this subject
        if best_schedule is None or best_schedule["fit"] < minimum_fit:
            continue

        matched_centers = best_schedule["matched_centers"]
        evaluated_centers = best_schedule["evaluated_centers"]

        # Smoothed hit probability:
        # P(recurrence) = (matched_centers + 1) / (evaluated_centers + 2)
        # +1 matched and +1 unmatched virtual centers prevent extreme 0 or 1 from little history
        probability = (matched_centers + 1) / (evaluated_centers + 2)
        if probability < minimum_probability:
            continue

        # Conditional expected cluster size:
        # E[count | recurrence] = total events in matched centers / number of matched centers
        expected_count = best_schedule["matched_events"] / matched_centers

        period = best_schedule["period_days"]
        phase_date = best_schedule["phase_date"]
        # Moves fitted historical phase forward to first center on or after forecast_start
        periods_to_forecast = math.ceil((forecast_start - phase_date).days / period)
        first_prediction = phase_date + timedelta(days=periods_to_forecast * period)

        # Iterates over candidate forecast event dates using winning period and phase
        for i in range(0, (forecast_end - first_prediction).days + 1, period):
            center = first_prediction + timedelta(days=i)

            # Does not predict an event if the candidate date is during a given break
            if is_during_break(center):
                continue

            # Does not predict another event if a known deadline already covers this center
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

    # Returns predictions sorted by deadline, then subject lexicographically
    return sorted(predictions, key=lambda prediction: (prediction["predicted_deadline"], prediction["subject"]))


def normalize_deadline(event: dict) -> datetime:
    """Returns event due_date as datetime. Treats date-only deadlines as end of that day."""

    due_date = event["due_date"]

    if isinstance(due_date, datetime):
        return due_date
    
    return datetime.combine(due_date, time.max)


def daily_overload_penalty(hours: float, allowance: float, penalty = lambda x: x ** 2) -> float:
    """Returns penalty for given amount of workload above daily allowance.
    Default penalty function is max(0, hours - allowance)^2, so work below allowance costs zero
    and overload becomes increasingly expensive. Penalty function needs to be convex."""

    return penalty(max(0, hours - allowance))


def last_workday(event: dict, cutoff = time(20, 0)) -> date:
    """Returns last day an event can be scheduled. Deadlines before cutoff require finishing
    the event one day earlier, for later and date-only deadlines returns the deadline day."""

    deadline = normalize_deadline(event)
    date = deadline.date()

    if deadline.time() < cutoff:
        return date - timedelta(days=1)

    return date


def relaxed_remaining_score(current_day: int, state: tuple, groups_by_unit: dict,
                            sorted_units: list, allowance_by_day: list) -> tuple:
    """Returns optimistic lower bound score for best possible completion of current DFS state.
    Real events are not allowed to be devided, but relaxation splits every remaining event
    into independent 0.5 hour units. The real schedule is a subset of all possible relaxed
    schedules, so its score is a valid lower bound. Because overload penalty is necessarily convex,
    each next half-hour has a higher or equal cost and the optimal position can be selected greedily."""

    remaining_events = []

    for i, unit in enumerate(sorted_units):
        group = groups_by_unit[unit]

        for event in group[state[i]:]:
            remaining_events.append((event["last_day"], unit))

    # Earlier deadlines' eligible assignment days are nested inside later deadlines'
    remaining_events.sort()

    assigned_units = [0] * len(allowance_by_day)
    daily_offers = []
    iterating_day = current_day

    # Initializes penalty count and early-work count
    total_penalty = 0
    total_ew_cost = 0

    # Each remaining event unit receives a cost from every possible assignment day
    # and chooses greedily the one with lowest cost. To avoid finding the lowest cost
    # offer in O(n) complexity every time, offers are stored in a min heap giving
    # O(log(n)) inserting and retrieving complexity.
    for last_day, unit in remaining_events:

        # Calculates cost of assigning the first unit to each of the legal days
        while iterating_day <= last_day:
            allowance = allowance_by_day[iterating_day]
            # Cost of assigning the first 0.5h to this day:
            # penalty(0.5) - penalty(0)
            heappush(daily_offers, (
                daily_overload_penalty(0.5, allowance) - daily_overload_penalty(0, allowance), iterating_day
            ))
            iterating_day += 1

        # Relaxation allows the event to be split into its half-hour units
        for _ in range(unit):
            # Retrieve best offer from min heap
            penalty_cost, date = heappop(daily_offers)

            total_penalty += penalty_cost
            # Early-work cost grows linearly, so adding date index is sufficient
            total_ew_cost += date
            assigned_units[date] += 1

            hours = assigned_units[date] / 2
            allowance = allowance_by_day[date]
            # Only the chosen date changes its next unit offer and pushes it into min heap
            # Cost of assigning the next unit = penalty(hours + 0.5) - penalty(hours)
            heappush(daily_offers, (
                daily_overload_penalty(hours + 0.5, allowance) - daily_overload_penalty(hours, allowance), date
            ))

    return total_penalty, total_ew_cost


def greedy_benchmark_score(groups_by_unit: dict, sorted_units: list,
                           allowance_by_day: list) -> tuple[tuple, list]:
    """Greedily, but quickly builds a schedule used as upper bound for exact DFS.
    Events stay whole and are sorted by earliest deadline. For every event, 
    compares all legal days and assigns it to a day with the lowest
    penalty cost = penalty(after adding event) - penalty(before adding event).
    Since the output is a valid schedule, thus a subset of schedules possibly searched by DFS,
    exact search can avoid looking for schedules with worse scores."""

    sorted_events = []

    for unit_index, unit in enumerate(sorted_units):
        for event in groups_by_unit[unit]:
            sorted_events.append((event["last_day"], unit, unit_index))

    # Tuple sorting puts earliest deadlines first
    sorted_events.sort()

    plan = [[0] * len(sorted_units) for _ in range(len(allowance_by_day))] 
    assigned_units = [0] * len(allowance_by_day)
    # Initializes penalty count and early-work count
    total_penalty = 0
    total_ew_cost = 0

    for last_day, unit, unit_index in sorted_events:
        best_offer = None

        # Calculates cost of placing the whole event on every legal day
        # and chooses the day with lowest penalty cost
        for current_day in range(last_day + 1):
            allowance = allowance_by_day[current_day]
            # Penalty cost = new daily penalty - current daily penalty
            # units are half-hours, therefore assigned hours = assigned_units / 2
            penalty = (
                daily_overload_penalty((assigned_units[current_day] + unit) / 2, allowance) 
                - daily_overload_penalty(assigned_units[current_day] / 2, allowance)
            )
            offer = (penalty, current_day)
            
            if best_offer is None or offer < best_offer:
                best_offer = offer

        # Updates totals to include the newly assigned units
        penalty, chosen_day = best_offer
        assigned_units[chosen_day] += unit
        total_penalty += penalty
        # Early-work cost grows linearly, so adding chosen_day index for each assigned unit is suffiecient
        total_ew_cost += chosen_day * unit
        plan[chosen_day][unit_index] += 1

    return (total_penalty, total_ew_cost), [tuple(date) for date in plan]


def build_timeline(events: list, start_date: date, hours_by_weekday: tuple) -> dict:
    """Returns exact event schedule from start_date while respecting deadlines.
    Durations are rounded up into 0.5 hour units and equal-duration events are grouped, so a DFS state
    stores only how many events of each group are already assigned instead of every event permutation.
    State score is tuple (total overload penalty, early-work cost), compared lexicographically:
    overload is minimized first and if equal, work is placed earlier. Greedy score gives score an
    upper bound and relaxation gives score a lower bound. Already visited state branches with worse score
    are cut off, through memoisation."""

    groups_by_unit = {}
    event_count = 0

    # Groups events of same duration by unit so a DFS state only stores completed count for each duration
    for index, event in enumerate(events):
        last_day = (last_workday(event) - start_date).days
        # Converts hours into indivisible half-hour units and rounds upward:
        # event_units = ceil(hours * 2), scheduled_hours = event_units / 2
        event_units = math.ceil(event["est_hours"]*2)

        # If the event is already passed, skip it
        if last_day < 0:
            continue

        if event_units not in groups_by_unit:
            groups_by_unit[event_units] = []

        groups_by_unit[event_units].append({"event_index": index, "last_day": last_day})
        event_count += 1

    # If there are no upcoming deadlines, return an empty schedule
    if not groups_by_unit:
        return {}

    # Sorts for unit count indexing
    sorted_units = sorted(groups_by_unit)

    # Within each unit group events are always completed in deadline order
    for group in groups_by_unit.values():
        group.sort(key=lambda event: event["last_day"])

    last_day_index = max(group[-1]["last_day"] for group in groups_by_unit.values())
    allowance_by_day = []

    # Creates a list of allowance values corresponding to day index from start_date
    for current_day in range(last_day_index + 1):
        planning_date = start_date + timedelta(days=current_day)
        allowance_by_day.append(hours_by_weekday[planning_date.weekday()])


    # Calculates greedy schedule score for DFS to beat
    best_score, best_plan = greedy_benchmark_score(groups_by_unit, sorted_units, allowance_by_day)
    best_seen = {}
    current_plan = []

    def state_space_DFS(current_day: int, remaining_events: int, state: tuple, score: tuple) -> None:
        """Searches depth-first through the state space, sending: current day, remaining events, state, score
        into recursion. Memoisation and finishing current state with allowing unit splitting allows for
        whole DFS branch elimination. DFS is chosen to reach a valid end state first, so other states
        can eliminate branches through relaxed scores."""

        nonlocal best_score, best_plan

        # A DFS state is represented by tuple (day, state)
        # Therefore if this tuple was already reached with smaller score,
        # current branch is eliminated since it cannot produce a better result
        if (current_day, state) not in best_seen or score < best_seen[(current_day, state)]:
            best_seen[(current_day, state)] = score
        else:
            return
        
        # Completes this schedule if no events remain, updates best score if lexicographic score improved
        if remaining_events == 0:
            if score < best_score:
                best_score = score
                best_plan = current_plan.copy()
            return

        # Optimistic relaxed score bounds the best score reachable from this state
        relaxed_penalty, relaxed_ew_cost = relaxed_remaining_score(current_day, state, groups_by_unit, sorted_units, allowance_by_day)
        relaxed_score = (score[0] + relaxed_penalty, score[1] + relaxed_ew_cost)

        # Optimistic completion cannot beat best encountered score and any valid
        # completion is equal or worse, so current branch is eliminated
        if relaxed_score >= best_score:
            return


        new_by_unit = []

        # Generates the number of events from each unit group that can be done today
        for i, unit in enumerate(sorted_units):
            group = groups_by_unit[unit]
            # Events whose deadline is today or earlier must already be completed after today
            required = sum(event["last_day"] <= current_day for event in group)

            # At least required - already_completed events must be done today to avoid missing a deadline
            # At most every still unfinished event of this group can be done today
            min_new = max(0, required - state[i])
            max_new = len(group) - state[i]
            new_by_unit.append(range(min_new, max_new + 1))

        # Allocation iterates over the Cartesian product giving every legal assignment of events today
        for allocation in product(*new_by_unit):
            units_today = 0
            events_today = 0

            for i, count in enumerate(allocation):
                events_today += count
                units_today += count * sorted_units[i]

            # First score component adds today's overload penalty.
            # Second is sum(day_index * half-hour units), so equal-penalty schedules prefer earlier work
            total_penalty = score[0] + daily_overload_penalty(units_today/2, allowance_by_day[current_day])
            total_ew_cost = score[1] + current_day*units_today
            new_score = (total_penalty, total_ew_cost)
            new_state = tuple(state[i] + allocation[i] for i in range(len(sorted_units)))

            # Backtracking keeps current_plan synchronized with current DFS path
            current_plan.append(allocation)
            state_space_DFS(current_day + 1, remaining_events - events_today, new_state, new_score)
            current_plan.pop()


    # Initially no events from any duration group are completed and score is zero
    state_space_DFS(0, event_count, (0,) * len(sorted_units), (0, 0))


    # Converts compressed count plan into event dictionaries timeline given by best_plan
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