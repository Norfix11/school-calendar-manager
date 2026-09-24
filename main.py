from datetime import date, timedelta

from deadline_sources import (get_html, extract_deadlines_nt, extract_deadlines_owl,
                              extract_deadlines_rr, extract_deadlines_recodex)

from calendar_export import build_backup_ics, sync_to_apple_calendar
from event_storage import save_events, load_events, merge_events
from risk_analysis import analyze_events, last_workday


def print_analysis(analysis: dict, hours_by_weekday: tuple, warning_probability: float):
    """Prints all results in a readable format, as calculated by analysis dictionary"""

    print("\nRecommended work order (tasks on the same day have no strict order):")

    task_count = 0
    for day, events in analysis["timeline"].items():
        if not events:
            continue

        probability = analysis["daily_risk"][day]
        warning = "WARNING" if probability >= warning_probability else ""

        print(f"\n{day:%A %d.%m.%Y}: allowance {hours_by_weekday[day.weekday()]:g}h, "
              f"overload chance {probability:.0%} {warning}")
        
        for event in events:
            task_count += 1
            print(f"  {task_count}. {event['title']} — estimated {event['est_hours']:.1f} h, "
                  f"due {event['due_date']:%d.%m.%Y}")
            
    if task_count == 0:
        print("No tasks can currently be scheduled before their deadlines.")

    print("\nPredicted assignments:")
    for prediction in analysis["predictions"]:
        print(f"  {prediction['predicted_deadline']:%d.%m.%Y}: {prediction['subject']} — "
              f"occurrence chance {prediction['occurrence_probability']:.0%}, "
              f"expected task count if occurring {prediction['expected_event_count']:.1f}")
        
    if not analysis["predictions"]:
        print("No predictions for this period.")

    print("\nWeekly workload by deadline:")
    for week in analysis["weekly_risk"].values():
        probability = week["forecast_overload_probability"]
        warning = "WARNING" if probability >= warning_probability else ""

        print(f"  {week['period_start']:%d.%m.%Y} to {week['period_end']:%d.%m.%Y}: "
              f"expected hours {week['known_hours']:.1f} known / "
              f"{week['forecast_hours']:.1f} including predictions, "
              f"allowance {week['allowance']:g} h; overload chance "
              f"{week['known_overload_probability']:.0%} known / "
              f"{probability:.0%} including predictions {warning}")



def main():
    live_mode = True
    start_date = date(2026, 3, 25)
    forecast_end = start_date + timedelta(days=50)
    hours_by_weekday = (1, 3, 3, 2, 3, 1, 2)  # Monday through Sunday
    default_est_hours = 2.0
    hours_by_subject = {}
    history_start = None
    breaks = []  # Pairs of start/end dates when assignments are not expected
    warning_probability = 0.5
    sync_to_calendar = False

    if live_mode:
        live_events = []
        
        #number theory
        nt_page, url = get_html("https://sites.google.com/view/simonafrysova/teaching/tč-2526")
        live_events += extract_deadlines_nt(nt_page, url)
        
        #postal owl
        live_events += extract_deadlines_owl("https://owl.mff.cuni.cz")
        
        #resitelak
        rr_page, url = get_html("https://karlin.mff.cuni.cz/resitel/LS2526/index.html")
        live_events += extract_deadlines_rr(rr_page, url)
        
        #recodex
        #live_events += extract_deadlines_recodex("https://recodex.mff.cuni.cz/app")

        try:
            saved_events = load_events(default_est_hours, hours_by_subject)
        except FileNotFoundError:
            saved_events = []

        combined_events = merge_events(saved_events, live_events, default_est_hours, hours_by_subject)
        save_events(combined_events)

    else:
        try:
            combined_events = load_events(default_est_hours, hours_by_subject)
        except FileNotFoundError:
            raise SystemExit("Offline data file not found: data/sample_deadlines.json.")

    
    # Builds a backup and preview .ics file
    build_backup_ics(combined_events)

    analysis = analyze_events(combined_events, start_date, hours_by_weekday, forecast_end, 
                              history_start, breaks, hours_by_subject)

    unscheduled_events = []
    for event in combined_events:
        if not event["completed"] and last_workday(event) < start_date:
            unscheduled_events.append(event)

    if unscheduled_events:
        print("\nUnfinished tasks whose last workday has passed (not scheduled):")
        for event in unscheduled_events:
            print(f"  {event['title']} — due {event['due_date'].isoformat()}")

    print_analysis(analysis, hours_by_weekday, warning_probability)

    if sync_to_calendar:
        sync_to_apple_calendar(combined_events)



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="School Calendar Manager")
    parser.add_argument("--cli", action="store_true", help="Run the existing console workflow")
    parser.add_argument("--no-browser", action="store_true", help="Print the local UI address without opening it")
    parser.add_argument("--port", type=int, default=0, help="Local UI port (default: choose an available port)")
    args = parser.parse_args()

    if args.cli:
        main()
    else:
        from frontend import launch

        launch(port=args.port, open_browser=not args.no_browser)