# Demonstration datasets

Run `python main.py`, select a dataset, and click **Open dataset**, then **Build my plan**.
Opening a demo sets the planning start to **24 September 2026** and the forecast end to
**21 October 2026**. The filenames contain synthetic assignments, not real course data.

| Dataset | Total tasks | Completed history | Unfinished | What to demonstrate |
| --- | ---: | ---: | ---: | --- |
| `demo_01_learning.json` | 47 | 42 | 5 | Learning different course durations, weekly recurrence, varying assignment counts |
| `demo_02_deadline_crunch.json` | 53 | 40 | 13 | Crowded deadlines, early submission times, overload warnings and an overdue task |
| `demo_03_mixed_patterns.json` | 41 | 33 | 8 | Weekly and biweekly courses, irregular milestones, known future deadlines and a break |
| `demo_04_large_benchmark.json` | 396 | 324 | 72 | Eighteen weeks of history across six subjects, large grouped scheduling and prediction |

## Suggested walkthrough

1. Open **Learning & weekly recurrence**. The original estimates are two hours, but the
   work plan learns from actual hours in the completed history. Inspect all three results tabs.
2. Edit an unfinished task, mark it completed, and enter its actual total hours. Rebuild
   the plan to see the remaining workload change. Use **Save a copy** to keep the edit.
3. Open **Deadline crunch**. One task is already overdue; twelve can still be scheduled.
   Compare daily overload risk with weekly risk. Set some weekday allowances to zero or
   raise them to see how the recommended workdays change.
4. Open **Mixed patterns & a holiday**. A break from **5 to 11 October** is prefilled.
   Compare predictions with and without that break. The break changes recurrence forecasts,
   not the amount of time available for studying.
5. Open **Large benchmark**. There are 324 completed tasks and 72 unfinished tasks.
   Three upcoming rounds per subject are already published. The fourth is deliberately
   absent: the default forecast produces six predictions, each with a 95% occurrence
   probability. All 72 unfinished tasks should appear in the plan.

The large benchmark deliberately has repeated two-hour expected durations, which lets
the scheduler group tasks efficiently. It demonstrates that optimization; it is not a
worst-case performance guarantee for many different durations and distant deadlines.
The interface displays elapsed analysis time. Timings depend on the machine and settings.

The first three demos produce 9, 12 and 4 predictions respectively with their default
dates, allowances, and breaks. The second demo's overdue task is listed separately.

## Working with your own data

- JSON datasets remain ordinary event lists, compatible with `event_storage.py`.
- Put a JSON file in `data`, reload the page, then select it. **Merge into current** uses
  the existing subject/title matching and preserves stored feedback.
- Edits stay in memory until **Save**. Demo files are protected by the interface: save
  an edited copy under another name.
- **Export calendar** downloads known deadlines as ICS. Predictions and work sessions
  are not calendar events. You can include or exclude completed history.
- On macOS, the same dialog also offers **Sync to Apple Calendar**. It requires confirmation
  because it replaces all events in the existing **Homework Deadlines** calendar with the
  selected tasks. It does not save JSON changes. Direct sync is unavailable on Windows;
  ICS download still works. No automatic or periodic sync is enabled.
- **Refresh sources** merges fetched tasks into the open workspace. Public course pages
  need no login. Owl and ReCodEx retain the existing workflow: log in in the opened browser,
  then press Enter in the terminal. Refresh does not automatically save changes.
- `python main.py --cli` runs the original console workflow.
- The local server stops with Ctrl+C in its terminal. Keep only one editing tab open;
  tabs share the same workspace. Planning settings are per browser page and are not stored
  in the event JSON.

Risk values are model estimates. The forecast window limits predicted assignments and
weekly reporting, while the planner still considers all known unfinished deadlines.
