from datetime import datetime, timezone

import streamlit as st

from services.portfolio_cost import (
    calculate_portfolio_costs,
    get_excluded_transaction_ids,
)


INVESTMENT_ASSET_TYPES = {
    "stock",
    "etf",
    "fund",
}

EPSILON = 0.000000000001


def show_split_entry(
    supabase,
    active_accounts,
    assets,
):
    with st.expander(
        "新增分割或反向分割",
        expanded=False,
    ):
        st.caption(
            "適用於股票分割、ETF 分割、基金單位分割"
            "及反向分割。只改變持有數量與平均成本，"
            "不改變總成本，也不連動現金。"
        )

        try:
            transactions_response = (
                supabase.table("transactions")
                .select(
                    "id, transaction_date, "
                    "transaction_type, "
                    "external_reference, "
                    "fee_amount, tax_amount, "
                    "dividend_type, gross_amount, "
                    "trade_currency, "
                    "related_account_id, "
                    "related_asset_id, created_at"
                )
                .execute()
            )

            entries_response = (
                supabase.table(
                    "transaction_entries"
                )
                .select(
                    "id, transaction_id, "
                    "account_id, asset_id, "
                    "quantity_delta, unit_price, "
                    "created_at"
                )
                .execute()
            )

            transactions = (
                transactions_response.data or []
            )

            entries = (
                entries_response.data or []
            )

        except Exception as error:
            st.error(
                f"讀取公司行動資料失敗：{error}"
            )
            return

        account_map = {
            account["id"]: account
            for account in active_accounts
        }

        asset_map = {
            asset["id"]: asset
            for asset in assets
        }

        portfolio_costs = (
            calculate_portfolio_costs(
                transactions,
                entries,
                asset_map,
            )
        )

        available_pairs = []

        for (
            account_id,
            asset_id,
        ), cost_state in portfolio_costs.items():
            account = account_map.get(
                account_id
            )

            asset = asset_map.get(
                asset_id
            )

            if account is None or asset is None:
                continue

            if (
                not asset["is_active"]
                or asset["asset_type"]
                not in INVESTMENT_ASSET_TYPES
            ):
                continue

            current_quantity = float(
                cost_state.get(
                    "quantity",
                    0,
                )
                or 0
            )

            if current_quantity <= EPSILON:
                continue

            available_pairs.append(
                (
                    account_id,
                    asset_id,
                )
            )

        if not available_pairs:
            st.info(
                "目前沒有可進行分割的投資持倉。"
            )
            return

        def format_holding_pair(pair):
            account_id, asset_id = pair

            account = account_map[
                account_id
            ]

            asset = asset_map[
                asset_id
            ]

            institution = (
                account.get("institution")
                or "未指定機構"
            )

            return (
                f'{account["name"]} | '
                f"{institution} | "
                f'{asset["symbol"]} | '
                f'{asset["name"]}'
            )

        selected_pair = st.selectbox(
            "選擇持倉",
            options=available_pairs,
            format_func=format_holding_pair,
            key="split_holding_pair",
        )

        selected_account_id = (
            selected_pair[0]
        )

        selected_asset_id = (
            selected_pair[1]
        )

        selected_account = account_map[
            selected_account_id
        ]

        selected_asset = asset_map[
            selected_asset_id
        ]

        cost_state = portfolio_costs[
            selected_pair
        ]

        current_quantity = float(
            cost_state.get(
                "quantity",
                0,
            )
            or 0
        )

        total_cost = float(
            cost_state.get(
                "total_cost",
                0,
            )
            or 0
        )

        current_average_cost = (
            total_cost / current_quantity
            if current_quantity > EPSILON
            else None
        )

        st.write(
            f"目前持有："
            f"{current_quantity:,.6f} 單位"
        )

        if current_average_cost is not None:
            st.write(
                f"目前平均成本："
                f"{current_average_cost:,.6f} "
                f'{selected_asset["currency"]}'
            )

        ratio_col1, ratio_col2 = (
            st.columns(2)
        )

        with ratio_col1:
            old_units = st.number_input(
                "分割前單位",
                min_value=0.000001,
                value=1.0,
                step=1.0,
                format="%.6f",
                key="split_old_units",
            )

        with ratio_col2:
            new_units = st.number_input(
                "分割後單位",
                min_value=0.000001,
                value=2.0,
                step=1.0,
                format="%.6f",
                key="split_new_units",
            )

        split_ratio = (
            float(new_units)
            / float(old_units)
        )

        new_quantity = (
            current_quantity
            * split_ratio
        )

        quantity_delta = (
            new_quantity
            - current_quantity
        )

        new_average_cost = (
            total_cost / new_quantity
            if new_quantity > EPSILON
            else None
        )

        if split_ratio > 1:
            action_name = "分割"

        elif split_ratio < 1:
            action_name = "反向分割"

        else:
            action_name = "比例未改變"

        st.markdown("##### 預覽")

        preview_col1, preview_col2 = (
            st.columns(2)
        )

        with preview_col1:
            st.metric(
                "公司行動類型",
                action_name,
            )

            st.metric(
                "分割後持有數量",
                f"{new_quantity:,.6f}",
                delta=(
                    f"{quantity_delta:+,.6f}"
                ),
            )

        with preview_col2:
            st.metric(
                "總成本",
                (
                    f"{total_cost:,.2f} "
                    f'{selected_asset["currency"]}'
                ),
            )

            st.metric(
                "分割後平均成本",
                (
                    f"{new_average_cost:,.6f} "
                    f'{selected_asset["currency"]}'
                    if new_average_cost
                    is not None
                    else "—"
                ),
            )

        st.caption(
            "分割只會改變數量及每單位平均成本，"
            "上方總成本不會改變。"
        )

        action_date = st.date_input(
            "公司行動日期",
            value="today",
            key="split_action_date",
        )

        memo = st.text_input(
            "備註（選填）",
            placeholder=(
                "例如：0050 股票分割 1：4"
            ),
            key="split_memo",
        )

        confirmed = st.checkbox(
            "我已確認分割比例與預覽數量正確",
            key="split_confirmed",
        )

        submitted = st.button(
            "儲存公司行動",
            use_container_width=True,
            disabled=not confirmed,
            key="save_split_action",
        )

        if submitted:
            if abs(split_ratio - 1.0) < EPSILON:
                st.warning(
                    "分割前後比例相同，"
                    "持有數量不會改變。"
                )
                return

            if abs(quantity_delta) < EPSILON:
                st.warning(
                    "分割後數量與目前數量相同。"
                )
                return

            transaction_id = None

            try:
                ratio_text = (
                    f"{float(old_units):g}:"
                    f"{float(new_units):g}"
                )

                description = (
                    f'{selected_asset["symbol"]} '
                    f"{action_name} "
                    f"{ratio_text}"
                )

                transaction_response = (
                    supabase.table("transactions")
                    .insert(
                        {
                            "transaction_date": (
                                f"{action_date.isoformat()}"
                                "T12:00:00+00:00"
                            ),
                            "transaction_type": (
                                "split"
                            ),
                            "description": (
                                description
                            ),
                            "related_account_id": (
                                selected_account_id
                            ),
                            "related_asset_id": (
                                selected_asset_id
                            ),
                            "trade_currency": (
                                selected_asset[
                                    "currency"
                                ]
                            ),
                        }
                    )
                    .execute()
                )

                transaction_data = (
                    transaction_response.data
                    or []
                )

                if not transaction_data:
                    raise RuntimeError(
                        "公司行動建立後"
                        "未取得交易 ID。"
                    )

                transaction_id = (
                    transaction_data[0]["id"]
                )

                (
                    supabase.table(
                        "transaction_entries"
                    )
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
                            "quantity_delta": (
                                float(
                                    quantity_delta
                                )
                            ),
                            "unit_price": None,
                            "memo": (
                                memo.strip()
                                if memo.strip()
                                else description
                            ),
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    f'{selected_asset["symbol"]} '
                    f"{action_name}已儲存："
                    f"{current_quantity:,.6f} → "
                    f"{new_quantity:,.6f} 單位。"
                )

                st.rerun()

            except Exception as error:
                if transaction_id is not None:
                    try:
                        (
                            supabase.table(
                                "transactions"
                            )
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
                    f"儲存公司行動失敗：{error}"
                )

def show_split_cancellation_manager(
    supabase,
    active_accounts,
    assets,
):
    try:
        transactions_response = (
            supabase.table("transactions")
            .select(
                "id, transaction_date, "
                "transaction_type, description, "
                "external_reference, "
                "fee_amount, tax_amount, "
                "dividend_type, gross_amount, "
                "trade_currency, "
                "related_account_id, "
                "related_asset_id, created_at"
            )
            .execute()
        )

        entries_response = (
            supabase.table(
                "transaction_entries"
            )
            .select(
                "id, transaction_id, "
                "account_id, asset_id, "
                "quantity_delta, unit_price, "
                "memo, created_at"
            )
            .execute()
        )

        transactions = (
            transactions_response.data or []
        )

        entries = (
            entries_response.data or []
        )

    except Exception as error:
        st.error(
            f"讀取分割紀錄失敗：{error}"
        )
        return

    excluded_transaction_ids = (
        get_excluded_transaction_ids(
            transactions
        )
    )

    account_map = {
        account["id"]: account
        for account in active_accounts
    }

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    entries_by_transaction = {}

    for entry in entries:
        transaction_id = entry[
            "transaction_id"
        ]

        entries_by_transaction.setdefault(
            transaction_id,
            [],
        ).append(entry)

    split_records = []

    for transaction in transactions:
        if (
            transaction["transaction_type"]
            != "split"
        ):
            continue

        if (
            transaction["id"]
            in excluded_transaction_ids
        ):
            continue

        matching_entries = (
            entries_by_transaction.get(
                transaction["id"],
                [],
            )
        )

        if len(matching_entries) != 1:
            continue

        entry = matching_entries[0]

        account = account_map.get(
            entry["account_id"]
        )

        asset = asset_map.get(
            entry["asset_id"]
        )

        if account is None or asset is None:
            continue

        if (
            asset["asset_type"]
            not in INVESTMENT_ASSET_TYPES
        ):
            continue

        split_records.append(
            {
                "transaction": transaction,
                "entry": entry,
                "account": account,
                "asset": asset,
            }
        )

    if not split_records:
        return

    portfolio_costs = (
        calculate_portfolio_costs(
            transactions,
            entries,
            asset_map,
        )
    )

    split_records.sort(
        key=lambda record: (
            record["transaction"][
                "transaction_date"
            ],
            record["transaction"][
                "created_at"
            ],
        ),
        reverse=True,
    )

    with st.expander(
        "取消分割或反向分割",
        expanded=False,
    ):
        st.caption(
            "取消後不會刪除原始紀錄，"
            "系統會建立一筆反向紀錄，"
            "並在成本與績效計算中排除兩者。"
        )

        split_transaction_ids = [
            record["transaction"]["id"]
            for record in split_records
        ]

        record_by_id = {
            record["transaction"]["id"]: (
                record
            )
            for record in split_records
        }

        def format_split_record(
            transaction_id,
        ):
            record = record_by_id[
                transaction_id
            ]

            transaction = record[
                "transaction"
            ]

            entry = record["entry"]
            account = record["account"]
            asset = record["asset"]

            transaction_date = str(
                transaction[
                    "transaction_date"
                ]
            )[:10]

            quantity_delta = float(
                entry["quantity_delta"]
            )

            description = (
                transaction.get("description")
                or "公司行動"
            )

            return (
                f"{transaction_date} | "
                f'{account["name"]} | '
                f'{asset["symbol"]} | '
                f"{description} | "
                f"數量變化 "
                f"{quantity_delta:+,.6f}"
            )

        selected_transaction_id = (
            st.selectbox(
                "選擇要取消的公司行動",
                options=split_transaction_ids,
                format_func=(
                    format_split_record
                ),
                key=(
                    "split_cancellation_"
                    "transaction"
                ),
            )
        )

        selected_record = record_by_id[
            selected_transaction_id
        ]

        selected_transaction = (
            selected_record["transaction"]
        )

        selected_entry = (
            selected_record["entry"]
        )

        selected_account = (
            selected_record["account"]
        )

        selected_asset = (
            selected_record["asset"]
        )

        original_quantity_delta = float(
            selected_entry["quantity_delta"]
        )

        reversal_quantity_delta = (
            -original_quantity_delta
        )

        holding_key = (
            selected_entry["account_id"],
            selected_entry["asset_id"],
        )

        cost_state = portfolio_costs.get(
            holding_key,
            {},
        )

        current_quantity = float(
            cost_state.get(
                "quantity",
                0,
            )
            or 0
        )

        quantity_after_cancellation = (
            current_quantity
            + reversal_quantity_delta
        )

        st.markdown("##### 取消預覽")

        preview_col1, preview_col2 = (
            st.columns(2)
        )

        with preview_col1:
            st.metric(
                "目前持有數量",
                f"{current_quantity:,.6f}",
            )

            st.metric(
                "原公司行動數量變化",
                f"{original_quantity_delta:+,.6f}",
            )

        with preview_col2:
            st.metric(
                "取消後持有數量",
                (
                    f"{quantity_after_cancellation:,.6f}"
                ),
                delta=(
                    f"{reversal_quantity_delta:+,.6f}"
                ),
            )

            st.metric(
                "幣別",
                selected_asset["currency"],
            )

        if (
            quantity_after_cancellation
            < -EPSILON
        ):
            st.error(
                "取消後持有數量會小於零。"
                "這通常代表分割後已有賣出或"
                "其他數量異動，請先檢查後續交易。"
            )

        cancellation_reason = st.text_input(
            "取消原因（選填）",
            placeholder=(
                "例如：分割比例輸入錯誤"
            ),
            key=(
                "split_cancellation_reason"
            ),
        )

        confirmed = st.checkbox(
            "我已確認要取消這筆公司行動",
            key=(
                "split_cancellation_confirmed"
            ),
        )

        cancellation_disabled = (
            not confirmed
            or quantity_after_cancellation
            < -EPSILON
        )

        submitted = st.button(
            "取消公司行動",
            use_container_width=True,
            disabled=cancellation_disabled,
            key=(
                "save_split_cancellation"
            ),
        )

        if submitted:
            reversal_transaction_id = None

            try:
                original_description = (
                    selected_transaction.get(
                        "description"
                    )
                    or (
                        f'{selected_asset["symbol"]} '
                        "公司行動"
                    )
                )

                description = (
                    f"取消：{original_description}"
                )

                reversal_response = (
                    supabase.table(
                        "transactions"
                    )
                    .insert(
                        {
                            "transaction_date": (
                                datetime.now(
                                    timezone.utc
                                ).isoformat()
                            ),
                            "transaction_type": (
                                "adjustment"
                            ),
                            "description": (
                                description
                            ),
                            "external_reference": (
                                "reversal:"
                                f"{selected_transaction_id}"
                            ),
                            "related_account_id": (
                                selected_entry[
                                    "account_id"
                                ]
                            ),
                            "related_asset_id": (
                                selected_entry[
                                    "asset_id"
                                ]
                            ),
                            "trade_currency": (
                                selected_asset[
                                    "currency"
                                ]
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
                        "取消紀錄建立後"
                        "未取得交易 ID。"
                    )

                reversal_transaction_id = (
                    reversal_data[0]["id"]
                )

                memo_parts = [
                    description,
                ]

                if cancellation_reason.strip():
                    memo_parts.append(
                        cancellation_reason.strip()
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
                                selected_entry[
                                    "account_id"
                                ]
                            ),
                            "asset_id": (
                                selected_entry[
                                    "asset_id"
                                ]
                            ),
                            "quantity_delta": (
                                reversal_quantity_delta
                            ),
                            "unit_price": None,
                            "memo": "；".join(
                                memo_parts
                            ),
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "transaction_success_message"
                ] = (
                    f'{selected_asset["symbol"]} '
                    "公司行動已取消。"
                )

                st.rerun()

            except Exception as error:
                if (
                    reversal_transaction_id
                    is not None
                ):
                    try:
                        (
                            supabase.table(
                                "transactions"
                            )
                            .delete()
                            .eq(
                                "id",
                                reversal_transaction_id,
                            )
                            .execute()
                        )

                    except Exception:
                        pass

                st.error(
                    f"取消公司行動失敗：{error}"
                )