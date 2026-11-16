import streamlit as st


def show_login(supabase):
    st.title("📊 Personal Asset Dashboard")
    st.caption("個人多幣別資產管理系統")

    with st.form("login_form"):
        email = st.text_input("Email")

        password = st.text_input(
            "Password",
            type="password",
        )

        submitted = st.form_submit_button(
            "Log in",
            width="stretch",
        )

    if submitted:
        if not email or not password:
            st.warning(
                "請輸入 Email 和 Password。"
            )
            return

        try:
            response = (
                supabase.auth.sign_in_with_password(
                    {
                        "email": email,
                        "password": password,
                    }
                )
            )

            if response.session:
                st.session_state.access_token = (
                    response.session.access_token
                )

                st.session_state.refresh_token = (
                    response.session.refresh_token
                )

                st.rerun()

        except Exception as error:
            st.error(f"登入失敗：{error}")