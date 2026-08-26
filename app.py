import csv
from datetime import datetime
import streamlit as st

from pathlib import Path
from api.client import client, CONDITION, MODEL

st.set_page_config(
    page_title="Reflection",
    page_icon=":material/bolt:",
    initial_sidebar_state="collapsed",
)

LOG_PATH = Path("data/sessions.csv")

GUESS_BRACKETS = [
    "under 0.001 Wh",
    "0.001-0.01 Wh",
    "0.01-0.1 Wh",
    "0.1-1 Wh",
    "over 1 Wh",
]

TASK_TEXT = "Be assistenten om hjelp til å planlegge en kort helgetur til en by dere ikke har vært i."


def init_state():
    defaults = {
        "stage": "entry",
        "group_code": "",
        "answer": "",
        "energy_wh": None,
        "co2_g": None,
        "tokens_in": None,
        "tokens_out": None,
        "guess": None,
        "vote": None,
        "reflection": "",
        "start_time": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def reset_for_next_group():
    keys = [
        "group_code",
        "answer",
        "energy_wh",
        "co2_g",
        "tokens_in",
        "tokens_out",
        "guess",
        "vote",
        "reflection",
        "start_time",
    ]
    for k in keys:
        st.session_state[k] = None
    st.session_state.group_code = ""
    st.session_state.answer = ""
    st.session_state.reflection = ""
    st.session_state.stage = "entry"


def render_entry():
    st.title("Velkommen")
    code = st.text_input("Skriv inn gruppekoden dere fikk utdelt")
    if st.button("Start", disabled=not code):
        st.session_state.group_code = code
        st.session_state.start_time = datetime.now()
        st.session_state.stage = "task"
        st.rerun()


def render_task():
    st.subheader("Oppgave")
    st.write(TASK_TEXT)

    # Init message history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display conversation
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Keeping track of (n) messages sent by the user
    user_message_count = sum(
        1 for message in st.session_state.messages if message["role"] == "user"
    )

    # Limit users to ten messages
    if user_message_count < 10:
        prompt = st.chat_input(f"Skriv meldingen deres her ({user_message_count}/10)")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})

            input_messages = [
                {"role": message["role"], "content": message["content"]}
                for message in st.session_state.messages
            ]

            with st.spinner("Tenker ..."):
                response = client.responses.create(model=MODEL, input=input_messages)

            impacts = response.impacts
            answer = response.output_text

            st.session_state.messages.append({"role": "assistant", "content": answer})

            # Store metrics
            st.session_state.energy_wh = impacts.energy.value.mean * 1000
            st.session_state.co2_g = impacts.gwp.value.mean * 1000
            st.session_state.tokens_in = response.usage.input_tokens
            st.session_state.tokens_out = response.usage.output_tokens

            # Count messages after adding the new one
            new_user_message_count = user_message_count + 1

            # Automatically finish after 10 messages
            if new_user_message_count >= 10:
                st.session_state.stage = "guess"

            st.rerun()

    # Allow user to finish after at least 1 message
    if user_message_count >= 1 and user_message_count < 10:
        if st.button("Gå videre"):
            st.session_state.stage = "guess"
            st.rerun()


def render_guess():
    st.subheader("Gjett")
    st.write("Før dere ser fasiten: hvor mye energi tror dere samtalen brukte?")
    guess = st.radio("Velg et intervall", GUESS_BRACKETS, index=None)
    if st.button("Lås gjetning", disabled=guess is None):
        st.session_state.guess = guess
        st.session_state.stage = "reveal"
        st.rerun()


def render_reveal():
    st.subheader("Fasit")
    if CONDITION == "abstract":
        st.metric("Energi", f"{st.session_state.energy_wh:.4f} Wh")
        st.caption(f"{st.session_state.co2_g:.4f} g CO2e")
    else:
        render_concrete_visual(st.session_state.energy_wh)

    if st.button("Neste"):
        st.session_state.stage = "vote"
        st.rerun()


def render_concrete_visual(energy_wh):
    # placeholder, replace with a real spatial/visual analogy
    reference_wh = (
        10  # calibrate against something relatable, e.g. 1% of a phone charge
    )
    fraction = min(energy_wh / reference_wh, 1.0)
    st.write("Så mye av en telefonlading gikk med til dette svaret:")
    st.progress(fraction)


def render_vote():
    st.subheader("Verdt det?")
    vote = st.radio("Var svaret verdt energibruken?", ["Ja", "Nei"], index=None)
    if st.button("Send stemme", disabled=vote is None):
        st.session_state.vote = vote
        st.session_state.stage = "reflect"
        st.rerun()


def render_reflect():
    st.subheader("Refleksjon")
    text = st.text_area("Hva overrasket dere mest?")
    if st.button("Fullfør", disabled=not text.strip()):
        st.session_state.reflection = text
        log_session()
        st.session_state.stage = "done"
        st.rerun()


def render_done():
    st.success("Takk for at dere deltok!")
    if st.button("Neste gruppe"):
        reset_for_next_group()
        st.rerun()


def log_session():
    LOG_PATH.parent.mkdir(exist_ok=True)
    file_exists = LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "timestamp",
                    "condition",
                    "group_code",
                    "duration_s",
                    "tokens_in",
                    "tokens_out",
                    "energy_wh",
                    "co2_g",
                    "guess",
                    "vote",
                    "reflection",
                ]
            )

        duration_s = round(
            (datetime.now() - st.session_state.start_time).total_seconds(), 1
        )
        writer.writerow(
            [
                datetime.now(),
                CONDITION,
                st.session_state.group_code,
                duration_s,
                st.session_state.tokens_in,
                st.session_state.tokens_out,
                st.session_state.energy_wh,
                st.session_state.co2_g,
                st.session_state.guess,
                st.session_state.vote,
                st.session_state.reflection,
            ]
        )


init_state()
stages = {
    "entry": render_entry,
    "task": render_task,
    "guess": render_guess,
    "reveal": render_reveal,
    "vote": render_vote,
    "reflect": render_reflect,
    "done": render_done,
}
stages[st.session_state.stage]()
