"""CSC-128 Capstone: Auto Shop Service Advisor interface.
Calvin A. Prepetit
"""

import streamlit as st
from groq import Groq

from advisor import MODEL, new_session, process_turn


def get_client():
    return Groq(api_key=st.secrets["GROQ_API_KEY"], timeout=30, max_retries=0)


def main():
    st.set_page_config(page_title="Auto Shop Service Advisor")
    st.title("Auto Shop Service Advisor and Intake Bot")
    st.caption("You are chatting with automated software for a fictional auto shop.")
    st.info("Development preview: describe a vehicle issue and get a follow-up question. "
            "Appointments and saved service tickets are not available yet.")
    if "advisor_session" not in st.session_state:
        st.session_state.advisor_session = new_session()
    session = st.session_state.advisor_session

    st.sidebar.header("Bot Settings")
    st.sidebar.write("Model:", MODEL)
    st.sidebar.caption("Conversation data stays in this browser session and can be lost "
                       "on refresh. Messages are sent to Groq to generate replies. "
                       "Use fictional details for this classroom demo.")
    if st.sidebar.button("Start Over"):
        st.session_state.advisor_session = new_session()
        st.rerun()
    with st.sidebar.expander("Original customer messages"):
        for message in session["original_messages"]:
            st.text(message)

    for message in session["messages"]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    text = st.chat_input("Describe your vehicle issue...")
    if text:
        with st.spinner("Working on it..."):
            process_turn(text, session, get_client)
        st.rerun()


if __name__ == "__main__":
    main()
