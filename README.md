# Auto Shop Service Advisor and Intake Bot

Calvin A. Prepetit - CSC-128 Capstone

I am continuing the auto shop theme from my earlier assignments. This bot will help
customers explain vehicle problems and prepare a service request without needing
to know automotive terms or choose a department first.

## Current Checkpoint

This is the first deployment shell, not the completed capstone. It has a Streamlit
chat interface, model conversation history, processing feedback, a Start Over
button, original customer messages stored directly by Python, and handled model
errors. It uses the same Groq model as my earlier assignments.

Appointment availability, slot filling, confirmed department selections, ticket
creation, document grounding, and technician summary confirmation are still to be
added. This checkpoint does not meet all 7 required capstone capabilities yet.

## Planned Capabilities

| Intent | Input | Output |
| --- | --- | --- |
| Service issue triage | Customer issue description and relevant follow-up details | Suggested departments with a short explanation for customer review |
| Appointment setting | Preferred appointment details | A validated selection from available demo times |
| Service request ticket creation | Reviewed issue and visit details | A saved request with a Python-generated ticket ID |
| Technician intake summary and confirmation | Collected details and original customer wording | A reviewable summary and exact preview before any request is saved |

The approved departments are electrical, drivability, interior, exterior, and
maintenance. More than 1 department may apply. The model will interpret language;
Python will control accepted values, availability, confirmation, IDs, and writes.

## Run

Use Python 3.13, the version used for the local shell checks.

```text
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Create a private `.streamlit/secrets.toml` using `secrets.toml.example` as a guide.
Never commit the real key. Set `GROQ_API_KEY` separately in Streamlit Community
Cloud's Secrets settings when deploying. The entry point is `app.py` at the root.

```text
git check-ignore -v .streamlit/secrets.toml
python -m unittest -v
```

The tests use simulated model responses and failures. They check history,
original wording, restart, rate limits, malformed responses, and interface startup.
They do not prove live model understanding or successful public deployment.

## Storage and Limits

This is automated software for a fictional classroom shop. Messages are sent to
Groq to generate replies. Use fictional customer details. Conversation data is
stored only in the browser session and may be lost on refresh. Start Over or
typing cancel clears the conversation. No appointments or tickets are saved yet.

The bot must not quote exact prices, decide warranty coverage, handle insurance
claims, look up recalls, or make definitive diagnoses. Those requests require an
appropriate service advisor, manufacturer, insurer, or qualified technician.

## Deployment and Remaining Work

After deployment, open the public URL in a private browser window and test a live
conversation. Check API failure behavior and cold startup separately. Open the
app the night before and morning of grading, as the course setup recommends.

Next: implement and verify the 4 flows, add the small fictional document set,
record actual testing failures and fixes, and complete the 2-3 page design PDF
and demo recording of 5 minutes or less. Final submission is due October 9, 2026,
at 11:59 PM Eastern.
