import pandas as pd
from features import prices
import streamlit as st

from config import ASSET_TYPE_LABELS
from services.portfolio_cost import (
    calculate_portfolio_costs,
    get_excluded_transaction_ids,
)

def show_holding_manager(supabase):
    st.subheader("非現金資產持倉")
    st.caption(
        "建立股票、ETF、基金與加密貨幣的期初持倉，"
        "之後可用實際持有數量定期更新。"
    )

    success_message = st.session_state.pop(
        "holding_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    try:
        accounts_response = (
            supabase.table("accounts")
            .select(
                "id, name, institution, is_active"
            )
            .order("created_at")
            .execute()
        )

        assets_response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, "
                "currency, is_active"
            )
            .order("created_at")
            .execute()
        )

        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "id, transaction_id, account_id, asset_id, "
                "quantity_delta, unit_price, created_at"
            )
            .execute()
        )

        transactions_response = (
            supabase.table("transactions")
            .select(
                "id, transaction_date, transaction_type, "
                "external_reference, fee_amount, tax_amount, "
                "dividend_type, gross_amount, trade_currency, "
                "related_account_id, related_asset_id, "
                "created_at"
            )
            .execute()
        )

        prices_response = (
            supabase.table("asset_prices")
            .select(
                "asset_id, price, price_date, "
                "currency, source, created_at, updated_at"
            )
            .order("price_date", desc=True)
            .order("updated_at", desc=True)
            .execute()
        )

        fx_response = (
            supabase.table("fx_rates")
            .select(
                "from_currency, to_currency, rate, "
                "rate_date, source, created_at"
            )
            .eq("to_currency", "TWD")
            .order("rate_date", desc=True)
            .order("created_at", desc=True)
            .execute()
        )

        accounts = accounts_response.data or []
        assets = assets_response.data or []
        entries = entries_response.data or []
        transactions = transactions_response.data or []
        prices = prices_response.data or []
        fx_rates = fx_response.data or []

    except Exception as error:
        st.error(f"讀取持倉資料失敗：{error}")
        return

    active_accounts = [
        account
        for account in accounts
        if account["is_active"]
    ]

    investment_asset_types = {
        "stock",
        "etf",
        "fund",
        "crypto",
    }

    active_investment_assets = [
        asset
        for asset in assets
        if (
            asset["is_active"]
            and asset["asset_type"]
            in investment_asset_types
        )
    ]

    account_map = {
        account["id"]: account
        for account in accounts
    }

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    transaction_map = {
        transaction["id"]: transaction
        for transaction in transactions
    }

    portfolio_costs = calculate_portfolio_costs(
        transactions,
        entries,
        asset_map,
    )

    latest_prices = {}

    for price_record in prices:
        asset_id = price_record["asset_id"]

        if asset_id not in latest_prices:
            latest_prices[asset_id] = price_record

    latest_fx_rates = {}

    for fx_record in fx_rates:
        currency = fx_record["from_currency"]

        if currency not in latest_fx_rates:
            latest_fx_rates[currency] = fx_record

    excluded_transaction_ids = (
        get_excluded_transaction_ids(
        transactions
        )
    )

    net_cash_dividends = {}

    for transaction in transactions:
        if (
            transaction["id"]
            in excluded_transaction_ids
        ):
            continue

        if (
            transaction["transaction_type"]
            != "dividend"
            or transaction["dividend_type"]
            != "cash"
        ):
            continue

        related_account_id = transaction[
            "related_account_id"
        ]

        related_asset_id = transaction[
            "related_asset_id"
        ]

        if (
            related_account_id is None
            or related_asset_id is None
        ):
            continue

        gross_amount = float(
            transaction["gross_amount"] or 0
        )

        tax_amount = float(
            transaction["tax_amount"] or 0
        )

        fee_amount = float(
            transaction["fee_amount"] or 0
        )

        net_amount = (
            gross_amount
            - tax_amount
            - fee_amount
        )

        dividend_key = (
            related_account_id,
            related_asset_id,
        )

        net_cash_dividends[dividend_key] = (
            net_cash_dividends.get(
                dividend_key,
                0.0,
            )
            + net_amount
        )

    holdings = {}

    for entry in entries:
        asset = asset_map.get(entry["asset_id"])

        if (
            asset is None
            or asset["asset_type"]
            not in investment_asset_types
        ):
            continue

        holding_key = (
            entry["account_id"],
            entry["asset_id"],
        )

        holdings[holding_key] = (
            holdings.get(holding_key, 0.0)
            + float(entry["quantity_delta"])
        )

    def get_current_quantity(account_id, asset_id):
        return holdings.get(
            (account_id, asset_id),
            0.0,
        )

    def format_account(account_id):
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

    def format_asset(asset_id):
        selected = next(
            asset
            for asset in active_investment_assets
            if asset["id"] == asset_id
        )

        asset_type_label = ASSET_TYPE_LABELS.get(
            selected["asset_type"],
            selected["asset_type"],
        )

        return (
            f'{selected["symbol"]} | '
            f'{selected["name"]} | '
            f'{asset_type_label} | '
            f'{selected["currency"]}'
        )

    if not active_accounts:
        st.warning("請先建立至少一個使用中的帳戶。")

    if not active_investment_assets:
        st.warning(
            "請先在「資產」分頁建立至少一個"
            "使用中的股票、ETF、基金或加密貨幣。"
        )

    if active_accounts and active_investment_assets:
        account_ids = [
            account["id"]
            for account in active_accounts
        ]

        asset_ids = [
            asset["id"]
            for asset in active_investment_assets
        ]

        with st.expander(
            "建立期初持倉",
            expanded=False,
        ):
            selected_account_id = st.selectbox(
                "持有帳戶",
                options=account_ids,
                format_func=format_account,
                key="opening_holding_account",
            )

            selected_asset_id = st.selectbox(
                "非現金資產",
                options=asset_ids,
                format_func=format_asset,
                key="opening_holding_asset",
            )

            selected_opening_asset = asset_map[
                selected_asset_id
            ]

            st.caption(
                "這筆期初持倉將使用資產設定的幣別："
                f' {selected_opening_asset["currency"]}'
            )

            with st.form(
                "add_opening_holding_form",
                clear_on_submit=True,
            ):

                opening_quantity = st.number_input(
                    "期初持有數量",
                    min_value=0.0,
                    value=0.0,
                    step=0.0001,
                    format="%.8f",
                )

                opening_average_cost = st.number_input(
                    (
                        "期初每單位平均成本"
                        f'（{selected_opening_asset["currency"]}）'
                    ),
                    min_value=0.0,
                    value=0.0,
                    step=0.01,
                    format="%.6f",
                    help=(
                        "請填寫開始使用本系統時，"
                        "這項持倉每單位的歷史平均成本。"
                        "如果目前不知道，可以保留為 0，之後再補登。"
                    ),
                )

                if opening_average_cost == 0:
                    st.caption(
                        "保留為 0 時，系統會將成本記錄為「尚未提供」。"
                    )
                else:
                    opening_total_cost = (
                        float(opening_quantity)
                        * float(opening_average_cost)
                    )

                    st.caption(
                        "期初持倉總成本：約 "
                        f'{opening_total_cost:,.2f} '
                        f'{selected_opening_asset["currency"]}'
                    )
            

                holding_date = st.date_input(
                    "持倉日期",
                    value="today",
                    key="opening_holding_date",
                )

                holding_memo = st.text_input(
                    "備註（選填）",
                    placeholder=(
                        "例如：開始使用系統時的實際持倉"
                    ),
                )

                opening_submitted = (
                    st.form_submit_button(
                        "儲存期初持倉",
                        width='stretch',
                    )
                )

            if opening_submitted:
                current_quantity = get_current_quantity(
                    selected_account_id,
                    selected_asset_id,
                )

                if opening_quantity <= 0:
                    st.warning(
                        "期初持有數量必須大於 0。"
                    )

                elif abs(current_quantity) > 0.000000000001:
                    st.warning(
                        "這個帳戶與資產已經有持倉紀錄。"
                        "請使用下方的「更新持倉數量」。"
                    )

                else:
                    selected_account = next(
                        account
                        for account in active_accounts
                        if (
                            account["id"]
                            == selected_account_id
                        )
                    )

                    selected_asset = next(
                        asset
                        for asset in active_investment_assets
                        if (
                            asset["id"]
                            == selected_asset_id
                        )
                    )

                    transaction_id = None

                    try:
                        transaction_response = (
                            supabase.table("transactions")
                            .insert(
                                {
                                    "transaction_date": (
                                        f"{holding_date.isoformat()}"
                                        "T12:00:00+00:00"
                                    ),
                                    "transaction_type": (
                                        "opening_balance"
                                    ),
                                    "description": (
                                        f'{selected_account["name"]} '
                                        f'{selected_asset["symbol"]} '
                                        "期初持倉"
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
                                "紀錄建立後未取得交易 ID。"
                            )

                        transaction_id = (
                            transaction_data[0]["id"]
                        )

                        (
                            supabase
                            .table("transaction_entries")
                            .insert(
                                {
                                    "transaction_id": (
                                        transaction_id
                                    ),
                                    "account_id": (
                                        selected_account_id
                                    ),
                                    "asset_id": (
                                        selected_asset_id
                                    ),
                                    "quantity_delta": float(
                                        opening_quantity
                                    ),
                                    "unit_price": (
                                        float(opening_average_cost)
                                        if opening_average_cost > 0
                                        else None
                                    ),
                                    "memo": (
                                        holding_memo.strip()
                                        if holding_memo.strip()
                                        else None
                                    ),
                                }
                            )
                            .execute()
                        )

                        st.session_state[
                            "holding_success_message"
                        ] = "期初持倉建立成功。"

                        st.rerun()

                    except Exception as error:
                        if transaction_id is not None:
                            try:
                                (
                                    supabase
                                    .table("transactions")
                                    .delete()
                                    .eq(
                                        "id",
                                        transaction_id,
                                    )
                                    .execute()
                                )
                            except Exception:
                                pass

                        st.error(
                            f"建立期初持倉失敗：{error}"
                        )

        st.divider()

        with st.expander("更新持倉數量"):
            update_account_id = st.selectbox(
                "持有帳戶",
                options=account_ids,
                format_func=format_account,
                key="holding_update_account",
            )

            update_asset_id = st.selectbox(
                "非現金資產",
                options=asset_ids,
                format_func=format_asset,
                key="holding_update_asset",
            )

            selected_update_account = next(
                account
                for account in active_accounts
                if account["id"] == update_account_id
            )

            selected_update_asset = next(
                asset
                for asset in active_investment_assets
                if asset["id"] == update_asset_id
            )

            current_quantity = get_current_quantity(
                update_account_id,
                update_asset_id,
            )

            st.metric(
                "系統目前持有數量",
                f"{current_quantity:,.8f}",
            )

            with st.form(
                (
                    "update_holding_form_"
                    f"{update_account_id}_"
                    f"{update_asset_id}"
                )
            ):
                new_quantity = st.number_input(
                    "最新實際持有數量",
                    min_value=0.0,
                    value=max(
                        float(current_quantity),
                        0.0,
                    ),
                    step=0.0001,
                    format="%.8f",
                )

                update_date = st.date_input(
                    "持倉日期",
                    value="today",
                    key="holding_update_date",
                )

                update_memo = st.text_input(
                    "備註（選填）",
                    placeholder=(
                        "例如：依券商月底庫存更新"
                    ),
                )

                update_submitted = (
                    st.form_submit_button(
                        "更新持倉",
                        width='stretch',
                    )
                )

            if update_submitted:
                quantity_delta = round(
                    float(new_quantity)
                    - current_quantity,
                    12,
                )

                if abs(quantity_delta) < 0.000000000001:
                    st.info(
                        "最新數量與系統目前數量相同，"
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
                                        f"{update_date.isoformat()}"
                                        "T12:00:00+00:00"
                                    ),
                                    "transaction_type": (
                                        "adjustment"
                                    ),
                                    "description": (
                                        f'{selected_update_account["name"]} '
                                        f'{selected_update_asset["symbol"]} '
                                        "持倉更新至 "
                                        f"{float(new_quantity):.8f}"
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
                                "紀錄建立後未取得交易 ID。"
                            )

                        transaction_id = (
                            transaction_data[0]["id"]
                        )

                        default_memo = (
                            "持倉數量更新："
                            f"{current_quantity:.8f} → "
                            f"{float(new_quantity):.8f}"
                        )

                        final_memo = default_memo

                        if update_memo.strip():
                            final_memo = (
                                f"{default_memo} | "
                                f"{update_memo.strip()}"
                            )

                        (
                            supabase
                            .table("transaction_entries")
                            .insert(
                                {
                                    "transaction_id": (
                                        transaction_id
                                    ),
                                    "account_id": (
                                        update_account_id
                                    ),
                                    "asset_id": (
                                        update_asset_id
                                    ),
                                    "quantity_delta": (
                                        quantity_delta
                                    ),
                                    "unit_price": None,
                                    "memo": final_memo,
                                }
                            )
                            .execute()
                        )

                        st.session_state[
                            "holding_success_message"
                        ] = (
                            "持倉數量更新成功："
                            f'{selected_update_asset["symbol"]} '
                            f"{float(new_quantity):,.8f}"
                        )

                        st.rerun()

                    except Exception as error:
                        if transaction_id is not None:
                            try:
                                (
                                    supabase
                                    .table("transactions")
                                    .delete()
                                    .eq(
                                        "id",
                                        transaction_id,
                                    )
                                    .execute()
                                )
                            except Exception:
                                pass

                        st.error(
                            f"更新持倉失敗：{error}"
                        )

    st.divider()

    opening_cost_entries = []

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

        if (
            transaction["transaction_type"]
            != "opening_balance"
        ):
            continue

        if (
            asset["asset_type"]
            not in investment_asset_types
        ):
            continue

        if float(entry["quantity_delta"]) <= 0:
            continue

        current_holding_quantity = (
            get_current_quantity(
                entry["account_id"],
                entry["asset_id"],
            )
        )

        if (
            abs(current_holding_quantity)
            < 0.000000000001
        ):
            continue

        opening_cost_entries.append(
            {
                "entry": entry,
                "transaction": transaction,
                "account": account,
                "asset": asset,
            }
        )

    with st.expander(
        "補登或修改期初平均成本",
        expanded=False,
    ):
        st.caption(
            "這裡只會修改期初平均成本，"
            "不會改變目前持有數量，"
            "也不會產生現金扣款。"
        )

        if not opening_cost_entries:
            st.info(
                "目前沒有可以補登成本的期初持倉。"
            )

        else:
            opening_entry_ids = [
                record["entry"]["id"]
                for record in opening_cost_entries
            ]

            def format_opening_cost_entry(
                entry_id,
            ):
                record = next(
                    record
                    for record in opening_cost_entries
                    if (
                        record["entry"]["id"]
                        == entry_id
                    )
                )

                entry = record["entry"]
                account = record["account"]
                asset = record["asset"]

                existing_cost = entry["unit_price"]

                cost_text = (
                    f"{float(existing_cost):,.6f} "
                    f'{asset["currency"]}'
                    if existing_cost is not None
                    else "尚未提供成本"
                )

                return (
                    f'{account["name"]} | '
                    f'{asset["symbol"]} '
                    f'{asset["name"]} | '
                    f"{cost_text}"
                )

            selected_cost_entry_id = st.selectbox(
                "選擇期初持倉",
                options=opening_entry_ids,
                format_func=format_opening_cost_entry,
                key="opening_cost_entry",
            )

            selected_cost_record = next(
                record
                for record in opening_cost_entries
                if (
                    record["entry"]["id"]
                    == selected_cost_entry_id
                )
            )

            selected_cost_entry = (
                selected_cost_record["entry"]
            )

            selected_cost_asset = (
                selected_cost_record["asset"]
            )

            existing_average_cost = (
                float(
                    selected_cost_entry["unit_price"]
                )
                if (
                    selected_cost_entry["unit_price"]
                    is not None
                )
                else 0.0
            )

            opening_quantity = float(
                selected_cost_entry[
                    "quantity_delta"
                ]
            )

            with st.form(
                (
                    "update_opening_cost_form_"
                    f"{selected_cost_entry_id}"
                )
            ):
                new_average_cost = st.number_input(
                    (
                        "期初每單位平均成本"
                        f'（{selected_cost_asset["currency"]}）'
                    ),
                    min_value=0.0,
                    value=existing_average_cost,
                    step=0.01,
                    format="%.6f",
                )

                clear_average_cost = st.checkbox(
                    "清除已儲存的期初成本",
                    value=False,
                )

                if (
                    not clear_average_cost
                    and new_average_cost > 0
                ):
                    st.caption(
                        "期初持倉總成本：約 "
                        f"{opening_quantity * new_average_cost:,.2f} "
                        f'{selected_cost_asset["currency"]}'
                    )

                cost_submitted = (
                    st.form_submit_button(
                        "儲存期初平均成本",
                        width="stretch",
                    )
                )

            if cost_submitted:
                if (
                    not clear_average_cost
                    and new_average_cost <= 0
                ):
                    st.warning(
                        "平均成本必須大於 0。"
                        "如果要刪除成本，"
                        "請勾選「清除已儲存的期初成本」。"
                    )

                else:
                    saved_average_cost = (
                        None
                        if clear_average_cost
                        else float(new_average_cost)
                    )

                    try:
                        (
                            supabase
                            .table(
                                "transaction_entries"
                            )
                            .update(
                                {
                                    "unit_price": (
                                        saved_average_cost
                                    )
                                }
                            )
                            .eq(
                                "id",
                                selected_cost_entry_id,
                            )
                            .execute()
                        )

                        st.session_state[
                            "holding_success_message"
                        ] = (
                            "期初平均成本已清除。"
                            if clear_average_cost
                            else "期初平均成本儲存成功。"
                        )

                        st.rerun()

                    except Exception as error:
                        st.error(
                            "儲存期初平均成本失敗："
                            f"{error}"
                        )
    
    st.divider()
    st.subheader("目前非現金資產持倉")

    holding_rows = []

    for (
        account_id,
        asset_id,
    ), quantity in holdings.items():
        if abs(quantity) < 0.000000000001:
            continue

        account = account_map.get(account_id)
        asset = asset_map.get(asset_id)

        if account is None or asset is None:
            continue

        cost_state = portfolio_costs.get(
            (account_id, asset_id),
            {},
        )

        cost_complete = cost_state.get(
            "cost_complete",
            False,
        )

        average_cost = (
            cost_state.get("average_cost")
            if cost_complete
            else None
        )

        total_cost = (
            cost_state.get("total_cost")
            if cost_complete
            else None
        )

        realized_pnl = (
            cost_state.get("realized_pnl")
            if cost_complete
            else None
        )

        price_record = latest_prices.get(asset_id)

        price_currency_matches = (
            price_record is not None
            and price_record["currency"]
            == asset["currency"]
        )

        latest_price = (
            float(price_record["price"])
            if price_currency_matches
            else None
        )

        price_date = (
            price_record["price_date"]
            if price_currency_matches
            else ""
        )

        market_value = (
            float(quantity) * latest_price
            if latest_price is not None
            else None
        )

        unrealized_pnl = (
            market_value - total_cost
            if (
                market_value is not None
                and total_cost is not None
            )
            else None
        )

        unrealized_return = (
            unrealized_pnl / total_cost
            if (
                unrealized_pnl is not None
                and total_cost is not None
                and total_cost > 0
            )
            else None
        )

        price_total_pnl = (
            realized_pnl + unrealized_pnl
            if (
                realized_pnl is not None
                and unrealized_pnl is not None
            )
            else None
        )

        net_cash_dividend = (
            net_cash_dividends.get(
                (account_id, asset_id),
                0.0,
            )
        )

        total_pnl_with_dividends = (
            price_total_pnl
            + net_cash_dividend
            if price_total_pnl is not None
            else None
        )

        price_status = (
            "缺少價格"
            if price_record is None
            else (
                "價格幣別不符"
                if not price_currency_matches
                else "正常"
            )
        )

        holding_rows.append(
            {
                "帳戶": account["name"],
                "資產類型": ASSET_TYPE_LABELS.get(
                    asset["asset_type"],
                    asset["asset_type"],
                ),
                "資產代號": asset["symbol"],
                "資產名稱": asset["name"],
                "幣別": asset["currency"],
                "持有數量": quantity,
                "平均成本": average_cost,
                "剩餘總成本": total_cost,
                "已實現損益": realized_pnl,
                "最新價格": latest_price,
                "目前市值": market_value,
                "未實現損益": unrealized_pnl,
                "未實現報酬率": unrealized_return,
                "價格總損益": price_total_pnl,
                "淨現金股利": net_cash_dividend,
                "含股利總損益": total_pnl_with_dividends,
                "價格日期": price_date,
                "價格狀態": price_status,
                "成本狀態": (
                    "完整"
                    if cost_complete
                    else cost_state.get(
                        "cost_note",
                        "成本資料不完整",
                    )
                ),
                "狀態": (
                    "使用中"
                    if (
                        account["is_active"]
                        and asset["is_active"]
                    )
                    else "已封存"
                ),
            }
        )

    if not holding_rows:
        st.info("目前還沒有非現金資產持倉。")
        return

    holding_dataframe = pd.DataFrame(
        holding_rows
    ).sort_values(
        by=[
            "帳戶",
            "資產類型",
            "資產代號",
        ]
    )

    st.dataframe(
        holding_dataframe,
        width='stretch',
        hide_index=True,
        column_config={
            "持有數量": st.column_config.NumberColumn(
                "持有數量",
                format="%.8f",
            ),
            "平均成本": st.column_config.NumberColumn(
                "平均成本",
                format="%.6f",
            ),
            "剩餘總成本": st.column_config.NumberColumn(
                "剩餘總成本",
                format="%.2f",
            ),
            "已實現損益": st.column_config.NumberColumn(
                "已實現損益",
                format="%.2f",
            ),
            "最新價格": st.column_config.NumberColumn(
                "最新價格",
                format="%.6f",
            ),
            "目前市值": st.column_config.NumberColumn(
                "目前市值",
                format="%.2f",
            ),
            "未實現損益": st.column_config.NumberColumn(
                "未實現損益",
                format="%.2f",
            ),
            "未實現報酬率": st.column_config.NumberColumn(
                "未實現報酬率",
                format="percent",
            ),
            "價格總損益": st.column_config.NumberColumn(
                "價格總損益",
                format="%.2f",
            ),
            "淨現金股利": st.column_config.NumberColumn(
                "淨現金股利",
                format="%.2f",
            ),
            "含股利總損益": st.column_config.NumberColumn(
                "含股利總損益",
                format="%.2f",
            ),
        },
    )

    st.divider()
    st.subheader("投資績效幣別彙總")

    currency_groups = {}

    for holding_row in holding_rows:
        currency = holding_row["幣別"]

        currency_groups.setdefault(
            currency,
            [],
        ).append(holding_row)

    def sum_complete_field(
        rows,
        field_name,
    ):
        values = [
            row[field_name]
            for row in rows
        ]

        if any(
            value is None
            for value in values
        ):
            return None

        return sum(
            float(value)
            for value in values
        )

    currency_summary_rows = []

    for currency in sorted(currency_groups):
        currency_rows = currency_groups[
            currency
        ]

        total_cost = sum_complete_field(
            currency_rows,
            "剩餘總成本",
        )

        total_market_value = sum_complete_field(
            currency_rows,
            "目前市值",
        )

        total_realized_pnl = sum_complete_field(
            currency_rows,
            "已實現損益",
        )

        total_unrealized_pnl = (
            total_market_value - total_cost
            if (
                total_market_value is not None
                and total_cost is not None
            )
            else None
        )

        total_net_dividend = sum(
            float(
                row["淨現金股利"]
                or 0
            )
            for row in currency_rows
        )

        total_price_pnl = (
            total_realized_pnl
            + total_unrealized_pnl
            if (
                total_realized_pnl is not None
                and total_unrealized_pnl is not None
            )
            else None
        )

        total_pnl_with_dividends = (
            total_price_pnl
            + total_net_dividend
            if total_price_pnl is not None
            else None
        )

        unrealized_return = (
            total_unrealized_pnl
            / total_cost
            if (
                total_unrealized_pnl is not None
                and total_cost is not None
                and total_cost > 0
            )
            else None
        )

        if currency == "TWD":
            fx_rate = 1.0
            fx_date = ""
            fx_status = "基準幣別"
        
        else:
            fx_record = latest_fx_rates.get(
                currency
            )
        
            if fx_record is None:
                fx_rate = None
                fx_date = ""
                fx_status = "缺少匯率"
        
            else:
                fx_rate = float(
                    fx_record["rate"]
                )
        
                fx_date = fx_record["rate_date"]
                fx_status = "正常"
        
        total_cost_twd = (
            total_cost * fx_rate
            if (
                total_cost is not None
                and fx_rate is not None
            )
            else None
        )
        
        total_market_value_twd = (
            total_market_value * fx_rate
            if (
                total_market_value is not None
                and fx_rate is not None
            )
            else None
        )
        
        total_price_pnl_twd = (
            total_price_pnl * fx_rate
            if (
                total_price_pnl is not None
                and fx_rate is not None
            )
            else None
        )
        
        total_net_dividend_twd = (
            total_net_dividend * fx_rate
            if fx_rate is not None
            else None
        )
        
        total_pnl_with_dividends_twd = (
            total_pnl_with_dividends
            * fx_rate
            if (
                total_pnl_with_dividends
                is not None
                and fx_rate is not None
            )
            else None
        )

        currency_summary_rows.append(
            {
                "幣別": currency,
                "持倉筆數": len(currency_rows),
                "剩餘總成本": total_cost,
                "目前總市值": (
                    total_market_value
                ),
                "已實現損益": (
                    total_realized_pnl
                ),
                "未實現損益": (
                    total_unrealized_pnl
                ),
                "未實現報酬率": (
                    unrealized_return
                ),
                "淨現金股利": (
                    total_net_dividend
                ),
                "價格總損益": (
                    total_price_pnl
                ),
                "含股利總損益": (
                    total_pnl_with_dividends
                ),
                "換算匯率": fx_rate,
                "匯率日期": fx_date,
                "TWD 剩餘成本": total_cost_twd,
                "TWD 目前市值": (
                    total_market_value_twd
                ),
                "TWD 價格總損益": (
                    total_price_pnl_twd
                ),
                "TWD 淨現金股利": (
                    total_net_dividend_twd
                ),
                "TWD 含股利總損益": (
                    total_pnl_with_dividends_twd
                ),
                "匯率狀態": fx_status,
                "資料狀態": (
                    "完整"
                    if (
                        total_pnl_with_dividends
                        is not None
                    )
                    else "部分資料缺失"
                ),
            }
        )

    currency_summary_dataframe = pd.DataFrame(
        currency_summary_rows
    )

    twd_conversion_complete = all(
        (
            row["TWD 剩餘成本"] is not None
            and row["TWD 目前市值"] is not None
            and row["TWD 價格總損益"] is not None
            and row["TWD 含股利總損益"]
            is not None
        )
        for row in currency_summary_rows
    )

    if twd_conversion_complete:
        portfolio_cost_twd = sum(
            row["TWD 剩餘成本"]
            for row in currency_summary_rows
        )

        portfolio_market_value_twd = sum(
            row["TWD 目前市值"]
            for row in currency_summary_rows
        )

        portfolio_price_pnl_twd = sum(
            row["TWD 價格總損益"]
            for row in currency_summary_rows
        )

        portfolio_total_pnl_twd = sum(
            row["TWD 含股利總損益"]
            for row in currency_summary_rows
        )

        summary_col1, summary_col2 = st.columns(2)
        summary_col3, summary_col4 = st.columns(2)

        with summary_col1:
            st.metric(
                "投資市值（TWD）",
                f"{portfolio_market_value_twd:,.2f}",
            )

        with summary_col2:
            st.metric(
                "剩餘成本參考值（TWD）",
                f"{portfolio_cost_twd:,.2f}",
            )

        with summary_col3:
            st.metric(
                "價格總損益參考值（TWD）",
                f"{portfolio_price_pnl_twd:,.2f}",
            )

        with summary_col4:
            st.metric(
                "含股利總損益參考值（TWD）",
                f"{portfolio_total_pnl_twd:,.2f}",
            )

    else:
        st.warning(
            "部分持倉缺少價格、成本或匯率，"
            "暫時無法計算完整的 TWD 投資績效。"
        )

    st.caption(
        "TWD 成本與損益目前是依最新匯率換算的參考值，"
        "尚未拆分交易期間的匯兌損益。"
    )

    st.dataframe(
        currency_summary_dataframe,
        width="stretch",
        hide_index=True,
        column_config={
            "持倉筆數": (
                st.column_config.NumberColumn(
                    "持倉筆數",
                    format="%d",
                )
            ),
            "剩餘總成本": (
                st.column_config.NumberColumn(
                    "剩餘總成本",
                    format="%.2f",
                )
            ),
            "目前總市值": (
                st.column_config.NumberColumn(
                    "目前總市值",
                    format="%.2f",
                )
            ),
            "已實現損益": (
                st.column_config.NumberColumn(
                    "已實現損益",
                    format="%.2f",
                )
            ),
            "未實現損益": (
                st.column_config.NumberColumn(
                    "未實現損益",
                    format="%.2f",
                )
            ),
            "未實現報酬率": (
                st.column_config.NumberColumn(
                    "未實現報酬率",
                    format="percent",
                )
            ),
            "淨現金股利": (
                st.column_config.NumberColumn(
                    "淨現金股利",
                    format="%.2f",
                )
            ),
            "價格總損益": (
                st.column_config.NumberColumn(
                    "價格總損益",
                    format="%.2f",
                )
            ),
            "含股利總損益": (
                st.column_config.NumberColumn(
                    "含股利總損益",
                    format="%.2f",
                )
            ),
            "換算匯率": st.column_config.NumberColumn(
                "換算匯率",
                format="%.6f",
            ),
            "TWD 剩餘成本": (
                st.column_config.NumberColumn(
                    "TWD 剩餘成本",
                    format="%.2f",
                )
            ),
            "TWD 目前市值": (
                st.column_config.NumberColumn(
                    "TWD 目前市值",
                    format="%.2f",
                )
            ),
            "TWD 價格總損益": (
                st.column_config.NumberColumn(
                    "TWD 價格總損益",
                    format="%.2f",
                )
            ),
            "TWD 淨現金股利": (
                st.column_config.NumberColumn(
                    "TWD 淨現金股利",
                    format="%.2f",
                )
            ),
            "TWD 含股利總損益": (
                st.column_config.NumberColumn(
                    "TWD 含股利總損益",
                    format="%.2f",
                )
            ),
        },
    )
