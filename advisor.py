"""Conversation state, slot filling, and confirmation control.
Calvin A. Prepetit - CSC-128 Capstone
"""
import re
import math
import time
from copy import deepcopy
from uuid import uuid4
from groq import APIConnectionError, APIError, AuthenticationError, RateLimitError
from knowledge import DEPARTMENTS, policy_answer
from model_client import MODEL, interpret
from tools import (find_openings, normalize_day, normalize_time, save_record,
                   validate_fields, slot_evidence, visit_selection)
from intake import (normalize, boundary, requested_intent, requested_work,
                    routine_service, routine_requests, policy_topic, preserve_observations, moving_stall, stalling_note,
                    readable_fallback, tire_request, suspected_location, ac_request, requested_parts)

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

def retry_seconds(error):
    try:
        return max(1, math.ceil(float(error.response.headers.get("retry-after", "60"))))
    except (AttributeError, ValueError, OverflowError):
        return 60


def rate_limit_message(seconds):
    return (f"The advisor reached its rate limit. Please try again in about {seconds} seconds. "
            "Your intake details are still here; no request was saved. "
            "You can still view openings or select a displayed time. "
            "If the limit persists, the provider may have exhausted a daily allowance.")


def friendly_error(error):
    if isinstance(error, RateLimitError):
        return rate_limit_message(retry_seconds(error))
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
    clean = re.sub(r"\b(?:pelas e|pleas e|pelase|pleae|plesae)\b", "please", normalize(text))
    clean = re.sub(r"^(?:thankyou|thank you|thanks)(?: so much)?\s+", "", clean)
    return bool(re.fullmatch(
        r"(?:(?:great|okay|ok|perfect|thanks) )?"
        r"(?:yes|y|yep|yup|yeah|yea|confirm|correct|seems correct|that seems correct|looks good|works for me|that works|go ahead(?: and (?:save|book) it)?|yes that s correct|yes thats correct)"
        r"(?: (?:please|thanks|thank you|thankyou|that s correct|thats correct|that looks (?:fine|good)|that works|looks fine|it does|it is|it looks good))*", clean))

def uncertain_reply(text):
    return bool(re.fullmatch(
        r"(?:(?:i guess|honestly|to be honest) )?(?:i m |im |i am )?"
        r"(?:unsure|not sure|i don t know|i dont know|idk)"
        r"(?: (?:to be honest|honestly))?", normalize(text)))

def intake_question(session, proposed):
    """Keep common missing observations from being skipped by an empty model question."""
    details = normalize(session["fields"]["summary"] + " " + " ".join(session.get("issue_messages", [])))
    if session.get("ac_inspection_requested") and not session.get("ac_detail_collected"):
        return "What would you like the technician to check about the AC?"
    if "restarted before shutting off again" in details and "lights remained on" in details:
        return ""  # This customer's stalling sequence already supplies useful observations.
    known = session.get("intake_details", {})
    onset = known.get("onset") or re.search(r"\b(?:last week|last month|today|yesterday|morning|mornin|evening|ago|since|started|first noticed|monday|mondya|tuesday|wednesday|thursday|friday|saturday|sunday)\b", details)
    conditions = known.get("conditions") or re.search(r"\b(?:idle|idling|braking|accelerating|turning|driving|dirve|drive|speed|stopped|moving|movin|parked|sitting|starting|stop light)\b|\b(?:over|above|under|below) \d+\b", details)
    location = known.get("location") or re.search(r"\b(?:front|back|rear|underneath|under|inside|outside|wheels?|tires?|tyres?|engine|muffler|exhaust|hood|vents?)\b", details)
    if session["questions_asked"] == 0 and not onset:
        return "When did you first notice the problem?"
    no_start = re.search(r"(?:won t|wont|will not|not|doesn t|doesnt).{0,18}(?:start|turn on|tur non)|no start", details)
    if no_start:
        if not re.search(r"\b(?:click|clicks|clicking|clickin|crank|cranks|cranking|silent|silence|nothing happens|no sound|buzz|buzzing)\b", details):
            return "What do you hear when you try to start it?"
        if not re.search(r"\b(?:lights?|dashboard|dash)\b", details):
            return "Do the dashboard lights turn on when you turn the key?"
    elif re.search(r"\b(?:rattle|rattles|rattling|rattlin|noise|squeak|squeaking|grinding)\b", details):
        if not conditions:
            return "When do you hear the noise?"
        if not location:
            return "Where does the noise seem to come from?"
    elif session["questions_asked"] == 1 and not proposed:
        return "What do you notice when the problem happens?"
    if ((conditions and re.search(r"when.*(?:hear|noise|sound|occur|hiss)", proposed, re.I))
            or (location and re.search(r"where|which.*(?:area|part)", proposed, re.I))
            or (onset and re.search(r"first notice|(?:did|does).*start|begin", proposed, re.I))):
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
        next_step = ("Does this note look right, and would you like to schedule a visit? Reply yes to see openings, "
                     "or tell me what to add or change. You can also request an unscheduled ticket or a summary."
                     if session["intent"] in {"triage", "appointment"} else
                     "Does this note describe the concern correctly? Reply yes to use it for your "
                     + ("unscheduled service ticket" if session["intent"] == "ticket" else "technician summary")
                     + ", or tell me what to change.")
        return ("Here is the technician note so far:\n\n" + f["summary"] +
                "\n\nSuggested departments for inspection, not a diagnosis:\n\n" + suggestions +
                "\n\n" + next_step + " Nothing has been booked or saved yet.")
    if session["intent"] == "triage":
        session["stage"] = "routed"
        return ("Confirmed departments: " + ", ".join(f["departments"]) +
                ". Would you like to schedule an appointment, prepare an unscheduled service ticket, "
                "or review the technician summary? Nothing has been booked or saved yet.")
    if session["intent"] == "summary":
        return prepare_preview(session, "summary")
    kind = session["intent"]
    if kind == "appointment" or f["day"] or f["time"]:
        openings = openings_text(session)
        if {"day": f["day"], "time": f["time"]} not in session["openings"]:
            session["stage"] = "schedule"
            if f["day"]:
                choices = [o["time"] for o in session["openings"] if o["day"] == f["day"]]
                if choices:
                    return (("That selected time is unavailable. " if f["time"] else "") +
                            f"For {f['day']}, the available demo times are: " + ", ".join(choices) +
                            ". Which time would you like? These are repeating weekdays, not calendar dates.")
            return ((f"No demo openings remain for {f['day']} in this session. " if f["day"] else "") + openings + "\n\nWhich day and time would you like?")
    missing = [label for key, label in (("customer_name", "name"), ("vehicle", "vehicle year, make, and model (or the details you know)")) if not f[key]]
    if missing:
        session["stage"] = "collect"
        retained = "selected time and issue details" if f["day"] and f["time"] else "service details"
        return "Please provide your " + " and ".join(missing) + ". I will keep your " + retained + "."
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
        if key == "time" and "day" in parsed and not re.search(r"\d|\b(?:noon|midday)\b", text, re.I):
            continue  # A model-suggested time must not block a valid weekday-only change.
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
            days = re.findall(r"\b(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:rs?(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b", evidence, re.I)
            if not days and re.search(r"\b(?:today|tomorrow|yesterday|next week)\b", text, re.I):
                raise ValueError("Please name a weekday; this demo does not use calendar dates.")
            if len(set(d.lower() for d in days)) > 1:
                raise ValueError("Ambiguous day")
            parsed[key] = normalize_day(days[0] if days else evidence)
        else:
            matches = re.findall(r"(?<![\w:])(\d{1,2}(?::[0-5]\d)?\s*[ap](?:\.?m\.?)?|\d{1,2}:[0-5]\d|noon)(?![\w:])", evidence, re.I)
            token = matches[0] if len(matches) == 1 else evidence
            try:
                parsed[key] = normalize_time(token)
            except ValueError:
                if not re.fullmatch(r"\d{1,4}(?::[0-5]\d)?", evidence.strip()):
                    raise
                day = parsed.get("day", session["fields"]["day"])
                shorthand = evidence.strip()
                if re.fullmatch(r"\d{3,4}", shorthand):
                    shorthand = shorthand[:-2] + ":" + shorthand[-2:]
                matches = [o["time"] for o in session["openings"] if (not day or o["day"] == day)
                           and (o["time"].split(":")[0] == shorthand or o["time"].split()[0] == shorthand)]
                if len(set(matches)) != 1:
                    raise ValueError("Ambiguous time")
                parsed[key] = matches[0]
    if "day" in parsed and parsed["day"] != session["fields"]["day"] and "time" not in parsed:
        parsed["time"] = ""
    session["fields"].update(parsed)
    parts = requested_parts(text)
    for part in parts:
        work = session["fields"]["expected_work"]
        if part not in normalize(work):
            session["fields"]["expected_work"] = (work + "; " if work else "") + part
    if result["summary"] and result["has_issue"]:
        session["fields"]["summary"] = result["summary"]
    if result["has_issue"] or first_concern:
        if result["summary"]:
            session["fields"]["summary"] = result["summary"]
        elif first_concern and result["has_issue"]:
            work = session["fields"]["expected_work"]
            session["fields"]["summary"] = (f"Customer requests {work.replace('Customer-requested ', '')}." if work
                                             else stalling_note(text) or readable_fallback(text) or "Customer reports: " + text)
        departments = list(dict.fromkeys(result["departments"] or old_departments))
        if "Customer-requested tire replacement" in session["fields"]["expected_work"] and "maintenance" not in departments:
            departments.append("maintenance")
        concern = normalize(text + " " + " ".join(session.get("issue_messages", [])))
        if ("Customer-requested tire replacement" in session["fields"]["expected_work"]
                and re.search(r"\b(?:noise|shaking|vibration|grinding|bumping)\b", concern)
                and "drivability" not in departments):
            departments.append("drivability")  # Requested tire work must not hide the reported fault.
        if departments:
            session["fields"]["departments"] = departments
            session["reasons"] = {d: DEPARTMENTS[d] for d in departments}
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
        session["reasons"] = {d: DEPARTMENTS[d] for d in result["departments"]}
        session["departments_confirmed"] = False
    if session.get("reported_vent_source") and "vent" not in session["fields"]["summary"].lower():
        session["fields"]["summary"] += " Customer reports a possible AC-vent source; location is uncertain."
    session.setdefault("requested_parts", []).extend(p for p in parts if p not in session.get("requested_parts", []))

def confirm(session):
    if session["stage"] == "departments":
        session["departments_confirmed"] = True
        if session["intent"] == "triage":
            session["intent"] = "appointment"
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
    if session["stage"] == "routed":
        return advance(session)
    return "There is no preview waiting for confirmation. Tell me what you would like help with."

def handle(text, session, client_factory, control=None):
    clean = normalize(text)
    if not control:
        control = {"show my technician summary": "summary", "create a service ticket": "ticket",
                   "schedule an appointment": "appointment", "show available times": "openings"}.get(clean)
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
        if refusal == "unsafe" and not session["last_saved"]:
            session["safety_handoff"] = True
            session["issue_messages"].append(text)
            concern = ("Customer reports smoke from under the hood." if re.search(r"\bsmoke\b.*\bhood\b", clean)
                       else "Customer reports: " + text.strip().rstrip(".") + ".")
            session.setdefault("intake_details", {})["concern"] = concern
            session["fields"]["summary"] = session["intake_details"]["concern"]
            session["fields"]["departments"] = ["drivability"]
            session["departments_confirmed"] = False
            session["stage"] = "safety"
            return REFUSALS[refusal] + "\n\nI kept your concern. Would you like me to prepare an intake note for a service advisor? This does not mean the vehicle is safe to drive."
        return REFUSALS[refusal]
    if session["stage"] == "safety" and re.fullmatch(r"(?:yes|yeah|yep|sure|ok|okay)(?: that s what i want| thats what i want| please)?", clean):
        session["stage"] = "clarify"
        session["questions_asked"] += 1
        session["last_question"] = "When did you first notice the problem?"
        return session["last_question"] + "\n\nIf unsure, choose Skip question."
    if session["fields"]["summary"] and not session["last_saved"] and re.search(r"\b(?:change|instead|actually|i think|i thinks)\b", clean):
        aliases = {"drivability": r"\b(?:drivability|driving|drivin)\b", "electrical": r"\belectrical\b",
                   "interior": r"\binterior\b", "exterior": r"\bexterior\b", "maintenance": r"\bmaintenance\b"}
        chosen = [name for name, pattern in aliases.items() if re.search(pattern, clean)]
        if chosen and not re.search(r"\b(?:not|no) (?:a |an |the )?(?:driving|drivin|drivability|electrical|interior|exterior|maintenance)\b|\b(?:don t|dont) change\b", clean):
            invalidate(session)
            session["fields"]["departments"] = chosen
            session["reasons"] = {d: "Customer-requested service area for inspection; not a diagnosis." for d in chosen}
            session["departments_confirmed"] = False
            return advance(session)
    answering_issue = session["stage"] == "clarify" and not control
    if session.get("question_queue") is not None and session["stage"] == "clarify" and (
            control == "skip" or (answering_issue and not requested_intent(text) and "?" not in text)):
        skipped = control == "skip" or uncertain_reply(text) or clean in {"skip", "skip question"}
        session.setdefault("collected_answers", []).append({"question": session["last_question"], "answer": text})
        if not skipped:
            session.setdefault("queued_observations", []).append(text)
            session["issue_messages"].append(text)
        if session["question_queue"]:
            session["last_question"] = session["question_queue"].pop(0)
            session["questions_asked"] += 1
            return session["last_question"] + "\n\nIf you are unsure, say so or choose Skip question."
        session.pop("question_queue")
        session["intake_complete"] = True
        session["questions_asked"] = 3
        return handle("", session, client_factory, control="finish")
    routine_jobs = routine_requests(text)
    remainder = clean
    for job, evidence in routine_jobs:
        remainder = remainder.replace(normalize(evidence), "")
    service_filler = {"i", "my", "the", "need", "want", "get", "just", "jsut", "also", "and", "could", "can", "please", "guess", "that", "works", "while", "im", "here"}
    if (routine_jobs and not session["last_saved"] and not control
            and set(remainder.split()) <= service_filler):
        invalidate(session)
        f = session["fields"]
        if f["expected_work"] == "Diagnostic inspection of reported concern":
            f["expected_work"] = ""
        for job, evidence in routine_jobs:
            if job not in f["expected_work"].lower():
                label = "Customer-requested tire replacement" if job == "tire replacement" else job
                f["expected_work"] += ("; " if f["expected_work"] else "") + label
            if job not in f["summary"].lower():
                f["summary"] += (" " if f["summary"] else "") + "Customer requests " + job + "."
        session["departments_confirmed"] = session["departments_confirmed"] and "maintenance" in f["departments"]
        f["departments"] = list(dict.fromkeys(f["departments"] + ["maintenance"]))
        session["issue_messages"].append(text)
        return advance(session)
    if control == "confirm" or (not answering_issue and clear_agreement(text)):
        return confirm(session)
    if control == "skip" or (answering_issue and (uncertain_reply(text) or clean in {"skip", "skip question"})):
        if session.get("queued_observations"):
            session["questions_asked"] = 3
            return handle("No further symptom details are known.", session, client_factory, control="finish")
        return advance(session)
    if session["stage"] == "departments" and uncertain_reply(text):
        return ("You do not need to know the cause or choose a department yourself. "
                "This is just a suggested starting point for a technician to inspect. "
                "May I use " + ", ".join(session["fields"]["departments"]) +
                " for the intake? Reply yes or choose Confirm departments. Nothing is booked yet.")
    if session["stage"] == "departments" and clean in {"sure", "sure why not", "sur why not", "sounds good", "that sounds good"}:
        return confirm(session)
    if answering_issue and clean in {"what problem", "what do you mean", "i just need service"}:
        return "You do not need to report a fault for requested service. " + session["last_question"] + " If unsure, choose Skip question."
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
    if re.fullmatch(r"(?:what(?: s|s| is)|explain) (?:a |the )?technician summary", clean):
        return ("A technician summary is a clear note of what you reported: the symptoms, "
                "when they happen, and other details a technician should review. "
                "It is not a diagnosis, ticket, or appointment. Your current intake is unchanged. "
                "Say 'show my technician summary' if you would like to review yours.")
    if not session["last_saved"] and session["fields"]["summary"] and not answering_issue:
        if re.fullmatch(r"(?:(?:i )?(?:want to |would like to |need to )?)?(?:book|schedule|reserve) (?:an? |my )?appointment(?: please)?", clean):
            invalidate(session)
            session["intent"] = "appointment"
            return advance(session)
        if clean in {"when can i come in", "when can i come in please", "show available times"}:
            invalidate(session)
            session["intent"] = "appointment"
            return advance(session)
        selection = visit_selection(text, find_openings(session["records"]), session["fields"]["day"])
        if selection:
            invalidate(session)
            session["intent"] = "appointment"
            session["fields"]["day"], session["fields"]["time"] = selection
            session["tool_log"].append({"tool": "visit_selection", "day": selection[0], "time": selection[1]})
            reply = advance(session)
            if selection[1] == "" and re.search(r"\d", text):
                return "I cannot match that time to an available opening. " + reply
            return reply
    if clean in {"what should i bring", "what should i bring to drop off"}:
        return policy_answer("bring", text)
    if re.fullmatch(r"(?:is this|is it|are we) (?:saved|booked|confirmed)(?: already)?", clean):
        return (f"Request {session['last_saved']} is already saved." if session["last_saved"]
                else "This request is not saved. " + ("Your displayed preview is still waiting for confirmation." if session["pending"] else "Complete and review the details first."))
    if session["pending"] and consent_conflict(text) and "?" not in text:
        invalidate(session)
    if (session["stage"] == "collect" and session["departments_confirmed"]
            and session["intent"] in {"appointment", "ticket"}):
        identity = re.fullmatch(r"([A-Za-z][A-Za-z .'-]{0,60}?)\s*,?\s+((?:19|20)\d{2}\s+[A-Za-z][A-Za-z0-9 .'-]{1,100})", text.strip())
        if identity:
            invalidate(session)
            session["fields"].update(customer_name=identity[1].strip(), vehicle=identity[2].strip())
            return advance(session)
        vehicle = re.fullmatch(r"(?:my (?:car|vehicle) is (?:a )?)?((?:19|20)\d{2}\s+[A-Za-z][A-Za-z0-9 .'-]{1,100})", text.strip(), re.I)
        if vehicle:
            invalidate(session)
            session["fields"]["vehicle"] = vehicle[1].strip()
            return advance(session)
        name = re.fullmatch(r"(?:my name is |i am |i m |im )?([A-Za-z][A-Za-z .'-]{0,60})", clean, re.I)
        if (name and session["fields"]["vehicle"] and not session["fields"]["customer_name"]
                and len(name[1].split()) <= 4 and not re.search(r"\b(?:car|vehicle|need|want|change|cancel|skip|not|no|thanks|appointment)\b", name[1])):
            invalidate(session)
            session["fields"]["customer_name"] = text.strip() if clean == name[1] else name[1].strip()
            return advance(session)
    # Collect clearly recognizable observations without spending a call per reply.
    onset = re.fullmatch(r"(?:this|today this|last) (?:morning|mornin|evening|week|month)|today|yesterday|(?:about )?(?:an?|\d+) (?:hours?|minutes?|days?|weeks?) ago", clean)
    simple_detail = onset or re.search(r"\b(?:clicks?|clicking|clickin|cranks?|lights?|dashboard)\b", clean)
    if (answering_issue and simple_detail and len(text) < 200 and not requested_intent(text)
            and "?" not in text and not re.search(r"\b(?:actually|instead|correction|change|cancel|book|schedule|appointment)\b", clean)):
        candidate = deepcopy(session)
        candidate.setdefault("issue_messages", []).append(text)
        if onset:
            candidate.setdefault("intake_details", {})["onset"] = "First noticed " + clean + "."
            if clean not in normalize(candidate["fields"]["summary"]):
                candidate["fields"]["summary"] += " First noticed " + clean + "."
        question = intake_question(candidate, "")
        if question and question != session["last_question"] and candidate["questions_asked"] < 3:
            candidate.setdefault("queued_observations", []).append(text)
            candidate["questions_asked"] += 1
            candidate["last_question"] = question
            session.update(candidate)
            return question + "\n\nIf you are unsure, say so or choose Skip question."
    remaining = math.ceil(session.get("retry_until", 0) - time.time())
    if remaining > 0:
        return rate_limit_message(remaining)
    model_text = "\n".join(session.get("queued_observations", []) + [text])
    result = interpret(model_text, session, client_factory())
    if session.get("safety_handoff") and (answering_issue or control == "finish") and result["refusal"] == "unsafe":
        result["refusal"] = ""  # Documenting reported facts follows the visible safety referral.
    if session.get("queued_observations") or control == "finish":
        result["has_issue"] = True
        result["updates"].pop("day", None)
        result["updates"].pop("time", None)
    if ac_request(text):
        result["has_issue"] = True
    replacement = tire_request(text)
    routine = re.search(r"\b(?:oil change|tire rotation)\b", text, re.I)
    if (not replacement and routine and re.search(r"\b(?:needs?|wants?|please|requests?|book|schedule)\b", clean)
            and not re.search(r"\b(?:not|don t|dont|cancel|no longer)\b", clean)):
        replacement = routine.group()
    proposed_work = result["updates"].get("expected_work") or {}
    if replacement and (not proposed_work or str(proposed_work.get("value", "")).casefold()
                        not in str(proposed_work.get("evidence", "")).casefold()):
        result["updates"]["expected_work"] = {"value": replacement, "evidence": replacement}
    if tire_request(text):
        result["has_issue"] = True
        result["departments"] = list(dict.fromkeys(session["fields"]["departments"] + result["departments"] + ["maintenance"]))
        # Work requested alone needs no symptom interview or shop-policy answer.
        if not re.search(r"\b(?:noise|click|shake|shaking|vibration|smoke|leak|hiss|broken|problem|fault|won t|wont)\b", clean):
            result["action"] = "provide"
            result["policy_topic"] = result["refusal"] = result["clarification"] = ""
            if not session["fields"]["summary"]:
                result["summary"] = "Customer requests tire replacement."
                result["details"] = {"concern": {"value": result["summary"], "evidence": text}}
    location = suspected_location(text)
    if location and session["fields"]["summary"] and not result["details"].get("location"):
        result["details"]["location"] = location
        result["has_issue"] = True
    if moving_stall(text):
        result["has_issue"] = True
        result["summary"] = result["summary"] or stalling_note(text)
        result["departments"] = list(dict.fromkeys(result["departments"] + ["drivability"]))
        if result["refusal"] == "unsafe":
            result["refusal"] = ""  # Warning is added below; documenting does not authorize driving.
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
    affirmative_choice = bool(re.match(r"^(?:yes|yep|yup|yeah|sure|okay|ok)\b", clean))
    chose_task = result["intent"] in {"appointment", "ticket", "summary"}
    routing_ok = (session["stage"] == "departments"
                  and (result["routing_agreement"] or result["action"] == "confirm"
                       or (affirmative_choice and chose_task))
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
    identity = [result["updates"][key] for key in ("customer_name", "vehicle") if result["updates"].get(key)]
    remainder = text.casefold()
    for item in identity:
        if isinstance(item, dict) and isinstance(item.get("value"), str) and item["value"]:
            remainder = remainder.replace(item["value"].casefold(), "")
    identity_only = bool(identity) and (not result["has_issue"] or set(normalize(remainder).split()) <=
                    {"well", "my", "name", "is", "and", "i", "drive", "a", "an", "its", "it", "s", "vehicle", "car", "please"})
    if identity_only:
        result["has_issue"] = False
        result["summary"] = result["clarification"] = ""
    symptom_answer = answering_issue and not explicit_visit and not identity_only
    if symptom_answer or (past_event and result["has_issue"] and not explicit_visit):
        result["updates"].pop("day", None)
        result["updates"].pop("time", None)
    if symptom_answer:
        result["has_issue"] = True
        result["action"] = "provide"
        result["intent"] = "continue"
    # A new concern alone is not a task choice. Other replies may express a task
    # naturally; trust the model's intent without requiring matching keywords.
    if (session["intent"] == "triage" and result["intent"] in {"appointment", "ticket", "summary"}
            and result["has_issue"] and not routing_ok and not task and not explicit_visit
            and not re.search(r"\b(?:ticket|summary)\b", clean)
            and not any(result["updates"].get(key) for key in ("day", "time"))):
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
        apply_updates(result, model_text, candidate)
        if ac_request(text):
            candidate["ac_inspection_requested"] = True
            candidate["fields"]["departments"] = list(dict.fromkeys(candidate["fields"]["departments"] + ["interior"]))
            work = candidate["fields"]["expected_work"]
            if "AC inspection" not in work:
                candidate["fields"]["expected_work"] = (work + "; " if work else "") + "AC inspection"
            candidate["departments_confirmed"] = False
        if symptom_answer and "about the AC" in session["last_question"]:
            candidate["ac_detail_collected"] = True
        if result["has_issue"]:
            preserve_observations(candidate, model_text, session["last_question"] if symptom_answer else "",
                                  result["details"], result["summary"])
        for part in candidate.get("requested_parts", []):
            if part not in normalize(candidate["fields"]["summary"]):
                candidate["fields"]["summary"] += " Customer requests " + part + "."
        candidate.pop("queued_observations", None)
    except ValueError as error:
        invalidate(session)
        session["tool_log"].append({"tool": "validate_updates", "error": str(error), "updates": result["updates"]})
        return "I could not validate those details. " + str(error) + " No request was saved."
    if result["intent"] not in {"continue", "information"}:
        candidate["intent"] = result["intent"]
    if routing_ok:
        candidate["departments_confirmed"] = True
        if candidate["intent"] == "triage":
            candidate["intent"] = "appointment"
    if candidate["intent"] == "ticket" and re.search(r"\b(?:unscheduled|without an? appointment|no appointment)\b", clean):
        candidate["fields"]["day"] = candidate["fields"]["time"] = ""
    session.update(candidate)
    session.pop("queued_observations", None)
    if result["has_issue"] and not control:
        session.setdefault("issue_messages", []).append(text)
    clarification = result["clarification"].strip()
    routine = routine_service(text) and not (session.get("ac_inspection_requested") and not session.get("ac_detail_collected"))
    plan = result["questions"]
    if result["has_issue"] and plan is not None and session["questions_asked"] == 0:
        if plan and not routine:
            session["last_question"] = plan[0]
            session["question_queue"] = plan[1:]
            session["questions_asked"] = 1
            session["stage"] = "clarify"
            return (prefix + "\n\n" if prefix else "") + plan[0] + "\n\nIf you are unsure, say so or choose Skip question."
        return (prefix + "\n\n" if prefix else "") + advance(session)
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
        session["tool_log"].append({"tool": "advisor_error", "error": type(error).__name__,
                                   "status": getattr(error, "status_code", None)})
        if isinstance(error, RateLimitError):
            session["retry_until"] = time.time() + retry_seconds(error)
        reply = friendly_error(error)
        if (isinstance(error, APIError) and session["stage"] == "clarify"
                and session["fields"]["summary"] and (not control or control == "finish")):
            details = "\n".join(session.pop("queued_observations", []) + [text])
            preserve_observations(session, details, session["last_question"])
            session["issue_messages"].append(text)
            session["questions_asked"] = 3
            reply += "\n\nI kept your answers. Here is a fallback intake note for your review; AI polishing is unavailable right now.\n\n" + advance(session)
    if moving_stall(text) and not control:
        reply = ("An engine shutting off while driving is a safety concern. I cannot tell you "
                 "it is safe to drive; contact a human service advisor or towing provider "
                 "about getting the vehicle inspected.\n\n" + reply)
    if session.get("safety_handoff") and REFUSALS["unsafe"] not in reply:
        reply = REFUSALS["unsafe"] + "\n\n" + reply
    session["messages"].append({"role": "assistant", "content": reply})
    return reply
