import streamlit as st

from auth import show_login
from dashboard import show_dashboard
from database import create_supabase_client

st.set_page_config(
    page_title="Personal Asset Dashboard",
    page_icon="📊",
    layout="wide",
)

supabase = create_supabase_client()

try:
    user_response = supabase.auth.get_user()
    current_user = user_response.user
except Exception:
    current_user = None


if current_user is None:
    show_login(supabase)
else:
    show_dashboard(supabase, current_user.email)
