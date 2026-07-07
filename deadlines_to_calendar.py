from datetime import datetime, timedelta

from icalendar import Calendar, Event

import requests

import re

import subprocess

from bs4 import BeautifulSoup

from playwright.sync_api import sync_playwright



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

    print(f"Created {output_file}")
    
    
def get_html(url: str) -> tuple[str, str]:
    '''Returns the whole string of the website's html'''
    
    response = requests.get(url)
    return response.text, url


def extract_deadlines_owl(url: str) -> list:
    event = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url)
        input("Navigate to The Postal Owl website and log in. Then press Enter ")
        
        headings = page.locator("h2")

        for i in range(headings.count()):
            heading = headings.nth(i)
            heading_text = heading.text_content()

            if "semester" in heading_text.lower():
                ul = heading.locator("xpath=following-sibling::ul[1]")
                links = ul.locator('a[href^="/c/"]')
                
                for j in range(links.count()):
                    link = links.nth(j)
                    reference = link.get_attribute("href")
                    
                    #deadline extraction from a subject page
                    page.goto(url + reference)
                    subject = page.locator("h2").first.text_content()
                    rows = page.locator("tr.told, tr.tnew")
                    
                    for k in range(rows.count()):
                        row = rows.nth(k)
                        text = row.locator("td")
                        title = f"{subject} {text.nth(0).text_content().strip()}"
                        date_string = text.nth(1).text_content().strip().rsplit(" (", 1)[0]
                        
                        if date_string:
                            event_reference = row.locator("a").first.get_attribute("href")
                            date = datetime.strptime(date_string, "%Y-%m-%d %H:%M")
                            event.append({"title": title, "due_date": date, "description": url + event_reference})
                        
                    page.goto(url)
                                 
    return event


def extract_deadlines_recodex(url: str) -> list:
    event = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url)
        input("Navigate to the ReCodEx website and log in. Then press Enter ")
        
        cards = page.locator("div.mb-3.card-outline.card-light.card")
        
        for i in range(cards.count()):
            card = cards.nth(i)
            card_title = card.locator(".card-title.h5").first
            subject = card_title.evaluate("""
                                          el => Array.from(el.childNodes)
                                          .filter(n => n.nodeType === Node.TEXT_NODE)
                                          .map(n => n.textContent.trim())
                                          .filter(Boolean)[2]
                                          """)
    
            if not subject:
                subject = card_title.locator("a").first.text_content()
            
            #deadline extraction from dropdown
            card.locator('[data-icon="plus"]').first.click()
            rows = card.locator("tr")
            page.wait_for_timeout(500)
            
            for j in range(rows.count()):
                row = rows.nth(j)
                table_data = row.locator("td")
                
                if table_data.count() >= 5:
                    date_string = table_data.nth(4).text_content()
                    date = datetime.strptime(date_string, "%m/%d/%Y %H:%M")
                    
                    event_title = table_data.nth(1)
                    title = event_title.text_content()
                    event_reference = table_data.locator("a").first.get_attribute("href")[4:]
                    
                    event.append({"title": f"{subject} {title}", "due_date": date, "description": url + event_reference})
                
            card.locator('[data-icon="minus"]').first.click()
    
    return event
    

def extract_deadlines_nt(html: str, url: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    event = []
    
    for line in soup.select(".zfr3Q.CDt4Ke"):
        text = line.get_text(" ", strip=True)
        
        if "odovzdajte do" in text:
            contents = line.contents
            title = contents[0].get_text().strip(":")
            date_string = re.search(r"\d{1,2}\.\d{1,2}\.\d{4}", text.replace(" ", "")).group()
            date = datetime.strptime(date_string, "%d.%m.%Y").date()
            new_url = url
            
            for item in contents:
                if item.name == "a":
                    new_url = item.get("href")
            
            event.append({"title": f"Teorie čísel {title}", "due_date": date, "description": new_url})
            
    return event


def extract_deadlines_rr(html: str, url: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    event = []
    
    heading = soup.select_one("h2")
    paragraphs = heading.find_next_siblings("p")
    
    for line in paragraphs:
        
        if line.get_text(strip=True):
            contents = line.contents
            
            title = contents[0].get_text().replace(" ", "", 1)
            reference = contents[0].get("href")
            date_string = contents[1].get_text().strip("()– \n")
            if date_string == "do 31. 11. 2025":
                date_string = "do 20. 4. 2026"
            date = datetime.strptime(date_string, "do %d. %m. %Y").date()
            
            event.append({"title": f"Řešitelský seminář {title}", "due_date": date, "description": url + reference})
    
    return event

        

if __name__ == "__main__":
    combined_events = []
    
    #number theory
    nt_page, url = get_html("https://sites.google.com/view/simonafrysova/teaching/tč-2526")
    combined_events += extract_deadlines_nt(nt_page, url)
    
    #postal owl
    combined_events += extract_deadlines_owl("https://owl.mff.cuni.cz")
    
    #resitelak
    rr_page, url = get_html("https://karlin.mff.cuni.cz/resitel/")
    combined_events += extract_deadlines_rr(rr_page, url)
    
    #recodex
    combined_events += extract_deadlines_recodex("https://recodex.mff.cuni.cz/app")
    
    #build backup and preview .ics file
    #build_backup_ics(combined_events)

    sync_to_apple_calendar(combined_events)