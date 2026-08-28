import csv
import streamlit as st
import time

from datetime import datetime
from pathlib import Path
from api.client import client, CONDITION, MODEL

st.set_page_config(
    page_title="Experiment",
    page_icon=":material/bolt:",
    initial_sidebar_state="collapsed",
    layout="centered",
)


LOG_PATH = Path("data/sessions.csv")
TRANSCRIPT_DIR = Path("data/transcripts")
TOPIC_COUNTER_PATH = Path("data/topic_counter.txt")


FREQUENCY_OPTIONS = [
    "Sjelden eller aldri",
    "Noen ganger i måneden",
    "Noen ganger i uken",
    "Nesten hver dag",
]

FREQUENCY_TO_PER_WEEK = {
    "Sjelden eller aldri": 0.5,
    "Noen ganger i måneden": 1,
    "Noen ganger i uken": 3,
    "Nesten hver dag": 7,
}

FREQUENCY_QUESTION = (
    "Hvor ofte bruker dere en chatbot til akkurat denne typen oppgave &rarr; "
    "å forberede dere raskt på noe dere kunne lite om fra før?"
)

TASK_TEXT = "Be assistenten om hjelp til å planlegge en kort helgetur til en by dere ikke har vært i."

TASK_TEXT_TEMPLATE = (
    "Dere har akkurat fått vite at om **fem minutter** skal gruppa deres holde en kort presentasjon om: \n\n"
    "> {topic}.\n\n"
    "Dette er **ikke** noe dere faktisk skal presentere etterpå.\n"
    "Bruk chatboten til å forberede dere så godt dere kan. "
    "Dere har maks fem meldinger å bruke, så tenk dere om før dere spør."
)

REACTION_OPTIONS = [
    "Overrasket meg",
    "Tvilte på tallet",
    "Ble nysgjerrig",
    "Følte litt skyld",
    "Brydde meg ikke",
    "Vet ikke hva jeg skal tenke",
]

PROMPTS_CAP = 5

REFERENCE_WH = 11.0  # approx. one full smartphone charge
GUESS_TOLERANCE = 0.20  # ±20% counts as "about the same"

PRESENTATION_TOPICS = [
    "historien til binderser",
    "hvordan Roquefort-ost lages",
    "sjøhesters parringsritualer",
    "hvorfor Danmark og Norge en gang delte konge",
    "oppfinnelsen av fraktcontaineren",
    "hva boblefolie egentlig ble laget for",
]


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
        "reveal_animated": False,
        "reveal_done": False,
        "awaiting_response": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def reset_for_next_group():
    st.session_state.clear()
    init_state()
    st.session_state.stage = "entry"


def render_entry():
    st.title("Velkommen")
    code = st.text_input("Skriv inn gruppekoden dere fikk utdelt")
    if st.button("Start", disabled=not code):
        st.session_state.group_code = code
        st.session_state.topic = assign_topic()

        if st.session_state.get("start_time") is None:
            st.session_state.start_time = datetime.now()
        st.session_state.stage = "task"
        st.rerun()


def assign_topic():
    if "topic_index" not in st.session_state:
        TOPIC_COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)

        if TOPIC_COUNTER_PATH.exists():
            try:
                idx = int(TOPIC_COUNTER_PATH.read_text().strip())
            except ValueError:
                idx = 0
        else:
            idx = 0

        idx = idx % len(PRESENTATION_TOPICS)
        next_idx = (idx + 1) % len(PRESENTATION_TOPICS)
        TOPIC_COUNTER_PATH.write_text(str(next_idx))

        st.session_state.topic_index = idx

    return PRESENTATION_TOPICS[st.session_state.topic_index]


def render_task():
    st.subheader("Oppgave")
    current_topic = st.session_state.get("topic")

    st.markdown(TASK_TEXT_TEMPLATE.format(topic=current_topic))

    # Init message history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for key in ["turn_energy_wh", "turn_co2_g", "turn_tokens_in", "turn_tokens_out"]:
        if key not in st.session_state:
            st.session_state[key] = []

    # Agent thinking
    if "awaiting_response" not in st.session_state:
        st.session_state.awaiting_response = False

    # Display conversation
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    # Keeping track of (n) messages sent by the user
    user_message_count = sum(
        1 for message in st.session_state.messages if message["role"] == "user"
    )

    # Limit users to ten messages
    if user_message_count < PROMPTS_CAP and not st.session_state.awaiting_response:
        prompt = st.chat_input(
            f"Skriv meldingen deres her ({user_message_count}/{PROMPTS_CAP})",
            disabled=user_message_count >= PROMPTS_CAP,
        )

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            st.session_state.awaiting_response = True
            st.rerun()
    if st.session_state.awaiting_response:
        with st.chat_message("assistant"):
            with st.spinner("Tenker ..."):
                input_messages = [
                    {"role": message["role"], "content": message["content"]}
                    for message in st.session_state.messages
                ]
                response = client.responses.create(model=MODEL, input=input_messages)

        impacts = response.impacts
        answer = response.output_text

        st.session_state.messages.append({"role": "assistant", "content": answer})

        # Store metrics
        st.session_state.turn_energy_wh.append(impacts.energy.value.mean * 1000)
        st.session_state.turn_co2_g.append(impacts.gwp.value.mean * 1000)
        st.session_state.turn_tokens_in.append(response.usage.input_tokens)
        st.session_state.turn_tokens_out.append(response.usage.output_tokens)

        st.session_state.awaiting_response = False
        st.rerun()

    # Allow user to finish after at least 1 message
    if user_message_count >= 1:
        if st.button("Gå videre"):
            finalize_session_metrics()
            st.session_state.stage = "habit"
            st.rerun()


def finalize_session_metrics():
    st.session_state.energy_wh = sum(st.session_state.turn_energy_wh)
    st.session_state.co2_g = sum(st.session_state.turn_co2_g)
    st.session_state.tokens_in = sum(st.session_state.turn_tokens_in)
    st.session_state.tokens_out = sum(st.session_state.turn_tokens_out)
    st.session_state.n_turns = len(st.session_state.turn_energy_wh)

    save_conversation_transcript()


def render_frequency():
    st.subheader("Vanen deres")
    st.write(FREQUENCY_QUESTION)
    freq = st.radio("Velg", FREQUENCY_OPTIONS, index=None)
    if st.button("Neste", disabled=freq is None):
        st.session_state.frequency = freq
        st.session_state.stage = "guess"
        st.rerun()


def render_guess():
    st.subheader("Gjett")
    st.write("Før dere ser fasiten: hva tror dere?")
    st.write(
        "Brukte denne samtalen mer, mindre, eller omtrent like mye energi "
        "som **å lade en telefon helt opp**?"
    )
    guess = st.radio("Velg", ["Mer", "Mindre", "Omtrent det samme"], index=None)
    if st.button("Lås gjetning", disabled=guess is None):
        st.session_state.guess = guess
        st.session_state.guess_correct = evaluate_guess(
            guess, st.session_state.energy_wh
        )
        st.session_state.stage = "reveal"
        st.rerun()


def evaluate_guess(
    guess, actual_wh, reference_wh=REFERENCE_WH, tolerance=GUESS_TOLERANCE
):
    lower = reference_wh * (1 - tolerance)
    upper = reference_wh * (1 + tolerance)
    if lower <= actual_wh <= upper:
        true_direction = "Omtrent det samme"
    elif actual_wh > upper:
        true_direction = "Mer"
    else:
        true_direction = "Mindre"
    return guess == true_direction


def render_reveal():
    st.subheader("Fasit")

    actual_wh = st.session_state.get("energy_wh")
    frequency_label = st.session_state.get("frequency")
    guess = st.session_state.get("guess")
    guess_correct = st.session_state.get("guess_correct")

    if CONDITION == "abstract":
        render_abstract_reveal(actual_wh, guess, guess_correct, frequency_label)
    else:
        render_concrete_visual(actual_wh)

    if st.button("Neste"):
        st.session_state.stage = "reaction"
        st.rerun()


def render_abstract_reveal(actual_wh, guess, guess_correct, frequency_label):
    if not st.session_state.get("reveal_animated"):
        st.write(f"Dere gjettet: **{guess}**")
        time.sleep(0.7)

        if guess_correct:
            st.success("Riktig gjettet! 🎯")
        else:
            st.error("Ikke helt &rarr; her er fasiten.")
        time.sleep(1.0)

        number_placeholder = st.empty()
        animate_number(
            number_placeholder, actual_wh, unit="Wh", label="Denne samtalen brukte"
        )
        time.sleep(1.0)

        per_week, yearly_wh = compute_yearly_projection(actual_wh, frequency_label)

        st.markdown(f"##### Hvis dere gjør dette {per_week}x i uken ...")
        time.sleep(0.6)

        yearly_placeholder = st.empty()
        animate_number(
            yearly_placeholder, yearly_wh, unit="Wh", label="... blir det på ett år"
        )

        phone_charges = yearly_wh / REFERENCE_WH
        st.caption(
            f"Det tilsvarer omtrent **{phone_charges:.0f} fulle telefonladninger** i året."
        )

        st.session_state.reveal_animated = True

    else:
        st.metric("Denne samtalen", f"{actual_wh:.2f} Wh")
        per_week, yearly_wh = compute_yearly_projection(actual_wh, frequency_label)
        st.metric("Estimert årlig bruk", f"{yearly_wh:.0f} Wh")
        phone_charges = yearly_wh / REFERENCE_WH
        st.caption(
            f"Tilsvarer omtrent {phone_charges:.0f} fulle telefonladninger i året."
        )

    st.session_state.reveal_done = True


def animate_number(placeholder, target_value, unit, label, duration=1.2, steps=20):
    for i in range(steps + 1):
        current = target_value * (i / steps)
        placeholder.metric(label, f"{current:.2f} {unit}")
        time.sleep(duration / steps)


def compute_yearly_projection(actual_wh, frequency_label):
    per_week = FREQUENCY_TO_PER_WEEK[frequency_label]
    yearly_wh = actual_wh * per_week * 52
    return per_week, yearly_wh


def render_concrete_visual(energy_wh):
    # placeholder, replace with a real spatial/visual analogy
    reference_wh = (
        10  # calibrate against something relatable, e.g. 1% of a phone charge
    )
    fraction = min(energy_wh / reference_wh, 1.0)
    st.write("Så mye av en telefonlading gikk med til dette svaret:")
    st.progress(fraction)


def render_reaction():
    st.subheader("Reaksjon")
    st.write("Hva kjenner dere på nå? (velg alt som passer)")
    reactions = st.multiselect("Reaksjoner", REACTION_OPTIONS)
    if st.button("Neste", disabled=len(reactions) == 0):
        st.session_state.reactions = reactions
        st.session_state.stage = "reflect"
        st.rerun()


def render_reflect():
    st.subheader("Refleksjon")
    text = st.text_area("Hva overrasket dere mest?")
    if st.button("Fullfør"):
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

    timestamp = datetime.now().isoformat(timespec="seconds")
    condition = CONDITION
    group_code = st.session_state.get("group_code")
    duration_s = (datetime.now() - st.session_state.get("start_time")).total_seconds()
    n_turns = st.session_state.get("n_turns")

    tokens_in = st.session_state.get("tokens_in")
    tokens_out = st.session_state.get("tokens_out")
    energy_wh = st.session_state.get("energy_wh")
    co2_g = st.session_state.get("co2_g")

    turn_energy_wh = ";".join(
        str(v) for v in st.session_state.get("turn_energy_wh", [])
    )
    turn_co2_g = ";".join(str(v) for v in st.session_state.get("turn_co2_g", []))
    turn_tokens_in = ";".join(
        str(v) for v in st.session_state.get("turn_tokens_in", [])
    )
    turn_tokens_out = ";".join(
        str(v) for v in st.session_state.get("turn_tokens_out", [])
    )

    frequency = st.session_state.get("frequency")
    guess = st.session_state.get("guess")
    guess_correct = st.session_state.get("guess_correct")
    reactions = ";".join(st.session_state.get("reactions", []))
    reflection = st.session_state.get("reflection")

    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(
                [
                    "timestamp",
                    "condition",
                    "group_code",
                    "duration_s",
                    "n_turns",
                    "tokens_in",
                    "tokens_out",
                    "energy_wh",
                    "co2_g",
                    "turn_energy_wh",
                    "turn_co2_g",
                    "turn_tokens_in",
                    "turn_tokens_out",
                    "frequency",
                    "guess",
                    "guess_correct",
                    "reactions",
                    "reflection",
                ]
            )
        writer.writerow(
            [
                timestamp,
                condition,
                group_code,
                duration_s,
                n_turns,
                tokens_in,
                tokens_out,
                energy_wh,
                co2_g,
                turn_energy_wh,
                turn_co2_g,
                turn_tokens_in,
                turn_tokens_out,
                frequency,
                guess,
                guess_correct,
                reactions,
                reflection,
            ]
        )


def save_conversation_transcript():
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    group_code = st.session_state.get("group_code", "unknown")
    safe_code = (
        "".join(c for c in str(group_code) if c.isalnum() or c in ("-", "_"))
        or "unknown"
    )

    filename = f"group_{safe_code}_{CONDITION}.md"
    filepath = TRANSCRIPT_DIR / filename

    lines = [
        f"# Group {safe_code}",
        f"- Condition: {CONDITION}",
        f"- Timestamp: {datetime.now().isoformat(timespec='seconds')}",
        f"- Turns: {st.session_state.get('n_turns')}",
        "",
        "---",
        "",
    ]

    for message in st.session_state.get("messages", []):
        divider = "\n".join(["", "---", ""])
        lines.append(divider)
        role = "## User" if message["role"] == "user" else "## Assistant"
        lines.append(f"{role}: {message['content']}")
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")


init_state()
stages = {
    "entry": render_entry,
    "task": render_task,
    "habit": render_frequency,
    "guess": render_guess,
    "reveal": render_reveal,
    "reaction": render_reaction,
    "reflect": render_reflect,
    "done": render_done,
}
stages[st.session_state.stage]()
