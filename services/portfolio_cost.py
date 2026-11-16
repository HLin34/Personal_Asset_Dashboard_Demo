from collections import defaultdict

import pandas as pd


INVESTMENT_ASSET_TYPES = {
    "stock",
    "etf",
    "fund",
    "crypto",
}

REVERSAL_PREFIXES = (
    "reversal:",
    "trade_reversal:",
    "trade_edit_reversal:",
    "dividend_reversal:",
    "dividend_edit_reversal:",
)

EPSILON = 0.000000000001


def _number(value):
    return float(value or 0)


def _transaction_sort_key(transaction):
    transaction_date = pd.to_datetime(
        transaction.get("transaction_date"),
        utc=True,
        errors="coerce",
    )

    created_at = pd.to_datetime(
        transaction.get("created_at"),
        utc=True,
        errors="coerce",
    )

    if pd.isna(transaction_date):
        transaction_date = (
            pd.Timestamp.min.tz_localize("UTC")
        )

    if pd.isna(created_at):
        created_at = transaction_date

    return (
        transaction_date,
        created_at,
        transaction.get("id", ""),
    )


def _excluded_transaction_ids(transactions):
    excluded_ids = set()

    for transaction in transactions:
        reference = (
            transaction.get("external_reference")
            or ""
        )

        for prefix in REVERSAL_PREFIXES:
            if reference.startswith(prefix):
                original_id = reference[len(prefix):]

                # 排除撤銷紀錄本身
                excluded_ids.add(
                    transaction["id"]
                )

                # 同時排除被撤銷的原始紀錄
                if original_id:
                    excluded_ids.add(original_id)

                break

    return excluded_ids

def get_excluded_transaction_ids(
    transactions,
):
    return _excluded_transaction_ids(
        transactions
    )

def calculate_portfolio_costs(
    transactions,
    entries,
    asset_map,
):
    """
    使用移動平均成本法計算各帳戶、各資產的成本。

    回傳的 key：
        (account_id, asset_id)

    金額維持資產原始幣別，不在這裡轉換成 TWD。
    """

    excluded_ids = _excluded_transaction_ids(
        transactions
    )

    entries_by_transaction = defaultdict(list)

    for entry in entries:
        entries_by_transaction[
            entry["transaction_id"]
        ].append(entry)

    states = defaultdict(
        lambda: {
            "quantity": 0.0,
            "total_cost": 0.0,
            "cumulative_invested_cost": 0.0,
            "realized_pnl": 0.0,
            "cost_complete": True,
            "cost_note": "",
        }
    )

    active_transactions = [
        transaction
        for transaction in transactions
        if transaction["id"] not in excluded_ids
    ]

    active_transactions.sort(
        key=_transaction_sort_key
    )

    for transaction in active_transactions:
        transaction_type = transaction[
            "transaction_type"
        ]

        transaction_entries = (
            entries_by_transaction.get(
                transaction["id"],
                [],
            )
        )

        investment_entries = []

        for entry in transaction_entries:
            asset = asset_map.get(
                entry["asset_id"]
            )

            if (
                asset is not None
                and asset["asset_type"]
                in INVESTMENT_ASSET_TYPES
            ):
                investment_entries.append(entry)

        for entry in investment_entries:
            cost_key = (
                entry["account_id"],
                entry["asset_id"],
            )

            state = states[cost_key]

            quantity_delta = _number(
                entry["quantity_delta"]
            )

            unit_price = (
                float(entry["unit_price"])
                if entry.get("unit_price")
                is not None
                else None
            )

            fee_amount = _number(
                transaction.get("fee_amount")
            )

            tax_amount = _number(
                transaction.get("tax_amount")
            )

            # 期初持倉
            if (
                transaction_type
                == "opening_balance"
            ):
                state["quantity"] += (
                    quantity_delta
                )

                if unit_price is None:
                    state["cost_complete"] = False
                    state["cost_note"] = (
                        "期初平均成本尚未提供"
                    )

                else:
                    opening_cost = (
                        quantity_delta
                        * unit_price
                    )

                    state["total_cost"] += (
                        opening_cost
                    )

                    state[
                        "cumulative_invested_cost"
                    ] += opening_cost

            # 買入
            elif transaction_type == "buy":
                state["quantity"] += (
                    quantity_delta
                )

                if unit_price is None:
                    state["cost_complete"] = False
                    state["cost_note"] = (
                        "買入價格不完整"
                    )

                else:
                    purchase_cost = (
                        quantity_delta
                        * unit_price
                        + fee_amount
                        + tax_amount
                    )

                    state["total_cost"] += (
                        purchase_cost
                    )

                    state[
                        "cumulative_invested_cost"
                    ] += purchase_cost

            # 賣出
            elif transaction_type == "sell":
                sold_quantity = abs(
                    quantity_delta
                )

                if (
                    sold_quantity
                    > state["quantity"] + EPSILON
                ):
                    state["cost_complete"] = False
                    state["cost_note"] = (
                        "歷史紀錄出現賣出數量"
                        "超過持倉"
                    )

                removable_quantity = min(
                    sold_quantity,
                    max(
                        state["quantity"],
                        0.0,
                    ),
                )

                if state["quantity"] > EPSILON:
                    average_cost = (
                        state["total_cost"]
                        / state["quantity"]
                    )
                else:
                    average_cost = 0.0

                removed_cost = (
                    removable_quantity
                    * average_cost
                )

                if (
                    unit_price is not None
                    and state["cost_complete"]
                ):
                    net_proceeds = (
                        sold_quantity
                        * unit_price
                        - fee_amount
                        - tax_amount
                    )

                    state["realized_pnl"] += (
                        net_proceeds
                        - removed_cost
                    )

                elif unit_price is None:
                    state["cost_complete"] = False
                    state["cost_note"] = (
                        "賣出價格不完整"
                    )

                state["quantity"] += (
                    quantity_delta
                )

                state["total_cost"] -= (
                    removed_cost
                )

            # 股票股利
            elif (
                transaction_type == "dividend"
                and transaction.get(
                    "dividend_type"
                ) == "stock"
            ):
                # 股票股利增加數量，
                # 但不增加原始總成本。
                state["quantity"] += (
                    quantity_delta
                )

            # 手動持倉數量校正
            elif transaction_type == "adjustment":
                previous_quantity = state["quantity"]
                
                previous_average_cost = (
                    state["total_cost"]
                    / previous_quantity
                    if (
                        previous_quantity > EPSILON
                        and state["cost_complete"]
                    )
                else None
                )

                if previous_average_cost is not None:
                    adjustment_cost = (
                        quantity_delta
                        * previous_average_cost
                    )

                    state[
                        "cumulative_invested_cost"
                    ] = max(
                        0.0,
                        state[
                            "cumulative_invested_cost"
                        ]
                        + adjustment_cost,
                    )

                state["quantity"] += quantity_delta

                if state["quantity"] < -EPSILON:
                    state["cost_complete"] = False
                    state["cost_note"] = (
                        "持倉校正後數量小於零，"
                        "請檢查歷史紀錄"
                    )

                elif (
                    previous_average_cost is not None
                    and state["quantity"] > EPSILON
                ):
                    # 手動校正只修正數量，
                    # 不改變原本每單位平均成本。
                    state["total_cost"] = (
                        state["quantity"]
                        * previous_average_cost
                    )

                elif state["quantity"] > EPSILON:
                    state["cost_complete"] = False
                    state["cost_note"] = (
                        "校正前沒有可沿用的平均成本"
                    )

                else:
                    state["quantity"] = 0.0
                    state["total_cost"] = 0.0

            else:
                state["quantity"] += (
                    quantity_delta
                )

            if (
                abs(state["quantity"])
                < EPSILON
            ):
                state["quantity"] = 0.0
                state["total_cost"] = 0.0

            elif state["total_cost"] < 0:
                state["total_cost"] = 0.0

    results = {}

    for cost_key, state in states.items():
        quantity = state["quantity"]

        average_cost = (
            state["total_cost"] / quantity
            if (
                quantity > EPSILON
                and state["cost_complete"]
            )
            else None
        )

        results[cost_key] = {
            **state,
            "average_cost": average_cost,
        }

    return results
