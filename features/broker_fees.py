import pandas as pd
import streamlit as st

def show_broker_fee_manager(supabase):
    
    st.subheader("券商手續費設定")
    st.caption(
        "依券商帳戶及市場設定手續費、折扣與賣出稅率。"
        "同一個券商帳戶可以分別建立台股與美股設定。"
    )

    success_message = st.session_state.pop(
        "broker_fee_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    try:
        accounts_response = (
            supabase.table("accounts")
            .select(
                "id, name, institution, account_type, "
                "base_currency, is_active"
            )
            .eq("account_type", "brokerage")
            .eq("is_active", True)
            .order("name")
            .execute()
        )

        brokerage_accounts = accounts_response.data or []

        settings_response = (
            supabase.table("broker_fee_settings")
            .select(
                "id, account_id, market, commission_rate, "
                "discount_rate, minimum_commission, "
                "sell_stock_tax_rate, sell_etf_tax_rate, "
                "currency, is_active, updated_at"
            )
            .eq("is_active", True)
            .order("updated_at", desc=True)
            .execute()
        )

        fee_settings = settings_response.data or []

    except Exception as error:
        st.error(f"讀取券商費率設定失敗：{error}")
        return

    if not brokerage_accounts:
        st.info(
            "目前沒有使用中的證券／券商帳戶，"
            "請先到「帳戶」頁面新增。"
        )
        return

    account_by_id = {
        account["id"]: account
        for account in brokerage_accounts
    }

    account_ids = list(account_by_id.keys())

    def format_brokerage_account(account_id):
        account = account_by_id[account_id]

        institution = (
            account["institution"]
            if account["institution"]
            else "未指定機構"
        )

        return f'{account["name"]}｜{institution}'

    selected_account_id = st.selectbox(
        "券商帳戶",
        options=account_ids,
        format_func=format_brokerage_account,
        key="broker_fee_account",
    )

    selected_market = st.selectbox(
        "市場",
        options=["TW", "US"],
        format_func=lambda value: {
            "TW": "台灣市場",
            "US": "美國市場",
        }[value],
        key="broker_fee_market",
    )

    existing_setting = next(
        (
            setting
            for setting in fee_settings
            if (
                setting["account_id"] == selected_account_id
                and setting["market"] == selected_market
            )
        ),
        None,
    )

    if existing_setting is not None:
        default_commission_percent = (
            float(existing_setting["commission_rate"])
            * 100
        )

        default_discount_fold = (
            float(existing_setting["discount_rate"])
            * 10
        )

        default_minimum_commission = float(
            existing_setting["minimum_commission"]
        )

        default_stock_tax_percent = (
            float(existing_setting["sell_stock_tax_rate"])
            * 100
        )

        default_etf_tax_percent = (
            float(existing_setting["sell_etf_tax_rate"])
            * 100
        )

        default_currency = existing_setting["currency"]

        st.info("已找到此券商與市場的設定，儲存後會更新原設定。")

    elif selected_market == "TW":
        default_commission_percent = 0.1425
        default_discount_fold = 10.0
        default_minimum_commission = 20.0
        default_stock_tax_percent = 0.3
        default_etf_tax_percent = 0.1
        default_currency = "TWD"

    else:
        default_commission_percent = 0.0
        default_discount_fold = 10.0
        default_minimum_commission = 0.0
        default_stock_tax_percent = 0.0
        default_etf_tax_percent = 0.0
        default_currency = "USD"

    with st.form(
        f"broker_fee_form_"
        f"{selected_account_id}_{selected_market}"
    ):
        commission_percent = st.number_input(
            "牌告手續費率（%）",
            min_value=0.0,
            value=default_commission_percent,
            step=0.0001,
            format="%.4f",
            help=(
                "例如台股 0.1425%，請輸入 0.1425，"
                "不要輸入 0.001425。"
            ),
        )

        discount_fold = st.number_input(
            "手續費折數",
            min_value=0.0,
            max_value=10.0,
            value=default_discount_fold,
            step=0.1,
            format="%.2f",
            help=(
                "例如六折輸入 6；2.8 折輸入 2.8；"
                "沒有折扣輸入 10。"
            ),
        )

        minimum_commission = st.number_input(
            "每筆最低手續費",
            min_value=0.0,
            value=default_minimum_commission,
            step=1.0,
            format="%.2f",
        )

        st.markdown("##### 賣出稅率")

        tax_col1, tax_col2 = st.columns(2)

        with tax_col1:
            stock_tax_percent = st.number_input(
                "股票賣出稅率（%）",
                min_value=0.0,
                value=default_stock_tax_percent,
                step=0.01,
                format="%.4f",
            )

        with tax_col2:
            etf_tax_percent = st.number_input(
                "ETF 賣出稅率（%）",
                min_value=0.0,
                value=default_etf_tax_percent,
                step=0.01,
                format="%.4f",
            )

        currency_options = ["TWD", "USD"]

        currency_index = (
            currency_options.index(default_currency)
            if default_currency in currency_options
            else 0
        )

        currency = st.selectbox(
            "費用幣別",
            options=currency_options,
            index=currency_index,
        )

        submitted = st.form_submit_button(
            "儲存券商費率設定",
            width="stretch",
        )

    if submitted:
        setting_data = {
            "account_id": selected_account_id,
            "market": selected_market,
            "commission_rate": (
                float(commission_percent) / 100
            ),
            "discount_rate": (
                float(discount_fold) / 10
            ),
            "minimum_commission": float(
                minimum_commission
            ),
            "sell_stock_tax_rate": (
                float(stock_tax_percent) / 100
            ),
            "sell_etf_tax_rate": (
                float(etf_tax_percent) / 100
            ),
            "currency": currency,
            "is_active": True,
            "updated_at": pd.Timestamp.now(
                tz="America/Los_Angeles"
            ).isoformat(),
        }

        try:
            if existing_setting is None:
                (
                    supabase.table("broker_fee_settings")
                    .insert(setting_data)
                    .execute()
                )

                message = "券商費率設定新增成功。"

            else:
                (
                    supabase.table("broker_fee_settings")
                    .update(setting_data)
                    .eq("id", existing_setting["id"])
                    .execute()
                )

                message = "券商費率設定更新成功。"

            st.session_state[
                "broker_fee_success_message"
            ] = message

            st.rerun()

        except Exception as error:
            st.error(f"儲存券商費率設定失敗：{error}")

    st.divider()
    st.subheader("目前設定")

    if not fee_settings:
        st.info("目前還沒有券商費率設定。")
        return

    display_rows = []

    for setting in fee_settings:
        account = account_by_id.get(setting["account_id"])

        if account is None:
            account_name = "已停用或不存在的帳戶"
        else:
            account_name = account["name"]

        display_rows.append(
            {
                "券商帳戶": account_name,
                "市場": (
                    "台灣"
                    if setting["market"] == "TW"
                    else "美國"
                ),
                "牌告費率（%）": (
                    float(setting["commission_rate"])
                    * 100
                ),
                "折數": (
                    float(setting["discount_rate"])
                    * 10
                ),
                "最低手續費": float(
                    setting["minimum_commission"]
                ),
                "股票賣出稅（%）": (
                    float(setting["sell_stock_tax_rate"])
                    * 100
                ),
                "ETF 賣出稅（%）": (
                    float(setting["sell_etf_tax_rate"])
                    * 100
                ),
                "幣別": setting["currency"],
            }
        )

    settings_dataframe = pd.DataFrame(display_rows)

    st.dataframe(
        settings_dataframe,
        width="stretch",
        hide_index=True,
        column_config={
            "牌告費率（%）": st.column_config.NumberColumn(
                "牌告費率（%）",
                format="%.4f",
            ),
            "折數": st.column_config.NumberColumn(
                "折數",
                format="%.2f",
            ),
            "最低手續費": st.column_config.NumberColumn(
                "最低手續費",
                format="%.2f",
            ),
            "股票賣出稅（%）": st.column_config.NumberColumn(
                "股票賣出稅（%）",
                format="%.4f",
            ),
            "ETF 賣出稅（%）": st.column_config.NumberColumn(
                "ETF 賣出稅（%）",
                format="%.4f",
            ),
        },
    )

    st.divider()

    with st.expander("刪除費率設定"):
        setting_ids = [
            setting["id"]
            for setting in fee_settings
        ]

        def format_fee_setting(setting_id):
            selected_setting = next(
                setting
                for setting in fee_settings
                if setting["id"] == setting_id
            )

            account = account_by_id.get(
                selected_setting["account_id"]
            )

            account_name = (
                account["name"]
                if account is not None
                else "未知帳戶"
            )

            market_name = {
                "TW": "台灣",
                "US": "美國",
            }.get(
                selected_setting["market"],
                selected_setting["market"],
            )

            return (
                f"{account_name}｜"
                f"{market_name}｜"
                f'{selected_setting["currency"]}'
            )

        selected_setting_id = st.selectbox(
            "選擇要刪除的設定",
            options=setting_ids,
            format_func=format_fee_setting,
            key="delete_broker_fee_setting",
        )

        confirm_delete = st.checkbox(
            "我確認要永久刪除這筆費率設定",
            key="confirm_delete_broker_fee_setting",
        )

        if st.button(
            "刪除費率設定",
            type="primary",
            width="stretch",
            disabled=not confirm_delete,
        ):
            try:
                (
                    supabase.table("broker_fee_settings")
                    .delete()
                    .eq("id", selected_setting_id)
                    .execute()
                )

                st.session_state[
                    "broker_fee_success_message"
                ] = "券商費率設定已刪除。"

                st.rerun()

            except Exception as error:
                st.error(
                    f"刪除券商費率設定失敗：{error}"
                )