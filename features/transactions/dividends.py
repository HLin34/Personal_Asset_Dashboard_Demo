import pandas as pd
import streamlit as st

def show_dividend_entry(supabase, active_accounts, assets):
    active_investment_assets = [
        asset
        for asset in assets
        if (
            asset["is_active"]
            and asset["asset_type"]
            in ["stock", "etf", "fund"]
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

    except Exception as error:
        st.error(f"讀取股利相關持倉失敗：{error}")
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

    st.divider()
    st.subheader("股利")

    with st.expander("新增現金或股票股利"):
        dividend_type = st.radio(
            "股利類型",
            options=["cash", "stock"],
            format_func=lambda value: {
                "cash": "現金股利",
                "stock": "股票股利",
            }[value],
            horizontal=True,
            key="dividend_type",
        )

        account_ids = [
            account["id"]
            for account in active_accounts
        ]

        account_by_id = {
            account["id"]: account
            for account in active_accounts
        }

        def format_dividend_account(account_id):
            account = account_by_id[account_id]

            institution = (
                account["institution"]
                if account["institution"]
                else "未指定機構"
            )

            return (
                f'{account["name"]}｜'
                f"{institution}"
            )

        source_account_id = st.selectbox(
            "持有資產的帳戶",
            options=account_ids,
            format_func=format_dividend_account,
            key="dividend_source_account",
            help="選擇收到這筆股利的券商或基金帳戶。",
        )

        investment_asset_ids = [
            asset["id"]
            for asset in active_investment_assets
        ]

        investment_asset_by_id = {
            asset["id"]: asset
            for asset in active_investment_assets
        }

        def format_dividend_asset(asset_id):
            asset = investment_asset_by_id[asset_id]

            return (
                f'{asset["symbol"]}｜'
                f'{asset["name"]}｜'
                f'{asset["currency"]}'
            )

        source_asset_id = st.selectbox(
            "發放股利的資產",
            options=investment_asset_ids,
            format_func=format_dividend_asset,
            key="dividend_source_asset",
        )

        source_account = account_by_id[
            source_account_id
        ]

        source_asset = investment_asset_by_id[
            source_asset_id
        ]

        current_holding = balances.get(
            (
                source_account_id,
                source_asset_id,
            ),
            0.0,
        )

        st.caption(
            f'目前持倉：{current_holding:,.6f} '
            f'{source_asset["symbol"]}'
        )

        if current_holding <= 0:
            st.warning(
                "这个账户目前没有系统持仓。"
                "如果这是卖出后才收到的股利，仍可继续记录；"
                "否则请确认账户及资产是否正确。"
            )

        widget_suffix = (
            f"{dividend_type}_"
            f"{source_account_id}_"
            f"{source_asset_id}"
        )

        cash_account_id = None
        cash_asset_id = None

        gross_amount = 0.0
        tax_amount = 0.0
        fee_amount = 0.0
        net_amount = 0.0
        stock_quantity = 0.0

        cash_assets_same_currency = [
            asset
            for asset in active_cash_assets
            if (
                asset["currency"]
                == source_asset["currency"]
            )
        ]

        if dividend_type == "cash":
            gross_amount = st.number_input(
                (
                    "稅前現金股利"
                    f'（{source_asset["currency"]}）'
                ),
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.6f",
                key=f"dividend_gross_{widget_suffix}",
            )

            tax_amount = st.number_input(
                (
                    "預扣稅"
                    f'（{source_asset["currency"]}）'
                ),
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.6f",
                key=f"dividend_tax_{widget_suffix}",
                help=(
                    "例如美股股利被预扣 USD 30，"
                    "就在这里输入 30。"
                ),
            )

            fee_amount = st.number_input(
                (
                    "其他費用"
                    f'（{source_asset["currency"]}）'
                ),
                min_value=0.0,
                value=0.0,
                step=0.01,
                format="%.6f",
                key=f"dividend_fee_{widget_suffix}",
            )

            net_amount = (
                float(gross_amount)
                - float(tax_amount)
                - float(fee_amount)
            )

            st.metric(
                "實際收到現金",
                (
                    f'{source_asset["currency"]} '
                    f"{net_amount:,.2f}"
                ),
            )

            if cash_assets_same_currency:
                cash_account_id = st.selectbox(
                    "現金入帳帳戶",
                    options=account_ids,
                    format_func=format_dividend_account,
                    key=(
                        f"dividend_cash_account_"
                        f"{widget_suffix}"
                    ),
                )

                cash_asset_ids = [
                    asset["id"]
                    for asset in cash_assets_same_currency
                ]

                cash_asset_by_id = {
                    asset["id"]: asset
                    for asset in cash_assets_same_currency
                }

                def format_dividend_cash_asset(asset_id):
                    asset = cash_asset_by_id[asset_id]

                    return (
                        f'{asset["symbol"]}｜'
                        f'{asset["name"]}'
                    )

                cash_asset_id = st.selectbox(
                    "入帳的現金資產",
                    options=cash_asset_ids,
                    format_func=format_dividend_cash_asset,
                    key=(
                        f"dividend_cash_asset_"
                        f"{widget_suffix}"
                    ),
                )

                current_cash_balance = balances.get(
                    (
                        cash_account_id,
                        cash_asset_id,
                    ),
                    0.0,
                )

                st.caption(
                    "入帳前現金餘額："
                    f'{source_asset["currency"]} '
                    f"{current_cash_balance:,.2f}"
                )

            else:
                st.warning(
                    f'目前没有使用中的 '
                    f'{source_asset["currency"]} 现金资产，'
                    "请先到「资产」页面建立。"
                )

        else:
            stock_quantity = st.number_input(
                "收到的股票數量",
                min_value=0.0,
                value=0.0,
                step=1.0,
                format="%.6f",
                key=(
                    f"dividend_stock_quantity_"
                    f"{widget_suffix}"
                ),
                help=(
                    "股票股利会增加该资产在此账户中的"
                    "持有数量，不会改变现金。"
                ),
            )

            st.metric(
                "收到後持倉",
                (
                    f"{current_holding + float(stock_quantity):,.6f} "
                    f'{source_asset["symbol"]}'
                ),
            )

        dividend_date = st.date_input(
            "股利入帳日期",
            value="today",
            key=f"dividend_date_{widget_suffix}",
        )

        dividend_memo = st.text_input(
            "備註（選填）",
            placeholder="例如：2026 年度现金股利",
            key=f"dividend_memo_{widget_suffix}",
        )

        cannot_save_cash_dividend = (
            dividend_type == "cash"
            and not cash_assets_same_currency
        )

        submitted = st.button(
            "儲存股利紀錄",
            width="stretch",
            disabled=cannot_save_cash_dividend,
            key=f"save_dividend_{widget_suffix}",
        )

        if submitted:
            validation_error = None

            if dividend_type == "cash":
                if gross_amount <= 0:
                    validation_error = (
                        "税前现金股利必须大于 0。"
                    )

                elif (
                    tax_amount + fee_amount
                    > gross_amount
                ):
                    validation_error = (
                        "预扣税与其他费用合计"
                        "不能超过税前股利。"
                    )

                elif net_amount <= 0:
                    validation_error = (
                        "实际收到的现金必须大于 0。"
                    )

                elif (
                    cash_account_id is None
                    or cash_asset_id is None
                ):
                    validation_error = (
                        "请选择现金入账账户及资产。"
                    )

            elif stock_quantity <= 0:
                validation_error = (
                    "收到的股票数量必须大于 0。"
                )

            if validation_error:
                st.warning(validation_error)
                return

            if dividend_type == "cash":
                description = (
                    f'收到 {source_asset["symbol"]} '
                    f'現金股利；稅前 '
                    f'{source_asset["currency"]} '
                    f'{float(gross_amount):,.2f}；'
                    f'預扣稅 {float(tax_amount):,.2f}；'
                    f'費用 {float(fee_amount):,.2f}；'
                    f'淨額 {float(net_amount):,.2f}'
                )

                entry_account_id = cash_account_id
                entry_asset_id = cash_asset_id
                entry_quantity = float(net_amount)
                cash_linked = True

            else:
                description = (
                    f'收到 {source_asset["symbol"]} '
                    f'股票股利 '
                    f'{float(stock_quantity):,.6f} 單位'
                )

                entry_account_id = source_account_id
                entry_asset_id = source_asset_id
                entry_quantity = float(stock_quantity)
                cash_linked = False

            transaction_id = None

            try:
                transaction_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{dividend_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": "dividend",
                            "description": description,
                            "fee_amount": float(fee_amount),
                            "tax_amount": float(tax_amount),
                            "trade_currency": (
                                source_asset["currency"]
                            ),
                            "cash_linked": cash_linked,
                            "related_account_id": (
                                source_account_id
                            ),
                            "related_asset_id": (
                                source_asset_id
                            ),
                            "dividend_type": dividend_type,
                            "gross_amount": (
                                float(gross_amount)
                                if dividend_type == "cash"
                                else None
                            ),
                        }
                    )
                    .execute()
                )

                transaction_rows = (
                    transaction_response.data or []
                )

                if not transaction_rows:
                    raise RuntimeError(
                        "股利交易建立后未取得交易 ID。"
                    )

                transaction_id = (
                    transaction_rows[0]["id"]
                )

                entry_memo = (
                    dividend_memo.strip()
                    if dividend_memo.strip()
                    else (
                        "現金股利"
                        if dividend_type == "cash"
                        else "股票股利"
                    )
                )

                (
                    supabase.table("transaction_entries")
                    .insert(
                        {
                            "transaction_id": transaction_id,
                            "account_id": entry_account_id,
                            "asset_id": entry_asset_id,
                            "quantity_delta": entry_quantity,
                            "unit_price": None,
                            "memo": entry_memo,
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    f'{source_asset["symbol"]} '
                    "股利紀錄新增成功。"
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

                st.error(f"新增股利紀錄失敗：{error}")

def show_dividend_edit_manager(
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
                "cash_linked, related_account_id, "
                "related_asset_id, dividend_type, "
                "gross_amount, created_at"
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
        st.error(f"讀取可修改股利失敗：{error}")
        return

    reversal_prefixes = (
        "dividend_reversal:",
        "dividend_edit_reversal:",
    )

    reversed_dividend_ids = set()

    for transaction in transactions:
        reference = (
            transaction["external_reference"] or ""
        )

        for prefix in reversal_prefixes:
            if reference.startswith(prefix):
                original_id = reference[len(prefix):]

                if original_id:
                    reversed_dividend_ids.add(original_id)

    dividend_transactions = [
        transaction
        for transaction in transactions
        if (
            transaction["transaction_type"] == "dividend"
            and transaction["id"]
            not in reversed_dividend_ids
        )
    ]

    dividend_entries = {}

    for transaction in dividend_transactions:
        matching_entries = [
            entry
            for entry in entries
            if (
                entry["transaction_id"]
                == transaction["id"]
            )
        ]

        if matching_entries:
            dividend_entries[
                transaction["id"]
            ] = matching_entries[0]

    dividend_transactions = [
        transaction
        for transaction in dividend_transactions
        if transaction["id"] in dividend_entries
    ]

    if not dividend_transactions:
        return

    account_by_id = {
        account["id"]: account
        for account in active_accounts
    }

    asset_by_id = {
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

    with st.expander("修改股利紀錄"):
        transaction_ids = [
            transaction["id"]
            for transaction in dividend_transactions
        ]

        transaction_by_id = {
            transaction["id"]: transaction
            for transaction in dividend_transactions
        }

        def format_dividend_for_edit(transaction_id):
            transaction = transaction_by_id[
                transaction_id
            ]

            source_asset = asset_by_id.get(
                transaction["related_asset_id"]
            )

            source_account = account_by_id.get(
                transaction["related_account_id"]
            )

            symbol = (
                source_asset["symbol"]
                if source_asset is not None
                else "未知資產"
            )

            account_name = (
                source_account["name"]
                if source_account is not None
                else "未知帳戶"
            )

            dividend_label = (
                "現金股利"
                if transaction["dividend_type"] == "cash"
                else "股票股利"
            )

            transaction_date = str(
                transaction["transaction_date"]
            )[:10]

            return (
                f"{transaction_date}｜"
                f"{account_name}｜"
                f"{symbol}｜"
                f"{dividend_label}"
            )

        selected_transaction_id = st.selectbox(
            "選擇要修改的股利紀錄",
            options=transaction_ids,
            format_func=format_dividend_for_edit,
            key="edit_dividend_transaction",
        )

        original_transaction = transaction_by_id[
            selected_transaction_id
        ]

        original_entry = dividend_entries[
            selected_transaction_id
        ]

        source_asset = asset_by_id.get(
            original_transaction["related_asset_id"]
        )

        source_account = account_by_id.get(
            original_transaction["related_account_id"]
        )

        entry_account = account_by_id.get(
            original_entry["account_id"]
        )

        entry_asset = asset_by_id.get(
            original_entry["asset_id"]
        )

        source_symbol = (
            source_asset["symbol"]
            if source_asset is not None
            else "未知資產"
        )

        source_account_name = (
            source_account["name"]
            if source_account is not None
            else "未知帳戶"
        )

        entry_account_name = (
            entry_account["name"]
            if entry_account is not None
            else "未知帳戶"
        )

        entry_asset_symbol = (
            entry_asset["symbol"]
            if entry_asset is not None
            else "未知資產"
        )

        dividend_type = original_transaction[
            "dividend_type"
        ]

        original_quantity = float(
            original_entry["quantity_delta"]
        )

        current_balance = balances.get(
            (
                original_entry["account_id"],
                original_entry["asset_id"],
            ),
            0.0,
        )

        st.caption(
            f"股利來源：{source_account_name}｜"
            f"{source_symbol}"
        )

        if dividend_type == "cash":
            new_gross_amount = st.number_input(
                (
                    "修正後稅前股利"
                    f'（{original_transaction["trade_currency"]}）'
                ),
                min_value=0.0,
                value=float(
                    original_transaction["gross_amount"]
                    or 0
                ),
                step=0.01,
                format="%.6f",
                key=(
                    f"edit_dividend_gross_"
                    f"{selected_transaction_id}"
                ),
            )

            new_tax_amount = st.number_input(
                (
                    "修正後預扣稅"
                    f'（{original_transaction["trade_currency"]}）'
                ),
                min_value=0.0,
                value=float(
                    original_transaction["tax_amount"]
                    or 0
                ),
                step=0.01,
                format="%.6f",
                key=(
                    f"edit_dividend_tax_"
                    f"{selected_transaction_id}"
                ),
            )

            new_fee_amount = st.number_input(
                (
                    "修正後其他費用"
                    f'（{original_transaction["trade_currency"]}）'
                ),
                min_value=0.0,
                value=float(
                    original_transaction["fee_amount"]
                    or 0
                ),
                step=0.01,
                format="%.6f",
                key=(
                    f"edit_dividend_fee_"
                    f"{selected_transaction_id}"
                ),
            )

            new_quantity = (
                float(new_gross_amount)
                - float(new_tax_amount)
                - float(new_fee_amount)
            )

            st.metric(
                "修正後實際收到現金",
                (
                    f'{original_transaction["trade_currency"]} '
                    f"{new_quantity:,.2f}"
                ),
                delta=(
                    f"{new_quantity - original_quantity:+,.2f}"
                ),
            )

        else:
            new_quantity = st.number_input(
                "修正後股票股利數量",
                min_value=0.0,
                value=float(original_quantity),
                step=1.0,
                format="%.6f",
                key=(
                    f"edit_dividend_quantity_"
                    f"{selected_transaction_id}"
                ),
            )

            new_gross_amount = None
            new_tax_amount = 0.0
            new_fee_amount = 0.0

            st.metric(
                "持倉數量變化",
                f"{float(new_quantity):,.6f}",
                delta=(
                    f"{float(new_quantity) - original_quantity:+,.6f}"
                ),
            )

        balance_after_edit = (
            current_balance
            - original_quantity
            + float(new_quantity)
        )

        st.caption(
            f"入帳位置：{entry_account_name}｜"
            f"{entry_asset_symbol}；"
            f"目前 {current_balance:,.6f}，"
            f"修改後 {balance_after_edit:,.6f}"
        )

        original_date = pd.to_datetime(
            original_transaction["transaction_date"]
        ).date()

        new_dividend_date = st.date_input(
            "修正後入帳日期",
            value=original_date,
            key=(
                f"edit_dividend_date_"
                f"{selected_transaction_id}"
            ),
        )

        new_memo = st.text_input(
            "修正後備註",
            value=original_entry["memo"] or "",
            key=(
                f"edit_dividend_memo_"
                f"{selected_transaction_id}"
            ),
        )

        edit_reason = st.text_input(
            "修改原因（選填）",
            placeholder="例如：输入金额错误",
            key=(
                f"edit_dividend_reason_"
                f"{selected_transaction_id}"
            ),
        )

        invalid_balance = (
            balance_after_edit < -0.00000001
        )

        if invalid_balance:
            st.error(
                "修改后会使现金余额或持仓成为负数，"
                "请检查后续交易或修正数量。"
            )

        confirm_edit = st.checkbox(
            "我確認要建立這筆股利修正版",
            key=(
                f"confirm_dividend_edit_"
                f"{selected_transaction_id}"
            ),
        )

        submitted = st.button(
            "儲存股利修正版",
            type="primary",
            width="stretch",
            disabled=(
                not confirm_edit
                or invalid_balance
            ),
            key=(
                f"save_dividend_edit_"
                f"{selected_transaction_id}"
            ),
        )

        if submitted:
            validation_error = None

            if dividend_type == "cash":
                if new_gross_amount <= 0:
                    validation_error = (
                        "税前股利必须大于 0。"
                    )

                elif (
                    new_tax_amount + new_fee_amount
                    > new_gross_amount
                ):
                    validation_error = (
                        "预扣税与费用合计"
                        "不能超过税前股利。"
                    )

                elif new_quantity <= 0:
                    validation_error = (
                        "实际收到的现金必须大于 0。"
                    )

            elif new_quantity <= 0:
                validation_error = (
                    "股票股利数量必须大于 0。"
                )

            if validation_error:
                st.warning(validation_error)
                return

            reason_text = (
                edit_reason.strip()
                if edit_reason.strip()
                else "修正股利资料"
            )

            reversal_transaction_id = None
            replacement_transaction_id = None

            try:
                reversal_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{new_dividend_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": "adjustment",
                            "description": (
                                "修改股利时撤销原纪录："
                                f'{original_transaction["description"]}'
                                f"；原因：{reason_text}"
                            ),
                            "external_reference": (
                                "dividend_edit_reversal:"
                                f"{selected_transaction_id}"
                            ),
                            "fee_amount": 0,
                            "tax_amount": 0,
                            "trade_currency": (
                                original_transaction[
                                    "trade_currency"
                                ]
                            ),
                            "cash_linked": (
                                original_transaction[
                                    "cash_linked"
                                ]
                            ),
                            "related_account_id": (
                                original_transaction[
                                    "related_account_id"
                                ]
                            ),
                            "related_asset_id": (
                                original_transaction[
                                    "related_asset_id"
                                ]
                            ),
                            "dividend_type": None,
                            "gross_amount": None,
                        }
                    )
                    .execute()
                )

                reversal_rows = (
                    reversal_response.data or []
                )

                if not reversal_rows:
                    raise RuntimeError(
                        "未取得股利撤销交易 ID。"
                    )

                reversal_transaction_id = (
                    reversal_rows[0]["id"]
                )

                (
                    supabase.table("transaction_entries")
                    .insert(
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
                            "quantity_delta": (
                                -original_quantity
                            ),
                            "unit_price": (
                                original_entry["unit_price"]
                            ),
                            "memo": (
                                "修改股利时撤销原纪录"
                            ),
                        }
                    )
                    .execute()
                )

                if dividend_type == "cash":
                    replacement_description = (
                        f'收到 {source_symbol} 現金股利；'
                        f'稅前 '
                        f'{original_transaction["trade_currency"]} '
                        f'{float(new_gross_amount):,.2f}；'
                        f'預扣稅 {float(new_tax_amount):,.2f}；'
                        f'費用 {float(new_fee_amount):,.2f}；'
                        f'淨額 {float(new_quantity):,.2f}'
                    )
                else:
                    replacement_description = (
                        f'收到 {source_symbol} 股票股利 '
                        f'{float(new_quantity):,.6f} 單位'
                    )

                replacement_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{new_dividend_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": "dividend",
                            "description": (
                                replacement_description
                            ),
                            "external_reference": (
                                "dividend_edit_replacement:"
                                f"{selected_transaction_id}"
                            ),
                            "fee_amount": float(
                                new_fee_amount
                            ),
                            "tax_amount": float(
                                new_tax_amount
                            ),
                            "trade_currency": (
                                original_transaction[
                                    "trade_currency"
                                ]
                            ),
                            "cash_linked": (
                                original_transaction[
                                    "cash_linked"
                                ]
                            ),
                            "related_account_id": (
                                original_transaction[
                                    "related_account_id"
                                ]
                            ),
                            "related_asset_id": (
                                original_transaction[
                                    "related_asset_id"
                                ]
                            ),
                            "dividend_type": dividend_type,
                            "gross_amount": (
                                float(new_gross_amount)
                                if dividend_type == "cash"
                                else None
                            ),
                        }
                    )
                    .execute()
                )

                replacement_rows = (
                    replacement_response.data or []
                )

                if not replacement_rows:
                    raise RuntimeError(
                        "未取得股利修正版交易 ID。"
                    )

                replacement_transaction_id = (
                    replacement_rows[0]["id"]
                )

                (
                    supabase.table("transaction_entries")
                    .insert(
                        {
                            "transaction_id": (
                                replacement_transaction_id
                            ),
                            "account_id": (
                                original_entry["account_id"]
                            ),
                            "asset_id": (
                                original_entry["asset_id"]
                            ),
                            "quantity_delta": float(
                                new_quantity
                            ),
                            "unit_price": (
                                original_entry["unit_price"]
                            ),
                            "memo": (
                                new_memo.strip()
                                if new_memo.strip()
                                else (
                                    "現金股利"
                                    if dividend_type == "cash"
                                    else "股票股利"
                                )
                            ),
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    "股利纪录修改成功，"
                    "已保留原纪录与撤销纪录。"
                )

                st.rerun()

            except Exception as error:
                if replacement_transaction_id is not None:
                    try:
                        (
                            supabase.table("transactions")
                            .delete()
                            .eq(
                                "id",
                                replacement_transaction_id,
                            )
                            .execute()
                        )
                    except Exception:
                        pass

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

                st.error(f"修改股利紀錄失敗：{error}")

def show_dividend_cancellation_manager(
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
                "cash_linked, related_account_id, "
                "related_asset_id, dividend_type, "
                "gross_amount, created_at"
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
        st.error(f"讀取可取消股利失敗：{error}")
        return

    reversal_prefixes = (
        "dividend_reversal:",
        "dividend_edit_reversal:",
    )

    reversed_dividend_ids = set()

    for transaction in transactions:
        reference = (
            transaction["external_reference"] or ""
        )

        for prefix in reversal_prefixes:
            if reference.startswith(prefix):
                original_id = reference[len(prefix):]

                if original_id:
                    reversed_dividend_ids.add(original_id)

    dividend_transactions = [
        transaction
        for transaction in transactions
        if (
            transaction["transaction_type"] == "dividend"
            and transaction["id"]
            not in reversed_dividend_ids
        )
    ]

    dividend_entries = {}

    for transaction in dividend_transactions:
        matching_entries = [
            entry
            for entry in entries
            if (
                entry["transaction_id"]
                == transaction["id"]
            )
        ]

        if matching_entries:
            dividend_entries[
                transaction["id"]
            ] = matching_entries[0]

    dividend_transactions = [
        transaction
        for transaction in dividend_transactions
        if transaction["id"] in dividend_entries
    ]

    if not dividend_transactions:
        return

    account_by_id = {
        account["id"]: account
        for account in active_accounts
    }

    asset_by_id = {
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

    with st.expander("取消股利紀錄"):
        transaction_ids = [
            transaction["id"]
            for transaction in dividend_transactions
        ]

        transaction_by_id = {
            transaction["id"]: transaction
            for transaction in dividend_transactions
        }

        def format_dividend_transaction(
            transaction_id,
        ):
            transaction = transaction_by_id[
                transaction_id
            ]

            source_asset = asset_by_id.get(
                transaction["related_asset_id"]
            )

            source_account = account_by_id.get(
                transaction["related_account_id"]
            )

            symbol = (
                source_asset["symbol"]
                if source_asset is not None
                else "未知資產"
            )

            account_name = (
                source_account["name"]
                if source_account is not None
                else "未知帳戶"
            )

            dividend_type_label = (
                "現金股利"
                if transaction["dividend_type"] == "cash"
                else "股票股利"
            )

            transaction_date = str(
                transaction["transaction_date"]
            )[:10]

            return (
                f"{transaction_date}｜"
                f"{account_name}｜"
                f"{symbol}｜"
                f"{dividend_type_label}"
            )

        selected_transaction_id = st.selectbox(
            "選擇要取消的股利紀錄",
            options=transaction_ids,
            format_func=format_dividend_transaction,
            key="cancel_dividend_transaction",
        )

        selected_transaction = transaction_by_id[
            selected_transaction_id
        ]

        selected_entry = dividend_entries[
            selected_transaction_id
        ]

        entry_account = account_by_id.get(
            selected_entry["account_id"]
        )

        entry_asset = asset_by_id.get(
            selected_entry["asset_id"]
        )

        entry_account_name = (
            entry_account["name"]
            if entry_account is not None
            else "未知帳戶"
        )

        entry_asset_symbol = (
            entry_asset["symbol"]
            if entry_asset is not None
            else "未知資產"
        )

        original_quantity = float(
            selected_entry["quantity_delta"]
        )

        current_balance = balances.get(
            (
                selected_entry["account_id"],
                selected_entry["asset_id"],
            ),
            0.0,
        )

        balance_after_cancellation = (
            current_balance - original_quantity
        )

        st.write(
            selected_transaction["description"]
            or "無交易說明"
        )

        if (
            selected_transaction["dividend_type"]
            == "cash"
        ):
            detail_col1, detail_col2, detail_col3 = (
                st.columns(3)
            )

            with detail_col1:
                st.metric(
                    "稅前股利",
                    (
                        f'{selected_transaction["trade_currency"]} '
                        f'{float(selected_transaction["gross_amount"] or 0):,.2f}'
                    ),
                )

            with detail_col2:
                st.metric(
                    "預扣稅",
                    (
                        f'{selected_transaction["trade_currency"]} '
                        f'{float(selected_transaction["tax_amount"] or 0):,.2f}'
                    ),
                )

            with detail_col3:
                st.metric(
                    "將扣回現金",
                    (
                        f'{selected_transaction["trade_currency"]} '
                        f"{original_quantity:,.2f}"
                    ),
                )

        else:
            st.metric(
                "將扣回股票數量",
                (
                    f"{original_quantity:,.6f} "
                    f"{entry_asset_symbol}"
                ),
            )

        st.caption(
            f"{entry_account_name}｜"
            f"{entry_asset_symbol}："
            f"目前 {current_balance:,.6f}，"
            "取消後 "
            f"{balance_after_cancellation:,.6f}"
        )

        insufficient_balance = (
            balance_after_cancellation
            < -0.00000001
        )

        if insufficient_balance:
            st.error(
                "目前余额或持仓不足以取消这笔股利。"
                "这通常代表收到的现金已经被其他交易使用，"
                "或股票股利已经卖出。请先检查后续交易。"
            )

        cancellation_date = st.date_input(
            "取消日期",
            value="today",
            key=(
                f"dividend_cancellation_date_"
                f"{selected_transaction_id}"
            ),
        )

        cancellation_reason = st.text_input(
            "取消原因（選填）",
            placeholder="例如：测试纪录、重复输入",
            key=(
                f"dividend_cancellation_reason_"
                f"{selected_transaction_id}"
            ),
        )

        confirm_cancellation = st.checkbox(
            "我確認要取消這筆股利紀錄",
            key=(
                f"confirm_dividend_cancellation_"
                f"{selected_transaction_id}"
            ),
        )

        submitted = st.button(
            "取消股利紀錄",
            type="primary",
            width="stretch",
            disabled=(
                not confirm_cancellation
                or insufficient_balance
            ),
            key=(
                f"cancel_dividend_button_"
                f"{selected_transaction_id}"
            ),
        )

        if submitted:
            reversal_transaction_id = None

            reason_text = (
                cancellation_reason.strip()
                if cancellation_reason.strip()
                else "未填写原因"
            )

            try:
                reversal_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{cancellation_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": "adjustment",
                            "description": (
                                "取消股利："
                                f'{selected_transaction["description"]}'
                                f"；原因：{reason_text}"
                            ),
                            "external_reference": (
                                "dividend_reversal:"
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
                            "related_account_id": (
                                selected_transaction[
                                    "related_account_id"
                                ]
                            ),
                            "related_asset_id": (
                                selected_transaction[
                                    "related_asset_id"
                                ]
                            ),
                            "dividend_type": None,
                            "gross_amount": None,
                        }
                    )
                    .execute()
                )

                reversal_rows = (
                    reversal_response.data or []
                )

                if not reversal_rows:
                    raise RuntimeError(
                        "取消股利后未取得调整交易 ID。"
                    )

                reversal_transaction_id = (
                    reversal_rows[0]["id"]
                )

                (
                    supabase.table("transaction_entries")
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
                                -original_quantity
                            ),
                            "unit_price": (
                                selected_entry["unit_price"]
                            ),
                            "memo": (
                                "取消股利："
                                f"{reason_text}"
                            ),
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = "股利紀錄已取消並建立反向調整。"

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

                st.error(f"取消股利紀錄失敗：{error}")