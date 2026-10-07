"""Conversation state, slot filling, and confirmation control.
Calvin A. Prepetit - CSC-128 Capstone
"""
import re
from copy import deepcopy
from uuid import uuid4
from groq import APIConnectionError, APIError, AuthenticationError, RateLimitError
from knowledge import DEPARTMENTS, policy_answer
from model_client import MODEL, interpret
from tools import (find_openings, normalize_day, normalize_time, save_record,
                   validate_fields, slot_evidence)
from intake import (normalize, boundary, requested_intent, requested_work,
                    routine_service, policy_topic, preserve_observations)

GREETING = ("Welcome! I'm your Auto Shop Service Advisor.\n\n"
            "In your own words, describe what's going on with your vehicle. "
            "I'll help organize the details for the right department and technicians to review.\n\n"
            "I can help you:\n\n"
            "- Describe a vehicle concern and find the right service area.\n"
            "- Schedule a service appointment.\n"
            "- Prepare a service ticket.\n"
            "- Review a technician summary.\n\n"
            "Choose an option below, or type a message to get started.")
REFUSALS = {
    "price": "I cannot give an exact repair price. Please ask a human service advisor for pricing.",
    "warranty": "I cannot decide warranty coverage. Please ask the manufacturer or dealer to review it.",
    "insurance": "I cannot file or decide insurance claims. Please contact your insurer.",
    "recall": "I cannot look up recalls. Please check with the manufacturer or dealer.",
    "diagnosis": "I cannot diagnose the vehicle or promise a repair. A qualified technician must inspect it. I can help describe the concern for them.",
    "saved_change": "I cannot change or cancel a saved request. Please contact a human service advisor. Saved records are unchanged.",
    "unsafe": "I cannot determine whether the vehicle is safe to drive. For an immediate danger, get to safety if possible and contact emergency services or a towing provider. A qualified technician needs to assess the vehicle.",
    "unrelated": "I can help with vehicle service intake and the fictional shop guide. Please ask about one of those topics.",
}

def new_session(records=None):
    return {"messages": [{"role": "assistant", "content": GREETING}], "original_messages": [],
            "fields": {"customer_name": "", "vehicle": "", "expected_work": "", "day": "", "time": "", "departments": [], "summary": ""},
            "reasons": {}, "intent": "triage", "stage": "collect", "questions_asked": 0,
            "departments_confirmed": False, "revision": 0, "pending": None, "issue_messages": [], "last_question": "",
            "records": [] if records is None else records, "tool_log": [], "openings": [], "last_saved": None}

def friendly_error(error):
    if isinstance(error, RateLimitError):
        return "The advisor reached its rate limit. Please wait a minute and try again. No request was saved."
    if isinstance(error, (AuthenticationError, KeyError, FileNotFoundError)):
        return "The advisor connection is not configured correctly. Please try again later. No request was saved."
    if isinstance(error, (APIConnectionError, APIError)):
        return "The advisor is temporarily unavailable. Please try again later. No request was saved."
    return "I could not interpret that response reliably. Please rephrase or try again. No request was saved."

def invalidate(session):
    session["pending"] = None
    session["revision"] += 1
    if session["stage"] == "preview":
        session["stage"] = "change"

def consent_conflict(text):
    return bool("?" in text or re.search(r"\b(?:but|except|unless|if|instead|change|actually|also|add|only|maybe|might|yesterday|tomorrow|ignore|override|not|never|cancel)\b|\bdon t\b", normalize(text)))

def clear_agreement(text):
    """Common unambiguous replies need no API call; mixed replies still get interpreted."""
    if consent_conflict(text):
        return False
    return bool(re.fullmatch(
        r"(?:(?:great|okay|ok|perfect|thanks) )?"
        r"(?:yes|y|yep|yup|yeah|yea|confirm|correct|looks good|works for me|that works|go ahead(?: and (?:save|book) it)?|yes that s correct|yes thats correct)"
        r"(?: (?:please|thanks|thank you|thankyou|that s correct|thats correct))*", normalize(text)))

def uncertain_reply(text):
    return bool(re.fullmatch(
        r"(?:(?:i guess|honestly|to be honest) )?(?:i m |im |i am )?"
        r"(?:unsure|not sure|i don t know|i dont know|idk)"
        r"(?: (?:to be honest|honestly))?", normalize(text)))

def intake_question(session, proposed):
    """Keep common missing observations from being skipped by an empty model question."""
    details = normalize(session["fields"]["summary"] + " " + " ".join(session.get("issue_messages", [])))
    onset = re.search(r"\b(?:today|yesterday|morning|mornin|evening|ago|since|started|first noticed|monday|mondya|tuesday|wednesday|thursday|friday|saturday|sunday)\b", details)
    if session["questions_asked"] == 0 and not onset:
        return "When did you first notice the problem?"
    no_start = re.search(r"(?:won t|wont|will not|not|doesn t|doesnt).{0,18}(?:start|turn on|tur non)|no start", details)
    if no_start:
        if not re.search(r"\b(?:click|clicks|clicking|clickin|crank|cranks|cranking|silent|silence|nothing happens|no sound|buzz|buzzing)\b", details):
            return "What do you hear when you try to start it?"
        if not re.search(r"\b(?:lights?|dashboard|dash)\b", details):
            return "Do the dashboard lights turn on when you turn the key?"
    elif re.search(r"\b(?:rattle|rattles|rattling|rattlin|noise|squeak|squeaking|grinding)\b", details):
        if not re.search(r"\b(?:idle|idling|braking|accelerating|turning|driving|speed|stopped|moving|parked|sitting|starting|stop light)\b", details):
            return "When do you hear the noise?"
        if not re.search(r"\b(?:front|back|rear|underneath|under|inside|outside|wheel|engine|vents?)\b", details):
            return "Where does the noise seem to come from?"
    elif session["questions_asked"] == 1 and not proposed:
        return "What do you notice when the problem happens?"
    if re.search(r"when.*(?:hear|noise|sound|occur|hiss)", proposed, re.I) and re.search(
            r"\b(?:idle|idling|braking|accelerating|turning|driving|parked|starting|stop light)\b", details):
        return ""  # Do not ask for conditions the customer already supplied.
    return proposed

def openings_text(session):
    session["openings"] = find_openings(session["records"])
    session["tool_log"].append({"tool": "find_openings", "result": deepcopy(session["openings"])})
    if not session["openings"]:
        return "There are no remaining demo openings in this session. Please contact a human service advisor."
    return "Available demo intake times (repeating weekdays, not calendar dates):\n\n" + "\n".join(f"- {o['day']} at {o['time']}" for o in session["openings"])

def preview_text(pending):
    f = pending["fields"]
    label = {"appointment": "appointment request", "ticket": "service ticket", "summary": "technician summary"}[pending["kind"]]
    lines = [f"Please review this {label}:", f"Name: {f['customer_name'] or 'Not provided'}",
             f"Vehicle: {f['vehicle'] or 'Not provided'}", "Departments: " + ", ".join(f["departments"]),
             f"Visit: {f['day']} at {f['time']}" if f["day"] and f["time"] else "Visit: Not scheduled",
             f"Requested work: {f['expected_work'] or 'Not specified'}",
             "Technician note (customer-reported; not a diagnosis): " + f["summary"], "Original customer messages:"]
    lines.extend(f"> {text.replace(chr(10), chr(10) + '> ')}" for text in pending["original_messages"])
    lines.append("Reply yes to confirm these exact details, or tell me what to change. " +
                 ("This only confirms the summary; it does not save a ticket or reserve a time." if pending["kind"] == "summary"
                  else "This saves a fictional request in this browser session only."))
    return "\n\n".join(lines)

def prepare_preview(session, kind):
    if not session["fields"]["expected_work"]:
        session["fields"]["expected_work"] = "Diagnostic inspection of reported concern"
    if kind != "summary":
        validate_fields(session["fields"], session["departments_confirmed"], kind, session["records"])
    session["pending"] = {"kind": kind, "fields": deepcopy(session["fields"]), "original_messages": list(session["original_messages"]),
                          "revision": session["revision"], "confirmation_id": uuid4().hex}
    session["stage"] = "preview"
    session["tool_log"].append({"tool": "prepare_preview", "kind": kind, "revision": session["revision"]})
    return preview_text(session["pending"])

def advance(session):
    f = session["fields"]
    if not f["summary"]:
        return "Tell me what is happening with your vehicle or what service you need."
    if not f["departments"]:
        return "I cannot confidently route this concern. A human service advisor should review it. You can add a little more detail if you know it."
    if not session["departments_confirmed"]:
        session["stage"] = "departments"
        suggestions = "\n".join(f"- {d.title()}: {session['reasons'].get(d) or DEPARTMENTS[d]}" for d in f["departments"])
        return ("Here is the technician note so far:\n\n" + f["summary"] +
                "\n\nSuggested departments for inspection, not a diagnosis:\n\n" + suggestions +
                "\n\nDoes this note describe the concern correctly? Reply yes to use this intake routing, or tell me what to change.")
    if session["intent"] == "triage":
        session["stage"] = "routed"
        return "Confirmed departments: " + ", ".join(f["departments"]) + ". I can now show available appointments, create an unscheduled service ticket, or review a technician summary."
    if session["intent"] == "summary":
        return prepare_preview(session, "summary")
    missing = [label for key, label in (("customer_name", "name"), ("vehicle", "vehicle year, make, and model (or the details you know)")) if not f[key]]
    if missing:
        session["stage"] = "collect"
        return "Please provide your " + " and ".join(missing) + ". I will keep the issue details already provided."
    kind = session["intent"]
    if kind == "appointment" or f["day"] or f["time"]:
        openings = openings_text(session)
        if {"day": f["day"], "time": f["time"]} not in session["openings"]:
            session["stage"] = "schedule"
            return openings + "\n\n" + ("Your selected time is unavailable. " if f["day"] and f["time"] else "") + "Which day and time would you like?"
    return prepare_preview(session, kind)

def apply_updates(result, text, session):
    """Evidence must come from this message; exact values are validated in Python."""
    first_concern = not session["fields"]["summary"]
    old_departments = list(session["fields"]["departments"])
    updates = result["updates"]
    if set(updates) - {"customer_name", "vehicle", "day", "time", "expected_work"}:
        raise ValueError("Unsupported field")
    parsed = {}
    # Day is always processed before shorthand time, independent of JSON key order.
    for key in ("customer_name", "vehicle", "day", "time", "expected_work"):
        if key not in updates:
            continue
        item = updates[key]
        if item is None or item == {} or item == {"value": "", "evidence": ""}:
            continue  # Empty optional slots mean no proposed value, never an accepted value.
        if not isinstance(item, dict) or set(item) != {"value", "evidence"}:
            raise ValueError("Invalid extraction")
        value, evidence = item["value"], item["evidence"]
        if key == "expected_work" and (not isinstance(evidence, str) or evidence not in text or not isinstance(value, str) or value.casefold() not in evidence.casefold()):
            # Optional work must be explicitly requested; retain original symptoms instead.
            continue
        if key == "expected_work" and not requested_work(value, text):
            continue
        # Some models echo unchanged slots. They cannot introduce a new value this way.
        if isinstance(value, str) and value == session["fields"].get(key) and isinstance(evidence, str) and evidence not in text:
            continue
        if key in {"day", "time"} and isinstance(value, str) and isinstance(evidence, str) and evidence not in text:
            evidence = slot_evidence(key, value, text)
        if not isinstance(value, str) or not isinstance(evidence, str) or not evidence.strip() or evidence not in text or len(value) > 160:
            raise ValueError("Extracted field lacks customer evidence")
        if key in {"customer_name", "vehicle", "expected_work"}:
            if value.casefold() not in evidence.casefold() or not value.strip():
                raise ValueError("Unsupported extracted text")
            parsed[key] = value.strip()
            if key == "expected_work":
                work = normalize(value)
                if "tire" in work and re.search(r"\b(?:change|changed|replace|replaced|replacement)\b", work):
                    parsed[key] = "Customer-requested tire replacement"
        elif key == "day":
            if re.search(r"\b(?:today|tomorrow|yesterday|(?:next|this|coming)\s+(?:week|monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b", text, re.I):
                raise ValueError("Please use a weekday without a relative calendar date.")
            days = re.findall(r"\b(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs?(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b", evidence, re.I)
            if len(set(d.lower() for d in days)) > 1:
                raise ValueError("Ambiguous day")
            parsed[key] = normalize_day(days[0] if days else evidence)
        else:
            matches = re.findall(r"(?<![\w:])(\d{1,2}(?::[0-5]\d)?\s*[ap](?:\.?m\.?)?|\d{1,2}:[0-5]\d|noon)(?![\w:])", evidence, re.I)
            token = matches[0] if len(matches) == 1 else evidence
            try:
                parsed[key] = normalize_time(token)
            except ValueError:
                if not re.fullmatch(r"\d{1,2}(?::[0-5]\d)?", evidence.strip()):
                    raise
                day = parsed.get("day", session["fields"]["day"])
                matches = [o["time"] for o in session["openings"] if (not day or o["day"] == day)
                           and (o["time"].split(":")[0] == evidence.strip() or o["time"].split()[0] == evidence.strip())]
                if len(set(matches)) != 1:
                    raise ValueError("Ambiguous time")
                parsed[key] = matches[0]
    if "day" in parsed and parsed["day"] != session["fields"]["day"] and "time" not in parsed:
        parsed["time"] = ""
    session["fields"].update(parsed)
    if result["summary"] and result["has_issue"]:
        session["fields"]["summary"] = result["summary"]
    if result["has_issue"] or first_concern:
        if result["summary"]:
            session["fields"]["summary"] = result["summary"]
        elif first_concern and result["has_issue"]:
            work = session["fields"]["expected_work"]
            session["fields"]["summary"] = (f"Customer requests {work}." if work
                                             else "Customer reports: " + text)
        departments = list(dict.fromkeys(result["departments"]))
        if departments:
            session["fields"]["departments"] = departments
            session["reasons"] = result["reasons"]
        if re.search(r"\b(?:not|isn t|isnt)\s+(?:the )?(?:ac|a c|air conditioning)\b", normalize(text)):
            session["reported_vent_source"] = False
        if re.search(r"\b(?:ac|a c|air conditioning)\s+vents?\b", normalize(text)) and not re.search(r"\b(?:not|isn t|isnt)\s+(?:the )?(?:ac|a c|air conditioning)\b", normalize(text)):
            session["reported_vent_source"] = True
            if "interior" not in session["fields"]["departments"]:
                session["fields"]["departments"].append("interior")
            session["reasons"]["interior"] = "Possible cabin vent source reported by the customer; inspection is needed."
        if first_concern or session["fields"]["departments"] != old_departments:
            session["departments_confirmed"] = False
    elif result["action"] == "revise" and result["departments"] and result["departments"] != session["fields"]["departments"]:
        session["fields"]["departments"] = result["departments"]
        session["reasons"] = result["reasons"]
        session["departments_confirmed"] = False
    if session.get("reported_vent_source") and "vent" not in session["fields"]["summary"].lower():
        session["fields"]["summary"] += " Customer reports a possible AC-vent source; location is uncertain."

def confirm(session):
    if session["stage"] == "departments":
        session["departments_confirmed"] = True
        return advance(session)
    pending = session["pending"]
    if pending:
        if pending["kind"] == "summary":
            session["pending"] = None
            session["stage"] = "summary_done"
            return "The technician summary is confirmed for this conversation. No ticket or appointment was saved. You can ask to create a service ticket or choose an appointment."
        try:
            record = save_record(pending, session)
        except Exception:
            invalidate(session)
            session["stage"] = "schedule"
            return "The request was not saved. Please check the details and available times, then request a fresh preview."
        session["pending"] = None
        session["last_saved"] = record["id"]
        session["stage"] = "saved"
        session["tool_log"].append({"tool": "save_record", "id": record["id"]})
        return f"Saved demo {record['kind']} {record['id']}. Your reviewed details and original messages are included. This is stored only in this browser session. To change a saved request, contact a human service advisor."
    if session["last_saved"]:
        return f"Request {session['last_saved']} is already saved. No duplicate was created."
    return "There is no preview waiting for confirmation. Tell me what you would like help with."

def handle(text, session, client_factory, control=None):
    clean = normalize(text)
    if clean in {"cancel", "restart", "start over"}:
        records = session["records"]
        session.clear()
        session.update(new_session(records))
        return "The unfinished conversation was cleared. Saved requests are unchanged. " + GREETING
    if re.search(r"\b(?:delete|erase|wipe)\b.*\b(?:records?|requests?|appointments?|everything)\b", clean):
        return "I cannot delete saved records. Type cancel to discard an unfinished conversation."
    if control == "human" or re.search(r"\b(?:talk|speak|connect) (?:to|with) (?:a |an |the )?(?:someone|person|human|advisor|service advisor|technician)\b", clean):
        return ("For a person to help, please contact the shop directly. This classroom demo "
                "cannot connect you to a live employee. I can help prepare a technician summary "
                "to share with a service advisor. Your current details are still here.")
    refusal = boundary(text) if not control else ""
    if refusal:
        invalidate(session)
        session["tool_log"].append({"tool": "intake_boundary", "reason": refusal})
        return REFUSALS[refusal]
    answering_issue = session["stage"] == "clarify" and not control
    if control == "confirm" or (not answering_issue and clear_agreement(text)):
        return confirm(session)
    if control == "skip":
        return advance(session)
    if session["stage"] == "departments" and uncertain_reply(text):
        return ("You do not need to know the cause or choose a department yourself. "
                "This is just a suggested starting point for a technician to inspect. "
                "May I use " + ", ".join(session["fields"]["departments"]) +
                " for the intake? Reply yes or choose Confirm departments. Nothing is booked yet.")
    if session["stage"] == "departments" and clean in {"sure", "sure why not", "sur why not", "sounds good", "that sounds good"}:
        return confirm(session)
    if session["stage"] == "clarify" and uncertain_reply(text):
        return advance(session)
    if clean in {"no", "no thanks"} and not answering_issue:
        invalidate(session)
        session["stage"] = "change"
        return "No request was saved. Tell me what to change, or type cancel."
    if clean in {"thanks", "thank you", "great thanks", "thankyou", "okay thanks"}:
        return "You're welcome. " + ("Your preview is still waiting for confirmation; nothing was saved." if session["pending"] else "Tell me what else you need help with.")
    if control in {"triage", "appointment", "ticket", "summary"}:
        if session["last_saved"]:
            return "Start Over to begin a new request. " + REFUSALS["saved_change"]
        invalidate(session)
        session["intent"] = control
        return advance(session)
    if control == "openings":
        return openings_text(session)
    if clean in {"what should i bring", "what should i bring to drop off"}:
        return policy_answer("bring", text)
    if re.fullmatch(r"(?:is this|is it|are we) (?:saved|booked|confirmed)(?: already)?", clean):
        return (f"Request {session['last_saved']} is already saved." if session["last_saved"]
                else "This request is not saved. " + ("Your displayed preview is still waiting for confirmation." if session["pending"] else "Complete and review the details first."))
    if session["pending"] and consent_conflict(text) and "?" not in text:
        invalidate(session)
    result = interpret(text, session, client_factory())
    # Task choice and explicit work survive a model's overly broad triage label.
    task = requested_intent(text)
    if task:
        result["intent"] = task
    elif session["intent"] in {"appointment", "ticket", "summary"} and result["intent"] == "triage":
        result["intent"] = "continue"
    work = result["updates"].get("expected_work")
    if isinstance(work, dict) and isinstance(work.get("value"), str) and requested_work(work["value"], text):
        result["has_issue"] = True
    result["policy_topic"] = policy_topic(text, result["policy_topic"])
    routing_ok = (session["stage"] == "departments" and result["routing_agreement"]
                  and not consent_conflict(text.replace("?", ""))
                  and (not result["has_issue"] or not result["departments"]
                       or set(result["departments"]) == set(session["fields"]["departments"])))
    if routing_ok:
        # Agreement to routing plus a visit question is not consent to save a record.
        result["has_issue"] = False
        result["summary"] = ""
    # Symptom history is not a requested appointment, even if it contains a weekday/time.
    explicit_visit = bool(re.search(r"\b(?:book|schedule|appointment|visit|bring|drop off|come in)\b", clean))
    past_event = bool(re.search(r"\b(?:tried|started|noticed|heard|happened|this morning|yesterday)\b", clean))
    identity_only = (not result["has_issue"] and any(result["updates"].get(key) for key in ("customer_name", "vehicle")))
    symptom_answer = answering_issue and not explicit_visit and not identity_only
    if symptom_answer or (past_event and result["has_issue"] and not explicit_visit):
        result["updates"].pop("day", None)
        result["updates"].pop("time", None)
    if symptom_answer:
        result["has_issue"] = True
        result["action"] = "provide"
        result["intent"] = "continue"
    asks_for_visit = bool(re.search(r"\b(?:soonest|earliest)\b|\bwhen(?:s| can| could| would).*\b(?:look|bring|take|appointment|available)\b", clean))
    if asks_for_visit and not result["refusal"]:
        result["intent"] = "appointment"
    elif session["intent"] == "appointment" and result["intent"] == "triage" and result["has_issue"]:
        result["intent"] = "continue"
    if result["action"] == "cancel":
        return handle("cancel", session, client_factory)
    prefixes = []
    if result["refusal"]:
        prefixes.append(REFUSALS[result["refusal"]])
        if result["refusal"] in {"saved_change", "unsafe", "unrelated"}:
            return prefixes[0]
    if result["policy_topic"]:
        prefixes.append(policy_answer(result["policy_topic"], text))
        session["tool_log"].append({"tool": "policy_answer", "topic": result["policy_topic"]})
    prefix = "\n\n".join(prefixes)
    if session["last_saved"]:
        if result["action"] == "confirm" and not consent_conflict(text):
            return confirm(session)
        return prefix or "Your saved request is unchanged. Start Over for a new request. " + REFUSALS["saved_change"]
    intent_changed = result["intent"] not in {"continue", "information"} and result["intent"] != session["intent"]
    changing = bool(result["updates"] or result["has_issue"] or result["action"] == "revise" or intent_changed or routing_ok)
    if result["action"] == "confirm" and not changing and not consent_conflict(text):
        return (prefix + "\n\n" if prefix else "") + confirm(session)
    if result["action"] == "decline":
        return prefix or handle("no", session, client_factory)
    if not changing and (result["action"] in {"question", "other"} or prefix):
        return prefix or ("No request was saved. Ask about the displayed details, tell me what to change, or reply yes to confirm." if session["pending"] else advance(session))
    candidate = deepcopy(session)
    invalidate(candidate)
    try:
        apply_updates(result, text, candidate)
        if result["has_issue"]:
            preserve_observations(candidate, text, session["last_question"] if symptom_answer else "")
    except ValueError as error:
        invalidate(session)
        session["tool_log"].append({"tool": "validate_updates", "error": str(error), "updates": result["updates"]})
        return "I could not validate those details. Please give the correction again, using a weekday and a time such as 9am when scheduling. No request was saved."
    if result["intent"] not in {"continue", "information"}:
        candidate["intent"] = result["intent"]
    if routing_ok:
        candidate["departments_confirmed"] = True
    if candidate["intent"] == "ticket" and re.search(r"\b(?:unscheduled|without an? appointment|no appointment)\b", clean):
        candidate["fields"]["day"] = candidate["fields"]["time"] = ""
    session.update(candidate)
    if result["has_issue"] and not control:
        session.setdefault("issue_messages", []).append(text)
    clarification = result["clarification"].strip()
    routine = routine_service(text)
    if result["has_issue"] and session["questions_asked"] == 0 and not routine and not session["departments_confirmed"]:
        clarification = intake_question(session, clarification)
    elif symptom_answer:
        clarification = intake_question(session, clarification)
    if result["has_issue"] and clarification and session["questions_asked"] < 3 and not routine and not session["departments_confirmed"]:
        question = clarification.split("?")[0].strip(" -\n") + "?"
        if question == session.get("last_question"):
            return (prefix + "\n\n" if prefix else "") + advance(session)
        session["questions_asked"] += 1
        session["last_question"] = question
        session["stage"] = "clarify"
        return (prefix + "\n\n" if prefix else "") + question + "\n\nIf you are unsure, say so or choose Skip question."
    return (prefix + "\n\n" if prefix else "") + advance(session)

def process_turn(text, session, client_factory, control=None):
    if not isinstance(text, str) or not text.strip():
        return "Please describe your vehicle issue."
    if len(text) > 3000:
        return "Please keep each message under 3,000 characters so I can process it reliably."
    if not control:
        session["original_messages"].append(text)
    session["messages"].append({"role": "user", "content": text})
    try:
        reply = handle(text, session, client_factory, control)
    except Exception as error:
        invalidate(session)
        reply = friendly_error(error)
    session["messages"].append({"role": "assistant", "content": reply})
    return reply
