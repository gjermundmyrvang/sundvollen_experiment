import streamlit as st

from openai import OpenAI
from ecologits import EcoLogits

# Initialize EcoLogits
EcoLogits.init(providers=["openai"])

client = OpenAI(api_key=st.secrets["OPEN_AI_TEST_KEY"])

CONDITION = st.secrets["CONDITION"]
# MODEL = "gpt-4o-mini"
MODEL = "gpt-5"
