import pandas as pd
import streamlit as st


def show_trade_entry(supabase, active_accounts, assets):
    active_investment_assets = [
        asset
        for asset in assets
        if (
            asset["is_active"]
            and asset["asset_type"]
            in ["stock", "etf", "fund", "crypto"]
        )
    ]

    active_cash_assets = [
        asset
        for asset in assets
        if (
            asset["is_active"]
            and asset["asset_type"] == "cash"
        )
    ]

    if not active_investment_assets:
        return

    try:
        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "account_id, asset_id, quantity_delta"
            )
            .execute()
        )

        existing_entries = entries_response.data or []

        fee_settings_response = (
            supabase.table("broker_fee_settings")
            .select(
                "id, account_id, market, commission_rate, "
                "discount_rate, minimum_commission, "
                "sell_stock_tax_rate, sell_etf_tax_rate, "
                "currency, is_active"
            )
            .eq("is_active", True)
            .execute()
        )

        fee_settings = fee_settings_response.data or []

    except Exception as error:
        st.error(f"讀取持倉或券商費率失敗：{error}")
        return

    balances = {}

    for entry in existing_entries:
        balance_key = (
            entry["account_id"],
            entry["asset_id"],
        )

        balances[balance_key] = (
            balances.get(balance_key, 0.0)
            + float(entry["quantity_delta"])
        )

    st.subheader("買入／賣出")

    with st.expander(
        "新增股票、ETF、基金或加密貨幣交易",
        expanded=False,
    ):
        transaction_type = st.radio(
            "交易類型",
            options=["buy", "sell"],
            format_func=lambda value: (
                "買入" if value == "buy" else "賣出"
            ),
            horizontal=True,
            key="trade_transaction_type",
        )

        account_ids = [
            account["id"]
            for account in active_accounts
        ]

        def format_trade_account(account_id):
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

        selected_account_id = st.selectbox(
            "交易帳戶",
            options=account_ids,
            format_func=format_trade_account,
            key="trade_account_id",
        )

        investment_asset_ids = [
            asset["id"]
            for asset in active_investment_assets
        ]

        def format_trade_asset(asset_id):
            selected = next(
                asset
                for asset in active_investment_assets
                if asset["id"] == asset_id
            )

            return (
                f'{selected["symbol"]} | '
                f'{selected["name"]} | '
                f'{selected["currency"]}'
            )

        selected_asset_id = st.selectbox(
            "交易資產",
            options=investment_asset_ids,
            format_func=format_trade_asset,
            key="trade_asset_id",
        )

        selected_account = next(
            account
            for account in active_accounts
            if account["id"] == selected_account_id
        )

        selected_asset = next(
            asset
            for asset in active_investment_assets
            if asset["id"] == selected_asset_id
        )

        asset_market_text = (
            selected_asset["market"] or ""
        ).strip().upper()

        if asset_market_text in {
            "TW",
            "TWN",
            "TAIWAN",
            "TWSE",
            "TPEX",
        }:
            normalized_market = "TW"

        elif asset_market_text in {
            "US",
            "USA",
            "NASDAQ",
            "NYSE",
            "AMEX",
        }:
            normalized_market = "US"

        elif selected_asset["currency"] == "TWD":
            normalized_market = "TW"

        elif selected_asset["currency"] == "USD":
            normalized_market = "US"

        else:
            normalized_market = None

        matching_fee_setting = next(
            (
                setting
                for setting in fee_settings
                if (
                    setting["account_id"]
                    == selected_account_id
                    and setting["market"]
                    == normalized_market
                )
            ),
            None,
        )

        current_holding = balances.get(
            (
                selected_account_id,
                selected_asset_id,
            ),
            0.0,
        )

        st.caption(
            f'目前持倉：{current_holding:,.6f} '
            f'{selected_asset["symbol"]}'
        )

        widget_suffix = (
            f"{transaction_type}_"
            f"{selected_account_id}_"
            f"{selected_asset_id}"
        )

        quantity = st.number_input(
            "交易數量",
            min_value=0.0,
            value=0.0,
            step=1.0,
            format="%.6f",
            key=f"trade_quantity_{widget_suffix}",
        )

        unit_price = st.number_input(
            f'每單位成交價格（{selected_asset["currency"]}）',
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.6f",
            key=f"trade_price_{widget_suffix}",
        )

        gross_value = (
            float(quantity) * float(unit_price)
        )

        st.caption(
            f"成交總額："
            f'{selected_asset["currency"]} '
            f"{gross_value:,.2f}"
        )

        if matching_fee_setting is not None:
            commission_rate = float(
                matching_fee_setting["commission_rate"]
            )

            discount_rate = float(
                matching_fee_setting["discount_rate"]
            )

            minimum_commission = float(
                matching_fee_setting[
                    "minimum_commission"
                ]
            )

            if (
                gross_value > 0
                and commission_rate > 0
            ):
                calculated_fee = max(
                    (
                        gross_value
                        * commission_rate
                        * discount_rate
                    ),
                    minimum_commission,
                )
            else:
                calculated_fee = 0.0

            calculated_fee = round(
                calculated_fee,
                2,
            )

            st.info(
                "已套用券商費率設定："
                f'{matching_fee_setting["market"]} 市場｜'
                f"牌告費率 "
                f"{commission_rate * 100:.4f}%｜"
                f"折數 {discount_rate * 10:.2f}｜"
                f"最低手續費 "
                f'{matching_fee_setting["currency"]} '
                f"{minimum_commission:,.2f}"
            )

            fee_mode = st.radio(
                "手續費輸入方式",
                options=[
                    "使用券商設定自動計算",
                    "手動輸入實際金額",
                ],
                horizontal=True,
                key=f"trade_fee_mode_{widget_suffix}",
            )

            if fee_mode == "使用券商設定自動計算":
                fee_amount = calculated_fee

                st.caption(
                    "自動計算手續費："
                    f'{selected_asset["currency"]} '
                    f"{fee_amount:,.2f}"
                )

            else:
                fee_amount = st.number_input(
                    (
                        "實際手續費／監管費"
                        f'（{selected_asset["currency"]}）'
                    ),
                    min_value=0.0,
                    value=float(calculated_fee),
                    step=0.01,
                    format="%.6f",
                    key=(
                        f"trade_manual_fee_"
                        f"{widget_suffix}"
                    ),
                    help=(
                        "請以券商成交確認單上的"
                        "實際費用為準。"
                    ),
                )

        else:
            fee_amount = st.number_input(
                (
                    "手續費／監管費"
                    f'（{selected_asset["currency"]}）'
                ),
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.6f",
                key=f"trade_fee_{widget_suffix}",
                help=(
                    "目前没有符合交易账户与市场的"
                    "费率设定，请手动输入实际费用。"
                ),
            )

            if normalized_market is None:
                st.warning(
                    "无法判断此资产所属市场，"
                    "请检查资产资料中的「市场」。"
                )
            else:
                st.warning(
                    "尚未找到此交易账户的"
                    f"{normalized_market} 市场费率设定，"
                    "本次费用需手动输入。"
                )

        suggested_tax_rate = 0.0

        if (
            transaction_type == "sell"
            and matching_fee_setting is not None
        ):
            if selected_asset["asset_type"] == "stock":
                suggested_tax_rate = float(
                    matching_fee_setting[
                        "sell_stock_tax_rate"
                    ]
                )

            elif selected_asset["asset_type"] == "etf":
                suggested_tax_rate = float(
                    matching_fee_setting[
                        "sell_etf_tax_rate"
                    ]
                )

        suggested_tax = round(
            gross_value * suggested_tax_rate,
            2,
        )

        can_auto_calculate_tax = (
            transaction_type == "sell"
            and matching_fee_setting is not None
            and selected_asset["asset_type"]
            in ["stock", "etf"]
        )

        if can_auto_calculate_tax:
            tax_mode = st.radio(
                "卖出税费输入方式",
                options=[
                    "使用券商設定自動計算",
                    "手動輸入實際金額",
                ],
                horizontal=True,
                key=f"trade_tax_mode_{widget_suffix}",
            )

            if tax_mode == "使用券商設定自動計算":
                tax_amount = suggested_tax

                st.caption(
                    "自动计算卖出税费："
                    f"税率 "
                    f"{suggested_tax_rate * 100:.4f}%｜"
                    f'{selected_asset["currency"]} '
                    f"{tax_amount:,.2f}"
                )

            else:
                tax_amount = st.number_input(
                    (
                        "实际卖出税费"
                        f'（{selected_asset["currency"]}）'
                    ),
                    min_value=0.0,
                    value=float(suggested_tax),
                    step=0.01,
                    format="%.6f",
                    key=(
                        f"trade_manual_tax_"
                        f"{widget_suffix}"
                    ),
                )

        else:
            tax_amount = st.number_input(
                (
                    "其他税费"
                    f'（{selected_asset["currency"]}）'
                ),
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.6f",
                key=f"trade_tax_{widget_suffix}",
                help=(
                    "买入通常为 0；如果成交确认单"
                    "列有其他税费，可在此手动输入。"
                ),
            )

        matching_cash_assets = [
            asset
            for asset in active_cash_assets
            if (
                asset["currency"]
                == selected_asset["currency"]
            )
        ]

        if matching_cash_assets:
            cash_linked = st.checkbox(
                "連動現金",
                value=True,
                key=f"trade_cash_linked_{widget_suffix}",
                help=(
                    "買入會扣除現金；"
                    "賣出會增加現金。"
                ),
            )

        else:
            cash_linked = False

            st.warning(
                f'目前沒有使用中的 '
                f'{selected_asset["currency"]} 現金資產，'
                "因此本次交易無法連動現金。"
            )

        selected_cash_account_id = None
        selected_cash_asset_id = None
        current_cash_balance = 0.0

        if cash_linked:
            cash_account_ids = [
                account["id"]
                for account in active_accounts
            ]

            def format_trade_cash_account(account_id):
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

            selected_cash_account_id = st.selectbox(
                "現金扣款／入帳帳戶",
                options=cash_account_ids,
                format_func=format_trade_cash_account,
                key=f"trade_cash_account_{widget_suffix}",
                help=(
                    "買入時從此帳戶扣款；"
                    "賣出時將款項加入此帳戶。"
                ),
            )

            cash_asset_ids = [
                asset["id"]
                for asset in matching_cash_assets
            ]

            def format_trade_cash_asset(asset_id):
                selected = next(
                    asset
                    for asset in matching_cash_assets
                    if asset["id"] == asset_id
                )

                return (
                    f'{selected["symbol"]} | '
                    f'{selected["name"]}'
                )

            selected_cash_asset_id = st.selectbox(
                "連動的現金資產",
                options=cash_asset_ids,
                format_func=format_trade_cash_asset,
                key=f"trade_cash_asset_{widget_suffix}",
            )

            current_cash_balance = balances.get(
                (
                    selected_cash_account_id,
                    selected_cash_asset_id,
                ),
                0.0,
            )

            selected_cash_account = next(
                account
                for account in active_accounts
                if (
                    account["id"]
                    == selected_cash_account_id
                )
            )

            st.caption(
                f'{selected_cash_account["name"]} '
                "目前現金："
                f'{selected_asset["currency"]} '
                f"{current_cash_balance:,.2f}"
            )

        if transaction_type == "buy":
            cash_delta = -(
                gross_value
                + float(fee_amount)
                + float(tax_amount)
            )
        else:
            cash_delta = (
                gross_value
                - float(fee_amount)
                - float(tax_amount)
            )

        summary_col1, summary_col2 = st.columns(2)

        with summary_col1:
            st.metric(
                "交易後持倉變化",
                (
                    f"{float(quantity):+,.6f}"
                    if transaction_type == "buy"
                    else f"{-float(quantity):+,.6f}"
                ),
            )

        with summary_col2:
            if cash_linked:
                st.metric(
                    "現金變化",
                    (
                        f'{selected_asset["currency"]} '
                        f"{cash_delta:+,.2f}"
                    ),
                )
            else:
                st.metric("現金變化", "不連動")

        trade_date = st.date_input(
            "交易日期",
            value="today",
            key=f"trade_date_{widget_suffix}",
        )

        trade_memo = st.text_input(
            "備註（選填）",
            placeholder="例如：定期定額、首次買入",
            key=f"trade_memo_{widget_suffix}",
        )

        submitted = st.button(
            "儲存交易",
            width="stretch",
            key=f"save_trade_{widget_suffix}",
        )

        if submitted:
            validation_error = None

            if quantity <= 0:
                validation_error = (
                    "交易數量必須大於 0。"
                )

            elif unit_price <= 0:
                validation_error = (
                    "成交價格必須大於 0。"
                )

            elif (
                transaction_type == "sell"
                and float(quantity)
                > current_holding + 0.00000001
            ):
                validation_error = (
                    "賣出數量不能超過目前持倉。"
                )

            elif (
                cash_linked
                and transaction_type == "buy"
                and (
                    current_cash_balance
                    + cash_delta
                    < -0.00000001
                )
            ):
                validation_error = (
                    "現金餘額不足。"
                    "請確認金額、更新現金餘額，"
                    "或取消勾選「連動現金」。"
                )

            elif (
                cash_linked
                and abs(cash_delta) < 0.00000001
            ):
                validation_error = (
                    "現金變化不能為 0。"
                )

            if validation_error:
                st.warning(validation_error)
                return

            asset_delta = (
                float(quantity)
                if transaction_type == "buy"
                else -float(quantity)
            )

            transaction_label = (
                "買入"
                if transaction_type == "buy"
                else "賣出"
            )

            description = (
                f'{transaction_label} '
                f'{selected_asset["symbol"]} '
                f'{float(quantity):,.6f} 單位，'
                f'成交價 {selected_asset["currency"]} '
                f'{float(unit_price):,.6f}；'
                f'費用 {float(fee_amount):,.2f}；'
                f'稅費 {float(tax_amount):,.2f}'
            )

            transaction_id = None

            try:
                transaction_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{trade_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": (
                                transaction_type
                            ),
                            "description": description,
                            "fee_amount": float(fee_amount),
                            "tax_amount": float(tax_amount),
                            "trade_currency": (
                                selected_asset["currency"]
                            ),
                            "cash_linked": cash_linked,
                        }
                    )
                    .execute()
                )

                transaction_rows = (
                    transaction_response.data or []
                )

                if not transaction_rows:
                    raise RuntimeError(
                        "交易建立後未取得交易 ID。"
                    )

                transaction_id = (
                    transaction_rows[0]["id"]
                )

                entry_rows = [
                    {
                        "transaction_id": transaction_id,
                        "account_id": selected_account_id,
                        "asset_id": selected_asset_id,
                        "quantity_delta": asset_delta,
                        "unit_price": float(unit_price),
                        "memo": (
                            trade_memo.strip()
                            if trade_memo.strip()
                            else None
                        ),
                    }
                ]

                if cash_linked:
                    entry_rows.append(
                        {
                            "transaction_id": transaction_id,
                            "account_id": selected_cash_account_id,
                            "asset_id": (
                                selected_cash_asset_id
                            ),
                            "quantity_delta": cash_delta,
                            "unit_price": None,
                            "memo": (
                                f"{transaction_label}"
                                "連動現金"
                            ),
                        }
                    )

                (
                    supabase
                    .table("transaction_entries")
                    .insert(entry_rows)
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    f'{selected_asset["symbol"]} '
                    f"{transaction_label}紀錄新增成功。"
                )

                st.rerun()

            except Exception as error:
                if transaction_id is not None:
                    try:
                        (
                            supabase
                            .table("transactions")
                            .delete()
                            .eq("id", transaction_id)
                            .execute()
                        )
                    except Exception:
                        pass

                st.error(f"新增交易失敗：{error}")

def show_trade_edit_manager(
    supabase,
    active_accounts,
    assets,
):
    try:
        transactions_response = (
            supabase.table("transactions")
            .select(
                "id, transaction_date, transaction_type, "
                "description, external_reference, "
                "fee_amount, tax_amount, trade_currency, "
                "cash_linked, created_at"
            )
            .order("transaction_date", desc=True)
            .order("created_at", desc=True)
            .execute()
        )

        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "id, transaction_id, account_id, asset_id, "
                "quantity_delta, unit_price, memo"
            )
            .execute()
        )

        transactions = transactions_response.data or []
        entries = entries_response.data or []

    except Exception as error:
        st.error(f"讀取可修改交易失敗：{error}")
        return

    reversal_prefixes = (
        "trade_reversal:",
        "trade_edit_reversal:",
    )

    reversed_transaction_ids = set()

    for transaction in transactions:
        reference = (
            transaction["external_reference"] or ""
        )

        for prefix in reversal_prefixes:
            if reference.startswith(prefix):
                reversed_transaction_ids.add(
                    reference.replace(prefix, "", 1)
                )

    active_trade_transactions = [
        transaction
        for transaction in transactions
        if (
            transaction["transaction_type"]
            in ["buy", "sell"]
            and transaction["id"]
            not in reversed_transaction_ids
        )
    ]

    if not active_trade_transactions:
        return

    entries_by_transaction = {}

    for entry in entries:
        entries_by_transaction.setdefault(
            entry["transaction_id"],
            [],
        ).append(entry)

    account_map = {
        account["id"]: account
        for account in active_accounts
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

    editable_records = []

    for transaction in active_trade_transactions:
        transaction_entries = (
            entries_by_transaction.get(
                transaction["id"],
                [],
            )
        )

        investment_entries = [
            entry
            for entry in transaction_entries
            if (
                asset_map.get(
                    entry["asset_id"],
                    {},
                ).get("asset_type")
                in ["stock", "etf", "fund", "crypto"]
            )
        ]

        cash_entries = [
            entry
            for entry in transaction_entries
            if (
                asset_map.get(
                    entry["asset_id"],
                    {},
                ).get("asset_type")
                == "cash"
            )
        ]

        if len(investment_entries) != 1:
            continue

        if (
            transaction["cash_linked"]
            and len(cash_entries) != 1
        ):
            continue

        editable_records.append(
            {
                "transaction": transaction,
                "investment_entry": (
                    investment_entries[0]
                ),
                "cash_entry": (
                    cash_entries[0]
                    if cash_entries
                    else None
                ),
            }
        )

    if not editable_records:
        return

    st.divider()
    st.subheader("更正交易")

    with st.expander("修改買入或賣出紀錄"):
        st.caption(
            "修改會保留原交易，並建立反向紀錄"
            "及一筆更正後的新交易。"
        )

        editable_transaction_ids = [
            record["transaction"]["id"]
            for record in editable_records
        ]

        def format_editable_trade(transaction_id):
            record = next(
                record
                for record in editable_records
                if (
                    record["transaction"]["id"]
                    == transaction_id
                )
            )

            transaction = record["transaction"]
            investment_entry = (
                record["investment_entry"]
            )

            asset = asset_map.get(
                investment_entry["asset_id"],
                {},
            )

            account = account_map.get(
                investment_entry["account_id"],
                {},
            )

            transaction_date = pd.to_datetime(
                transaction["transaction_date"],
                utc=True,
            ).strftime("%Y-%m-%d")

            trade_label = (
                "買入"
                if (
                    transaction["transaction_type"]
                    == "buy"
                )
                else "賣出"
            )

            quantity = abs(
                float(
                    investment_entry[
                        "quantity_delta"
                    ]
                )
            )

            return (
                f"{transaction_date} | "
                f"{trade_label} | "
                f'{account.get("name", "未知帳戶")} | '
                f'{asset.get("symbol", "未知資產")} | '
                f"{quantity:,.6f}"
            )

        selected_transaction_id = st.selectbox(
            "選擇要修改的交易",
            options=editable_transaction_ids,
            format_func=format_editable_trade,
            key="selected_trade_to_edit",
        )

        selected_record = next(
            record
            for record in editable_records
            if (
                record["transaction"]["id"]
                == selected_transaction_id
            )
        )

        selected_transaction = (
            selected_record["transaction"]
        )

        investment_entry = (
            selected_record["investment_entry"]
        )

        cash_entry = selected_record["cash_entry"]

        selected_asset = asset_map[
            investment_entry["asset_id"]
        ]

        original_quantity = abs(
            float(
                investment_entry["quantity_delta"]
            )
        )

        original_price = float(
            investment_entry["unit_price"] or 0
        )

        original_fee = float(
            selected_transaction["fee_amount"] or 0
        )

        original_tax = float(
            selected_transaction["tax_amount"] or 0
        )

        original_date = pd.to_datetime(
            selected_transaction["transaction_date"],
            utc=True,
        ).date()

        with st.form(
            f"edit_trade_form_"
            f"{selected_transaction_id}"
        ):
            edited_quantity = st.number_input(
                "更正後交易數量",
                min_value=0.0,
                value=original_quantity,
                step=1.0,
                format="%.6f",
            )

            edited_price = st.number_input(
                (
                    "更正後每單位成交價格"
                    f'（{selected_asset["currency"]}）'
                ),
                min_value=0.0,
                value=original_price,
                step=0.01,
                format="%.6f",
            )

            edited_fee = st.number_input(
                (
                    "更正後手續費／監管費"
                    f'（{selected_asset["currency"]}）'
                ),
                min_value=0.0,
                value=original_fee,
                step=0.01,
                format="%.6f",
            )

            edited_tax = st.number_input(
                (
                    "更正後稅費"
                    f'（{selected_asset["currency"]}）'
                ),
                min_value=0.0,
                value=original_tax,
                step=0.01,
                format="%.6f",
            )

            edited_date = st.date_input(
                "更正後交易日期",
                value=original_date,
            )

            edited_memo = st.text_input(
                "更正後備註（選填）",
                value=investment_entry["memo"] or "",
            )

            confirm_edit = st.checkbox(
                "我確認要建立更正紀錄"
            )

            edit_submitted = st.form_submit_button(
                "儲存交易修改",
                width="stretch",
            )

        if edit_submitted:
            if not confirm_edit:
                st.warning("請先勾選確認。")
                return

            if edited_quantity <= 0:
                st.warning(
                    "交易數量必須大於 0。"
                )
                return

            if edited_price <= 0:
                st.warning(
                    "成交價格必須大於 0。"
                )
                return

            transaction_type = (
                selected_transaction[
                    "transaction_type"
                ]
            )

            gross_value = (
                float(edited_quantity)
                * float(edited_price)
            )

            if transaction_type == "buy":
                new_asset_delta = float(
                    edited_quantity
                )

                new_cash_delta = -(
                    gross_value
                    + float(edited_fee)
                    + float(edited_tax)
                )

            else:
                new_asset_delta = -float(
                    edited_quantity
                )

                new_cash_delta = (
                    gross_value
                    - float(edited_fee)
                    - float(edited_tax)
                )

            investment_balance_key = (
                investment_entry["account_id"],
                investment_entry["asset_id"],
            )

            current_holding = balances.get(
                investment_balance_key,
                0.0,
            )

            original_asset_delta = float(
                investment_entry["quantity_delta"]
            )

            holding_before_original = (
                current_holding
                - original_asset_delta
            )

            if (
                transaction_type == "sell"
                and float(edited_quantity)
                > holding_before_original + 0.00000001
            ):
                st.warning(
                    "更正後的賣出數量不能超過"
                    "扣除原交易後可用的持倉。"
                )
                return

            if cash_entry is not None:
                cash_balance_key = (
                    cash_entry["account_id"],
                    cash_entry["asset_id"],
                )

                current_cash_balance = balances.get(
                    cash_balance_key,
                    0.0,
                )

                original_cash_delta = float(
                    cash_entry["quantity_delta"]
                )

                cash_before_original = (
                    current_cash_balance
                    - original_cash_delta
                )

                if (
                    transaction_type == "buy"
                    and (
                        cash_before_original
                        + new_cash_delta
                        < -0.00000001
                    )
                ):
                    st.warning(
                        "更正後的買入金額超過"
                        "可用現金餘額。"
                    )
                    return

                if abs(new_cash_delta) < 0.00000001:
                    st.warning(
                        "更正後的現金變化不能為 0。"
                    )
                    return

            trade_label = (
                "買入"
                if transaction_type == "buy"
                else "賣出"
            )

            corrected_description = (
                f'更正後{trade_label} '
                f'{selected_asset["symbol"]} '
                f'{float(edited_quantity):,.6f} 單位，'
                f'成交價 {selected_asset["currency"]} '
                f'{float(edited_price):,.6f}；'
                f'費用 {float(edited_fee):,.2f}；'
                f'稅費 {float(edited_tax):,.2f}'
            )

            reversal_transaction_id = None
            corrected_transaction_id = None

            try:
                reversal_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                pd.Timestamp.now(
                                    tz=(
                                        "America/"
                                        "Los_Angeles"
                                    )
                                ).isoformat()
                            ),
                            "transaction_type": (
                                "adjustment"
                            ),
                            "description": (
                                "修改交易－撤回原紀錄："
                                f'{selected_transaction["description"]}'
                            ),
                            "external_reference": (
                                "trade_edit_reversal:"
                                f"{selected_transaction_id}"
                            ),
                            "fee_amount": 0,
                            "tax_amount": 0,
                            "trade_currency": (
                                selected_transaction[
                                    "trade_currency"
                                ]
                            ),
                            "cash_linked": (
                                selected_transaction[
                                    "cash_linked"
                                ]
                            ),
                        }
                    )
                    .execute()
                )

                reversal_rows = (
                    reversal_response.data or []
                )

                if not reversal_rows:
                    raise RuntimeError(
                        "未取得反向交易 ID。"
                    )

                reversal_transaction_id = (
                    reversal_rows[0]["id"]
                )

                original_entries = (
                    entries_by_transaction[
                        selected_transaction_id
                    ]
                )

                reversal_entries = [
                    {
                        "transaction_id": (
                            reversal_transaction_id
                        ),
                        "account_id": (
                            original_entry["account_id"]
                        ),
                        "asset_id": (
                            original_entry["asset_id"]
                        ),
                        "quantity_delta": -float(
                            original_entry[
                                "quantity_delta"
                            ]
                        ),
                        "unit_price": (
                            original_entry["unit_price"]
                        ),
                        "memo": (
                            "修改交易－撤回原紀錄："
                            f"{selected_transaction_id}"
                        ),
                    }
                    for original_entry in original_entries
                ]

                (
                    supabase
                    .table("transaction_entries")
                    .insert(reversal_entries)
                    .execute()
                )

                corrected_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{edited_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": (
                                transaction_type
                            ),
                            "description": (
                                corrected_description
                            ),
                            "external_reference": (
                                "trade_edit_replacement:"
                                f"{selected_transaction_id}"
                            ),
                            "fee_amount": float(
                                edited_fee
                            ),
                            "tax_amount": float(
                                edited_tax
                            ),
                            "trade_currency": (
                                selected_asset["currency"]
                            ),
                            "cash_linked": (
                                selected_transaction[
                                    "cash_linked"
                                ]
                            ),
                        }
                    )
                    .execute()
                )

                corrected_rows = (
                    corrected_response.data or []
                )

                if not corrected_rows:
                    raise RuntimeError(
                        "未取得更正交易 ID。"
                    )

                corrected_transaction_id = (
                    corrected_rows[0]["id"]
                )

                corrected_entries = [
                    {
                        "transaction_id": (
                            corrected_transaction_id
                        ),
                        "account_id": (
                            investment_entry[
                                "account_id"
                            ]
                        ),
                        "asset_id": (
                            investment_entry["asset_id"]
                        ),
                        "quantity_delta": (
                            new_asset_delta
                        ),
                        "unit_price": float(
                            edited_price
                        ),
                        "memo": (
                            edited_memo.strip()
                            if edited_memo.strip()
                            else None
                        ),
                    }
                ]

                if cash_entry is not None:
                    corrected_entries.append(
                        {
                            "transaction_id": (
                                corrected_transaction_id
                            ),
                            "account_id": (
                                cash_entry["account_id"]
                            ),
                            "asset_id": (
                                cash_entry["asset_id"]
                            ),
                            "quantity_delta": (
                                new_cash_delta
                            ),
                            "unit_price": None,
                            "memo": (
                                f"更正後{trade_label}"
                                "連動現金"
                            ),
                        }
                    )

                (
                    supabase
                    .table("transaction_entries")
                    .insert(corrected_entries)
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    "交易修改成功，"
                    "持倉與現金已重新計算。"
                )

                st.rerun()

            except Exception as error:
                if corrected_transaction_id is not None:
                    try:
                        (
                            supabase
                            .table("transactions")
                            .delete()
                            .eq(
                                "id",
                                corrected_transaction_id,
                            )
                            .execute()
                        )
                    except Exception:
                        pass

                if reversal_transaction_id is not None:
                    try:
                        (
                            supabase
                            .table("transactions")
                            .delete()
                            .eq(
                                "id",
                                reversal_transaction_id,
                            )
                            .execute()
                        )
                    except Exception:
                        pass

                st.error(f"修改交易失敗：{error}")

def show_trade_cancellation_manager(
    supabase,
    active_accounts,
    assets,
):
    try:
        transactions_response = (
            supabase.table("transactions")
            .select(
                "id, transaction_date, transaction_type, "
                "description, external_reference, "
                "fee_amount, tax_amount, trade_currency, "
                "cash_linked, created_at"
            )
            .order("transaction_date", desc=True)
            .order("created_at", desc=True)
            .execute()
        )

        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "id, transaction_id, account_id, asset_id, "
                "quantity_delta, unit_price, memo"
            )
            .execute()
        )

        transactions = (
            transactions_response.data or []
        )

        entries = entries_response.data or []

    except Exception as error:
        st.error(f"讀取可取消交易失敗：{error}")
        return

    reversal_prefix = "trade_reversal:"

    reversal_prefixes = (
        reversal_prefix,
        "trade_edit_reversal:",
    )

    reversed_transaction_ids = set()

    for transaction in transactions:
        reference = (
            transaction["external_reference"] or ""
        )

        for prefix in reversal_prefixes:
            if reference.startswith(prefix):
                reversed_transaction_ids.add(
                    reference.replace(prefix, "", 1)
                )

    cancellable_transactions = [
        transaction
        for transaction in transactions
        if (
            transaction["transaction_type"]
            in ["buy", "sell"]
            and transaction["id"]
            not in reversed_transaction_ids
        )
    ]

    if not cancellable_transactions:
        return

    entries_by_transaction = {}

    for entry in entries:
        transaction_id = entry["transaction_id"]

        entries_by_transaction.setdefault(
            transaction_id,
            [],
        ).append(entry)

    account_map = {
        account["id"]: account
        for account in active_accounts
    }

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    with st.expander("取消買入或賣出紀錄"):
        st.caption(
            "取消後不會刪除原始資料；"
            "系統會建立相反紀錄，還原持倉與現金。"
        )

        transaction_ids = [
            transaction["id"]
            for transaction in cancellable_transactions
        ]

        def format_cancellable_trade(transaction_id):
            transaction = next(
                transaction
                for transaction
                in cancellable_transactions
                if transaction["id"] == transaction_id
            )

            transaction_entries = (
                entries_by_transaction.get(
                    transaction_id,
                    [],
                )
            )

            investment_entry = next(
                (
                    entry
                    for entry in transaction_entries
                    if (
                        asset_map.get(
                            entry["asset_id"],
                            {},
                        ).get("asset_type")
                        in ["stock", "etf", "fund", "crypto"]
                    )
                ),
                None,
            )

            transaction_date = pd.to_datetime(
                transaction["transaction_date"],
                utc=True,
            ).strftime("%Y-%m-%d")

            trade_label = (
                "買入"
                if (
                    transaction["transaction_type"]
                    == "buy"
                )
                else "賣出"
            )

            if investment_entry is None:
                return (
                    f"{transaction_date} | "
                    f"{trade_label} | "
                    f'{transaction["description"]}'
                )

            asset = asset_map.get(
                investment_entry["asset_id"],
                {},
            )

            account = account_map.get(
                investment_entry["account_id"],
                {},
            )

            quantity = abs(
                float(
                    investment_entry[
                        "quantity_delta"
                    ]
                )
            )

            return (
                f"{transaction_date} | "
                f"{trade_label} | "
                f'{account.get("name", "未知帳戶")} | '
                f'{asset.get("symbol", "未知資產")} | '
                f"{quantity:,.6f}"
            )

        with st.form(
            "cancel_trade_form",
        ):
            selected_transaction_id = st.selectbox(
                "選擇要取消的交易",
                options=transaction_ids,
                format_func=format_cancellable_trade,
            )

            selected_transaction = next(
                transaction
                for transaction
                in cancellable_transactions
                if (
                    transaction["id"]
                    == selected_transaction_id
                )
            )

            st.caption(
                selected_transaction["description"]
                or ""
            )

            confirm_cancellation = st.checkbox(
                "我確認要取消這筆交易，"
                "並還原其持倉與現金變化"
            )

            cancel_submitted = (
                st.form_submit_button(
                    "取消所選交易",
                    width="stretch",
                )
            )

        if cancel_submitted:
            if not confirm_cancellation:
                st.warning("請先勾選確認。")
                return

            original_entries = (
                entries_by_transaction.get(
                    selected_transaction_id,
                    [],
                )
            )

            if not original_entries:
                st.error(
                    "找不到這筆交易的明細，"
                    "因此無法安全取消。"
                )
                return

            reversal_transaction_id = None

            try:
                reversal_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                pd.Timestamp.now(
                                    tz=(
                                        "America/"
                                        "Los_Angeles"
                                    )
                                ).isoformat()
                            ),
                            "transaction_type": (
                                "adjustment"
                            ),
                            "description": (
                                "取消交易："
                                f'{selected_transaction["description"]}'
                            ),
                            "external_reference": (
                                reversal_prefix
                                + selected_transaction_id
                            ),
                            "fee_amount": 0,
                            "tax_amount": 0,
                            "trade_currency": (
                                selected_transaction[
                                    "trade_currency"
                                ]
                            ),
                            "cash_linked": (
                                selected_transaction[
                                    "cash_linked"
                                ]
                            ),
                        }
                    )
                    .execute()
                )

                reversal_rows = (
                    reversal_response.data or []
                )

                if not reversal_rows:
                    raise RuntimeError(
                        "取消交易建立後未取得交易 ID。"
                    )

                reversal_transaction_id = (
                    reversal_rows[0]["id"]
                )

                reversal_entries = []

                for original_entry in original_entries:
                    reversal_entries.append(
                        {
                            "transaction_id": (
                                reversal_transaction_id
                            ),
                            "account_id": (
                                original_entry[
                                    "account_id"
                                ]
                            ),
                            "asset_id": (
                                original_entry[
                                    "asset_id"
                                ]
                            ),
                            "quantity_delta": -float(
                                original_entry[
                                    "quantity_delta"
                                ]
                            ),
                            "unit_price": (
                                original_entry[
                                    "unit_price"
                                ]
                            ),
                            "memo": (
                                "取消原交易："
                                f"{selected_transaction_id}"
                            ),
                        }
                    )

                (
                    supabase
                    .table("transaction_entries")
                    .insert(reversal_entries)
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    "交易取消成功，"
                    "持倉與現金已還原。"
                )

                st.rerun()

            except Exception as error:
                if reversal_transaction_id is not None:
                    try:
                        (
                            supabase
                            .table("transactions")
                            .delete()
                            .eq(
                                "id",
                                reversal_transaction_id,
                            )
                            .execute()
                        )
                    except Exception:
                        pass

                st.error(f"取消交易失敗：{error}")