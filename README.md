# Auto Shop Service Advisor

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
- Symptom intake collects up to 3 focused observations before routing, with a Skip question button.
- Symptom dates/times stay in the technician history; they do not fill appointment slots.
- Confirm suggested departments before proceeding. A suggestion is not a diagnosis.
- Start with the visible How can I help buttons or type a request. After the first turn,
  the buttons collapse under Need something else so they do not crowd the conversation.
- Contact a service advisor gives a human handoff message while keeping current details.
- Review the exact preview before a save. The model cannot write records.
- AI interprets agreement to routing separately from a scheduling question. Python
  advances the flow without treating routing agreement as permission to save.
- When specific work is not requested, the preview uses Diagnostic inspection of
  reported concern. This is a visit purpose, not a diagnosis or repair authorization.
- Corrections require a fresh preview and confirmation. A weekday-only change clears the old time.
- Clear agreement such as "Great yes please" works. Thanks alone and questions do not save.
- Being unsure about the cause keeps the suggested routing available. Casual routing agreement does not itself save a request.
- Asking for the soonest visit keeps appointment intent through later symptom replies.
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

Explicit danger and unsupported decisions take priority over ordinary intake.
Refusal messages survive model decline actions. Policy topics must match the
question before their documents are used. Follow-up observations survive note
revisions; requested service can use a factual service-only note without inventing
a vehicle fault.

- `app.py`: Streamlit interface, session state, controls, and request downloads.
- `advisor.py`: conversation flow, slot filling, correction, and consent control.
- `model_client.py`: structured Groq interpretation and response validation.
- `intake.py`: explicit safety boundaries, task/work checks, and retained observations.
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

Verification checkpoint: 70 no-key tests passed. The focused live samples completed
6 booking turns, 5 triage/summary turns, and 6 ticket turns. Earlier failed runs
remain in the development reports; they are not counted as passes. The model
request uses [Groq strict structured outputs](https://console.groq.com/docs/structured-outputs)
to prevent missing JSON fields, with Python validation still required for meaning,
customer evidence, exact values, and consent.

The reported no-start conversation was also replayed with the live model: 7 turns
reached available times while retaining the clicking symptom, appointment intent,
and confirmed electrical routing. Earlier failures remain in development reports.

## Continuity with Earlier Assignments

The capstone carries forward the 5 service departments and multiple matches from
Assignments 1 and 3, staged conversation and restart from Assignment 2, missing
slots, corrections, time validation and review-before-confirmation from Assignment
4, Groq, bounded conversation history, disclosure and failure handling from
Assignment 5, TF-IDF document retrieval from Assignment 6, and local availability
and record tools from Assignment 7. The code stays in small Python modules with
the Streamlit interface separate from conversation logic.

The scope uses 1 vehicle per request rather than Assignment 4's vehicle count.
Saved requests require a human for changes; corrections remain available before
saving. Model interpretation uses a complete structured response rather than
Assignment 5's streamed prose so Python can validate it before advancing or saving.

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

Simple displayed weekday/time choices and summary-definition questions work locally.
AI receives current state and issue history, not repeated chat previews. Rate-limit
responses use Retry-After when available and avoid more AI calls during that
session's cooldown. This reduces usage; it does not increase provider quotas.

Appointment intake shows available times before collecting identity. Choosing a
time does not save anything; customer name and vehicle remain required. Readable
starting/lighting observations survive note revisions. Identity and simple time
replies do not rewrite the technician note; original messages remain separate.

With 4 more weeks I would add a shared persistent database, calendar dates, a staff
view, shop-reviewed policies, and broader testing of ambiguous language.

Before grading, open the app in a private browser window, complete a conversation,
and check that no setup is required. Open it the night before and morning of the
deadline as the course recommends. The design PDF and a recorded demo of 5 minutes
or less must also be submitted; the code and app links do not replace them.
