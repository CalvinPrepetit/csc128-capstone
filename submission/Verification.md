# Final capstone verification

Calvin A. Prepetit | October 9, 2026

## Alignment

- Official local folder: `csc128/csc128-capstone`.
- Public repository: https://github.com/CalvinPrepetit/csc128-capstone
- Deployment: https://calvinprepetit-auto-shop.streamlit.app/
- Streamlit management shows `calvinprepetit/csc128-capstone/main/app.py`.
- Streamlit sharing shows `Make this app public` enabled; no permission change was needed.
- App-code checkpoint: `e38d08b`; final document commits do not change app behavior.
- Direct dependencies are pinned. `git check-ignore -v .streamlit/secrets.toml`
  confirms protection; no local key file is tracked. Cloud Secrets remain separate.
- GitHub publishing works with the repository-local username CalvinPrepetit.

## Tests

All 122 no-key tests pass from the official folder. These include state, slot
validation, four intents, confirmation, correction, duplicate prevention, bad
model responses, API failure, rate limits, empty retrieval, and the interface.
The test runner uses simulated model responses, not proof of all live language.

## Final live rehearsal

- `My car isnt starting` entered a focused interview instead of a restart loop.
  Follow-up answers were collected locally; two AI interpretations produced the
  question plan and cumulative technician note.
- The note retained clicking, dashboard lights, onset, and battery uncertainty,
  routed to Electrical, and offered scheduling without automatically saving.
- Openings appeared before identity. Friday was corrected to Monday at 11 AM.
  Reviewed fictional appointment `APT-6ADB42FEEF` saved successfully. Another yes
  reported the existing identifier and did not create a duplicate.
- Tire replacement and oil change both remained in the Maintenance note.
  Standalone summary confirmation saved no request or appointment.
- Switching that summary to a service ticket saved `SR-FF0673762A`, with
  `Visit: Not scheduled` and both requested jobs.
- What-to-bring showed the fictional Vehicle Check-In Guide source.
- Warranty coverage received manufacturer/dealer handoff, not a coverage decision.
- Simulated outage showed a usable retry message with no traceback or new save.
  Saved requests still contained only the appointment and ticket above; simulation
  was turned off afterward. No rate-limit response occurred in the final rehearsal.

## Scope and limits

The four outcomes are triage/routing, appointment, unscheduled ticket, and summary
review without saving. All records above are disposable browser-session demo
records, not real shop reservations. AI may repeat a fact or vary its questions;
customers must review previews. Provider availability, sleep behavior, and the
instructor's grade cannot be guaranteed. Record the <=5-minute video, including
simulated failure and one improvement, and submit both public links and the PDF.
