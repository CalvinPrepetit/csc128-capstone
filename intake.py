"""Small language safeguards; the model still interprets the open-ended concern."""
import re

NOTE_FILLER = {"customer", "reports", "reported", "vehicle", "occurs", "when",
               "the", "a", "an", "is", "at", "of", "first", "noticed"}


def detail_words(text):
    return set(normalize(text).split()) - NOTE_FILLER


def normalize(text):
    clean = " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())
    return re.sub(r"\b(?:appoitnment|appoitment|appointmet)\b", "appointment", clean)


def matches(pattern, text):
    return bool(re.search(pattern, normalize(text)))


def boundary(text):
    """Explicit danger and unsupported decisions must not depend on model guesses."""
    danger = (r"\b(?:cannot|can t|cant|unable to) stop\b|\b(?:no|lost) brakes\b|"
              r"\bbrakes? (?:failed|quit|do not work|don t work|dont work|not working)\b|"
              r"\b(?:brake )?pedal (?:goes|went|sinks|drops).{0,16}\bfloor\b|"
              r"\b(?:gasoline|gas|fuel) (?:is )?(?:leaking|pouring)\b|"
              r"\b(?:leaking|pouring) (?:gasoline|gas|fuel)\b|"
              r"\b(?:on fire|flames|smoke coming|smoke pouring)\b|"
              r"\b(?:engine|car|vehicle) (?:is )?smoking\b|\bsmoke (?:from|under)\b")
    clean = normalize(text)
    for risk in re.finditer(danger, clean):
        prefix = clean[:risk.start()]
        if not re.search(r"\b(?:no|not|without)(?: smoke (?:or|and))?\s*$", prefix):
            return "unsafe"
    rules = {
        "warranty": r"\bwarranty\b.*\b(?:cover|coverage|pay|approve|guarantee|claim)\b|\b(?:cover|coverage|approve|guarantee|what about)\b.*\bwarranty\b",
        "insurance": r"\binsurance claim\b|\binsurer\b.*\b(?:approve|pay|file|decide)\b",
        "recall": r"\brecalls?\b.*\b(?:look|check|active|open)\b|\b(?:look up|check|active|open)\b.*\brecalls?\b",
        "price": r"\b(?:how much|what s|whats|what is|exact|guarantee)\b.*\b(?:price|cost|total|quote)\b|\bhow much\b.*\b(?:charge|pay)\b",
        "diagnosis": r"\b(?:exactly|definitely|certainly)\b.*\b(?:part|broken|wrong|cause)\b|\bdiagnose\b",
    }
    return next((name for name, pattern in rules.items() if matches(pattern, text)), "")


def requested_intent(text):
    """Recognize explicit task names; leave vague wording to the model."""
    clean = normalize(text)
    if re.search(r"\b(?:do not|don t|dont|not|cancel)\b.{0,20}\b(?:ticket|summary|appointment)\b", clean):
        return ""  # Mixed/negative choices need the model's context, not a keyword override.
    if re.search(r"\b(?:service ticket|service request|unscheduled ticket)\b", clean) and "summary" not in clean:
        return "ticket"
    if re.search(r"\b(?:review|prepare|show|create|want|need)\b.*\b(?:technician |intake )?summary\b", clean):
        return "summary"
    if re.search(r"\b(?:book|schedule|reserve)\b.*\b(?:appointment|visit|me)\b|\b(?:soonest|earliest|come in)\b|"
                 r"\bwhen(?:s| can| could| would).*\b(?:look|bring|take|appointment|available)\b", clean):
        return "appointment"
    return ""


def moving_stall(text):
    """A reported engine shutdown while moving merits a warning, not a diagnosis."""
    clean = normalize(text)
    return bool(re.search(r"\b(?:driving|moving)\b", clean) and
                re.search(r"\b(?:stalled|stalling|shut off|died|dies|cut out)\b", clean) and
                not re.search(r"\b(?:never|not|hasn t|hasnt)\b.{0,12}\b(?:stalled|died|shut off)\b", clean))


def stalling_note(text):
    """Preserve clearly reported events even if the model omits its note."""
    if not moving_stall(text):
        return ""
    facts = ["Engine shut off while driving"]
    if matches(r"\bstop light\b|\bstoplight\b", text):
        facts.append("also shut off at a stoplight")
    if matches(r"\b(?:able to get it to start again|restarted|started again)\b", text):
        facts.append("restarted before shutting off again")
    if matches(r"\blights\b.{0,20}\b(?:still on|stayed on|remained on)\b", text):
        facts.append("lights remained on")
    if matches(r"\btoday\b", text):
        facts.append("reported onset today")
    return "Customer reports: " + "; ".join(facts) + "."


def requested_work(value, text):
    """Evidence proves wording, not intent: a symptom is not requested repair work."""
    service = r"\b(?:oil change|tire rotation|tire replacement|routine|scheduled maintenance)\b"
    action = r"\b(?:inspect|inspection|diagnostic|diagnosis|replace|replacement|repair|rotate|change|changed|check|checked|service)\b"
    return matches(service, value) or (matches(action, value) and
           matches(r"\b(?:want|need|please|request|book|schedule|can you|could you)\b", text))


def routine_service(text):
    return matches(r"\b(?:oil change|tire rotation|tire replacement|routine|scheduled maintenance)\b|"
                   r"\b(?:want|need|please)\b.*\btire\b.*\b(?:changed|replaced)\b", text)


def tire_request(text):
    """Recognize explicit replacement wording, not a tire symptom alone."""
    if matches(r"\b(?:not|don t|dont|cancel|no longer)\b", text):
        return ""
    match = re.search(r"\btires?\s+need\s+(?:to\s+be\s+)?(?:changed|replaced)\b|"
                      r"\b(?:need|want)\s+(?:my |the )?tires?\s+(?:changed|chaned|replaced)\b", text, re.I)
    return match.group() if match else ""


def ac_request(text):
    """An explicit inspection request is not evidence of an AC fault."""
    return (matches(r"\b(?:ac|a c|air conditioning)\b", text)
            and matches(r"\b(?:looked at|looks? at|checked|check|inspect|inspection)\b", text)
            and not matches(r"\b(?:not|don t|dont|cancel|no longer)\b", text))


def requested_parts(text):
    """Retain explicit part-service clauses when the model extracts only one job."""
    parts = []
    for clause in re.split(r"\band\b|[.;]", normalize(text)):
        if matches(r"\b(?:not|don t|dont|cancel|no longer)\b", clause):
            continue
        match = re.search(r"\bneeds?\s+(?:my |the |a |an )?([a-z]+(?: [a-z]+){0,2}?)\s+(replaced|changed|checked)\b", clause)
        if match and not matches(r"\b(?:tires?|to|be|it|this|that)\b", match[1]):
            action = {"replaced": "replacement", "changed": "replacement", "checked": "inspection"}[match[2]]
            parts.append(match[1] + " " + action)
    return list(dict.fromkeys(parts))


def suspected_location(text):
    """A short questioned location is an observation, not a confirmed fault."""
    match = re.match(r"\s*(?:the\s+)?(tires?|wheels?|engine|(?:front|back|rear)(?:\s+(?:left|right))?|(?:ac\s+)?vents?)\s*\?", text, re.I)
    if match:
        return {"value": f"Customer suspects the {match.group(1).lower()}; source is uncertain", "evidence": match.group().strip()}
    return None


def policy_topic(text, proposed):
    """A source label is useful only when its document answers the actual question."""
    topics = {
        "bring": r"\b(?:bring|paperwork|take with|check in)\b",
        "drop_off": r"\b(?:drop off|dropoff|key drop)\b",
        "hours": r"\b(?:hours|open|close|closed|closing)\b",
        "departments": r"\b(?:departments?|service areas?)\b",
        "requests": r"\b(?:demo|fictional|browser|session|records|refresh|saved|save|stored)\b",
    }
    if matches(r"\b(?:loaner|rental|payment|financing|free snacks|waiting room)\b", text):
        return "unknown"
    if proposed in topics and not matches(topics[proposed], text):
        return "unknown"
    return proposed


def starting_observations(text):
    """Readable safeguards for reported starting behavior, never a cause or repair."""
    facts = {}
    if matches(r"\bcranks?\b", text) and matches(r"\b(?:won t|wont|will not|doesn t|doesnt) start\b", text):
        facts["starting"] = "Vehicle cranks but does not consistently start"
    elif matches(r"\b(?:won t|wont|will not|doesn t|doesnt) (?:start|turn on)\b", text):
        facts["starting"] = "Customer reports the vehicle will not start"
    if matches(r"\b(?:clicks?|clicking|clickin)\b", text):
        if matches(r"\b(?:no|not|never|isn t|isnt) (?:any )?click(?:s|ing|in)?\b|\b(?:doesn t|doesnt|stopped) click", text):
            facts["starting sound"] = "Customer reports no clicking sound"
        else:
            facts["starting sound"] = "Customer reports repeated clicking" if matches(r"clicks and clicks|repeated", text) else "Customer reports a clicking sound"
    if matches(r"\bable to get it (?:goin|going|running).{0,15}\b(?:little|briefly)\b|\b(?:starts? briefly|briefly starts?)\b", text):
        facts["brief start"] = "The vehicle briefly starts"
    if matches(r"\b(?:won t|wont|will not|doesn t|doesnt) (?:stay|remain|run).{0,12}\bidle\b", text):
        facts["idle"] = "When running, the vehicle will not stay running at idle"
    if matches(r"\blights?\b.{0,20}\b(?:don t|dont|do not|won t|wont) (?:turn on|illuminate)\b", text):
        facts["lighting"] = "Customer reports the lights do not turn on"
    elif matches(r"\blights?\b.{0,20}\b(?:seem|look|are|work) (?:fine|normal|normally)\b", text):
        facts["lighting"] = "Customer reports the lights appear normal"
    elif matches(r"\blights?\b.{0,20}\bdim\b|\bdim\b.{0,10}\blights?\b", text):
        facts["lighting"] = "Customer reports dim lights"
    elif matches(r"\b(?:all (?:of )?(?:the )?)?lights?\b.{0,20}\b(?:are on|still on|stayed on|remain on|remaining on|illuminate)\b", text):
        facts["lighting"] = "Customer reports the lights illuminate"
    onset = onset_observation(text)
    if onset:
        facts["onset"] = onset
    elif matches(r"\b(?:started|began|first noticed) today\b", text):
        facts["onset"] = "First noticed today"
    return facts


def readable_fallback(text):
    facts = starting_observations(text)
    return ". ".join(facts.values()) + "." if "starting" in facts else ""


def onset_observation(text):
    if (matches(r"\btoday\b", text) and matches(r"\bstop ?light\b", text)
            and matches(r"\b(?:turned off|shut off|stalled)\b", text)):
        note = "First noticed today when the vehicle shut off at a stoplight"
        if matches(r"\b(?:able to get it on|restarted|started again)\b", text) and matches(r"\bgas station\b", text):
            note += "; restarted long enough to reach a gas station"
        return note
    return ""


def preserve_observations(session, text, question="", details=None):
    """Keep the latest answer per topic so revisions cannot silently erase observations."""
    clean_details = session.setdefault("intake_details", {})
    for topic, item in (details or {}).items():
        if item is None:
            continue
        if (isinstance(item, dict)
                and normalize(str(item.get("value", ""))) in {"", "unknown", "not specified"}):
            continue  # An absent detail is not evidence of an observation.
        if (not isinstance(item, dict) or set(item) != {"value", "evidence"}
                or not isinstance(item["value"], str) or not item["value"].strip()
                or len(item["value"]) > 500 or not isinstance(item["evidence"], str)
                or not item["evidence"].strip()):
            raise ValueError("Observation lacks customer evidence")
        if item["evidence"] not in text:
            session["tool_log"].append({"tool": "validate_observation", "topic": topic,
                                        "ignored": "No evidence in latest message"})
            continue  # Keep verified facts; an optional model echo must not reject the turn.
        if (topic == "onset" and matches(r"\b(?:driving|drive|dirve|moving|speed)\b", item["evidence"])
                and not matches(r"\b(?:first|started|began|noticed|today|yesterday|ago|last|since)\b", item["evidence"])):
            continue  # A driving condition does not establish when the problem began.
        answer = item["value"].strip().rstrip(".") + "."
        previous = clean_details.get(topic, "")
        correction = matches(r"\b(?:actually|correction|instead|i meant|rather than)\b", text)
        if previous and topic in {"concern", "conditions", "additional"} and not correction:
            if detail_words(answer) <= detail_words(previous):
                continue
            if not detail_words(previous) <= detail_words(answer):
                answer = previous + " " + answer
        clean_details[topic] = answer
    onset = onset_observation(text)
    if onset:
        clean_details["onset"] = onset + "."
    if (clean_details.get("conditions") and matches(r"\b(?:slow|slowly|low speed)\b", text)
            and not matches(r"\b(?:not|never|doesn t|doesnt)\b.{0,20}\b(?:slow|slowly|low speed)\b", text)
            and not matches(r"\b(?:slow|slowly|low speed)\b", clean_details["conditions"])):
        clean_details["conditions"] += " Customer also reports the concern at low speed."
    if clean_details.get("concern"):
        # Join AI-written observations once; short follow-ups cannot erase earlier topics.
        note = ""
        for answer in clean_details.values():
            words = detail_words(answer)
            if not words <= set(normalize(note).split()):
                note += (" " if note else "") + answer
        source = " ".join(session.get("issue_messages", []) + [text])
        if not matches(r"\b(?:mph|kph|km h|kmh|miles per hour|kilometers per hour)\b", source):
            note = re.sub(r"\s*\b(?:mph|kph|km/h|kmh|miles per hour|kilometers per hour)\b", "", note, flags=re.I)
        work = session["fields"]["expected_work"]
        if "Customer-requested tire replacement" in work and not matches(r"\btires?\b.*\b(?:replacement|replace|replaced|change|changed)\b", note):
            note += " Customer requests tire replacement; inspection is needed before any repair decision."
        session["fields"]["summary"] = note
    observations = session.setdefault("observations", {})
    facts = starting_observations(text)
    observations.update(facts)
    if "lighting" in facts and matches(r"\b(?:actually|correction|instead|not)\b", text):
        # Remove the old lighting sentence; retained starting/idle facts are restored below.
        session["fields"]["summary"] = ". ".join(
            sentence.strip() for sentence in re.split(r"[.;]", session["fields"]["summary"])
            if sentence.strip() and not matches(r"\blights?\b", sentence)) + "."
    if moving_stall(text):
        observations["stalling sequence"] = stalling_note(text)
    key = "" if clean_details.get("concern") else normalize(question)
    if re.search(r"first notice|(?:did|does).*start|begin", key):
        key = "onset"
    if key and not matches(r"\b(?:no warning lights|no smoke|no visible smoke)\b", text):
        observations[key] = (onset_observation(text) if key == "onset" else "") or text.strip()
    elif matches(r"\b(?:actually|correction)\b.*\b(?:noticed|started|onset)\b", text):
        observations["onset"] = text.strip()
    for topic, pattern in {
        "warning lights": r"\b(?:no|without) (?:dashboard )?warning lights?\b",
        "smoke": r"\b(?:no smoke|no visible smoke|don t see smoke|dont see smoke)\b",
    }.items():
        if matches(pattern, text):
            observations[topic] = "No warning lights" if topic == "warning lights" else "no visible smoke"
        elif matches(r"\b(?:actually|now|correction)\b", text) and topic in normalize(text):
            observations.pop(topic, None)
    note = session["fields"]["summary"]
    onset_note = clean_details.get("onset", "")
    if onset_note and normalize(onset_note) not in normalize(note):
        note += " " + onset_note
    for key, answer in observations.items():
        if clean_details.get("concern") and key not in {"starting", "starting sound", "brief start", "idle", "lighting", "stalling sequence", "warning lights", "smoke"}:
            continue  # Structured topics replace raw-answer appendices, not factual safeguards.
        if key == "onset" and answer.startswith("First noticed"):
            if normalize(answer) not in normalize(note):
                note += " " + answer + "."
            continue
        patterns = {"starting": r"\b(?:does not|won t|wont|not)\b.*\b(?:start|turn on)\b",
                    "starting sound": r"\bclick(?:s|ing|in)?\b",
                    "brief start": r"\b(?:briefly starts?|starts? briefly)\b",
                    "idle": r"\b(?:won t|wont|not|does not)\b.*\bidle\b",
                    "lighting": r"\blights?\b.*\b(?:on|illuminate|illuminated)\b"}
        if key in facts or key in patterns:
            if key == "lighting" and "dim" in answer:
                if matches(r"\bdim\b", note):
                    continue
            elif key in patterns and matches(patterns[key], note):
                continue
            if normalize(answer) not in normalize(note):
                note += " " + answer + "."
            continue
        if key == "stalling sequence":
            clues = {"driving": r"\bwhile (?:driving|moving)\b", "stoplight": r"\bstop ?light\b", "restarted": r"\b(?:restarted|started again|start again)\b",
                     "lights remained on": r"\blights\b.{0,30}\b(?:on|illuminated)\b", "today": r"\btoday\b"}
            if all(matches(pattern, note) for word, pattern in clues.items() if word in answer.lower()):
                continue
        if key == "smoke" and matches(r"\bno (?:visible )?smoke\b", note):
            continue
        if normalize(answer) not in normalize(note):
            label = "first noticed" if key == "onset" else key.rstrip(" ?")
            note += f" Customer observation ({label}): {answer.rstrip('.')}."
    if session.get("ac_inspection_requested") and not matches(r"\b(?:ac|a c|air conditioning)\b", note):
        note += " Customer also requests an air-conditioning inspection; no specific AC fault is assumed."
    note = re.sub(r"\bunknown\s*\.", "", note, flags=re.I).strip()
    note = re.sub(r"^(?:car|vehicle)\s", "Customer reports the vehicle ", note, flags=re.I)
    session["fields"]["summary"] = note[:1].upper() + note[1:]
    if "starting" in observations and "electrical" not in session["fields"]["departments"]:
        session["fields"]["departments"].append("electrical")
        session["departments_confirmed"] = False
