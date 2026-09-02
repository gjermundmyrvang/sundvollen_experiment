import csv
import streamlit as st
import time

from datetime import datetime
from pathlib import Path
from api.client import client, CONDITION, MODEL
from schema import EXPECTED_COLUMNS
from api.supabase import supabase

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
    "Hvor ofte bruker dere en chatbot til en slik type oppgave &rarr; "
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

SCOPE_OPTIONS = [
    "Selve regnekraften (databehandling)",
    "Kjøling av datasenteret",
    "Nettverk/dataoverføring",
    "Produksjon av maskinvaren",
    "Lagring av data",
    "Selve treningen av modellen (før dette ble tatt i bruk)",
]

GROUND_TRUTH_INCLUDED = {
    "Selve regnekraften (databehandling)": True,
    "Kjøling av datasenteret": True,
    "Nettverk/dataoverføring": False,
    "Produksjon av maskinvaren": True,
    "Lagring av data": False,
    "Selve treningen av modellen (før dette ble tatt i bruk)": False,
}

SCOPE_TRUTH_NOTE = (
    "Tallet inkluderer strømbruk til selve databehandlingen (GPU/server) "
    "og kjøling av datasenteret, samt en andel av utstyrets produksjon. "
    "Nettverk, datalagring og selve treningen av modellen er **IKKE** med."
)


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

    turn_keys = [
        "turn_energy_wh",
        "turn_energy_wh_min",
        "turn_energy_wh_max",
        "turn_co2_g",
        "turn_co2_g_min",
        "turn_co2_g_max",
        "turn_water_l",
        "turn_water_l_min",
        "turn_water_l_max",
        "turn_tokens_in",
        "turn_tokens_out",
        "scope_beliefs",
    ]
    for key in turn_keys:
        if key not in st.session_state:
            st.session_state[key] = []


def reset_for_next_group():
    st.session_state.clear()
    init_state()
    st.session_state.stage = "entry"


def render_entry():
    print(f"Running experiment in mode: {CONDITION}")
    st.title("Sundvollen AI")
    st.markdown(
        "> Hvor mye ressurser krever en kort samtale med en AI chatbot egentlig?"
    )
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        code = st.text_input("Skriv inn gruppekoden dere fikk utdelt")
    with col2:
        st.space("small")
        if st.button("Start", disabled=not code, type="primary"):
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
    st.badge(MODEL)
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

        answer = response.output_text
        impacts_data = extract_impacts(response)

        st.session_state.messages.append({"role": "assistant", "content": answer})

        # Store metrics
        st.session_state.turn_energy_wh.append(impacts_data["energy_wh"])
        st.session_state.turn_energy_wh_min.append(impacts_data["energy_wh_min"])
        st.session_state.turn_energy_wh_max.append(impacts_data["energy_wh_max"])

        st.session_state.turn_co2_g.append(impacts_data["co2_g"])
        st.session_state.turn_co2_g_min.append(impacts_data["co2_g_min"])
        st.session_state.turn_co2_g_max.append(impacts_data["co2_g_max"])

        st.session_state.turn_water_l.append(impacts_data["water_l"])
        st.session_state.turn_water_l_min.append(impacts_data["water_l_min"])
        st.session_state.turn_water_l_max.append(impacts_data["water_l_max"])
        st.session_state.turn_tokens_in.append(response.usage.input_tokens)
        st.session_state.turn_tokens_out.append(response.usage.output_tokens)

        st.session_state.awaiting_response = False
        st.rerun()

    # Allow user to finish after at least 1 message
    if user_message_count >= 1:
        if st.button(
            "Trykk her hvis dere ønsker å fullføre", type="secondary", width="stretch"
        ):
            finalize_session_metrics()
            st.session_state.stage = "habit"
            st.rerun()


def extract_impacts(response):
    impacts = response.impacts

    energy_min = impacts.energy.value.min * 1000
    energy_max = impacts.energy.value.max * 1000
    energy_mid = (energy_min + energy_max) / 2

    co2_min = impacts.gwp.value.min * 1000
    co2_max = impacts.gwp.value.max * 1000
    co2_mid = (co2_min + co2_max) / 2

    water_min = impacts.wcf.value.min
    water_max = impacts.wcf.value.max
    water_mid = (water_min + water_max) / 2

    return {
        "energy_wh": energy_mid,
        "energy_wh_min": energy_min,
        "energy_wh_max": energy_max,
        "co2_g": co2_mid,
        "co2_g_min": co2_min,
        "co2_g_max": co2_max,
        "water_l": water_mid,
        "water_l_min": water_min,
        "water_l_max": water_max,
    }


def finalize_session_metrics():
    st.session_state.energy_wh = sum(st.session_state.turn_energy_wh)
    st.session_state.energy_wh_min = sum(st.session_state.turn_energy_wh_min)
    st.session_state.energy_wh_max = sum(st.session_state.turn_energy_wh_max)

    st.session_state.co2_g = sum(st.session_state.turn_co2_g)
    st.session_state.co2_g_min = sum(st.session_state.turn_co2_g_min)
    st.session_state.co2_g_max = sum(st.session_state.turn_co2_g_max)

    st.session_state.water_l = sum(st.session_state.turn_water_l)
    st.session_state.water_l_min = sum(st.session_state.turn_water_l_min)
    st.session_state.water_l_max = sum(st.session_state.turn_water_l_max)

    st.session_state.tokens_in = sum(st.session_state.turn_tokens_in)
    st.session_state.tokens_out = sum(st.session_state.turn_tokens_out)
    st.session_state.n_turns = len(st.session_state.turn_energy_wh)

    try:
        update_shared_total(st.session_state.energy_wh, st.session_state.water_l)
    except Exception as e:
        st.warning(
            "Kunne ikke oppdatere delt total (ingen nettverk?), fortsetter lokalt."
        )

    save_conversation_transcript()


def update_shared_total(energy_wh, water_l):
    if supabase is None:
        return  # feature not configured, silently skip
    try:
        supabase.rpc(
            "increment_totals",
            {
                "add_energy": energy_wh,
                "add_water": water_l,
            },
        ).execute()
    except Exception:
        pass  # continue if network hiccup breaks flow


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
        st.session_state.stage = "scope"
        st.rerun()

    st.image(
        "https://images.unsplash.com/photo-1711056831898-97718f6972d3?q=80&w=4140&auto=format&fit=crop&ixlib=rb-4.1.0&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D",
        caption="Photo by Maxence Pira on Unsplash",
        width="stretch",
    )


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


def render_scope():
    st.subheader("Hva tror dere telles med?")
    st.write(
        "Før 'fasiten', hvilke av disse operasjonene tror dere "
        "faktisk er regnet med i det tallet?"
    )
    scope_beliefs = st.multiselect("Velg alt dere tror er inkludert", SCOPE_OPTIONS)
    if st.button("Lås svar", disabled=len(scope_beliefs) == 0):
        st.session_state.scope_beliefs = scope_beliefs
        st.session_state.stage = "reveal"
        st.rerun()


def render_reveal():
    st.subheader("Fasit")

    actual_wh = st.session_state.get("energy_wh")
    frequency_label = st.session_state.get("frequency")
    guess = st.session_state.get("guess")
    guess_correct = st.session_state.get("guess_correct")

    if CONDITION == "abstract":
        render_abstract_reveal(actual_wh, guess, guess_correct, frequency_label)
    else:
        render_concrete_visual(actual_wh, frequency_label, guess, guess_correct)

    st.divider()

    render_scope_comparison()

    if st.button("Neste"):
        st.session_state.stage = "reaction"
        st.rerun()


def render_scope_comparison():
    st.markdown("##### Hva trodde dere var med i tallet?")

    beliefs = st.session_state.get("scope_beliefs", [])
    scoreable_options = [
        opt for opt in SCOPE_OPTIONS if GROUND_TRUTH_INCLUDED[opt] is not None
    ]

    believed_included = [opt for opt in scoreable_options if opt in beliefs]
    believed_excluded = [opt for opt in scoreable_options if opt not in beliefs]

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Trodde var med:**")
        if not believed_included:
            st.write("_(ingenting valgt)_")
        for opt in believed_included:
            correct = GROUND_TRUTH_INCLUDED[opt] is True
            icon = ":material/task_alt:" if correct else ":material/cancel:"
            st.write(f"{icon} {opt}")

    with col2:
        st.write("**Trodde ikke var med:**")
        if not believed_excluded:
            st.write("_(alt ble valgt)_")
        for opt in believed_excluded:
            correct = GROUND_TRUTH_INCLUDED[opt] is False
            icon = ":material/task_alt:" if correct else ":material/cancel:"
            st.write(f"{icon} {opt}")

    st.caption(SCOPE_TRUTH_NOTE)


def render_abstract_reveal(actual_wh, guess, guess_correct, frequency_label):
    st.caption(
        f"Sammenlikner med **{REFERENCE_WH}Wh** som tilsvarer fulladet smarttelefon."
    )
    energy_min = st.session_state.get("energy_wh_min")
    energy_max = st.session_state.get("energy_wh_max")
    water_l = st.session_state.get("water_l")
    water_l_min = st.session_state.get("water_l_min")
    water_l_max = st.session_state.get("water_l_max")

    if not st.session_state.get("reveal_animated"):
        st.write(f"Dere gjettet: **{guess}**")
        time.sleep(0.7)

        if guess_correct:
            st.success("Riktig gjettet!")
        else:
            st.error("Ikke helt &rarr; her er fasiten.")
        time.sleep(1.0)

        number_placeholder = st.empty()
        animate_number(
            number_placeholder, actual_wh, unit="Wh", label="Denne samtalen brukte"
        )
        st.caption(
            f"Estimert mellom {energy_min:.2f} og {energy_max:.2f} Wh &rarr; "
            f"arkitekturen til denne modellen er ikke offentlig kjent, "
            f"så dette er et anslag."
        )
        time.sleep(1.0)

        st.write(
            f"💧 I tillegg brukte samtalen omtrent **{water_l:.3f} liter vann** "
            f"({water_l_min:.3f}–{water_l_max:.3f} L)."
        )

        time.sleep(1.0)

        per_week, yearly_wh = compute_yearly_projection(actual_wh, frequency_label)
        yearly_min = energy_min * per_week * 52
        yearly_max = energy_max * per_week * 52

        st.markdown(f"##### Hvis dere gjør dette {per_week}x i uken ...")
        time.sleep(0.6)

        yearly_placeholder = st.empty()
        animate_number(
            yearly_placeholder, yearly_wh, unit="Wh", label="... blir det på ett år"
        )
        st.caption(
            f"Et sted mellom {yearly_min:.0f} og {yearly_max:.0f} Wh, avhengig av anslaget."
        )

        phone_charges = yearly_wh / REFERENCE_WH
        st.caption(
            f"Det tilsvarer omtrent **{phone_charges:.0f} fulle telefonladninger** i året."
        )

        st.session_state.reveal_animated = True

    else:
        st.metric("Denne samtalen", f"{actual_wh:.2f} Wh")
        st.caption(f"({energy_min:.2f}–{energy_max:.2f} Wh)")
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


def render_concrete_visual(actual_wh, frequency_label, guess, guess_correct):
    if not st.session_state.get("reveal_animated"):
        st.write(f"Dere gjettet: **{guess}**")
        time.sleep(0.7)

        if guess_correct:
            st.success("Riktig gjettet!")
        else:
            st.error("Ikke helt &rarr; her er fasiten.")
        time.sleep(1.0)

    st.markdown("##### Denne samtalen, i telefonladninger:")
    render_battery_row(actual_wh, icon_width=70, per_row=6)

    per_week, yearly_wh = compute_yearly_projection(actual_wh, frequency_label)
    st.markdown(f"##### Hvis dere gjør dette {per_week}x i uken, i ett år:")
    st.caption(f"Basert på deres valg tidligere: `{frequency_label}`")
    render_battery_row(yearly_wh)

    st.session_state.reveal_animated = True
    st.session_state.reveal_done = True


def render_battery_row(wh_value, reference_wh=None, icon_width=20, per_row=25):
    reference_wh = reference_wh or REFERENCE_WH
    n_full = wh_value / reference_wh
    full_icons = int(n_full)
    remainder_fraction = n_full - full_icons

    total = full_icons + (1 if remainder_fraction > 0 else 0)
    if total == 0:
        st.write("(ingen målbar ladning)")
        return

    rows = (total + per_row - 1) // per_row
    idx = 0
    for _ in range(rows):
        cols = st.columns(per_row)
        for col in cols:
            if idx >= total:
                break
            with col:
                if idx < full_icons:
                    st.image("assets/battery_full.svg", width=icon_width)
                else:
                    st.image(
                        battery_icon_for_fraction(remainder_fraction), width=icon_width
                    )
            idx += 1


def battery_icon_for_fraction(fraction):
    if fraction >= 0.75:
        return "assets/battery_full.svg"
    elif fraction >= 0.25:
        return "assets/battery_half.svg"
    else:
        return "assets/battery_low.svg"


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
    with st.expander("Trenger dere noen tanker å starte fra?", expanded=True):
        st.markdown(
            "- Hva endret seg, om noe, i hvordan dere tenker om denne typen chatbot-bruk?\n"
            "- Hva hjelper tallet dere forstå, og hva er fortsatt uklart?\n"
            "- Hvem bør ha ansvar for å redusere denne typen påvirkning, og hvorfor?\n"
            "- Følte representasjonen ut som en måling, et anslag, en sammenligning, "
            "eller noe annet?"
        )

    text = st.text_area("Hva overrasket dere mest?")
    if st.button("Fullfør", disabled=not text.strip(), type="primary"):
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

    row_values = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "condition": CONDITION,
        "group_code": st.session_state.get("group_code"),
        "duration_s": (
            datetime.now() - st.session_state.get("start_time")
        ).total_seconds(),
        "n_turns": st.session_state.get("n_turns"),
        "tokens_in": st.session_state.get("tokens_in"),
        "tokens_out": st.session_state.get("tokens_out"),
        "energy_wh": st.session_state.get("energy_wh"),
        "energy_wh_min": st.session_state.get("energy_wh_min"),
        "energy_wh_max": st.session_state.get("energy_wh_max"),
        "co2_g": st.session_state.get("co2_g"),
        "co2_g_min": st.session_state.get("co2_g_min"),
        "co2_g_max": st.session_state.get("co2_g_max"),
        "water_l": st.session_state.get("water_l"),
        "water_l_min": st.session_state.get("water_l_min"),
        "water_l_max": st.session_state.get("water_l_max"),
        "turn_energy_wh": ";".join(
            str(v) for v in st.session_state.get("turn_energy_wh", [])
        ),
        "turn_energy_wh_min": ";".join(
            str(v) for v in st.session_state.get("turn_energy_wh_min", [])
        ),
        "turn_energy_wh_max": ";".join(
            str(v) for v in st.session_state.get("turn_energy_wh_max", [])
        ),
        "turn_co2_g": ";".join(str(v) for v in st.session_state.get("turn_co2_g", [])),
        "turn_co2_g_min": ";".join(
            str(v) for v in st.session_state.get("turn_co2_g_min", [])
        ),
        "turn_co2_g_max": ";".join(
            str(v) for v in st.session_state.get("turn_co2_g_max", [])
        ),
        "turn_water_l": ";".join(
            str(v) for v in st.session_state.get("turn_water_l", [])
        ),
        "turn_water_l_min": ";".join(
            str(v) for v in st.session_state.get("turn_water_l_min", [])
        ),
        "turn_water_l_max": ";".join(
            str(v) for v in st.session_state.get("turn_water_l_max", [])
        ),
        "turn_tokens_in": ";".join(
            str(v) for v in st.session_state.get("turn_tokens_in", [])
        ),
        "turn_tokens_out": ";".join(
            str(v) for v in st.session_state.get("turn_tokens_out", [])
        ),
        "frequency": st.session_state.get("frequency"),
        "guess": st.session_state.get("guess"),
        "guess_correct": st.session_state.get("guess_correct"),
        "reactions": ";".join(st.session_state.get("reactions", [])),
        "reflection": st.session_state.get("reflection"),
        "scope_beliefs": ";".join(st.session_state.get("scope_beliefs", [])),
    }

    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(EXPECTED_COLUMNS)
        writer.writerow([row_values[col] for col in EXPECTED_COLUMNS])


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
    "scope": render_scope,
    "reveal": render_reveal,
    "reaction": render_reaction,
    "reflect": render_reflect,
    "done": render_done,
}
stages[st.session_state.stage]()
