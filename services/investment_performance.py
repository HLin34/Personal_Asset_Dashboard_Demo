from collections import defaultdict

from services.portfolio_cost import (
    get_excluded_transaction_ids,
)
from services.xirr import (
    XirrCalculationError,
    calculate_xirr,
)

def calculate_cash_dividend_totals(
    transactions,
):
    """
    依帳戶及投資資產彙總有效的現金股利。

    回傳 key：
        (account_id, asset_id)

    金額維持交易原始幣別。
    已取消或被更正的紀錄會被排除。
    """

    excluded_transaction_ids = (
        get_excluded_transaction_ids(
            transactions
        )
    )

    dividend_totals = {}

    for transaction in transactions:
        transaction_id = transaction["id"]

        if (
            transaction_id
            in excluded_transaction_ids
        ):
            continue

        if (
            transaction["transaction_type"]
            != "dividend"
            or transaction.get("dividend_type")
            != "cash"
        ):
            continue

        account_id = transaction.get(
            "related_account_id"
        )

        asset_id = transaction.get(
            "related_asset_id"
        )

        if (
            account_id is None
            or asset_id is None
        ):
            continue

        gross_amount = float(
            transaction.get("gross_amount")
            or 0
        )

        tax_amount = float(
            transaction.get("tax_amount")
            or 0
        )

        fee_amount = float(
            transaction.get("fee_amount")
            or 0
        )

        net_amount = (
            gross_amount
            - tax_amount
            - fee_amount
        )

        dividend_key = (
            account_id,
            asset_id,
        )

        if dividend_key not in dividend_totals:
            dividend_totals[dividend_key] = {
                "gross_dividend": 0.0,
                "withholding_tax": 0.0,
                "dividend_fee": 0.0,
                "net_dividend": 0.0,
                "dividend_count": 0,
            }

        dividend_state = (
            dividend_totals[dividend_key]
        )

        dividend_state["gross_dividend"] += (
            gross_amount
        )

        dividend_state["withholding_tax"] += (
            tax_amount
        )

        dividend_state["dividend_fee"] += (
            fee_amount
        )

        dividend_state["net_dividend"] += (
            net_amount
        )

        dividend_state["dividend_count"] += 1

    return dividend_totals

def calculate_asset_xirr_results(
    transactions,
    entries,
    asset_map,
    current_market_values,
    valuation_date,
):
    """
    依帳戶與資產建立 XIRR 現金流。

    current_market_values 格式：
        {
            (account_id, asset_id): market_value,
        }

    回傳格式：
        {
            (account_id, asset_id): {
                "xirr": 0.10,
                "xirr_complete": True,
                "xirr_note": "",
                "cash_flows": [...],
            }
        }
    """

    investment_asset_types = {
        "stock",
        "etf",
        "fund",
        "crypto",
    }

    excluded_transaction_ids = (
        get_excluded_transaction_ids(
            transactions
        )
    )

    entries_by_transaction = defaultdict(
        list
    )

    for entry in entries:
        entries_by_transaction[
            entry["transaction_id"]
        ].append(entry)

    states = defaultdict(
        lambda: {
            "cash_flows": [],
            "xirr_complete": True,
            "xirr_notes": [],
        }
    )

    def number(value):
        return float(value or 0)

    def transaction_date_text(
        transaction,
    ):
        value = transaction.get(
            "transaction_date"
        )

        if value is None:
            return None

        return str(value)[:10]

    def mark_incomplete(
        state,
        note,
    ):
        state["xirr_complete"] = False

        if note not in state["xirr_notes"]:
            state["xirr_notes"].append(
                note
            )

    def add_cash_flow(
        state,
        flow_date,
        amount,
        flow_type,
        description,
        transaction_id=None,
    ):
        amount = float(amount or 0)

        if abs(amount) < 0.000000000001:
            return

        state["cash_flows"].append(
            {
                "date": flow_date,
                "amount": amount,
                "flow_type": flow_type,
                "description": description,
                "transaction_id": (
                    transaction_id
                ),
            }
        )

    active_transactions = [
        transaction
        for transaction in transactions
        if (
            transaction["id"]
            not in excluded_transaction_ids
        )
    ]

    for transaction in active_transactions:
        transaction_id = transaction["id"]

        transaction_type = transaction[
            "transaction_type"
        ]

        flow_date = transaction_date_text(
            transaction
        )

        if flow_date is None:
            continue

        # 現金股利使用 related_account_id
        # 與 related_asset_id 指向來源投資。
        if (
            transaction_type == "dividend"
            and transaction.get(
                "dividend_type"
            ) == "cash"
        ):
            account_id = transaction.get(
                "related_account_id"
            )

            asset_id = transaction.get(
                "related_asset_id"
            )

            asset = asset_map.get(
                asset_id
            )

            if (
                account_id is None
                or asset is None
                or asset["asset_type"]
                not in investment_asset_types
            ):
                continue

            state = states[
                (
                    account_id,
                    asset_id,
                )
            ]

            gross_amount = number(
                transaction.get(
                    "gross_amount"
                )
            )

            tax_amount = number(
                transaction.get(
                    "tax_amount"
                )
            )

            fee_amount = number(
                transaction.get(
                    "fee_amount"
                )
            )

            net_dividend = (
                gross_amount
                - tax_amount
                - fee_amount
            )

            add_cash_flow(
                state,
                flow_date,
                net_dividend,
                "cash_dividend",
                "現金股利淨額",
                transaction_id,
            )

            continue

        transaction_entries = (
            entries_by_transaction.get(
                transaction_id,
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
                in investment_asset_types
            ):
                investment_entries.append(
                    entry
                )

        if not investment_entries:
            continue

        # 正常買賣設計應只有一筆投資資產 entry。
        # 若未來一筆交易涉及多個投資資產，
        # 手續費與稅費需要另外分攤。
        if (
            transaction_type
            in {
                "opening_balance",
                "buy",
                "sell",
            }
            and len(investment_entries) != 1
        ):
            for entry in investment_entries:
                state = states[
                    (
                        entry["account_id"],
                        entry["asset_id"],
                    )
                ]

                mark_incomplete(
                    state,
                    "單筆交易包含多個投資資產，"
                    "無法正確分攤費用。",
                )

            continue

        for entry in investment_entries:
            account_id = entry[
                "account_id"
            ]

            asset_id = entry[
                "asset_id"
            ]

            state = states[
                (
                    account_id,
                    asset_id,
                )
            ]

            quantity_delta = number(
                entry.get(
                    "quantity_delta"
                )
            )

            unit_price = (
                float(entry["unit_price"])
                if entry.get("unit_price")
                is not None
                else None
            )

            fee_amount = number(
                transaction.get(
                    "fee_amount"
                )
            )

            tax_amount = number(
                transaction.get(
                    "tax_amount"
                )
            )

            if (
                transaction_type
                == "opening_balance"
            ):
                if unit_price is None:
                    mark_incomplete(
                        state,
                        "期初持倉缺少平均成本。",
                    )

                else:
                    opening_cost = (
                        abs(quantity_delta)
                        * unit_price
                    )

                    add_cash_flow(
                        state,
                        flow_date,
                        -opening_cost,
                        "opening_balance",
                        "期初持倉成本",
                        transaction_id,
                    )

            elif transaction_type == "buy":
                if unit_price is None:
                    mark_incomplete(
                        state,
                        "買入交易缺少單位價格。",
                    )

                else:
                    purchase_cost = (
                        abs(quantity_delta)
                        * unit_price
                        + fee_amount
                        + tax_amount
                    )

                    add_cash_flow(
                        state,
                        flow_date,
                        -purchase_cost,
                        "buy",
                        "買入成本",
                        transaction_id,
                    )

            elif transaction_type == "sell":
                if unit_price is None:
                    mark_incomplete(
                        state,
                        "賣出交易缺少單位價格。",
                    )

                else:
                    net_proceeds = (
                        abs(quantity_delta)
                        * unit_price
                        - fee_amount
                        - tax_amount
                    )

                    add_cash_flow(
                        state,
                        flow_date,
                        net_proceeds,
                        "sell",
                        "賣出淨收入",
                        transaction_id,
                    )

            elif (
                transaction_type
                == "adjustment"
            ):
                # 一般 adjustment 可能只是資料校正，
                # 也可能代表未記錄的買賣。
                # 無法確認實際資金日期，因此不猜測。
                mark_incomplete(
                    state,
                    "存在持倉數量校正，"
                    "無法確認實際投入日期。",
                )

            elif (
                transaction_type
                == "dividend"
                and transaction.get(
                    "dividend_type"
                ) == "stock"
            ):
                # 股票股利增加數量，
                # 但本身沒有現金流。
                continue

            elif transaction_type == "split":
                # 分割改變數量與平均成本，
                # 但沒有現金流。
                continue

    # 加入估值日的目前市值。
    for (
        account_id,
        asset_id,
    ), market_value in current_market_values.items():
        state = states[
            (
                account_id,
                asset_id,
            )
        ]

        if market_value is None:
            mark_incomplete(
                state,
                "缺少目前市值。",
            )
            continue

        market_value = float(
            market_value
        )

        if market_value > 0.000000000001:
            add_cash_flow(
                state,
                valuation_date,
                market_value,
                "current_market_value",
                "估值日目前市值",
                None,
            )

    results = {}

    for xirr_key, state in states.items():
        cash_flows = state[
            "cash_flows"
        ]

        xirr_value = None

        if state["xirr_complete"]:
            try:
                calculation_flows = [
                    (
                        flow["date"],
                        flow["amount"],
                    )
                    for flow in cash_flows
                ]

                xirr_value = calculate_xirr(
                    calculation_flows
                )

            except XirrCalculationError as error:
                mark_incomplete(
                    state,
                    str(error),
                )

        results[xirr_key] = {
            "xirr": xirr_value,
            "xirr_complete": state[
                "xirr_complete"
            ],
            "xirr_note": "；".join(
                state["xirr_notes"]
            ),
            "cash_flows": cash_flows,
        }

    return results
