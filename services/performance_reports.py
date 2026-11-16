from services.dividend_statistics import (
    calculate_annual_dividend_summary,
)
from services.investment_performance import (
    calculate_asset_xirr_results,
    calculate_cash_dividend_totals,
)
from services.portfolio_cost import (
    calculate_portfolio_costs,
)


INVESTMENT_ASSET_TYPES = {
    "stock",
    "etf",
    "fund",
}


def _number(value):
    return float(value or 0)


def _record_sort_key(
    record,
    date_field,
):
    return (
        str(record.get(date_field) or ""),
        str(
            record.get("updated_at")
            or record.get("created_at")
            or ""
        ),
    )


def _latest_records(
    records,
    key_field,
    date_field,
):
    sorted_records = sorted(
        records,
        key=lambda record: _record_sort_key(
            record,
            date_field,
        ),
        reverse=True,
    )

    latest_records = {}

    for record in sorted_records:
        record_key = record.get(key_field)

        if (
            record_key is not None
            and record_key not in latest_records
        ):
            latest_records[record_key] = record

    return latest_records


def _translate_xirr_note(note):
    if not note:
        return ""

    replacements = {
        (
            "At least two non-zero "
            "cash flows are required."
        ): (
            "至少需要兩筆非零現金流。"
        ),
        (
            "XIRR requires at least "
            "one negative and one "
            "positive cash flow."
        ): (
            "XIRR 至少需要一筆投入"
            "與一筆回收現金流。"
        ),
        (
            "Unable to find an XIRR "
            "solution for these cash flows."
        ): (
            "目前現金流無法求得"
            "有效的 XIRR。"
        ),
    }

    translated_note = note

    for english_text, chinese_text in (
        replacements.items()
    ):
        translated_note = (
            translated_note.replace(
                english_text,
                chinese_text,
            )
        )

    return translated_note


def build_investment_performance_reports(
    accounts,
    assets,
    transactions,
    entries,
    prices,
    fx_rates,
    valuation_date,
):
    """
    建立投資績效、年度股利及 XIRR 現金流報表。

    所有績效金額保留資產原始幣別；
    另外提供換算 TWD 的欄位。
    """
    account_map = {
        account["id"]: account
        for account in accounts
    }

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    portfolio_costs = calculate_portfolio_costs(
        transactions,
        entries,
        asset_map,
    )

    dividend_totals = (
        calculate_cash_dividend_totals(
            transactions
        )
    )

    annual_dividend_states = (
        calculate_annual_dividend_summary(
            transactions
        )
    )

    latest_prices = _latest_records(
        prices,
        key_field="asset_id",
        date_field="price_date",
    )

    twd_fx_rates = [
        rate_record
        for rate_record in fx_rates
        if rate_record.get("to_currency")
        == "TWD"
    ]

    latest_fx_rates = _latest_records(
        twd_fx_rates,
        key_field="from_currency",
        date_field="rate_date",
    )

    performance_keys = (
        set(portfolio_costs.keys())
        | set(dividend_totals.keys())
    )

    performance_rows = []

    missing_price_assets = set()
    missing_fx_currencies = set()

    for account_id, asset_id in sorted(
        performance_keys,
        key=lambda key: (
            str(key[0]),
            str(key[1]),
        ),
    ):
        account = account_map.get(account_id)
        asset = asset_map.get(asset_id)

        if account is None or asset is None:
            continue

        if (
            asset.get("asset_type")
            not in INVESTMENT_ASSET_TYPES
        ):
            continue

        cost_state = portfolio_costs.get(
            (account_id, asset_id),
            {},
        )

        dividend_state = dividend_totals.get(
            (account_id, asset_id),
            {},
        )

        quantity = _number(
            cost_state.get("quantity")
        )

        remaining_cost = _number(
            cost_state.get("total_cost")
        )

        cumulative_invested_cost = _number(
            cost_state.get(
                "cumulative_invested_cost"
            )
        )

        realized_pnl = _number(
            cost_state.get("realized_pnl")
        )

        cost_complete = cost_state.get(
            "cost_complete",
            True,
        )

        cost_note = cost_state.get(
            "cost_note",
            "",
        )

        gross_dividend = _number(
            dividend_state.get(
                "gross_dividend"
            )
        )

        withholding_tax = _number(
            dividend_state.get(
                "withholding_tax"
            )
        )

        dividend_fee = _number(
            dividend_state.get(
                "dividend_fee"
            )
        )

        net_dividend = _number(
            dividend_state.get(
                "net_dividend"
            )
        )

        dividend_count = int(
            dividend_state.get(
                "dividend_count",
                0,
            )
        )

        has_activity = any(
            abs(value) > 0.000000001
            for value in (
                quantity,
                remaining_cost,
                cumulative_invested_cost,
                realized_pnl,
                gross_dividend,
                withholding_tax,
                dividend_fee,
                net_dividend,
            )
        )

        if not has_activity:
            continue

        price_record = latest_prices.get(
            asset_id
        )

        latest_price = None
        market_value = None
        unrealized_pnl = None

        if abs(quantity) < 0.000000001:
            market_value = 0.0

            if cost_complete:
                unrealized_pnl = (
                    market_value
                    - remaining_cost
                )

        elif price_record is not None:
            latest_price = _number(
                price_record.get("price")
            )

            market_value = (
                quantity
                * latest_price
            )

            if cost_complete:
                unrealized_pnl = (
                    market_value
                    - remaining_cost
                )

        else:
            missing_price_assets.add(
                f'{asset.get("symbol", "")} '
                f'{asset.get("name", "")}'
            )

        price_total_pnl = None
        total_pnl_with_dividend = None

        if unrealized_pnl is not None:
            price_total_pnl = (
                realized_pnl
                + unrealized_pnl
            )

            total_pnl_with_dividend = (
                price_total_pnl
                + net_dividend
            )

        price_return_rate = None
        total_return_rate = None

        if (
            cumulative_invested_cost
            > 0.000000001
            and price_total_pnl is not None
        ):
            price_return_rate = (
                price_total_pnl
                / cumulative_invested_cost
            )

            total_return_rate = (
                total_pnl_with_dividend
                / cumulative_invested_cost
            )

        currency = asset.get(
            "currency",
            "TWD",
        )

        if currency == "TWD":
            fx_rate = 1.0

        else:
            fx_record = latest_fx_rates.get(
                currency
            )

            if fx_record is None:
                fx_rate = None

                missing_fx_currencies.add(
                    currency
                )

            else:
                fx_rate = _number(
                    fx_record.get("rate")
                )

        def to_twd(value):
            if (
                value is None
                or fx_rate is None
            ):
                return None

            return value * fx_rate

        performance_rows.append(
            {
                "account_id": account_id,
                "asset_id": asset_id,
                "帳戶": account.get(
                    "name",
                    "",
                ),
                "金融機構": (
                    account.get("institution")
                    or "未指定機構"
                ),
                "代號": asset.get(
                    "symbol",
                    "",
                ),
                "資產名稱": asset.get(
                    "name",
                    "",
                ),
                "幣別": currency,
                "持有數量": quantity,
                "最新價格": latest_price,
                "目前市值": market_value,
                "剩餘成本": remaining_cost,
                "累計投入成本": (
                    cumulative_invested_cost
                ),
                "已實現損益": realized_pnl,
                "未實現損益": unrealized_pnl,
                "價格總損益": price_total_pnl,
                "價格報酬率": (
                    price_return_rate * 100
                    if price_return_rate
                    is not None
                    else None
                ),
                "現金股利總額": (
                    gross_dividend
                ),
                "股利預扣稅": (
                    withholding_tax
                ),
                "股利費用": dividend_fee,
                "現金股利淨額": (
                    net_dividend
                ),
                "股利筆數": dividend_count,
                "含股利總損益": (
                    total_pnl_with_dividend
                ),
                "含股利報酬率": (
                    total_return_rate * 100
                    if total_return_rate
                    is not None
                    else None
                ),
                "匯率": fx_rate,
                "目前市值 TWD": to_twd(
                    market_value
                ),
                "累計投入成本 TWD": to_twd(
                    cumulative_invested_cost
                ),
                "價格總損益 TWD": to_twd(
                    price_total_pnl
                ),
                "現金股利淨額 TWD": to_twd(
                    net_dividend
                ),
                "含股利總損益 TWD": to_twd(
                    total_pnl_with_dividend
                ),
                "成本狀態": (
                    "完整"
                    if cost_complete
                    else (
                        cost_note
                        or "資料不完整"
                    )
                ),
            }
        )

    current_market_values = {
        (
            row["account_id"],
            row["asset_id"],
        ): row["目前市值"]
        for row in performance_rows
    }

    xirr_results = (
        calculate_asset_xirr_results(
            transactions,
            entries,
            asset_map,
            current_market_values,
            valuation_date,
        )
    )

    xirr_cash_flow_rows = []

    for row in performance_rows:
        report_key = (
            row["account_id"],
            row["asset_id"],
        )

        xirr_result = xirr_results.get(
            report_key,
            {},
        )

        xirr_value = xirr_result.get(
            "xirr"
        )

        xirr_complete = xirr_result.get(
            "xirr_complete",
            False,
        )

        xirr_note = _translate_xirr_note(
            xirr_result.get(
                "xirr_note",
                "",
            )
        )

        row["XIRR 年化報酬率"] = (
            xirr_value * 100
            if xirr_value is not None
            else None
        )

        row["XIRR 狀態"] = (
            "可計算"
            if (
                xirr_complete
                and xirr_value is not None
            )
            else (
                xirr_note
                or "現金流資料不完整"
            )
        )

        cash_flows = xirr_result.get(
            "cash_flows",
            [],
        )

        for cash_flow in cash_flows:
            amount = _number(
                cash_flow.get("amount")
            )

            xirr_cash_flow_rows.append(
                {
                    "帳戶": row["帳戶"],
                    "代號": row["代號"],
                    "資產名稱": (
                        row["資產名稱"]
                    ),
                    "幣別": row["幣別"],
                    "日期": cash_flow.get(
                        "date",
                        "",
                    ),
                    "現金流類型": (
                        cash_flow.get(
                            "flow_type",
                            "",
                        )
                    ),
                    "方向": (
                        "資金投入"
                        if amount < 0
                        else "資金回收"
                    ),
                    "金額": amount,
                    "說明": cash_flow.get(
                        "description",
                        "",
                    ),
                    "交易 ID": (
                        cash_flow.get(
                            "transaction_id"
                        )
                        or ""
                    ),
                }
            )

    annual_dividend_rows = []

    for dividend_state in (
        annual_dividend_states
    ):
        account = account_map.get(
            dividend_state["account_id"],
            {},
        )

        asset = asset_map.get(
            dividend_state["asset_id"],
            {},
        )

        annual_dividend_rows.append(
            {
                "年度": dividend_state[
                    "year"
                ],
                "帳戶": account.get(
                    "name",
                    "未知帳戶",
                ),
                "金融機構": (
                    account.get("institution")
                    or ""
                ),
                "代號": asset.get(
                    "symbol",
                    "",
                ),
                "資產名稱": asset.get(
                    "name",
                    "未知資產",
                ),
                "幣別": dividend_state[
                    "currency"
                ],
                "股利總額": dividend_state[
                    "gross_dividend"
                ],
                "預扣稅": dividend_state[
                    "withholding_tax"
                ],
                "股利費用": dividend_state[
                    "dividend_fee"
                ],
                "淨股利": dividend_state[
                    "net_dividend"
                ],
                "股利筆數": dividend_state[
                    "dividend_count"
                ],
            }
        )

    performance_rows.sort(
        key=lambda row: (
            row["幣別"],
            -(
                row["含股利總損益"]
                if row["含股利總損益"]
                is not None
                else float("-inf")
            ),
        )
    )

    annual_dividend_rows.sort(
        key=lambda row: (
            -row["年度"],
            row["幣別"],
            -row["淨股利"],
        )
    )

    xirr_cash_flow_rows.sort(
        key=lambda row: (
            row["帳戶"],
            row["代號"],
            str(row["日期"]),
        )
    )

    return {
        "performance_rows": (
            performance_rows
        ),
        "annual_dividend_rows": (
            annual_dividend_rows
        ),
        "xirr_cash_flow_rows": (
            xirr_cash_flow_rows
        ),
        "missing_price_assets": sorted(
            missing_price_assets
        ),
        "missing_fx_currencies": sorted(
            missing_fx_currencies
        ),
    }