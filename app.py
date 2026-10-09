"""CSC-128 Capstone: Auto Shop Service Advisor interface.
Calvin A. Prepetit
"""

import json
import streamlit as st
from groq import Groq

from advisor import MODEL, new_session, process_turn


def get_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"], timeout=30, max_retries=0)


def main():
    st.set_page_config(page_title="Auto Shop Service Advisor")
    st.title("Auto Shop Service Advisor")
    st.caption("You are chatting with automated software for a fictional auto shop.")
    st.caption("Demo intake requests only. A qualified technician must inspect the vehicle; no repair is diagnosed or authorized here.")
    if "capstone_session" not in st.session_state:
        st.session_state.capstone_session = new_session()
    session = st.session_state.capstone_session

    st.sidebar.header("Bot Settings")
    st.sidebar.write("Model:", MODEL)
    st.sidebar.caption("Records and reserved times stay in this browser session and can be lost "
                       "on refresh. Each visitor has a separate demo schedule. Messages are sent "
                       "to Groq. Use fictional details for this classroom demo.")
    if st.sidebar.button("Start Over"):
        st.session_state.capstone_session = new_session(session["records"])
        st.rerun()
    simulate_failure = st.sidebar.checkbox("Simulate API outage (demo)", help="Tests the failure message without using API quota. Turn off to resume.")
    with st.sidebar.expander("Saved requests"):
        if not session["records"]:
            st.write("No saved requests.")
        for record in session["records"]:
            st.write(record["id"], record["kind"], record["vehicle"])
        if session["records"]:
            st.download_button("Download my demo requests", json.dumps(session["records"], indent=2),
                               file_name="auto_shop_requests.json", mime="application/json")
    with st.sidebar.expander("Tool log"):
        st.json(session["tool_log"])
    with st.sidebar.expander("Original customer messages"):
        for message in session["original_messages"]:
            st.text(message)

    for message in session["messages"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    action = None
    if session["stage"] == "clarify" and st.button("Skip question"):
        action = ("Skip question", "skip")
    if session["stage"] == "departments" or session["pending"]:
        label = ("Confirm note and see openings" if session["stage"] == "departments"
                 and session["intent"] in {"triage", "appointment"} else "Confirm displayed details")
        if st.button(label):
            action = (label, "confirm")
    options = (("Describe a vehicle concern", "triage"), ("Schedule an appointment", "appointment"),
               ("Create a service ticket", "ticket"), ("Review technician summary", "summary"),
               ("Show available times", "openings"), ("Contact a service advisor", "human"))
    if session["stage"] == "routed":
        options = options[1:4]
        st.caption("Choose your next step, or type a day and time to schedule.")
        menu = st.container()
    elif len(session["messages"]) == 1:
        st.subheader("How can I help?")
        menu = st.container()
    else:
        menu = st.expander("Need something else?")
    with menu:
        columns = st.columns(2)
        for index, (label, kind) in enumerate(options):
            if columns[index % 2].button(label, width="stretch"):
                action = (label, kind)
    text = st.chat_input("Tell me what's going on, or what you need help with...")
    if action or text:
        def active_client():
            if simulate_failure:
                from groq import APIConnectionError
                import httpx
                raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
            return get_client()
        with st.spinner("Working on it..."):
            process_turn(action[0] if action else text, session, active_client, action[1] if action else None)
        st.rerun()


if __name__ == "__main__":
    main()
