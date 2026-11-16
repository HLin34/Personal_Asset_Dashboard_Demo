import streamlit as st
from supabase import create_client


def create_supabase_client():
    """建立目前 Streamlit session 使用的 Supabase client。"""

    client = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )

    access_token = st.session_state.get(
        "access_token"
    )

    refresh_token = st.session_state.get(
        "refresh_token"
    )

    if access_token and refresh_token:
        try:
            response = client.auth.set_session(
                access_token,
                refresh_token,
            )

            if response.session:
                st.session_state.access_token = (
                    response.session.access_token
                )

                st.session_state.refresh_token = (
                    response.session.refresh_token
                )

        except Exception:
            st.session_state.pop(
                "access_token",
                None,
            )

            st.session_state.pop(
                "refresh_token",
                None,
            )

    return client