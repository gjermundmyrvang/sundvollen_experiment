import re
import streamlit as st
import pandas as pd

from pathlib import Path

VIZ_HEIGHT = 700
LOG_PATH = Path("data/sessions.csv")


st.set_page_config(
    page_title="Dashboard",
    page_icon=":material/bolt:",
    initial_sidebar_state="collapsed",
    layout="wide",
)

st.title("Dashboard")
st.caption("Inspect data")


def load_sessions():
    if not LOG_PATH.exists():
        return pd.DataFrame(
            columns=[
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
                "guess",
                "guess_correct",
                "reactions",
                "reflection",
            ]
        )
    return pd.read_csv(LOG_PATH, parse_dates=["timestamp"])


df = load_sessions()

if df.empty:
    st.info("Ingen data enda. Kjør gjennom eksperimentet med minst én gruppe først.")
    st.stop()

# Process data
for col in ["turn_energy_wh", "turn_co2_g"]:
    df[col] = df[col].apply(
        lambda s: (
            [float(x) for x in re.split(r"[,;]", str(s))]
            if pd.notna(s) and str(s).strip() != ""
            else []
        )
    )

for col in ["turn_tokens_in", "turn_tokens_out"]:
    df[col] = df[col].apply(
        lambda s: (
            [int(x) for x in re.split(r"[,;]", str(s))]
            if pd.notna(s) and str(s).strip() != ""
            else []
        )
    )

df["reactions"] = df["reactions"].apply(
    lambda s: (
        [t.strip() for t in re.split(r"[,;]", str(s)) if t.strip()]
        if pd.notna(s)
        else []
    )
)

# --- High-Level KPIs ---
st.header("High-Level KPIs")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Sessions", len(df))
m2.metric("Total Energy (Wh)", f"{df['energy_wh'].sum():.2f}")
m3.metric("Total CO2 (g)", f"{df['co2_g'].sum():.2f}")
m4.metric("Avg Session Duration", f"{df['duration_s'].mean():.1f}s")
m5.metric(
    "Guess Accuracy",
    f"{(df['guess_correct'].sum() / len(df) * 100):.0f}%" if len(df) > 0 else "N/A",
)

st.divider()

# --- Insight Tabs ---
st.header("Insights")

tab1, tab2, tab3 = st.tabs(
    ["Energy & Tokens", "Turn Progression", "Participant Perception"]
)

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Total Energy (Wh) by Group")
        energy_by_group = (
            df.groupby("group_code")["energy_wh"].sum().sort_values(ascending=False)
        )
        st.bar_chart(energy_by_group, y_label="Energy (Wh)", height=VIZ_HEIGHT)

    with col2:
        st.subheader("Input vs Output Tokens by Group")
        tokens_df = df.set_index("group_code")[["tokens_in", "tokens_out"]]
        st.bar_chart(tokens_df, stack=False, height=VIZ_HEIGHT)

with tab2:
    st.subheader("Energy Draw Per Prompt")
    turn_df = df.explode("turn_energy_wh").copy()
    turn_df["turn_number"] = turn_df.groupby(level=0).cumcount() + 1
    turn_df["turn_energy_wh"] = turn_df["turn_energy_wh"].astype(float)

    chart_data = turn_df.pivot(
        index="turn_number", columns="group_code", values="turn_energy_wh"
    )
    st.line_chart(
        chart_data, y_label="Wh per Turn", x_label="Turn Number", height=VIZ_HEIGHT
    )

with tab3:
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Participant Reactions")
        all_reactions = [r for sublist in df["reactions"] for r in sublist]
        reaction_counts = pd.Series(all_reactions).value_counts().reset_index()
        reaction_counts.columns = ["Reaction", "Count"]
        st.bar_chart(
            reaction_counts.set_index("Reaction"),
            y_label="Occurrences",
            height=VIZ_HEIGHT,
        )

    with col_b:
        st.subheader("Pre-Session Guess Accuracy")
        guess_dist = df.groupby(["guess", "guess_correct"]).size().unstack(fill_value=0)
        st.bar_chart(guess_dist, height=VIZ_HEIGHT)

    st.subheader("Participant Qualitative Reflections")
    st.dataframe(
        df[["group_code", "frequency", "reflection"]].dropna(subset=["reflection"]),
        hide_index=True,
        height=VIZ_HEIGHT,
    )

st.divider()

st.header("Raw data")
st.dataframe(df)
