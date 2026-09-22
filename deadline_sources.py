from datetime import datetime
import re
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright



def get_html(url: str) -> tuple[str, str]:
    '''Returns the whole string of the website's html'''
    
    response = requests.get(url)
    response.encoding = "utf-8"
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
                            event.append({"title": title, "due_date": date, "description": url + event_reference, "subject": subject})
                        
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
                    
                    event.append({"title": f"{subject} {title}", "due_date": date, "description": url + event_reference, "subject": subject})
                
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
            
            event.append({"title": f"Teorie čísel {title}", "due_date": date, "description": new_url, "subject": "Teorie čísel"})
            
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
            date_string = contents[1].get_text().strip("()– \n\r")
            date = datetime.strptime(date_string, "do %d. %m. %Y").date()
            
            event.append({"title": f"Řešitelský seminář {title}", "due_date": date, "description": url + reference, "subject": "Řešitelský seminář"})
    
    return event