import streamlit as st


def get_supabase_client():
    try:
        from supabase import create_client

        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")
        if not url or not key:
            return None
        return create_client(url, key)
    except Exception:
        print("Exception in client")
        return None


supabase = get_supabase_client()
