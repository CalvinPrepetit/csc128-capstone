"""Small fictional shop guide, adapted from Assignment 6. Calvin A. Prepetit."""
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

DEPARTMENTS = {
    "electrical": "Starting, charging, battery, wiring, lights, and powered accessories.",
    "drivability": "How the vehicle runs, moves, shifts, steers, or stops; engine, exhaust, brakes, vibration, and unusual running noises.",
    "interior": "Seats, dashboard, interior trim, and cabin heating or air conditioning.",
    "exterior": "Body panels, dents, paint, glass, mirrors, and exterior damage.",
    "maintenance": "Requested routine upkeep such as oil changes, filters, tire rotation, and fluid checks. A reported fault is not assumed to be fixed by maintenance.",
}
DOCUMENTS = [
    {"id": "departments", "source": "Department Guide", "text": "\n".join(f"{n.title()}: {d}" for n, d in DEPARTMENTS.items())},
    {"id": "bring", "source": "Vehicle Check-In Guide - What to Bring", "text": "At drop-off, bring the vehicle key, current contact information, and a description of the issue. Bring warning-light photos, recent repair paperwork, or maintenance records if available. Remove valuables and items that block access to the area being inspected."},
    {"id": "drop_off", "source": "Vehicle Drop-Off Guide", "text": "For this fictional shop, park in a marked customer space and bring your key to the service desk. For after-hours drop-off, complete a key-drop envelope, put the key inside, seal it, and place it in the key-drop box. A service advisor must confirm repair authorization before work begins."},
    {"id": "hours", "source": "Customer Visit Guide - Hours", "text": "The fictional shop is open Monday through Friday from 7:30 AM to 6:00 PM and Saturday from 8:00 AM to 2:00 PM. It is closed Sunday. Ask the service desk about holiday hours."},
    {"id": "requests", "source": "Demo Request Guide", "text": "Appointments and service tickets in this classroom app are fictional intake requests, not authorization for repairs or a promise of completion. Appointment slots repeat by weekday, not calendar date. Records and reservations exist only in your current browser session; another visitor has a separate demo schedule. Refreshing or closing the session can lose records. Contact a human service advisor to change a saved request."},
]

def analyze(text):
    """Reuse Assignment 6's token/bigram idea with a smaller guide."""
    stop = {"i", "my", "the", "a", "is", "it", "to", "for", "and", "you", "can", "car"}
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in stop]
    return words + ["_".join(words[i:i + 2]) for i in range(len(words) - 1)]

class Retriever:
    def __init__(self, documents=None):
        self.documents = DOCUMENTS if documents is None else documents
        self.vectorizer = TfidfVectorizer(analyzer=analyze)
        self.matrix = self.vectorizer.fit_transform([d["text"] for d in self.documents]) if self.documents else None

    def search(self, question, top_k=2):
        if self.matrix is None:
            return []
        scores = cosine_similarity(self.vectorizer.transform([question]), self.matrix)[0]
        return [self.documents[i] for i in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k] if scores[i] >= 0.10]

def policy_answer(topic, query, retriever=None):
    """Return approved text and source names directly; never invent a policy."""
    if topic in {d["id"] for d in DOCUMENTS}:
        query = next(d["text"] for d in DOCUMENTS if d["id"] == topic)
    hits = (retriever or Retriever()).search(query)
    if topic:
        hits = [d for d in hits if d["id"] == topic]
    if not hits:
        return "I do not have that information in the shop guide. Please ask a human service advisor."
    return "\n\n".join(f"{d['text']}\n\nSource: {d['source']} (fictional classroom policy)." for d in hits)
