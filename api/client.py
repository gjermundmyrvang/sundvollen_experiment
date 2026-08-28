import sys
import streamlit as st

from openai import OpenAI
from ecologits import EcoLogits

REQUIRED_SECRETS = ["OPEN_AI_TEST_KEY", "CONDITION"]


def check_secrets():
    missing = [key for key in REQUIRED_SECRETS if key not in st.secrets]
    if missing:
        st.error(
            "Manglende oppsett: .streamlit/secrets.toml finnes ikke, eller mangler "
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
