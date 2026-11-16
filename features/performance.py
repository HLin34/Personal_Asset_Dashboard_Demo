import altair as alt
import pandas as pd
import streamlit as st

from services.investment_performance import (
    calculate_asset_xirr_results,
    calculate_cash_dividend_totals,
)
from services.dividend_statistics import (
    calculate_annual_dividend_summary,
)
from services.portfolio_cost import (
    calculate_portfolio_costs,
)
from features.twr_performance import (
    show_twr_performance,
)


INVESTMENT_ASSET_TYPES = {
    "stock",
    "etf",
    "fund",
}


def _number(value):
    return float(value or 0)


def _format_money(value, currency="TWD"):
    if value is None:
        return "—"

    if currency in {"TWD", "JPY"}:
        return f"{value:,.0f} {currency}"

    return f"{value:,.2f} {currency}"


def _format_rate(value):
    if value is None:
        return "—"

    return f"{value:.2%}"


def show_performance_manager(supabase):
    st.subheader("投資績效")

    st.caption(
        "統計股票、ETF 與基金的已實現損益、"
        "未實現損益及現金股利。"
        "跨幣別的 TWD 數字以目前最新匯率換算，"
        "暫不代表實際歷史匯兌損益。"
    )

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
                "id, transaction_id, account_id, "
                "asset_id, quantity_delta, unit_price, "
                "created_at"
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
        st.error(f"讀取投資績效資料失敗：{error}")
        return

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

    annual_dividend_rows = (
        calculate_annual_dividend_summary(
            transactions
        )
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

    performance_keys = (
        set(portfolio_costs.keys())
        | set(dividend_totals.keys())
    )

    performance_rows = []

    missing_price_assets = set()
    missing_fx_currencies = set()

    for account_id, asset_id in performance_keys:
        account = account_map.get(account_id)
        asset = asset_map.get(asset_id)

        if account is None or asset is None:
            continue

        if (
            asset["asset_type"]
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
            dividend_state.get("gross_dividend")
        )

        withholding_tax = _number(
            dividend_state.get("withholding_tax")
        )

        dividend_fee = _number(
            dividend_state.get("dividend_fee")
        )

        net_dividend = _number(
            dividend_state.get("net_dividend")
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

        price_record = latest_prices.get(asset_id)

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
                price_record["price"]
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
                f'{asset["symbol"]} {asset["name"]}'
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

        currency = asset["currency"]

        if currency == "TWD":
            fx_rate = 1.0

        else:
            fx_record = latest_fx_rates.get(
                currency
            )

            if fx_record is None:
                fx_rate = None
                missing_fx_currencies.add(currency)

            else:
                fx_rate = _number(
                    fx_record["rate"]
                )

        def to_twd(value):
            if value is None or fx_rate is None:
                return None

            return value * fx_rate

        institution = (
            account["institution"]
            if account["institution"]
            else "未指定機構"
        )

        performance_rows.append(
            {
                "account_id": account_id,
                "asset_id": asset_id,
                "帳戶": account["name"],
                "金融機構": institution,
                "代號": asset["symbol"],
                "資產名稱": asset["name"],
                "幣別": currency,
                "持有數量": quantity,
                "最新價格": latest_price,
                "剩餘成本": remaining_cost,
                "累計投入成本": (
                    cumulative_invested_cost
                ),
                "目前市值": market_value,
                "已實現損益": realized_pnl,
                "未實現損益": unrealized_pnl,
                "價格總損益": price_total_pnl,
                "價格報酬率": (
                    price_return_rate * 100
                    if price_return_rate is not None
                    else None
                ),
                "現金股利總額": gross_dividend,
                "股利預扣稅": withholding_tax,
                "股利費用": dividend_fee,
                "現金股利淨額": net_dividend,
                "股利筆數": dividend_count,
                "含股利總損益": (
                    total_pnl_with_dividend
                ),
                "含股利報酬率":  (
                    total_return_rate * 100
                    if total_return_rate is not None
                    else None
                ),
                "目前市值_TWD": to_twd(
                    market_value
                ),
                "累計投入成本_TWD": to_twd(
                    cumulative_invested_cost
                ),
                "價格總損益_TWD": to_twd(
                    price_total_pnl
                ),
                "現金股利淨額_TWD": to_twd(
                    net_dividend
                ),
                "含股利總損益_TWD": to_twd(
                    total_pnl_with_dividend
                ),
                "成本狀態": (
                    "完整"
                    if cost_complete
                    else cost_note or "資料不完整"
                ),
            }
        )

    if not performance_rows:
        st.info(
            "目前沒有可計算的投資績效資料。"
        )
        return

    valuation_date = (
        pd.Timestamp.now(
            tz="America/Los_Angeles"
        ).date()
    )

    current_market_values = {
        (
            row["account_id"],
            row["asset_id"],
        ): row["目前市值"]
        for row in performance_rows
    }

    asset_xirr_results = (
        calculate_asset_xirr_results(
            transactions,
            entries,
            asset_map,
            current_market_values,
            valuation_date,
        )
    )

    def translate_xirr_note(note):
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

        for (
            english_text,
            chinese_text,
        ) in replacements.items():
            translated_note = (
                translated_note.replace(
                    english_text,
                    chinese_text,
                )
            )

        return translated_note

    for row in performance_rows:
        xirr_key = (
            row["account_id"],
            row["asset_id"],
        )

        xirr_result = (
            asset_xirr_results.get(
                xirr_key,
                {},
            )
        )

        xirr_value = xirr_result.get(
            "xirr"
        )

        xirr_complete = xirr_result.get(
            "xirr_complete",
            False,
        )

        xirr_note = translate_xirr_note(
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

        row["_xirr_cash_flows"] = (
            xirr_result.get(
                "cash_flows",
                [],
            )
        )

    data_issues = []

    for row in performance_rows:
        asset_label = (
            f'{row["代號"]} | '
            f'{row["資產名稱"]}'
        )

        account_label = row["帳戶"]

        quantity = _number(
            row["持有數量"]
        )

        remaining_cost = _number(
            row["剩餘成本"]
        )

        cumulative_cost = _number(
            row["累計投入成本"]
        )

        latest_price = row["最新價格"]

        # 持倉不應小於零
        if quantity < -0.000000001:
            data_issues.append(
                {
                    "嚴重程度": "錯誤",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": "持有數量小於零",
                    "建議": (
                        "請檢查賣出、取消或"
                        "持倉校正紀錄。"
                    ),
                }
            )

        # 有持倉但沒有價格
        if (
            quantity > 0.000000001
            and latest_price is None
        ):
            data_issues.append(
                {
                    "嚴重程度": "警告",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": "缺少最新價格",
                    "建議": (
                        "請更新市場價格或"
                        "手動輸入價格。"
                    ),
                }
            )

        # 剩餘成本原則上不應高於累計投入
        if (
            remaining_cost
            > cumulative_cost + 0.000001
        ):
            data_issues.append(
                {
                    "嚴重程度": "錯誤",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": (
                        "剩餘成本高於"
                        "累計投入成本"
                    ),
                    "建議": (
                        "請檢查期初持倉及"
                        "持倉校正是否正確計入成本。"
                    ),
                }
            )

        # 有成本但累計投入為零
        if (
            remaining_cost > 0.000001
            and cumulative_cost
            <= 0.000001
        ):
            data_issues.append(
                {
                    "嚴重程度": "錯誤",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": "累計投入成本為零",
                    "建議": (
                        "請檢查期初平均成本"
                        "或買入價格。"
                    ),
                }
            )

        # 已經沒有持倉，但仍留有剩餘成本
        if (
            abs(quantity) <= 0.000000001
            and remaining_cost > 0.000001
        ):
            data_issues.append(
                {
                    "嚴重程度": "錯誤",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": (
                        "持倉為零但仍有剩餘成本"
                    ),
                    "建議": (
                        "請檢查賣出或"
                        "持倉校正紀錄。"
                    ),
                }
            )

        # 成本計算標記為不完整
        if row["成本狀態"] != "完整":
            data_issues.append(
                {
                    "嚴重程度": "警告",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": row["成本狀態"],
                    "建議": (
                        "請補齊期初成本、"
                        "買入價格或交易紀錄。"
                    ),
                }
            )

        # 外幣資產缺少匯率
        if (
            row["幣別"] != "TWD"
            and row["目前市值"] is not None
            and row["目前市值_TWD"] is None
        ):
            data_issues.append(
                {
                    "嚴重程度": "警告",
                    "帳戶": account_label,
                    "資產": asset_label,
                    "問題": (
                        f'缺少 {row["幣別"]}/TWD '
                        "匯率"
                    ),
                    "建議": (
                        "請到匯率頁更新"
                        "最新匯率。"
                    ),
                }
            )

    with st.expander(
        f"績效資料完整性檢查"
        f"（{len(data_issues)} 項）",
        expanded=False,
    ):
        if not data_issues:
            st.success(
                "目前沒有發現明顯的"
                "持倉、成本、價格或匯率異常。"
            )

        else:
            st.warning(
                "以下項目可能影響績效計算，"
                "建議先檢查交易歷史。"
            )

            issue_dataframe = pd.DataFrame(
                data_issues
            )

            severity_order = {
                "錯誤": 0,
                "警告": 1,
            }

            issue_dataframe[
                "_severity_order"
            ] = issue_dataframe[
                "嚴重程度"
            ].map(severity_order)

            issue_dataframe = (
                issue_dataframe.sort_values(
                    by=[
                        "_severity_order",
                        "帳戶",
                        "資產",
                    ]
                )
                .drop(
                    columns=[
                        "_severity_order",
                    ]
                )
            )

            st.dataframe(
                issue_dataframe,
                use_container_width=True,
                hide_index=True,
            )

    available_currencies = sorted(
        {
            row["幣別"]
            for row in performance_rows
        }
    )

    available_account_ids = sorted(
        {
            row["account_id"]
            for row in performance_rows
        }
    )

    available_asset_ids = sorted(
        {
            row["asset_id"]
            for row in performance_rows
        }
    )

    def format_performance_account(account_id):
        account = account_map.get(
            account_id,
            {},
        )

        account_name = account.get(
            "name",
            "未知帳戶",
        )

        institution = (
            account.get("institution")
            or "未指定機構"
        )

        return (
            f"{account_name} | "
            f"{institution}"
        )

    def format_performance_asset(asset_id):
        asset = asset_map.get(
            asset_id,
            {},
        )

        symbol = asset.get(
            "symbol",
            "未知代號",
        )

        asset_name = asset.get(
            "name",
            "未知資產",
        )

        currency = asset.get(
            "currency",
            "",
        )

        return (
            f"{symbol} | "
            f"{asset_name} | "
            f"{currency}"
        )

    with st.expander(
        "篩選績效資料",
        expanded=False,
    ):
        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:
            selected_currencies = st.multiselect(
                "幣別",
                options=available_currencies,
                default=available_currencies,
                key="performance_currency_filter",
            )

        with filter_col2:
            selected_account_ids = st.multiselect(
                "帳戶",
                options=available_account_ids,
                default=available_account_ids,
                format_func=(
                    format_performance_account
                ),
                key="performance_account_filter",
            )

        selected_asset_ids = st.multiselect(
            "資產",
            options=available_asset_ids,
            default=available_asset_ids,
            format_func=format_performance_asset,
            key="performance_asset_filter",
        )

    performance_rows = [
        row
        for row in performance_rows
        if (
            row["幣別"]
            in selected_currencies
            and row["account_id"]
            in selected_account_ids
            and row["asset_id"]
            in selected_asset_ids
        )
    ]

    if not performance_rows:
        st.info(
            "目前的篩選條件沒有符合的績效資料。"
        )
        return

    with st.expander(
        "單項資產績效拆解",
        expanded=False,
    ):
        detail_row_map = {
            (
                row["account_id"],
                row["asset_id"],
            ): row
            for row in performance_rows
        }

        detail_options = list(
            detail_row_map.keys()
        )

        def format_detail_option(detail_key):
            row = detail_row_map[detail_key]

            return (
                f'{row["帳戶"]} | '
                f'{row["代號"]} | '
                f'{row["資產名稱"]} | '
                f'{row["幣別"]}'
            )

        selected_detail_key = st.selectbox(
            "選擇帳戶與資產",
            options=detail_options,
            format_func=format_detail_option,
            key="performance_detail_selection",
        )

        detail_row = detail_row_map[
            selected_detail_key
        ]

        detail_currency = detail_row["幣別"]

        def format_detail_rate(value):
            if value is None:
                return "—"

            return f"{value:.2f}%"

        st.caption(
            "以下金額均以該資產的原始幣別顯示。"
        )

        detail_col1, detail_col2, detail_col3 = (
            st.columns(3)
        )

        with detail_col1:
            st.metric(
                "持有數量",
                f'{detail_row["持有數量"]:,.6f}',
            )

        with detail_col2:
            st.metric(
                "最新價格",
                _format_money(
                    detail_row["最新價格"],
                    detail_currency,
                ),
            )

        with detail_col3:
            st.metric(
                "目前市值",
                _format_money(
                    detail_row["目前市值"],
                    detail_currency,
                ),
            )

        detail_col4, detail_col5, detail_col6 = (
            st.columns(3)
        )

        with detail_col4:
            st.metric(
                "剩餘成本",
                _format_money(
                    detail_row["剩餘成本"],
                    detail_currency,
                ),
            )

        with detail_col5:
            st.metric(
                "累計投入成本",
                _format_money(
                    detail_row[
                        "累計投入成本"
                    ],
                    detail_currency,
                ),
            )

        with detail_col6:
            st.metric(
                "未實現損益",
                _format_money(
                    detail_row[
                        "未實現損益"
                    ],
                    detail_currency,
                ),
            )

        detail_col7, detail_col8, detail_col9 = (
            st.columns(3)
        )

        with detail_col7:
            st.metric(
                "已實現損益",
                _format_money(
                    detail_row[
                        "已實現損益"
                    ],
                    detail_currency,
                ),
            )

        with detail_col8:
            st.metric(
                "價格總損益",
                _format_money(
                    detail_row[
                        "價格總損益"
                    ],
                    detail_currency,
                ),
                delta=format_detail_rate(
                    detail_row[
                        "價格報酬率"
                    ]
                ),
            )

        with detail_col9:
            st.metric(
                "現金股利淨額",
                _format_money(
                    detail_row[
                        "現金股利淨額"
                    ],
                    detail_currency,
                ),
            )

        detail_col10, detail_col11, detail_col12 = st.columns(3)

        with detail_col10:
            st.metric(
                "含股利總損益",
                _format_money(
                    detail_row[
                        "含股利總損益"
                    ],
                    detail_currency,
                ),
            )

        with detail_col11:
            st.metric(
                "含股利報酬率",
                format_detail_rate(
                    detail_row[
                        "含股利報酬率"
                    ]
                ),
            )

        with detail_col12:
            st.metric(
                "XIRR 年化報酬率",
                format_detail_rate(
                    detail_row[
                        "XIRR 年化報酬率"
                    ]
                ),
            )        


        with detail_col11:
            st.metric(
                "含股利報酬率",
                format_detail_rate(
                    detail_row[
                        "含股利報酬率"
                    ]
                ),
            )

        st.markdown("##### 計算過程")

        quantity = detail_row[
            "持有數量"
        ]

        latest_price = detail_row[
            "最新價格"
        ]

        market_value = detail_row[
            "目前市值"
        ]

        remaining_cost = detail_row[
            "剩餘成本"
        ]

        realized_pnl = detail_row[
            "已實現損益"
        ]

        unrealized_pnl = detail_row[
            "未實現損益"
        ]

        price_total_pnl = detail_row[
            "價格總損益"
        ]

        net_dividend = detail_row[
            "現金股利淨額"
        ]

        total_pnl = detail_row[
            "含股利總損益"
        ]

        cumulative_cost = detail_row[
            "累計投入成本"
        ]

        if (
            latest_price is not None
            and market_value is not None
        ):
            st.markdown(
                f"""
**1. 目前市值**

`{quantity:,.6f} × {latest_price:,.4f} = {market_value:,.2f} {detail_currency}`
                """
            )

        else:
            st.markdown(
                """
**1. 目前市值**

尚未取得最新價格，因此無法計算。
                """
            )

        if unrealized_pnl is not None:
            st.markdown(
                f"""
**2. 未實現損益**

`{market_value:,.2f} − {remaining_cost:,.2f} = {unrealized_pnl:,.2f} {detail_currency}`
                """
            )

        else:
            st.markdown(
                """
**2. 未實現損益**

價格或成本資料不完整，暫時無法計算。
                """
            )

        if price_total_pnl is not None:
            st.markdown(
                f"""
**3. 價格總損益**

`{realized_pnl:,.2f} + {unrealized_pnl:,.2f} = {price_total_pnl:,.2f} {detail_currency}`

已實現損益加上未實現損益。
                """
            )

        if total_pnl is not None:
            st.markdown(
                f"""
**4. 含股利總損益**

`{price_total_pnl:,.2f} + {net_dividend:,.2f} = {total_pnl:,.2f} {detail_currency}`
                """
            )

        if (
            total_pnl is not None
            and cumulative_cost
            > 0.000000001
        ):
            calculated_return = (
                total_pnl
                / cumulative_cost
                * 100
            )

            st.markdown(
                f"""
**5. 含股利報酬率**

`{total_pnl:,.2f} ÷ {cumulative_cost:,.2f} = {calculated_return:.2f}%`
                """
            )

        else:
            st.markdown(
                """
**5. 含股利報酬率**

累計投入成本或損益資料不完整，暫時無法計算。
                """
            )

        if detail_row["現金股利總額"] != 0:
            st.markdown("##### 現金股利拆解")

            st.markdown(
                f"""
- 股利總額：{detail_row["現金股利總額"]:,.2f} {detail_currency}
- 預扣稅：{detail_row["股利預扣稅"]:,.2f} {detail_currency}
- 股利費用：{detail_row["股利費用"]:,.2f} {detail_currency}
- 股利淨額：{detail_row["現金股利淨額"]:,.2f} {detail_currency}
                """
            )

        st.markdown(
            "##### XIRR 年化報酬率"
        )

        detail_xirr = detail_row[
            "XIRR 年化報酬率"
        ]

        detail_xirr_status = detail_row[
            "XIRR 狀態"
        ]

        if detail_xirr is not None:
            st.success(
                f"目前 XIRR 年化報酬率："
                f"{detail_xirr:.2f}%"
            )

            st.caption(
                "XIRR 會考慮每筆投入、賣出、"
                "股利及目前市值發生的日期。"
                "持有期間很短時，年化數字可能"
                "顯得非常大或非常小。"
            )

        else:
            st.warning(
                "目前無法準確計算 XIRR："
                f"{detail_xirr_status}"
            )

        xirr_cash_flows = detail_row[
            "_xirr_cash_flows"
        ]

        if xirr_cash_flows:
            flow_type_labels = {
                "opening_balance": (
                    "期初持倉成本"
                ),
                "buy": "買入成本",
                "sell": "賣出淨收入",
                "cash_dividend": (
                    "現金股利淨額"
                ),
                "current_market_value": (
                    "目前市值"
                ),
            }

            xirr_flow_rows = []

            for flow in xirr_cash_flows:
                amount = float(
                    flow["amount"]
                )

                xirr_flow_rows.append(
                    {
                        "日期": flow["date"],
                        "現金流類型": (
                            flow_type_labels.get(
                                flow[
                                    "flow_type"
                                ],
                                flow[
                                    "description"
                                ],
                            )
                        ),
                        "方向": (
                            "資金回收"
                            if amount > 0
                            else "資金投入"
                        ),
                        "金額": amount,
                        "幣別": detail_currency,
                    }
                )

            xirr_flow_dataframe = (
                pd.DataFrame(
                    xirr_flow_rows
                )
            )

            xirr_flow_dataframe[
                "日期"
            ] = pd.to_datetime(
                xirr_flow_dataframe[
                    "日期"
                ]
            ).dt.strftime("%Y-%m-%d")

            st.dataframe(
                xirr_flow_dataframe,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "金額": (
                        st.column_config.NumberColumn(
                            "金額",
                            format="%.2f",
                        )
                    ),
                },
            )

            st.caption(
                "負數代表投入資金；"
                "正數代表賣出收入、"
                "股利或估值日市值。"
            )

    total_market_value_twd = sum(
        row["目前市值_TWD"]
        for row in performance_rows
        if row["目前市值_TWD"] is not None
    )

    total_invested_cost_twd = sum(
        row["累計投入成本_TWD"]
        for row in performance_rows
        if row["累計投入成本_TWD"] is not None
    )

    total_price_pnl_twd = sum(
        row["價格總損益_TWD"]
        for row in performance_rows
        if row["價格總損益_TWD"] is not None
    )

    total_dividend_twd = sum(
        row["現金股利淨額_TWD"]
        for row in performance_rows
        if row["現金股利淨額_TWD"] is not None
    )

    total_pnl_twd = sum(
        row["含股利總損益_TWD"]
        for row in performance_rows
        if row["含股利總損益_TWD"] is not None
    )

    total_price_return_rate = None
    total_return_rate = None

    if total_invested_cost_twd > 0.000000001:
        total_price_return_rate = (
            total_price_pnl_twd
            / total_invested_cost_twd
        )

        total_return_rate = (
            total_pnl_twd
            / total_invested_cost_twd
        )

    metric_col1, metric_col2 = st.columns(2)

    with metric_col1:
        st.metric(
            "目前投資市值",
            _format_money(
                total_market_value_twd
            ),
        )

    with metric_col2:
        st.metric(
            "累計投入成本",
            _format_money(
                total_invested_cost_twd
            ),
        )

    metric_col3, metric_col4 = st.columns(2)

    with metric_col3:
        st.metric(
            "價格總損益",
            _format_money(
                total_price_pnl_twd
            ),
            delta=_format_rate(
                total_price_return_rate
            ),
        )

    with metric_col4:
        st.metric(
            "含股利總損益",
            _format_money(total_pnl_twd),
            delta=_format_rate(
                total_return_rate
            ),
        )

    st.caption(
        f"累計現金股利淨額："
        f"{_format_money(total_dividend_twd)}"
    )

    if missing_price_assets:
        st.warning(
            "以下資產尚未取得價格，因此無法完整計算"
            "未實現損益："
            + "、".join(
                sorted(missing_price_assets)
            )
        )

    if missing_fx_currencies:
        st.warning(
            "以下幣別尚未取得 TWD 匯率，因此未納入"
            "上方 TWD 合計："
            + "、".join(
                sorted(missing_fx_currencies)
            )
        )

    st.divider()
    st.subheader("依幣別績效摘要")

    st.caption(
        "各幣別分開計算，金額維持原始幣別。"
        "股利欄位為扣除預扣稅及費用後的現金股利淨額。"
    )

    currency_summary = {}

    for row in performance_rows:
        currency = row["幣別"]

        if currency not in currency_summary:
            currency_summary[currency] = {
                "幣別": currency,
                "投資項目數": 0,
                "目前市值": 0.0,
                "累計投入成本": 0.0,
                "價格總損益": 0.0,
                "現金股利淨額": 0.0,
                "含股利總損益": 0.0,
                "資料完整": True,
            }

        summary = currency_summary[currency]

        summary["投資項目數"] += 1

        invested_cost = row[
            "累計投入成本"
        ]

        if invested_cost is not None:
            summary["累計投入成本"] += (
                invested_cost
            )

        net_dividend = row[
            "現金股利淨額"
        ]

        if net_dividend is not None:
            summary["現金股利淨額"] += (
                net_dividend
            )

        market_value = row["目前市值"]
        price_pnl = row["價格總損益"]
        total_pnl = row["含股利總損益"]

        if market_value is None:
            summary["資料完整"] = False
        else:
            summary["目前市值"] += (
                market_value
            )

        if price_pnl is None:
            summary["資料完整"] = False
        else:
            summary["價格總損益"] += (
                price_pnl
            )

        if total_pnl is None:
            summary["資料完整"] = False
        else:
            summary["含股利總損益"] += (
                total_pnl
            )

    currency_summary_rows = []

    currency_order = {
        "TWD": 0,
        "USD": 1,
        "JPY": 2,
    }

    sorted_currencies = sorted(
        currency_summary.keys(),
        key=lambda currency: (
            currency_order.get(currency, 99),
            currency,
        ),
    )

    for currency in sorted_currencies:
        summary = currency_summary[currency]

        invested_cost = summary[
            "累計投入成本"
        ]

        if (
            summary["資料完整"]
            and invested_cost > 0.000000001
        ):
            total_return_rate = (
                summary["含股利總損益"]
                / invested_cost
                * 100
            )

        else:
            total_return_rate = None

        currency_summary_rows.append(
            {
                "幣別": currency,
                "投資項目數": summary[
                    "投資項目數"
                ],
                "目前市值": summary[
                    "目前市值"
                ],
                "累計投入成本": summary[
                    "累計投入成本"
                ],
                "價格總損益": summary[
                    "價格總損益"
                ],
                "現金股利淨額": summary[
                    "現金股利淨額"
                ],
                "含股利總損益": summary[
                    "含股利總損益"
                ],
                "含股利報酬率": (
                    total_return_rate
                ),
                "資料狀態": (
                    "完整"
                    if summary["資料完整"]
                    else "缺少價格資料"
                ),
            }
        )

    currency_summary_dataframe = pd.DataFrame(
        currency_summary_rows
    )

    st.dataframe(
        currency_summary_dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "投資項目數": (
                st.column_config.NumberColumn(
                    "投資項目數",
                    format="%d",
                )
            ),
            "目前市值": (
                st.column_config.NumberColumn(
                    "目前市值",
                    format="%.2f",
                )
            ),
            "累計投入成本": (
                st.column_config.NumberColumn(
                    "累計投入成本",
                    format="%.2f",
                )
            ),
            "價格總損益": (
                st.column_config.NumberColumn(
                    "價格總損益",
                    format="%.2f",
                )
            ),
            "現金股利淨額": (
                st.column_config.NumberColumn(
                    "現金股利淨額",
                    format="%.2f",
                )
            ),
            "含股利總損益": (
                st.column_config.NumberColumn(
                    "含股利總損益",
                    format="%.2f",
                )
            ),
            "含股利報酬率": (
                st.column_config.NumberColumn(
                    "含股利報酬率",
                    format="%.2f%%",
                )
            ),
        },
    )

    st.divider()

    with st.expander(
        "各資產含股利報酬率比較",
        expanded=False,
    ):
        st.caption(
            "相同資產若分散在多個帳戶，"
            "會合併投入成本與損益後計算。"
            "此處為累計報酬率，尚未依持有時間年化。"
        )

        asset_chart_summary = {}

        for row in performance_rows:
            asset_id = row["asset_id"]

            if asset_id not in asset_chart_summary:
                asset_chart_summary[asset_id] = {
                    "asset_id": asset_id,
                    "代號": row["代號"],
                    "資產名稱": row["資產名稱"],
                    "幣別": row["幣別"],
                    "累計投入成本": 0.0,
                    "含股利總損益": 0.0,
                    "資料完整": True,
                }

            asset_summary = (
                asset_chart_summary[asset_id]
            )

            invested_cost = row[
                "累計投入成本"
            ]

            total_pnl = row[
                "含股利總損益"
            ]

            if invested_cost is not None:
                asset_summary[
                    "累計投入成本"
                ] += invested_cost

            if total_pnl is None:
                asset_summary[
                    "資料完整"
                ] = False

            else:
                asset_summary[
                    "含股利總損益"
                ] += total_pnl

        asset_chart_rows = []

        for asset_summary in (
            asset_chart_summary.values()
        ):
            invested_cost = asset_summary[
                "累計投入成本"
            ]

            if (
                not asset_summary["資料完整"]
                or invested_cost
                <= 0.000000001
            ):
                continue

            return_rate = (
                asset_summary[
                    "含股利總損益"
                ]
                / invested_cost
                * 100
            )

            asset_chart_rows.append(
                {
                    "資產": (
                        f'{asset_summary["代號"]} | '
                        f'{asset_summary["資產名稱"]}'
                    ),
                    "幣別": asset_summary[
                        "幣別"
                    ],
                    "累計投入成本": (
                        invested_cost
                    ),
                    "含股利總損益": (
                        asset_summary[
                            "含股利總損益"
                        ]
                    ),
                    "含股利報酬率": (
                        return_rate
                    ),
                }
            )

        if not asset_chart_rows:
            st.info(
                "目前沒有成本與價格皆完整的"
                "資產可供比較。"
            )

        else:
            asset_chart_dataframe = (
                pd.DataFrame(
                    asset_chart_rows
                )
            )

            asset_chart_dataframe = (
                asset_chart_dataframe.sort_values(
                    by="含股利報酬率",
                    ascending=False,
                )
            )

            return_chart = (
                alt.Chart(
                    asset_chart_dataframe
                )
                .mark_bar(
                    cornerRadiusEnd=4,
                )
                .encode(
                    x=alt.X(
                        "含股利報酬率:Q",
                        title="含股利報酬率 (%)",
                        axis=alt.Axis(
                            format=".2f",
                        ),
                    ),
                    y=alt.Y(
                        "資產:N",
                        title=None,
                        sort="-x",
                    ),
                    color=alt.condition(
                        (
                            alt.datum[
                                "含股利報酬率"
                            ]
                            >= 0
                        ),
                        alt.value("#2E8B57"),
                        alt.value("#D9534F"),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "資產:N",
                            title="資產",
                        ),
                        alt.Tooltip(
                            "幣別:N",
                            title="幣別",
                        ),
                        alt.Tooltip(
                            "累計投入成本:Q",
                            title="累計投入成本",
                            format=",.2f",
                        ),
                        alt.Tooltip(
                            "含股利總損益:Q",
                            title="含股利總損益",
                            format=",.2f",
                        ),
                        alt.Tooltip(
                            "含股利報酬率:Q",
                            title="含股利報酬率",
                            format=".2f",
                        ),
                    ],
                )
                .properties(
                    height=max(
                        250,
                        len(
                            asset_chart_dataframe
                        )
                        * 38,
                    )
                )
            )

            zero_line = (
                alt.Chart(
                    pd.DataFrame(
                        {
                            "零": [0],
                        }
                    )
                )
                .mark_rule(
                    color="#888888",
                    strokeDash=[4, 4],
                )
                .encode(
                    x="零:Q",
                )
            )

            st.altair_chart(
                return_chart + zero_line,
                use_container_width=True,
            )

    st.divider()
    st.subheader("年度股利統計")

    st.caption(
        "依股利發放年度、資產及原始幣別統計。"
        "不同幣別不直接相加，以避免混淆匯率影響。"
    )

    if not annual_dividend_rows:
        st.info("目前沒有可統計的現金股利紀錄。")

    else:
        dividend_years = sorted(
            {
                row["year"]
                for row in annual_dividend_rows
            },
            reverse=True,
        )

        dividend_currencies = sorted(
            {
                row["currency"]
                for row in annual_dividend_rows
            }
        )

        filter_col1, filter_col2 = st.columns(2)

        with filter_col1:
            selected_dividend_year = st.selectbox(
                "股利年度",
                options=dividend_years,
                key="performance_dividend_year",
            )

        with filter_col2:
            selected_dividend_currency = st.selectbox(
                "股利幣別",
                options=[
                    "全部",
                    *dividend_currencies,
                ],
                key="performance_dividend_currency",
            )

        filtered_dividend_rows = [
            row
            for row in annual_dividend_rows
            if (
                row["year"]
                == selected_dividend_year
                and (
                    selected_dividend_currency
                    == "全部"
                    or row["currency"]
                    == selected_dividend_currency
                )
            )
        ]

        dividend_currency_summary = {}

        for row in filtered_dividend_rows:
            currency = row["currency"]

            if currency not in dividend_currency_summary:
                dividend_currency_summary[currency] = {
                    "gross_dividend": 0.0,
                    "withholding_tax": 0.0,
                    "dividend_fee": 0.0,
                    "net_dividend": 0.0,
                    "dividend_count": 0,
                }

            currency_summary = (
                dividend_currency_summary[currency]
            )

            currency_summary["gross_dividend"] += (
                row["gross_dividend"]
            )

            currency_summary["withholding_tax"] += (
                row["withholding_tax"]
            )

            currency_summary["dividend_fee"] += (
                row["dividend_fee"]
            )

            currency_summary["net_dividend"] += (
                row["net_dividend"]
            )

            currency_summary["dividend_count"] += (
                row["dividend_count"]
            )

        for currency in sorted(
            dividend_currency_summary
        ):
            currency_summary = (
                dividend_currency_summary[currency]
            )

            st.markdown(
                f"#### {selected_dividend_year} 年 "
                f"{currency} 現金股利"
            )

            (
                dividend_col1,
                dividend_col2,
                dividend_col3,
                dividend_col4,
            ) = st.columns(4)

            with dividend_col1:
                st.metric(
                    "股利總額",
                    _format_money(
                        currency_summary[
                            "gross_dividend"
                        ],
                        currency,
                    ),
                )

            with dividend_col2:
                st.metric(
                    "預扣稅",
                    _format_money(
                        currency_summary[
                            "withholding_tax"
                        ],
                        currency,
                    ),
                )

            with dividend_col3:
                st.metric(
                    "股利費用",
                    _format_money(
                        currency_summary[
                            "dividend_fee"
                        ],
                        currency,
                    ),
                )

            with dividend_col4:
                st.metric(
                    "淨股利",
                    _format_money(
                        currency_summary[
                            "net_dividend"
                        ],
                        currency,
                    ),
                    help=(
                        "股利總額減去預扣稅及"
                        "股利相關費用。"
                    ),
                )

            st.caption(
                "股利紀錄筆數："
                f'{currency_summary["dividend_count"]}'
            )

        st.markdown("#### 年度淨股利趨勢")

        st.caption(
            "趨勢圖會顯示所有年度資料；"
            "不同幣別分開繪製，不直接加總。"
        )

        if selected_dividend_currency == "全部":
            trend_currencies = dividend_currencies
        else:
            trend_currencies = [
                selected_dividend_currency
            ]

        for trend_currency in trend_currencies:
            trend_summary = {}

            for row in annual_dividend_rows:
                if row["currency"] != trend_currency:
                    continue

                year = row["year"]

                if year not in trend_summary:
                    trend_summary[year] = {
                        "年度": year,
                        "幣別": trend_currency,
                        "股利總額": 0.0,
                        "預扣稅": 0.0,
                        "股利費用": 0.0,
                        "淨股利": 0.0,
                        "股利筆數": 0,
                    }

                year_summary = trend_summary[year]

                year_summary["股利總額"] += (
                    row["gross_dividend"]
                )

                year_summary["預扣稅"] += (
                    row["withholding_tax"]
                )

                year_summary["股利費用"] += (
                    row["dividend_fee"]
                )

                year_summary["淨股利"] += (
                    row["net_dividend"]
                )

                year_summary["股利筆數"] += (
                    row["dividend_count"]
                )

            trend_rows = [
                trend_summary[year]
                for year in sorted(trend_summary)
            ]

            if not trend_rows:
                continue

            trend_dataframe = pd.DataFrame(
                trend_rows
            )

            st.markdown(
                f"**{trend_currency}**"
            )

            trend_base = (
                alt.Chart(trend_dataframe)
                .encode(
                    x=alt.X(
                        "年度:O",
                        title="年度",
                        sort="ascending",
                        axis=alt.Axis(
                            labelAngle=0,
                        ),
                    ),
                    y=alt.Y(
                        "淨股利:Q",
                        title=(
                            "淨股利 "
                            f"({trend_currency})"
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "年度:O",
                            title="年度",
                        ),
                        alt.Tooltip(
                            "幣別:N",
                            title="幣別",
                        ),
                        alt.Tooltip(
                            "股利總額:Q",
                            title="股利總額",
                            format=",.2f",
                        ),
                        alt.Tooltip(
                            "預扣稅:Q",
                            title="預扣稅",
                            format=",.2f",
                        ),
                        alt.Tooltip(
                            "股利費用:Q",
                            title="股利費用",
                            format=",.2f",
                        ),
                        alt.Tooltip(
                            "淨股利:Q",
                            title="淨股利",
                            format=",.2f",
                        ),
                        alt.Tooltip(
                            "股利筆數:Q",
                            title="股利筆數",
                            format=".0f",
                        ),
                    ],
                )
            )

            trend_bar = trend_base.mark_bar(
                color="#4C78A8",
                opacity=0.75,
            )

            trend_line = trend_base.mark_line(
                color="#F2C14E",
                point=alt.OverlayMarkDef(
                    filled=True,
                    size=80,
                ),
                strokeWidth=3,
            )

            zero_line = (
                alt.Chart(
                    pd.DataFrame(
                        {
                            "零": [0],
                        }
                    )
                )
                .mark_rule(
                    color="#888888",
                    strokeDash=[4, 4],
                )
                .encode(
                    y="零:Q",
                )
            )

            dividend_trend_chart = (
                trend_bar
                + trend_line
                + zero_line
            ).properties(
                height=280,
            )

            st.altair_chart(
                dividend_trend_chart,
                use_container_width=True,
            )
        
        dividend_detail_rows = []

        for row in filtered_dividend_rows:
            account = account_map.get(
                row["account_id"],
                {},
            )

            asset = asset_map.get(
                row["asset_id"],
                {},
            )

            dividend_detail_rows.append(
                {
                    "年度": row["year"],
                    "帳戶": account.get(
                        "name",
                        "未知帳戶",
                    ),
                    "代號": asset.get(
                        "symbol",
                        "",
                    ),
                    "資產名稱": asset.get(
                        "name",
                        "未知資產",
                    ),
                    "幣別": row["currency"],
                    "股利總額": row[
                        "gross_dividend"
                    ],
                    "預扣稅": row[
                        "withholding_tax"
                    ],
                    "股利費用": row[
                        "dividend_fee"
                    ],
                    "淨股利": row[
                        "net_dividend"
                    ],
                    "股利筆數": row[
                        "dividend_count"
                    ],
                }
            )

        dividend_dataframe = pd.DataFrame(
            dividend_detail_rows
        )

        dividend_dataframe = (
            dividend_dataframe.sort_values(
                by=[
                    "幣別",
                    "淨股利",
                    "資產名稱",
                ],
                ascending=[
                    True,
                    False,
                    True,
                ],
            )
        )

        st.dataframe(
            dividend_dataframe,
            use_container_width=True,
            hide_index=True,
            column_config={
                "年度": st.column_config.NumberColumn(
                    "年度",
                    format="%d",
                ),
                "股利總額": (
                    st.column_config.NumberColumn(
                        "股利總額",
                        format="%.2f",
                    )
                ),
                "預扣稅": (
                    st.column_config.NumberColumn(
                        "預扣稅",
                        format="%.2f",
                    )
                ),
                "股利費用": (
                    st.column_config.NumberColumn(
                        "股利費用",
                        format="%.2f",
                    )
                ),
                "淨股利": (
                    st.column_config.NumberColumn(
                        "淨股利",
                        format="%.2f",
                    )
                ),
                "股利筆數": (
                    st.column_config.NumberColumn(
                        "股利筆數",
                        format="%d",
                    )
                ),
            },
        )

    st.divider()
    st.subheader("各項投資績效")
    

    display_columns = [
        "帳戶",
        "代號",
        "資產名稱",
        "幣別",
        "持有數量",
        "最新價格",
        "目前市值",
        "剩餘成本",
        "累計投入成本",
        "已實現損益",
        "未實現損益",
        "價格總損益",
        "價格報酬率",
        "現金股利總額",
        "股利預扣稅",
        "股利費用",
        "現金股利淨額",
        "含股利總損益",
        "含股利報酬率",
        "XIRR 年化報酬率",
        "XIRR 狀態",
        "成本狀態",
    ]

    performance_dataframe = pd.DataFrame(
        performance_rows
    )[display_columns]

    performance_dataframe = (
        performance_dataframe.sort_values(
            by=[
                "幣別",
                "含股利總損益",
            ],
            ascending=[
                True,
                False,
            ],
            na_position="last",
        )
    )

    st.dataframe(
        performance_dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "持有數量": st.column_config.NumberColumn(
                "持有數量",
                format="%.6f",
            ),
            "最新價格": st.column_config.NumberColumn(
                "最新價格",
                format="%.4f",
            ),
            "目前市值": st.column_config.NumberColumn(
                "目前市值",
                format="%.2f",
            ),
            "剩餘成本": st.column_config.NumberColumn(
                "剩餘成本",
                format="%.2f",
            ),
            "累計投入成本": (
                st.column_config.NumberColumn(
                    "累計投入成本",
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
            "價格總損益": (
                st.column_config.NumberColumn(
                    "價格總損益",
                    format="%.2f",
                )
            ),
            "價格報酬率": (
                st.column_config.NumberColumn(
                    "價格報酬率",
                    format="%.2f%%",
                )
            ),
            "現金股利總額": (
                st.column_config.NumberColumn(
                    "現金股利總額",
                    format="%.2f",
                )
            ),
            "股利預扣稅": (
                st.column_config.NumberColumn(
                    "股利預扣稅",
                    format="%.2f",
                )
            ),
            "股利費用": (
                st.column_config.NumberColumn(
                    "股利費用",
                    format="%.2f",
                )
            ),
            "現金股利淨額": (
                st.column_config.NumberColumn(
                    "現金股利淨額",
                    format="%.2f",
                )
            ),
            "含股利總損益": (
                st.column_config.NumberColumn(
                    "含股利總損益",
                    format="%.2f",
                )
            ),
            "含股利報酬率": (
                st.column_config.NumberColumn(
                    "含股利報酬率",
                    format="%.2f%%",
                )
            ),
            "XIRR 年化報酬率": (
                st.column_config.NumberColumn(
                    "XIRR 年化報酬率",
                    format="%.2f%%",
                )
            ),
        },
    )

    with st.expander("計算方式說明"):
        st.markdown(
            """
- **剩餘成本**：目前仍持有部位的成本。
- **累計投入成本**：期初成本加上歷次買入成本，不因賣出而減少。
- **已實現損益**：賣出收入扣除售出部位成本、手續費及稅費。
- **未實現損益**：目前市值減去剩餘成本。
- **價格總損益**：已實現損益加未實現損益。
- **含股利總損益**：價格總損益加現金股利淨額。
- **現金股利淨額**：股利總額減預扣稅及股利費用。
- **價格報酬率與含股利報酬率**：以累計投入成本為分母，屬於簡易累計報酬率，不是 TWR 或 XIRR。
- **XIRR 年化報酬率**：考慮每筆資金投入與回收的實際日期後計算的年化報酬率；持有期間很短時，年化數字可能非常大或非常小。
- XIRR 以資產的原始幣別計算，目前不包含換算為 TWD 後的匯率損益。
- 含有一般持倉校正的資產，由於無法確認實際資金投入日期，暫不顯示 XIRR。
            """
        )

        st.markdown(
            """
- **價格總損益**：已實現損益加未實現損益。
...
            """
        )

    st.divider()

    show_twr_performance(
        supabase
    )