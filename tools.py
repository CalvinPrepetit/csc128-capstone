"""Validation and demo record tools, adapted from Assignments 4 and 7.
Calvin A. Prepetit
"""
import re
from difflib import get_close_matches
from copy import deepcopy
from uuid import uuid4
from knowledge import DEPARTMENTS

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# General intake slots serve every department; a multi-department request uses 1 slot.
OPENINGS = (("Monday", "11:00 AM"), ("Tuesday", "9:00 AM"), ("Wednesday", "10:00 AM"),
            ("Thursday", "1:30 PM"), ("Friday", "9:00 AM"), ("Friday", "2:00 PM"), ("Saturday", "9:30 AM"))

def normalize_day(value):
    value = value.strip().lower().rstrip(".")
    aliases = {"tues": "Tuesday", "thur": "Thursday", "thurs": "Thursday"}
    for day in DAYS:
        aliases[day.lower()] = aliases[day[:3].lower()] = day
    if value not in aliases and len(value) >= 4 and value.isalpha():
        matches = get_close_matches(value, [d.lower() for d in DAYS], n=2, cutoff=0.82)
        if len(matches) == 1:
            value = matches[0]
    if value not in aliases:
        raise ValueError("Please choose a weekday name. The demo does not use calendar dates.")
    return aliases[value]

def normalize_time(value):
    value = value.strip().lower().replace(".", "")
    compact = re.fullmatch(r"(\d{1,2})([0-5]\d)\s*([ap]m?)", value)
    if compact:
        value = f"{compact[1]}:{compact[2]}{compact[3]}"
    if value in {"noon", "midday"}:
        return "12:00 PM"
    match = re.fullmatch(r"(\d{1,2})(?::([0-5]\d))?\s*(am?|pm?)?", value)
    if not match:
        raise ValueError("Please give a time such as 9am or 1:30pm.")
    hour, minute, period = int(match[1]), int(match[2] or 0), match[3]
    if not period and match[2] is None:
        raise ValueError("Please include AM or PM, or select a displayed opening.")
    if period:
        if not 1 <= hour <= 12:
            raise ValueError("Use a valid 12-hour time.")
        hour = hour % 12 + (12 if period.startswith("p") else 0)
    elif not 0 <= hour <= 23:
        raise ValueError("Use a valid 24-hour time.")
    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"

def find_openings(records):
    reserved = {(r.get("day"), r.get("time")) for r in records}
    return [{"day": d, "time": t} for d, t in OPENINGS if (d, t) not in reserved]

def validate_fields(fields, departments_confirmed, kind, records):
    if kind not in {"appointment", "ticket"}:
        raise ValueError("Unsupported record type.")
    for key in ("customer_name", "vehicle"):
        value = fields.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise ValueError(f"Please provide your {key.replace('_', ' ')}.")
        if value.lower() in {"unknown", "tbd", "n/a", "not provided", "your name", "vehicle"}:
            raise ValueError("Please provide a customer value, not a placeholder.")
    departments = fields.get("departments", [])
    if not departments_confirmed or not departments or any(d not in DEPARTMENTS for d in departments):
        raise ValueError("Please confirm the suggested departments first.")
    if not fields.get("summary"):
        raise ValueError("The intake summary is missing.")
    day, time = fields.get("day"), fields.get("time")
    if kind == "appointment" or day or time:
        if not day or not time:
            raise ValueError("Please select both a day and a time.")
        if {"day": day, "time": time} not in find_openings(records):
            raise ValueError("That time is unavailable. Please select another opening.")
    return deepcopy(fields)

def save_record(pending, session):
    """Only the controller calls this after consent to the displayed snapshot."""
    if pending["revision"] != session["revision"]:
        raise ValueError("The details changed. Please review a new preview.")
    for record in session["records"]:
        if record["confirmation_id"] == pending["confirmation_id"]:
            return deepcopy(record)
    values = validate_fields(pending["fields"], session["departments_confirmed"], pending["kind"], session["records"])
    if not pending["original_messages"]:
        raise ValueError("Original customer messages are missing.")
    record = {"id": ("APT-" if pending["kind"] == "appointment" else "SR-") + uuid4().hex[:10].upper(),
              "kind": pending["kind"], "confirmation_id": pending["confirmation_id"], **values,
              "original_messages": deepcopy(pending["original_messages"])}
    session["records"].append(record)
    return deepcopy(record)
