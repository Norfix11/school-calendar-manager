from datetime import datetime
import subprocess
from icalendar import Calendar, Event



def sync_to_apple_calendar(combined_events: list):
    calendar_name = "Homework Deadlines"
    serialized_events = []
    month_names = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    for homework in combined_events:
        if isinstance(homework["due_date"], datetime):
            end_date = homework["due_date"]
            start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
            serialized_events.append(
                {
                    "title": homework["title"],
                    "url": homework["description"],
                    "is_all_day": False,
                    "start_year": start_date.year,
                    "start_month": month_names[start_date.month],
                    "start_day": start_date.day,
                    "start_seconds": start_date.hour * 3600 + start_date.minute * 60,
                    "end_year": end_date.year,
                    "end_month": month_names[end_date.month],
                    "end_day": end_date.day,
                    "end_seconds": end_date.hour * 3600 + end_date.minute * 60 + end_date.second,
                    "reminder_1": 1020 if end_date.hour >= 18 else -420,
                    "reminder_2": -420 if end_date.hour >= 18 else -1860
                }
            )   
        else:
            start_date = datetime.combine(homework["due_date"], datetime.min.time())
            end_date = start_date.replace(hour=23, minute=59, second=59, microsecond=0)
            serialized_events.append(
                {
                    "title": homework["title"],
                    "url": homework["description"],
                    "is_all_day": True,
                    "start_year": start_date.year,
                    "start_month": month_names[start_date.month],
                    "start_day": start_date.day,
                    "start_seconds": 0,
                    "end_year": end_date.year,
                    "end_month": month_names[end_date.month],
                    "end_day": end_date.day,
                    "end_seconds": end_date.hour * 3600 + end_date.minute * 60 + end_date.second,
                    "reminder_1":1020,
                    "reminder_2":-420
                }
            )
            
    applescript = f'''
        tell application "Calendar"
            activate
            if not (exists calendar "{calendar_name}") then
                error "Calendar '{calendar_name}' was not found. Create it manually in iCloud Calendar first."
            end if
            set targetCalendar to first calendar whose name is "{calendar_name}"
            delete every event of targetCalendar
        end tell
        '''
    subprocess.run(["osascript", "-e", applescript], check=True)

    count = 0
    for current_event in serialized_events:
        applescript = f'''
        tell application "Calendar"
            set targetCalendar to first calendar whose name is "{calendar_name}"
            tell targetCalendar
                set startDate to current date
                set year of startDate to {current_event["start_year"]}
                set month of startDate to {current_event["start_month"]}
                set day of startDate to {current_event["start_day"]}
                set time of startDate to {current_event["start_seconds"]}

                set endDate to current date
                set year of endDate to {current_event["end_year"]}
                set month of endDate to {current_event["end_month"]}
                set day of endDate to {current_event["end_day"]}
                set time of endDate to {current_event["end_seconds"]}

                set newEvent to make new event with properties {{summary:"{current_event["title"]}", url:"{current_event["url"]}", start date:startDate, end date:endDate, allday event:{str(current_event["is_all_day"]).lower()}}}
                tell newEvent
                    make new display alarm at end with properties {{trigger interval:"{current_event["reminder_1"]}"}}
                    make new display alarm at end with properties {{trigger interval:"{current_event["reminder_2"]}"}}
                end tell
            end tell
        end tell
        '''
        subprocess.run(["osascript", "-e", applescript], check=True)
        
        count += 1
    
    print(f"Synced {count} events")
    print(f'"{calendar_name}" calendar synced successfully')
   
        
def build_backup_ics(combined_events: list, output_file="homework_deadlines.ics"):
    calendar = Calendar()
    calendar.add("prodid", "-//Homework Deadlines//")
    calendar.add("version", "2.0")

    for homework in combined_events:
        event = Event()
        event.add("summary", homework["title"])
        event.add("dtstart", homework["due_date"])
        event.add("dtstamp", datetime.now())
        event.add("description", homework["description"])
        calendar.add_component(event)

    with open(output_file, "wb") as file:
        file.write(calendar.to_ical())

    print(f"Created {output_file.rsplit('/', 1)[-1]}")