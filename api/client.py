import sys
import streamlit as st

from openai import OpenAI
from ecologits import EcoLogits
from pathlib import Path

REQUIRED_SECRETS = ["OPEN_AI_TEST_KEY", "CONDITION"]

secrets_path = Path(".streamlit/secrets.toml")


def check_secrets():
    if secrets_path.is_file():
        print("Found secrets.toml file, continuing checking variables")
    else:
        st.error(
            "Manglende oppsett: .streamlit/secrets.toml finnes ikke\n"
            "Kopier `.streamlit/secrets.toml.example` til `.streamlit/secrets.toml` "
            "og fyll inn dine egne verdier. Se README for detaljer."
        )
        st.stop()

    missing = [key for key in REQUIRED_SECRETS if key not in st.secrets]
    if missing:
        st.error(
            "Manglende oppsett: .streamlit/secrets.toml mangler "
            f"følgende nøkler: {', '.join(missing)}.\n\n"
            "Kopier `.streamlit/secrets.toml.example` til `.streamlit/secrets.toml` "
            "og fyll inn dine egne verdier. Se README for detaljer."
        )
        st.stop()

    if st.secrets["CONDITION"] not in ("abstract", "concrete"):
        st.error(
            f"CONDITION må være 'abstract' eller 'concrete', fikk: "
            f"'{st.secrets['CONDITION']}'"
        )
        st.stop()


check_secrets()

# Initialize EcoLogits
EcoLogits.init(providers=["openai"])

client = OpenAI(api_key=st.secrets["OPEN_AI_TEST_KEY"])

CONDITION = st.secrets["CONDITION"]
MODEL = "gpt-5"
