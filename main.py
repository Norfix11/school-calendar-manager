from deadline_sources import (
    get_html,
    extract_deadlines_nt,
    extract_deadlines_owl,
    extract_deadlines_rr,
    extract_deadlines_recodex,
)
from calendar_export import build_backup_ics, sync_to_apple_calendar
from event_storage import save_events, load_events, merge_events



def main():
    live_mode = True

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
            saved_events = load_events()
        except FileNotFoundError:
            saved_events = []

        combined_events = merge_events(saved_events, live_events)
        save_events(combined_events)

    else:
        try:
            combined_events = load_events()
        except FileNotFoundError:
            raise SystemExit("Offline data file not found: data/sample_deadlines.json.")

    
    #build backup and preview .ics file
    build_backup_ics(combined_events)

    #sync_to_apple_calendar(combined_events)



if __name__ == "__main__":
    main()