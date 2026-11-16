import pandas as pd
import streamlit as st

from .corporate_actions import (
    show_split_cancellation_manager,
    show_split_entry,
)
from .csv_import import (
    show_yushan_csv_import_preview,
)
from .general_csv_import import (
    show_general_csv_import_preview,
)
from .dividends import (
    show_dividend_cancellation_manager,
    show_dividend_edit_manager,
    show_dividend_entry,
)
from .trades import (
    show_trade_cancellation_manager,
    show_trade_edit_manager,
    show_trade_entry,
)

def show_transaction_manager(supabase):
    st.subheader("交易與餘額")
    st.caption(
        "先輸入各帳戶目前的現金餘額，作為資產追蹤起點。"
    )

    success_message = st.session_state.pop(
        "transaction_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    try:
        accounts_response = (
            supabase.table("accounts")
            .select(
                "id, name, institution, base_currency, is_active"
            )
            .order("created_at")
            .execute()
        )

        assets_response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, "
                "currency, market, external_symbol, "
                "price_source, is_active"
            )
            .order("created_at")
            .execute()
        )

        accounts = accounts_response.data or []
        assets = assets_response.data or []

    except Exception as error:
        st.error(f"讀取帳戶或資產失敗：{error}")
        return

    active_accounts = [
        account
        for account in accounts
        if account["is_active"]
    ]

    active_cash_assets = [
        asset
        for asset in assets
        if (
            asset["is_active"]
            and asset["asset_type"] == "cash"
        )
    ]

    if not active_accounts:
        st.warning("請先建立至少一個使用中的帳戶。")
        return

    if not active_cash_assets:
        st.warning("請先建立至少一個使用中的現金資產。")
        return

    show_trade_entry(
        supabase,
        active_accounts,
        assets,
    )

    show_dividend_entry(
        supabase,
        active_accounts,
        assets,
    )

    st.divider()

    show_split_entry(
        supabase,
        active_accounts,
        assets,
    )

    show_split_cancellation_manager(
        supabase,
        active_accounts,
        assets,
    )    
    
    show_dividend_edit_manager(
        supabase,
        active_accounts,
        assets,
    )

    show_dividend_cancellation_manager(
        supabase,
        active_accounts,
        assets,
    )

    show_trade_edit_manager(
        supabase,
        active_accounts,
        assets,
    )

    show_trade_cancellation_manager(
        supabase,
        active_accounts,
        assets,
    )

    st.divider()

    with st.expander("新增期初餘額", expanded=False):
        account_ids = [
            account["id"]
            for account in active_accounts
        ]

        def format_transaction_account(account_id):
            selected = next(
                account
                for account in active_accounts
                if account["id"] == account_id
            )

            institution = (
                selected["institution"]
                if selected["institution"]
                else "未指定機構"
            )

            return (
                f'{selected["name"]} | '
                f"{institution}"
            )

        cash_asset_ids = [
            asset["id"]
            for asset in active_cash_assets
        ]

        def format_cash_asset(asset_id):
            selected = next(
                asset
                for asset in active_cash_assets
                if asset["id"] == asset_id
            )

            return (
                f'{selected["symbol"]} | '
                f'{selected["name"]}'
            )

        with st.form(
            "add_opening_balance_form",
            clear_on_submit=True,
        ):
            selected_account_id = st.selectbox(
                "帳戶",
                options=account_ids,
                format_func=format_transaction_account,
            )

            selected_asset_id = st.selectbox(
                "現金資產",
                options=cash_asset_ids,
                format_func=format_cash_asset,
            )

            opening_balance = st.number_input(
                "目前餘額",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
            )

            transaction_date = st.date_input(
                "餘額日期",
                value="today",
            )

            memo = st.text_input(
                "備註（選填）",
                placeholder="例如：首次建立資產紀錄",
            )

            submitted = st.form_submit_button(
                "儲存期初餘額",
                width='stretch',
            )

        if submitted:
            if opening_balance <= 0:
                st.warning("期初餘額必須大於 0。")

            else:
                selected_account = next(
                    account
                    for account in active_accounts
                    if account["id"] == selected_account_id
                )

                selected_asset = next(
                    asset
                    for asset in active_cash_assets
                    if asset["id"] == selected_asset_id
                )

                transaction_id = None

                try:
                    transaction_response = (
                        supabase.table("transactions")
                        .insert(
                            {
                                "transaction_date": (
                                    f"{transaction_date.isoformat()}"
                                    "T12:00:00+00:00"
                                ),
                                "transaction_type": (
                                    "opening_balance"
                                ),
                                "description": (
                                    f'{selected_account["name"]} '
                                    f'{selected_asset["symbol"]} '
                                    "期初餘額"
                                ),
                            }
                        )
                        .execute()
                    )

                    transaction_data = (
                        transaction_response.data or []
                    )

                    if not transaction_data:
                        raise RuntimeError(
                            "交易建立後未取得交易 ID。"
                        )

                    transaction_id = transaction_data[0]["id"]

                    (
                        supabase.table("transaction_entries")
                        .insert(
                            {
                                "transaction_id": transaction_id,
                                "account_id": selected_account_id,
                                "asset_id": selected_asset_id,
                                "quantity_delta": float(
                                    opening_balance
                                ),
                                "unit_price": None,
                                "memo": (
                                    memo.strip()
                                    if memo.strip()
                                    else None
                                ),
                            }
                        )
                        .execute()
                    )

                    st.session_state[
                        "transaction_success_message"
                    ] = "期初餘額新增成功。"

                    st.rerun()

                except Exception as error:
                    if transaction_id is not None:
                        try:
                            (
                                supabase.table("transactions")
                                .delete()
                                .eq("id", transaction_id)
                                .execute()
                            )
                        except Exception:
                            pass

                    st.error(f"新增期初餘額失敗：{error}")

    st.divider()
    with st.expander("更新現金餘額"):
        update_account_ids = [
            account["id"]
            for account in active_accounts
        ]

        def format_update_account(account_id):
            selected = next(
                account
                for account in active_accounts
                if account["id"] == account_id
            )

            institution = (
                selected["institution"]
                if selected["institution"]
                else "未指定機構"
            )

            return (
                f'{selected["name"]} | '
                f"{institution}"
            )

        update_asset_ids = [
            asset["id"]
            for asset in active_cash_assets
        ]

        def format_update_asset(asset_id):
            selected = next(
                asset
                for asset in active_cash_assets
                if asset["id"] == asset_id
            )

            return (
                f'{selected["symbol"]} | '
                f'{selected["name"]}'
            )

        update_account_id = st.selectbox(
            "選擇帳戶",
            options=update_account_ids,
            format_func=format_update_account,
            key="update_balance_account_id",
        )

        update_asset_id = st.selectbox(
            "選擇現金資產",
            options=update_asset_ids,
            format_func=format_update_asset,
            key="update_balance_asset_id",
        )

        selected_update_account = next(
            account
            for account in active_accounts
            if account["id"] == update_account_id
        )

        selected_update_asset = next(
            asset
            for asset in active_cash_assets
            if asset["id"] == update_asset_id
        )

        try:
            current_entries_response = (
                supabase.table("transaction_entries")
                .select("quantity_delta")
                .eq("account_id", update_account_id)
                .eq("asset_id", update_asset_id)
                .execute()
            )

            current_entries = (
                current_entries_response.data or []
            )

            current_balance = sum(
                float(entry["quantity_delta"])
                for entry in current_entries
            )

        except Exception as error:
            st.error(f"讀取目前餘額失敗：{error}")
            current_balance = 0.0

        st.metric(
            "系統目前餘額",
            (
                f'{selected_update_asset["symbol"]} '
                f"{current_balance:,.2f}"
            ),
        )

        with st.form(
            (
                "update_cash_balance_form_"
                f"{update_account_id}_"
                f"{update_asset_id}"
            )
        ):
            new_balance = st.number_input(
                "最新實際餘額",
                min_value=0.0,
                value=float(current_balance),
                step=100.0,
                format="%.2f",
            )

            balance_date = st.date_input(
                "餘額日期",
                value="today",
            )

            update_memo = st.text_input(
                "備註（選填）",
                placeholder="例如：10 月銀行餘額更新",
            )

            update_submitted = st.form_submit_button(
                "更新餘額",
                width='stretch',
            )

        if update_submitted:
            balance_delta = round(
                float(new_balance) - current_balance,
                8,
            )

            if abs(balance_delta) < 0.00000001:
                st.info(
                    "最新餘額與系統目前餘額相同，"
                    "不需要建立調整紀錄。"
                )

            else:
                transaction_id = None

                try:
                    transaction_response = (
                        supabase.table("transactions")
                        .insert(
                            {
                                "transaction_date": (
                                    f"{balance_date.isoformat()}"
                                    "T12:00:00+00:00"
                                ),
                                "transaction_type": "adjustment",
                                "description": (
                                    f'{selected_update_account["name"]} '
                                    f'{selected_update_asset["symbol"]} '
                                    f"餘額更新至 "
                                    f"{float(new_balance):.2f}"
                                ),
                            }
                        )
                        .execute()
                    )

                    transaction_data = (
                        transaction_response.data or []
                    )

                    if not transaction_data:
                        raise RuntimeError(
                            "交易建立後未取得交易 ID。"
                        )

                    transaction_id = transaction_data[0]["id"]

                    default_memo = (
                        "定期餘額更新："
                        f"{current_balance:.2f} → "
                        f"{float(new_balance):.2f}"
                    )

                    final_memo = default_memo

                    if update_memo.strip():
                        final_memo = (
                            f"{default_memo} | "
                            f"{update_memo.strip()}"
                        )

                    (
                        supabase.table("transaction_entries")
                        .insert(
                            {
                                "transaction_id": transaction_id,
                                "account_id": update_account_id,
                                "asset_id": update_asset_id,
                                "quantity_delta": balance_delta,
                                "unit_price": None,
                                "memo": final_memo,
                            }
                        )
                        .execute()
                    )

                    st.session_state[
                        "transaction_success_message"
                    ] = (
                        "現金餘額更新成功："
                        f'{selected_update_asset["symbol"]} '
                        f"{float(new_balance):,.2f}"
                    )

                    st.rerun()

                except Exception as error:
                    if transaction_id is not None:
                        try:
                            (
                                supabase.table("transactions")
                                .delete()
                                .eq("id", transaction_id)
                                .execute()
                            )
                        except Exception:
                            pass

                    st.error(f"更新現金餘額失敗：{error}")

    st.subheader("目前帳戶餘額")

    try:
        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "id, transaction_id, account_id, asset_id, "
                "quantity_delta, unit_price, memo, created_at"
            )
            .execute()
        )

        entries = entries_response.data or []

    except Exception as error:
        st.error(f"讀取餘額失敗：{error}")
        return

    if not entries:
        st.info("目前還沒有餘額紀錄。")
        return

    account_map = {
        account["id"]: account
        for account in accounts
    }

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    balances = {}

    for entry in entries:
        balance_key = (
            entry["account_id"],
            entry["asset_id"],
        )

        balances[balance_key] = (
            balances.get(balance_key, 0.0)
            + float(entry["quantity_delta"])
        )

    balance_rows = []

    for (
        account_id,
        asset_id,
    ), balance in balances.items():
        account = account_map.get(account_id)
        asset = asset_map.get(asset_id)

        if account is None or asset is None:
            continue

        balance_rows.append(
            {
                "帳戶": account["name"],
                "資產代號": asset["symbol"],
                "資產名稱": asset["name"],
                "幣別": asset["currency"],
                "餘額": balance,
            }
        )

    if not balance_rows:
        st.info("目前還沒有可顯示的餘額。")
        return

    balance_dataframe = pd.DataFrame(balance_rows)

    balance_dataframe = balance_dataframe.sort_values(
        by=["帳戶", "資產代號"]
    )

    st.dataframe(
        balance_dataframe,
        width='stretch',
        hide_index=True,
        column_config={
            "餘額": st.column_config.NumberColumn(
                "餘額",
                format="%.2f",
            )
        },
    )

    st.divider()

    show_general_csv_import_preview(
        supabase,
        accounts,
        assets,
    )

    st.divider()

    show_yushan_csv_import_preview(
        supabase,
        accounts,
        assets,
    )
    
    st.divider()
    st.subheader("交易紀錄")

    transaction_type_labels = {
        "opening_balance": "期初餘額",
        "deposit": "存入",
        "withdrawal": "提領",
        "buy": "買入",
        "sell": "賣出",
        "dividend": "股利",
        "interest": "利息",
        "fee": "費用",
        "tax": "稅款",
        "transfer": "轉帳",
        "fx_exchange": "換匯",
        "split": "股票分割",
        "adjustment": "餘額調整",
    }

    try:
        transactions_response = (
            supabase.table("transactions")
            .select(
                "id, transaction_date, transaction_type, "
                "description, external_reference, created_at"
            )
            .execute()
        )

        transactions = transactions_response.data or []

    except Exception as error:
        st.error(f"讀取交易紀錄失敗：{error}")
        return

    transaction_map = {
        transaction["id"]: transaction
        for transaction in transactions
    }

    history_rows = []

    for entry in entries:
        transaction = transaction_map.get(
            entry["transaction_id"]
        )

        account = account_map.get(
            entry["account_id"]
        )

        asset = asset_map.get(
            entry["asset_id"]
        )

        if (
            transaction is None
            or account is None
            or asset is None
        ):
            continue

        history_rows.append(
            {
                "帳戶ID": entry["account_id"],
                "資產ID": entry["asset_id"],
                "交易時間": transaction["transaction_date"],
                "建立時間": entry["created_at"],
                "日期": transaction["transaction_date"],
                "類型": transaction_type_labels.get(
                    transaction["transaction_type"],
                    transaction["transaction_type"],
                ),
                "帳戶": account["name"],
                "資產": asset["symbol"],
                "幣別": asset["currency"],
                "增減數量": float(
                    entry["quantity_delta"]
                ),
                "說明": transaction["description"] or "",
                "備註": entry["memo"] or "",
            }
        )

    if not history_rows:
        st.info("目前還沒有交易紀錄。")
        return

    history_dataframe = pd.DataFrame(history_rows)

    history_dataframe["交易時間"] = pd.to_datetime(
        history_dataframe["交易時間"],
        utc=True,
        format="mixed",
    )

    history_dataframe["建立時間"] = pd.to_datetime(
        history_dataframe["建立時間"],
        utc=True,
        format="mixed",
    )

    history_dataframe = history_dataframe.sort_values(
        by=[
            "帳戶ID",
            "資產ID",
            "交易時間",
            "建立時間",
        ]
    )

    history_dataframe["更新後餘額"] = (
        history_dataframe.groupby(
            ["帳戶ID", "資產ID"]
        )["增減數量"].cumsum()
    )

    history_dataframe = history_dataframe.sort_values(
        by=[
            "交易時間",
            "建立時間",
        ],
        ascending=False,
    )

    history_dataframe["日期"] = (
        history_dataframe["交易時間"]
        .dt.strftime("%Y-%m-%d")
    )

    history_dataframe["增減"] = (
        history_dataframe["增減數量"]
        .apply(
            lambda value: (
                f"+{value:,.2f}"
                if value > 0
                else f"{value:,.2f}"
            )
        )
    )

    history_dataframe["更新後餘額"] = (
        history_dataframe["更新後餘額"]
        .apply(lambda value: f"{value:,.2f}")
    )

    history_display = history_dataframe[
        [
            "日期",
            "類型",
            "帳戶",
            "資產",
            "幣別",
            "增減",
            "更新後餘額",
            "說明",
            "備註",
        ]
    ]

    st.dataframe(
        history_display,
        width='stretch',
        hide_index=True,
    )

    st.divider()

    with st.expander("撤銷最新紀錄"):
        st.caption(
            "系統只允許撤銷每個帳戶與資產組合中，"
            "最新建立的期初餘額或餘額調整紀錄。"
        )

        latest_entries = {}

        for entry in entries:
            entry_key = (
                entry["account_id"],
                entry["asset_id"],
            )

            existing_entry = latest_entries.get(entry_key)

            if existing_entry is None:
                latest_entries[entry_key] = entry

            else:
                existing_time = pd.to_datetime(
                    existing_entry["created_at"],
                    utc=True,
                )

                current_time = pd.to_datetime(
                    entry["created_at"],
                    utc=True,
                )

                if current_time > existing_time:
                    latest_entries[entry_key] = entry

        reversible_entries = []

        for entry in latest_entries.values():
            transaction = transaction_map.get(
                entry["transaction_id"]
            )

            if transaction is None:
                continue

            if transaction["transaction_type"] not in [
                "opening_balance",
                "adjustment",
            ]:
                continue

            reversible_entries.append(entry)

        reversible_entries = sorted(
            reversible_entries,
            key=lambda entry: pd.to_datetime(
                entry["created_at"],
                utc=True,
            ),
            reverse=True,
        )

        if not reversible_entries:
            st.info("目前沒有可以撤銷的紀錄。")

        else:
            reversible_entry_ids = [
                entry["id"]
                for entry in reversible_entries
            ]

            def format_reversible_entry(entry_id):
                selected_entry = next(
                    entry
                    for entry in reversible_entries
                    if entry["id"] == entry_id
                )

                selected_transaction = transaction_map[
                    selected_entry["transaction_id"]
                ]

                selected_account = account_map[
                    selected_entry["account_id"]
                ]

                selected_asset = asset_map[
                    selected_entry["asset_id"]
                ]

                transaction_date = pd.to_datetime(
                    selected_transaction["transaction_date"],
                    utc=True,
                ).strftime("%Y-%m-%d")

                quantity_delta = float(
                    selected_entry["quantity_delta"]
                )

                formatted_delta = (
                    f"+{quantity_delta:,.2f}"
                    if quantity_delta > 0
                    else f"{quantity_delta:,.2f}"
                )

                return (
                    f"{transaction_date} | "
                    f'{selected_account["name"]} | '
                    f'{selected_asset["symbol"]} | '
                    f"{formatted_delta}"
                )

            with st.form("reverse_latest_entry_form"):
                selected_reverse_entry_id = st.selectbox(
                    "選擇要撤銷的最新紀錄",
                    options=reversible_entry_ids,
                    format_func=format_reversible_entry,
                )

                confirm_reverse = st.checkbox(
                    "我確認要建立一筆相反金額的撤銷紀錄"
                )

                reverse_submitted = st.form_submit_button(
                    "撤銷所選紀錄",
                    width='stretch',
                )

            if reverse_submitted:
                if not confirm_reverse:
                    st.warning("請先勾選確認。")

                else:
                    selected_entry = next(
                        entry
                        for entry in reversible_entries
                        if (
                            entry["id"]
                            == selected_reverse_entry_id
                        )
                    )

                    original_transaction = transaction_map[
                        selected_entry["transaction_id"]
                    ]

                    selected_account = account_map[
                        selected_entry["account_id"]
                    ]

                    selected_asset = asset_map[
                        selected_entry["asset_id"]
                    ]

                    original_delta = float(
                        selected_entry["quantity_delta"]
                    )

                    reverse_delta = -original_delta
                    reversal_transaction_id = None

                    try:
                        reversal_response = (
                            supabase.table("transactions")
                            .insert(
                                {
                                    "transaction_date": (
                                        pd.Timestamp.now(
                                            tz="America/Los_Angeles"
                                        ).isoformat()
                                    ),
                                    "transaction_type": (
                                        "adjustment"
                                    ),
                                    "description": (
                                        "撤銷："
                                        f'{original_transaction["description"]}'
                                    ),
                                    "external_reference": (
                                        "reversal:"
                                        f'{original_transaction["id"]}'
                                    ),
                                }
                            )
                            .execute()
                        )

                        reversal_data = (
                            reversal_response.data or []
                        )

                        if not reversal_data:
                            raise RuntimeError(
                                "撤銷交易建立後未取得交易 ID。"
                            )

                        reversal_transaction_id = (
                            reversal_data[0]["id"]
                        )

                        (
                            supabase.table(
                                "transaction_entries"
                            )
                            .insert(
                                {
                                    "transaction_id": (
                                        reversal_transaction_id
                                    ),
                                    "account_id": (
                                        selected_entry["account_id"]
                                    ),
                                    "asset_id": (
                                        selected_entry["asset_id"]
                                    ),
                                    "quantity_delta": (
                                        reverse_delta
                                    ),
                                    "unit_price": None,
                                    "memo": (
                                        "撤銷交易："
                                        f'{original_transaction["id"]}'
                                    ),
                                }
                            )
                            .execute()
                        )

                        st.session_state[
                            "transaction_success_message"
                        ] = (
                            "紀錄撤銷成功："
                            f'{selected_account["name"]} | '
                            f'{selected_asset["symbol"]} | '
                            f"{reverse_delta:+,.2f}"
                        )

                        st.rerun()

                    except Exception as error:
                        if reversal_transaction_id is not None:
                            try:
                                (
                                    supabase.table("transactions")
                                    .delete()
                                    .eq(
                                        "id",
                                        reversal_transaction_id,
                                    )
                                    .execute()
                                )
                            except Exception:
                                pass

                        st.error(f"撤銷紀錄失敗：{error}")
