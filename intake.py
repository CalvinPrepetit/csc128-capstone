"""Small language safeguards; the model still interprets the open-ended concern."""
import re


def normalize(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower()).split())


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
        "warranty": r"\bwarranty\b.*\b(?:cover|coverage|pay|approve|guarantee|claim)\b|\b(?:cover|coverage|approve|guarantee)\b.*\bwarranty\b",
        "insurance": r"\binsurance claim\b|\binsurer\b.*\b(?:approve|pay|file|decide)\b",
        "recall": r"\brecalls?\b.*\b(?:look|check|active|open)\b|\b(?:look up|check|active|open)\b.*\brecalls?\b",
        "price": r"\bexact\b.*\b(?:price|cost|total|quote)\b|\bguarantee\b.*\b(?:price|cost|quote)\b",
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
    if re.search(r"\b(?:book|schedule|reserve)\b.*\b(?:appointment|visit)\b|\b(?:soonest|earliest|come in)\b", clean):
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
    if matches(r"\bable to get it (?:goin|going|running).{0,15}\b(?:little|briefly)\b|\b(?:starts? briefly|briefly starts?)\b", text):
        facts["brief start"] = "The vehicle briefly starts"
    if matches(r"\b(?:won t|wont|will not|doesn t|doesnt) (?:stay|remain|run).{0,12}\bidle\b", text):
        facts["idle"] = "When running, the vehicle will not stay running at idle"
    if matches(r"\blights?\b.{0,20}\bdim\b|\bdim\b.{0,10}\blights?\b", text):
        facts["lighting"] = "Customer reports dim lights"
    elif matches(r"\b(?:all (?:of )?(?:the )?)?lights?\b.{0,20}\b(?:are on|still on|stayed on|remain on|remaining on|illuminate)\b", text):
        facts["lighting"] = "Customer reports the lights illuminate"
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


def preserve_observations(session, text, question=""):
    """Keep the latest answer per topic so revisions cannot silently erase observations."""
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
    key = normalize(question)
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
    for key, answer in observations.items():
        if key == "onset" and answer.startswith("First noticed"):
            if normalize(answer) not in normalize(note):
                note += " " + answer + "."
            continue
        patterns = {"starting": r"\bcranks?\b.*\b(?:does not|won t|wont|not)\b.*\bstart\b",
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
    session["fields"]["summary"] = note
