# Auto Shop Service Advisor and Intake Bot

Calvin A. Prepetit - CSC-128 Capstone

[Open the app](https://calvinprepetit-auto-shop.streamlit.app/)

I continued the auto shop theme from my earlier assignments. A customer can
describe a problem in their own words without knowing the part name or department.
The bot asks a focused question when useful, suggests service areas, and helps
prepare an appointment request, service ticket, or technician summary.

## 4 Main Intents

| Intent | Input | Result |
| --- | --- | --- |
| Service issue triage | Customer description and useful follow-up details | Explained department suggestions for customer confirmation |
| Appointment setting | Concern, name, vehicle, available weekday/time | Confirmed demo appointment request with an APT identifier |
| Service request ticket creation | Reviewed customer and issue details, with an optional appointment | Saved service ticket with an SR identifier |
| Technician intake summary and confirmation | Collected concern and original messages | Reviewable service note; confirmation alone does not save or reserve anything |

The departments are electrical, drivability, interior, exterior, and maintenance.
More than 1 may apply. General intake openings serve all 5 departments, so the
schedule does not substitute Assignment 7's 3 scheduling categories for them.
Each request covers 1 vehicle. For another vehicle, start a separate request.

## Conversation and Confirmation

- Give all your details at once or supply missing details later.
- Clarification is limited to 2 questions, with a Skip question button.
- Confirm suggested departments before proceeding. A suggestion is not a diagnosis.
- Ask for appointments, a ticket, or a summary in chat, or use Choose what you need.
- Review the exact preview before a save. The model cannot write records.
- Corrections require a fresh preview and confirmation. A weekday-only change clears the old time.
- Clear agreement such as "Great yes please" works. Thanks alone and questions do not save.
- Repeated confirmation does not create duplicates. Reserved times disappear from this session's openings.
- Cancel or Start Over clears unfinished work while preserving this session's saved requests.
- Changes to saved records require a human service advisor. There is no deletion tool.

## Code and Model Responsibilities

The model interprets language, proposes extracted values, suggests departments,
chooses clarification, and drafts the technician note. Python validates values
against customer evidence and the approved lists. It owns availability, exact
appointment values, confirmation state, identifiers, and committed records.

Original messages are stored directly from conversation data, alongside the note.
The model is not responsible for copying them. Model notes can omit details, so
customers review the summary and can correct it before saving.

The small fictional document set covers departments, drop-off, what to bring,
hours, and demo limitations. Retrieval reuses Assignment 6's TF-IDF approach.
Policy answers display approved text and deterministic source labels. An empty
result refers the customer to a human. The local tools check openings, prepare
previews, and save validated requests.

## Files

- `app.py`: Streamlit interface, session state, controls, and request downloads.
- `advisor.py`: conversation flow, slot filling, correction, and consent control.
- `model_client.py`: structured Groq interpretation and response validation.
- `tools.py`: exact values, availability, record validation, and saves.
- `knowledge.py`: fictional guide and small retriever.
- `test_advisor.py`: deterministic and simulated failure tests; no API key required.

The design PDF and personal demo materials are separate submission deliverables.

## Run and Deploy

Tested with Python 3.13.15. Direct dependency versions are pinned.

```text
python -m pip install -r requirements.txt
python -m unittest -v
python -m streamlit run app.py
```

Put `GROQ_API_KEY` in your private `.streamlit/secrets.toml`, using
`secrets.toml.example` as the format. Verify protection before pushing:

```text
git check-ignore -v .streamlit/secrets.toml
```

Deploy repository `CalvinPrepetit/csc128-capstone`, branch `main`, entry point
`app.py`, Python 3.13. Configure the key separately in Streamlit's Secrets settings.
The deployed app does not require visitors to bring a key or install software.

## Testing

The no-key suite checks distinct intents, all-at-once and later slot filling,
multiple departments, corrections, shorthand times, natural agreement, questions,
cancel/restart, duplicate writes, unavailable/reserved slots, original wording,
refusals, empty retrieval, malformed output, API failures, rate limits, and write
failures. Streamlit's interface is also tested with a simulated outage.

Paced live conversation reports are kept in the external Auto Shop Bot Checks
folder, separately from simulated tests. Actual failures found during development
included excess questions, an appointment question staying in triage, a natural
agreement causing a preview loop, and optional extraction fields blocking intake.
The design document explains the main changes. Passing focused samples does not
prove every possible conversation will work.

Verification checkpoint: 29 no-key tests passed. The focused live samples completed
6 booking turns, 5 triage/summary turns, and 6 ticket turns. Earlier failed runs
remain in the development reports; they are not counted as passes. The model
request uses [Groq strict structured outputs](https://console.groq.com/docs/structured-outputs)
to prevent missing JSON fields, with Python validation still required for meaning,
customer evidence, exact values, and consent.

To demonstrate failure without consuming API quota, enable Simulate API outage
in the sidebar, submit a new issue, show the recovery message, and turn it off.
The Confirm button and local read-only functions can still work without the API.

## Storage, Refusals, and Limits

This is a fictional classroom app, not a real booking system. Requests and reserved
times exist only in the current browser session. Refreshing or closing that session
can lose them. Different visitors have separate schedules. Download demo requests
before leaving if you want a copy. Weekdays repeat; there are no calendar dates.

Messages are sent to Groq. Use fictional customer details. The bot cannot quote
exact prices, decide warranty coverage, handle insurance claims, look up recalls,
or diagnose a vehicle. It refers these to the appropriate advisor, manufacturer,
insurer, or technician. It cannot declare a vehicle safe to drive.

With 4 more weeks I would add a shared persistent database, calendar dates, a staff
view, shop-reviewed policies, and broader testing of ambiguous language.

Before grading, open the app in a private browser window, complete a conversation,
and check that no setup is required. Open it the night before and morning of the
deadline as the course recommends. The design PDF and a recorded demo of 5 minutes
or less must also be submitted; the code and app links do not replace them.
