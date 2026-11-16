import streamlit as st

from features.accounts import show_account_manager
from features.assets import show_asset_manager
from features.broker_fees import show_broker_fee_manager
from features.fx import show_fx_manager
from features.holdings import show_holding_manager
from features.overview import show_overview
from features.performance import show_performance_manager
from features.prices import show_price_manager
from features.transactions.page import show_transaction_manager
from features.data_export import show_data_export_manager
from features.insurance import show_insurance_manager


def show_dashboard(supabase, user_email):
    top_left, top_right = st.columns([5, 1])

    with top_left:
        st.title("📊 Personal Asset Dashboard")
        st.caption(f"Signed in as {user_email}")

    with top_right:
        if st.button(
            "Log out",
            width='stretch',
        ):
            try:
                supabase.auth.sign_out()
            finally:
                st.session_state.pop("access_token", None)
                st.session_state.pop("refresh_token", None)
                st.rerun()

    (   overview_tab, 
        accounts_tab,
        insurance_tab, 
        assets_tab, 
        holdings_tab,
        performance_tab,
        prices_tab, 
        transactions_tab, 
        fees_tab,
        fx_tab,
        data_export_tab,
    ) = st.tabs(
        [
            "總覽",
            "帳戶",
            "保險",
            "資產",
            "持倉",
            "績效",
            "價格",
            "交易",
            "券商費率",
            "匯率",
            "資料匯出",
        ]
    )

    with overview_tab:
        show_overview(supabase)

    with accounts_tab:
        show_account_manager(supabase)

    with insurance_tab:
        show_insurance_manager(supabase)
    
    with assets_tab:
        show_asset_manager(supabase)

    with holdings_tab:
        show_holding_manager(supabase)

    with performance_tab:
        show_performance_manager(supabase)

    with prices_tab:
        show_price_manager(supabase)

    with transactions_tab:
        show_transaction_manager(supabase)

    with fees_tab:
        show_broker_fee_manager(supabase)

    with fx_tab:
        show_fx_manager(supabase)

    with data_export_tab:
        show_data_export_manager(
            supabase
        )    