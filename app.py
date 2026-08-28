import streamlit as st

nav = st.navigation(
    [
        st.Page("Pages/experiment.py", title="Experiment"),
        st.Page("pages/1_dashboard.py", title="Dashboard"),
    ]
)

nav.run()
