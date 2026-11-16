import altair as alt
import pandas as pd
import plotly.express as px
import streamlit as st

from config import ASSET_TYPE_LABELS
from services.market_data import (
    refresh_all_market_data,
)
from services.portfolio_cost import (
    calculate_portfolio_costs,
)
from services.portfolio_snapshots import (
    load_portfolio_snapshots,
    save_account_snapshot_rows,
    save_daily_snapshot,
)
from features.institution_overview import (
    show_institution_overview,
)

def show_recent_market_change(supabase):
    st.subheader("最近市場變動")
    st.caption(
        "依目前持倉數量，比較每項資產最新兩個價格日期，"
        "並分開顯示價格與匯率造成的變動。"
    )

    try:
        assets_response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, currency"
            )
            .execute()
        )

        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "asset_id, quantity_delta"
            )
            .execute()
        )

        prices_response = (
            supabase.table("asset_prices")
            .select(
                "asset_id, price, price_date, source"
            )
            .order("price_date", desc=True)
            .execute()
        )

        fx_response = (
            supabase.table("fx_rates")
            .select(
                "from_currency, to_currency, "
                "rate, rate_date, source"
            )
            .eq("to_currency", "TWD")
            .order("rate_date", desc=True)
            .execute()
        )

        assets = assets_response.data or []
        entries = entries_response.data or []
        prices = prices_response.data or []
        fx_rates = fx_response.data or []

    except Exception as error:
        st.error(
            f"讀取市場變動資料失敗：{error}"
        )
        return

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    quantities = {}

    for entry in entries:
        asset_id = entry["asset_id"]

        quantities[asset_id] = (
            quantities.get(asset_id, 0.0)
            + float(entry["quantity_delta"])
        )

    price_histories = {}

    for price_record in prices:
        asset_id = price_record["asset_id"]

        price_histories.setdefault(
            asset_id,
            [],
        ).append(price_record)

    for asset_id in price_histories:
        price_histories[asset_id] = sorted(
            price_histories[asset_id],
            key=lambda record: record["price_date"],
            reverse=True,
        )

    fx_histories = {}

    for fx_record in fx_rates:
        currency = fx_record["from_currency"]

        fx_histories.setdefault(
            currency,
            [],
        ).append(fx_record)

    for currency in fx_histories:
        fx_histories[currency] = sorted(
            fx_histories[currency],
            key=lambda record: record["rate_date"],
            reverse=True,
        )

    def find_fx_rate(currency, target_date):
        if currency == "TWD":
            return {
                "rate": 1.0,
                "rate_date": target_date,
            }

        currency_rates = fx_histories.get(
            currency,
            [],
        )

        for rate_record in currency_rates:
            if rate_record["rate_date"] <= target_date:
                return rate_record

        return None

    change_rows = []
    unavailable_assets = []

    total_price_effect_twd = 0.0
    total_fx_effect_twd = 0.0
    total_market_change_twd = 0.0

    for asset_id, quantity in quantities.items():
        if abs(quantity) < 0.000000000001:
            continue

        asset = asset_map.get(asset_id)

        if asset is None:
            continue

        currency = asset["currency"]

        if asset["asset_type"] == "cash":
            if currency == "TWD":
                continue

            currency_rates = fx_histories.get(
                currency,
                [],
            )

            if len(currency_rates) < 2:
                unavailable_assets.append(
                    f'{asset["symbol"]}：匯率紀錄不足'
                )
                continue

            latest_fx = currency_rates[0]
            previous_fx = currency_rates[1]

            latest_fx_rate = float(
                latest_fx["rate"]
            )

            previous_fx_rate = float(
                previous_fx["rate"]
            )

            price_effect_twd = 0.0

            fx_effect_twd = (
                quantity
                * (
                    latest_fx_rate
                    - previous_fx_rate
                )
            )

            total_change_twd = fx_effect_twd

            change_rows.append(
                {
                    "資產代號": asset["symbol"],
                    "資產名稱": asset["name"],
                    "資產類型": "現金",
                    "比較期間": (
                        f'{previous_fx["rate_date"]}'
                        " → "
                        f'{latest_fx["rate_date"]}'
                    ),
                    "目前數量": quantity,
                    "前次價格": None,
                    "最新價格": None,
                    "價格變動率": None,
                    "價格影響 TWD": price_effect_twd,
                    "匯率影響 TWD": fx_effect_twd,
                    "合計變動 TWD": total_change_twd,
                }
            )

            total_fx_effect_twd += fx_effect_twd
            total_market_change_twd += (
                total_change_twd
            )

            continue

        asset_prices = price_histories.get(
            asset_id,
            [],
        )

        if len(asset_prices) < 2:
            unavailable_assets.append(
                f'{asset["symbol"]}：價格紀錄不足'
            )
            continue

        latest_price_record = asset_prices[0]
        previous_price_record = asset_prices[1]

        latest_price = float(
            latest_price_record["price"]
        )

        previous_price = float(
            previous_price_record["price"]
        )

        latest_price_date = (
            latest_price_record["price_date"]
        )

        previous_price_date = (
            previous_price_record["price_date"]
        )

        latest_fx_record = find_fx_rate(
            currency,
            latest_price_date,
        )

        previous_fx_record = find_fx_rate(
            currency,
            previous_price_date,
        )

        if (
            latest_fx_record is None
            or previous_fx_record is None
        ):
            unavailable_assets.append(
                f'{asset["symbol"]}：歷史匯率不足'
            )
            continue

        latest_fx_rate = float(
            latest_fx_record["rate"]
        )

        previous_fx_rate = float(
            previous_fx_record["rate"]
        )

        price_effect_twd = (
            quantity
            * (latest_price - previous_price)
            * latest_fx_rate
        )

        fx_effect_twd = (
            quantity
            * previous_price
            * (
                latest_fx_rate
                - previous_fx_rate
            )
        )

        total_change_twd = (
            price_effect_twd
            + fx_effect_twd
        )

        price_change_percentage = (
            (
                latest_price
                / previous_price
                - 1
            )
            * 100
            if previous_price != 0
            else None
        )

        change_rows.append(
            {
                "資產代號": asset["symbol"],
                "資產名稱": asset["name"],
                "資產類型": ASSET_TYPE_LABELS.get(
                    asset["asset_type"],
                    asset["asset_type"],
                ),
                "比較期間": (
                    f"{previous_price_date}"
                    " → "
                    f"{latest_price_date}"
                ),
                "目前數量": quantity,
                "前次價格": previous_price,
                "最新價格": latest_price,
                "價格變動率": (
                    price_change_percentage
                ),
                "價格影響 TWD": price_effect_twd,
                "匯率影響 TWD": fx_effect_twd,
                "合計變動 TWD": total_change_twd,
            }
        )

        total_price_effect_twd += (
            price_effect_twd
        )

        total_fx_effect_twd += fx_effect_twd

        total_market_change_twd += (
            total_change_twd
        )

    if not change_rows:
        st.info(
            "目前還沒有足夠的兩期價格或匯率資料，"
            "至少需要兩個不同日期的紀錄。"
        )

        if unavailable_assets:
            st.caption(
                "尚無法計算："
                + "、".join(unavailable_assets)
            )

        return

    metric1, metric2, metric3 = st.columns(3)

    with metric1:
        st.metric(
            "最近市場變動",
            f"TWD {total_market_change_twd:,.2f}",
        )

    with metric2:
        st.metric(
            "價格影響",
            f"TWD {total_price_effect_twd:,.2f}",
        )

    with metric3:
        st.metric(
            "匯率影響",
            f"TWD {total_fx_effect_twd:,.2f}",
        )

    change_dataframe = pd.DataFrame(
        change_rows
    )

    change_dataframe = (
        change_dataframe.sort_values(
            by="合計變動 TWD",
            ascending=False,
        )
    )

    st.dataframe(
        change_dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "目前數量":
                st.column_config.NumberColumn(
                    "目前數量",
                    format="%.8f",
                ),
            "前次價格":
                st.column_config.NumberColumn(
                    "前次價格",
                    format="%.6f",
                ),
            "最新價格":
                st.column_config.NumberColumn(
                    "最新價格",
                    format="%.6f",
                ),
            "價格變動率":
                st.column_config.NumberColumn(
                    "價格變動率",
                    format="%.2f%%",
                ),
            "價格影響 TWD":
                st.column_config.NumberColumn(
                    "價格影響 TWD",
                    format="%.2f",
                ),
            "匯率影響 TWD":
                st.column_config.NumberColumn(
                    "匯率影響 TWD",
                    format="%.2f",
                ),
            "合計變動 TWD":
                st.column_config.NumberColumn(
                    "合計變動 TWD",
                    format="%.2f",
                ),
        },
    )

    if unavailable_assets:
        st.warning(
            "下列項目因歷史資料不足，"
            "尚未納入市場變動："
            + "、".join(unavailable_assets)
        )

    st.caption(
        "這裡衡量目前持倉受到價格與匯率變化的影響，"
        "不把存提款或手動更新餘額當成投資損益。"
        "正式買賣與已實現損益將在後續交易功能補上。"
    )

def run_daily_market_refresh_if_needed(
    supabase,
):
    today_text = (
        pd.Timestamp.now(
            tz="America/Los_Angeles"
        )
        .date()
        .isoformat()
    )

    # 避免同一個 Streamlit 工作階段重複查詢。
    if (
        st.session_state.get(
            "market_auto_refresh_attempt_date"
        )
        == today_text
    ):
        return None

    try:
        user_response = (
            supabase.auth.get_user()
        )

        current_user = user_response.user

        if current_user is None:
            return None

        user_id = str(current_user.id)

        state_response = (
            supabase
            .table("market_sync_state")
            .select(
                "last_auto_refresh_date"
            )
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )

        state_rows = (
            state_response.data or []
        )

        last_refresh_date = None

        if state_rows:
            last_refresh_date = (
                state_rows[0].get(
                    "last_auto_refresh_date"
                )
            )

        # 今天已經自動同步過，不再呼叫外部資料。
        if last_refresh_date == today_text:
            st.session_state[
                "market_auto_refresh_attempt_date"
            ] = today_text

            return None

        # 先標記已嘗試，避免錯誤造成 rerun 迴圈。
        st.session_state[
            "market_auto_refresh_attempt_date"
        ] = today_text

        with st.spinner(
            "正在執行每日市場資料自動同步..."
        ):
            refresh_result = (
                refresh_all_market_data(
                    supabase
                )
            )

            current_timestamp = (
                pd.Timestamp.now(
                    tz="America/Los_Angeles"
                ).isoformat()
            )

            (
                supabase
                .table("market_sync_state")
                .upsert(
                    {
                        "user_id": user_id,
                        "last_auto_refresh_date": (
                            today_text
                        ),
                        "last_auto_refresh_at": (
                            current_timestamp
                        ),
                        "updated_at": (
                            current_timestamp
                        ),
                    },
                    on_conflict="user_id",
                )
                .execute()
            )

        st.session_state[
            "market_refresh_result"
        ] = refresh_result

        st.session_state[
            "market_refresh_mode"
        ] = "automatic"

        st.rerun()

    except Exception as error:
        return str(error)

def show_overview(supabase):
    st.subheader("資產總覽")
    st.caption(
        "所有資產統一換算為 TWD。"
        "非現金資產市值＝持有數量 × 最新價格 × 匯率。"
    )

    auto_refresh_error = (
        run_daily_market_refresh_if_needed(
            supabase
        )
    )

    if auto_refresh_error:
        st.warning(
            "每日市場資料自動同步失敗："
            f"{auto_refresh_error}。"
            "你仍可使用下方按鈕手動重試。"
        )

    refresh_result = st.session_state.pop(
        "market_refresh_result",
        None,
    )

    refresh_mode = st.session_state.pop(
        "market_refresh_mode",
        "manual",
    )

    if refresh_result is not None:
        if refresh_mode == "automatic":
            success_prefix = (
                "每日市場資料自動同步完成："
            )
        else:
            success_prefix = (
                "市場資料同步完成："
            )

        st.success(
            success_prefix
            + (
                f'價格 '
                f'{refresh_result["prices_updated"]} 項，'
                f'匯率 '
                f'{refresh_result["fx_updated"]} 項。'
            )
        )

        protected_count = (
            refresh_result["prices_protected"]
            + refresh_result["fx_protected"]
        )

        if protected_count:
            st.info(
                f"另有 {protected_count} 筆同日期"
                "手動資料受到保護，未被自動覆蓋。"
            )

        if refresh_result["errors"]:
            st.warning(
                "部分資料無法更新："
                + "；".join(
                    refresh_result["errors"]
                )
            )

    if st.button(
        "更新全部外部行情",
        use_container_width=True,
        type="primary",
    ):
        try:
            with st.spinner(
                "正在更新價格與匯率..."
            ):
                refresh_result = (
                    refresh_all_market_data(supabase)
                )

            st.session_state[
                "market_refresh_result"
            ] = refresh_result

            st.session_state[
                "market_refresh_mode"
            ] = "manual"

            st.rerun()

        except Exception as error:
            st.error(
                f"同步市場資料失敗：{error}"
            )

    price_source_labels = {
        "manual": "手動輸入",
        "yahoo": "Yahoo Finance",
        "yfinance": "Yahoo Finance（yfinance）",
        "yuanta_fund": "元大投信官方淨值",
        "franklin_fund": "Franklin Templeton 官方淨值",
        "schroders_fund": "施羅德官方淨值",
    }

    fx_source_labels = {
        "manual": "手動輸入",
        "frankfurter": "Frankfurter",
    }

    try:
        accounts_response = (
            supabase.table("accounts")
            .select(
                "id, name, institution, "
                "include_in_twr, is_active"
            )
            .execute()
        )

        assets_response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, "
                "currency, is_active"
            )
            .execute()
        )

        entries_response = (
            supabase.table("transaction_entries")
            .select(
                "id, transaction_id, account_id, "
                "asset_id, quantity_delta, "
                "unit_price, created_at"
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

        transactions_response = (
            supabase.table("transactions")
            .select(
                "id, transaction_date, transaction_type, "
                "external_reference, dividend_type, "
                "gross_amount, tax_amount, fee_amount, "
                "trade_currency, created_at"
            )
            .order("transaction_date", desc=True)
            .execute()
        )

        accounts = accounts_response.data or []
        assets = assets_response.data or []
        entries = entries_response.data or []
        prices = prices_response.data or []
        fx_rates = fx_response.data or []
        transactions = transactions_response.data or []

    except Exception as error:
        st.error(f"讀取總覽資料失敗：{error}")
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

    fx_rates_by_currency = {}

    for fx_record in fx_rates:
        currency = fx_record["from_currency"]

        fx_rates_by_currency.setdefault(
            currency,
            [],
        ).append(fx_record)

    reversed_dividend_ids = set()

    for transaction in transactions:
        reference = (
            transaction["external_reference"] or ""
        )

        for prefix in (
            "dividend_reversal:",
            "dividend_edit_reversal:",
        ):
            if reference.startswith(prefix):
                original_id = reference[len(prefix):]

                if original_id:
                    reversed_dividend_ids.add(
                        original_id
                    )

    valid_cash_dividends = [
        transaction
        for transaction in transactions
        if (
            transaction["transaction_type"]
            == "dividend"
            and transaction["dividend_type"]
            == "cash"
            and transaction["id"]
            not in reversed_dividend_ids
        )
    ]

    def get_dividend_fx_rate(
        currency,
        transaction_date,
    ):
        if currency == "TWD":
            return 1.0

        currency_rates = fx_rates_by_currency.get(
            currency,
            [],
        )

        if not currency_rates:
            return None

        dividend_date = pd.to_datetime(
            transaction_date,
            utc=True,
            format="mixed",
        ).date()

        for rate_record in currency_rates:
            rate_date = pd.to_datetime(
                rate_record["rate_date"]
            ).date()

            if rate_date <= dividend_date:
                return float(rate_record["rate"])

        # 如果没有股利日期以前的汇率，
        # 暂时使用目前最新汇率。
        return float(currency_rates[0]["rate"])

    dividend_gross_twd = 0.0
    dividend_tax_twd = 0.0
    dividend_net_twd = 0.0

    missing_dividend_fx_currencies = set()
    counted_cash_dividends = 0

    for dividend in valid_cash_dividends:
        currency = (
            dividend["trade_currency"] or "TWD"
        )

        fx_rate = get_dividend_fx_rate(
            currency,
            dividend["transaction_date"],
        )

        if fx_rate is None:
            missing_dividend_fx_currencies.add(
                currency
            )
            continue

        gross_amount = float(
            dividend["gross_amount"] or 0
        )

        tax_amount = float(
            dividend["tax_amount"] or 0
        )

        fee_amount = float(
            dividend["fee_amount"] or 0
        )

        net_amount = (
            gross_amount
            - tax_amount
            - fee_amount
        )

        dividend_gross_twd += (
            gross_amount * fx_rate
        )

        dividend_tax_twd += (
            tax_amount * fx_rate
        )

        dividend_net_twd += (
            net_amount * fx_rate
        )

        counted_cash_dividends += 1

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

    valuation_rows = []
    missing_price_assets = set()
    missing_fx_currencies = set()

    cash_total_twd = 0.0
    non_cash_total_twd = 0.0

    investment_asset_types = {
        "stock",
        "etf",
        "fund",
        "crypto",
    }

    investment_cost_twd = 0.0
    investment_unrealized_pnl_twd = 0.0

    missing_performance_cost_assets = set()
    missing_performance_fx_currencies = set()

    for (
        account_id,
        asset_id,
    ), quantity in balances.items():
        if abs(quantity) < 0.000000000001:
            continue

        account = account_map.get(account_id)
        asset = asset_map.get(asset_id)

        if account is None or asset is None:
            continue

        currency = asset["currency"]
        asset_type = asset["asset_type"]

        unit_price = None
        price_date = ""
        price_source = ""
        original_market_value = None

        if asset_type == "cash":
            original_market_value = quantity
            price_source = "現金餘額"

        else:
            price_record = latest_prices.get(asset_id)

            if price_record is None:
                missing_price_assets.add(
                    f'{asset["symbol"]}（{asset["name"]}）'
                )

            else:
                unit_price = float(
                    price_record["price"]
                )

                original_market_value = (
                    quantity * unit_price
                )

                price_date = (
                    price_record["price_date"]
                )

                price_source = (
                    price_source_labels.get(
                        price_record["source"],
                        price_record["source"],
                    )
                )

        if currency == "TWD":
            fx_rate = 1.0
            fx_date = ""
            fx_source = "基準幣別"

        else:
            fx_record = latest_fx_rates.get(currency)

            if fx_record is None:
                fx_rate = None
                fx_date = ""
                fx_source = ""

                missing_fx_currencies.add(currency)

            else:
                fx_rate = float(
                    fx_record["rate"]
                )

                fx_date = fx_record["rate_date"]

                fx_source = fx_source_labels.get(
                    fx_record["source"],
                    fx_record["source"],
                )

        if (
            original_market_value is not None
            and fx_rate is not None
        ):
            market_value_twd = (
                original_market_value * fx_rate
            )

            if asset_type == "cash":
                cash_total_twd += market_value_twd
            else:
                non_cash_total_twd += (
                    market_value_twd
                )

            valuation_status = "已估值"

        elif original_market_value is None:
            market_value_twd = None
            valuation_status = "缺少價格"

        else:
            market_value_twd = None
            valuation_status = "缺少匯率"

        if asset_type in investment_asset_types:
            cost_state = portfolio_costs.get(
                (account_id, asset_id)
            )

            cost_complete = (
                cost_state is not None
                and cost_state.get(
                    "cost_complete",
                    False,
                )
            )

            if not cost_complete:
                missing_performance_cost_assets.add(
                    f'{asset["symbol"]}'
                    f'（{account["name"]}）'
                )

            elif (
                original_market_value is not None
                and fx_rate is not None
            ):
                remaining_cost = float(
                    cost_state["total_cost"]
                )

                investment_cost_twd += (
                    remaining_cost * fx_rate
                )

                investment_unrealized_pnl_twd += (
                    (
                        original_market_value
                        - remaining_cost
                    )
                    * fx_rate
                )

            elif fx_rate is None:
                missing_performance_fx_currencies.add(
                    currency
                )        

        item_status = (
            "使用中"
            if (
                account["is_active"]
                and asset["is_active"]
            )
            else "已封存"
        )

        valuation_rows.append(
            {
                "帳戶": account["name"],
                "資產類型": ASSET_TYPE_LABELS.get(
                    asset_type,
                    asset_type,
                ),
                "資產代號": asset["symbol"],
                "資產名稱": asset["name"],
                "數量／餘額": quantity,
                "幣別": currency,
                "單位價格": unit_price,
                "原幣市值": original_market_value,
                "匯率": fx_rate,
                "TWD 市值": market_value_twd,
                "價格日期": price_date,
                "價格來源": price_source,
                "匯率日期": fx_date,
                "匯率來源": fx_source,
                "估值狀態": valuation_status,
                "資料狀態": item_status,
            }
        )

    investment_realized_pnl_twd = 0.0

    for (
        cost_account_id,
        cost_asset_id,
    ), cost_state in portfolio_costs.items():
        asset = asset_map.get(
            cost_asset_id
        )

        account = account_map.get(
            cost_account_id
        )

        if (
            asset is None
            or asset["asset_type"]
            not in investment_asset_types
        ):
            continue

        if not cost_state.get(
            "cost_complete",
            False,
        ):
            account_name = (
                account["name"]
                if account is not None
                else "未知帳戶"
            )

            missing_performance_cost_assets.add(
                f'{asset["symbol"]}'
                f"（{account_name}）"
            )

            continue

        realized_pnl = float(
            cost_state.get(
                "realized_pnl",
                0.0,
            )
        )

        if abs(realized_pnl) < 0.000000000001:
            continue

        currency = asset["currency"]

        if currency == "TWD":
            realized_fx_rate = 1.0

        else:
            realized_fx_record = (
                latest_fx_rates.get(currency)
            )

            if realized_fx_record is None:
                missing_performance_fx_currencies.add(
                    currency
                )

                continue

            realized_fx_rate = float(
                realized_fx_record["rate"]
            )

        investment_realized_pnl_twd += (
            realized_pnl
            * realized_fx_rate
        )

    investment_price_pnl_twd = (
        investment_realized_pnl_twd
        + investment_unrealized_pnl_twd
    )

    investment_total_pnl_twd = (
        investment_price_pnl_twd
        + dividend_net_twd
    )

    investment_performance_complete = not (
        missing_performance_cost_assets
        or missing_price_assets
        or missing_performance_fx_currencies
        or missing_dividend_fx_currencies
    )

    total_assets_twd = (
        cash_total_twd
        + non_cash_total_twd
    )

    has_missing_data = bool(
        missing_price_assets
        or missing_fx_currencies
    )

    metric1, metric2, metric3 = st.columns(
        [1.2, 1, 1]
    )

    with metric1:
        total_label = (
            "已估值資產"
            if has_missing_data
            else "總資產"
        )

        st.metric(
            f"{total_label}（TWD）",
            f"{total_assets_twd:,.2f}",
        )

    with metric2:
        st.metric(
            "現金資產（TWD）",
            f"{cash_total_twd:,.2f}",
        )

    with metric3:
        st.metric(
            "非現金資產（TWD）",
            f"{non_cash_total_twd:,.2f}",
        )

    st.divider()

    with st.expander(
        "各資產類型配置",
        expanded=False,
    ):
        allocation_dataframe = pd.DataFrame(
            valuation_rows
        )

        allocation_dataframe = (
            allocation_dataframe[
                (
                    allocation_dataframe["估值狀態"]
                    == "已估值"
                )
                & (
                    allocation_dataframe[
                        "TWD 市值"
                    ].notna()
                )
            ]
        )

        if (
            allocation_dataframe.empty
            or abs(total_assets_twd) < 0.000001
        ):
            st.info(
                "目前沒有足夠的估值資料可以計算"
                "資產配置。"
            )

        else:
            allocation_summary = (
                allocation_dataframe
                .groupby(
                    "資產類型",
                    as_index=False,
                )["TWD 市值"]
                .sum()
            )

            allocation_summary["配置比例"] = (
                allocation_summary["TWD 市值"]
                / total_assets_twd
                * 100
            )

            allocation_summary = (
                allocation_summary.sort_values(
                    by="TWD 市值",
                    ascending=False,
                )
            )

            allocation_summary["比例標籤"] = (
                allocation_summary[
                    "配置比例"
                ].map(
                    lambda value: f"{value:.1f}%"
                )
            )

            pie_base = alt.Chart(
                allocation_summary
            ).encode(
                theta=alt.Theta(
                    field="TWD 市值",
                    type="quantitative",
                    stack=True,
                ),
                color=alt.Color(
                    field="資產類型",
                    type="nominal",
                    title="資產類型",
                ),
                tooltip=[
                    alt.Tooltip(
                        field="資產類型",
                        type="nominal",
                        title="資產類型",
                    ),
                    alt.Tooltip(
                        field="TWD 市值",
                        type="quantitative",
                        title="TWD 市值",
                        format=",.2f",
                    ),
                    alt.Tooltip(
                        field="配置比例",
                        type="quantitative",
                        title="配置比例（%）",
                        format=".2f",
                    ),
                ],
            )

            pie_chart = pie_base.mark_arc(
                innerRadius=65,
                outerRadius=145,
            )

            percentage_labels = (
                pie_base.mark_text(
                    radius=105,
                    size=14,
                    fontWeight="bold",
                    color="white",
                ).encode(
                    text=alt.Text(
                        field="比例標籤",
                        type="nominal",
                    )
                )
            )

            allocation_chart = (
                pie_chart
                + percentage_labels
            ).properties(
                height=360,
            )

            st.altair_chart(
                allocation_chart,
                use_container_width=True,
            )

            st.dataframe(
                allocation_summary[
                    [
                        "資產類型",
                        "TWD 市值",
                        "配置比例",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "TWD 市值":
                        st.column_config.NumberColumn(
                            "TWD 市值",
                            format="%.2f",
                        ),
                    "配置比例":
                        st.column_config.NumberColumn(
                            "配置比例",
                            format="%.2f%%",
                        ),
                },
            )

    with st.expander(
        "計價幣別配置",
        expanded=False,
    ):
        currency_allocation_dataframe = (
            pd.DataFrame(valuation_rows)
        )

        currency_allocation_dataframe = (
            currency_allocation_dataframe[
                (
                    currency_allocation_dataframe[
                        "估值狀態"
                    ]
                    == "已估值"
                )
                & (
                    currency_allocation_dataframe[
                        "TWD 市值"
                    ].notna()
                )
                & (
                    currency_allocation_dataframe[
                        "TWD 市值"
                    ]
                    > 0
                )
            ].copy()
        )

        if currency_allocation_dataframe.empty:
            st.info(
                "目前沒有足夠的估值資料可以計算"
                "計價幣別配置。"
            )

        else:
            currency_allocation_summary = (
                currency_allocation_dataframe
                .groupby(
                    "幣別",
                    as_index=False,
                )["TWD 市值"]
                .sum()
            )

            currency_allocation_total = (
                currency_allocation_summary[
                    "TWD 市值"
                ].sum()
            )

            currency_allocation_summary[
                "配置比例"
            ] = (
                currency_allocation_summary[
                    "TWD 市值"
                ]
                / currency_allocation_total
                * 100
            )

            currency_allocation_summary = (
                currency_allocation_summary.sort_values(
                    by="TWD 市值",
                    ascending=False,
                )
            )

            currency_allocation_summary[
                "比例標籤"
            ] = (
                currency_allocation_summary[
                    "配置比例"
                ].map(
                    lambda value: f"{value:.1f}%"
                )
            )

            currency_pie_base = alt.Chart(
                currency_allocation_summary
            ).encode(
                theta=alt.Theta(
                    field="TWD 市值",
                    type="quantitative",
                    stack=True,
                ),
                color=alt.Color(
                    field="幣別",
                    type="nominal",
                    title="計價幣別",
                ),
                tooltip=[
                    alt.Tooltip(
                        field="幣別",
                        type="nominal",
                        title="計價幣別",
                    ),
                    alt.Tooltip(
                        field="TWD 市值",
                        type="quantitative",
                        title="TWD 市值",
                        format=",.2f",
                    ),
                    alt.Tooltip(
                        field="配置比例",
                        type="quantitative",
                        title="配置比例（%）",
                        format=".2f",
                    ),
                ],
            )

            currency_pie_chart = (
                currency_pie_base.mark_arc(
                    innerRadius=65,
                    outerRadius=145,
                )
            )

            currency_percentage_labels = (
                currency_pie_base.mark_text(
                    radius=105,
                    size=14,
                    fontWeight="bold",
                    color="white",
                ).encode(
                    text=alt.Text(
                        field="比例標籤",
                        type="nominal",
                    )
                )
            )

            currency_allocation_chart = (
                currency_pie_chart
                + currency_percentage_labels
            ).properties(
                height=360,
            )

            st.altair_chart(
                currency_allocation_chart,
                use_container_width=True,
            )

            st.dataframe(
                currency_allocation_summary[
                    [
                        "幣別",
                        "TWD 市值",
                        "配置比例",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "TWD 市值":
                        st.column_config.NumberColumn(
                            "TWD 市值",
                            format="%.2f",
                        ),
                    "配置比例":
                        st.column_config.NumberColumn(
                            "配置比例",
                            format="%.2f%%",
                        ),
                },
            )

        st.caption(
            "此處按照資產的計價幣別分類，"
            "並以最新匯率換算為 TWD 比較。"
            "這不等同於投資標的底層公司的"
            "實際國家或營收曝險。"
        )

    st.divider()

    show_institution_overview(
        supabase
    )

    st.divider()

    with st.expander(
        "帳戶資產配置",
        expanded=False,
    ):
        account_allocation_dataframe = (
            pd.DataFrame(valuation_rows)
        )

        account_allocation_dataframe = (
            account_allocation_dataframe[
                (
                    account_allocation_dataframe[
                        "估值狀態"
                    ]
                    == "已估值"
                )
                & (
                    account_allocation_dataframe[
                        "TWD 市值"
                    ].notna()
                )
                & (
                    account_allocation_dataframe[
                        "TWD 市值"
                    ]
                    > 0
                )
            ].copy()
        )

        if account_allocation_dataframe.empty:
            st.info(
                "目前沒有足夠的估值資料可以計算"
                "帳戶資產配置。"
            )

        else:
            account_allocation_summary = (
                account_allocation_dataframe
                .groupby(
                    "帳戶",
                    as_index=False,
                )["TWD 市值"]
                .sum()
            )

            account_allocation_total = (
                account_allocation_summary[
                    "TWD 市值"
                ].sum()
            )

            account_allocation_summary[
                "配置比例"
            ] = (
                account_allocation_summary[
                    "TWD 市值"
                ]
                / account_allocation_total
                * 100
            )

            account_allocation_summary = (
                account_allocation_summary.sort_values(
                    by="TWD 市值",
                    ascending=False,
                )
            )

            account_allocation_summary[
                "比例標籤"
            ] = (
                account_allocation_summary[
                    "配置比例"
                ].map(
                    lambda value: f"{value:.1f}%"
                )
            )

            account_pie_base = alt.Chart(
                account_allocation_summary
            ).encode(
                theta=alt.Theta(
                    field="TWD 市值",
                    type="quantitative",
                    stack=True,
                ),
                color=alt.Color(
                    field="帳戶",
                    type="nominal",
                    title="帳戶",
                ),
                tooltip=[
                    alt.Tooltip(
                        field="帳戶",
                        type="nominal",
                        title="帳戶",
                    ),
                    alt.Tooltip(
                        field="TWD 市值",
                        type="quantitative",
                        title="TWD 市值",
                        format=",.2f",
                    ),
                    alt.Tooltip(
                        field="配置比例",
                        type="quantitative",
                        title="配置比例（%）",
                        format=".2f",
                    ),
                ],
            )

            account_pie_chart = (
                account_pie_base.mark_arc(
                    innerRadius=65,
                    outerRadius=145,
                )
            )

            account_percentage_labels = (
                account_pie_base.mark_text(
                    radius=105,
                    size=14,
                    fontWeight="bold",
                    color="white",
                ).encode(
                    text=alt.Text(
                        field="比例標籤",
                        type="nominal",
                    )
                )
            )

            account_allocation_chart = (
                account_pie_chart
                + account_percentage_labels
            ).properties(
                height=360,
            )

            st.altair_chart(
                account_allocation_chart,
                use_container_width=True,
            )

            st.dataframe(
                account_allocation_summary[
                    [
                        "帳戶",
                        "TWD 市值",
                        "配置比例",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "TWD 市值":
                        st.column_config.NumberColumn(
                            "TWD 市值",
                            format="%.2f",
                        ),
                    "配置比例":
                        st.column_config.NumberColumn(
                            "配置比例",
                            format="%.2f%%",
                        ),
                },
            )

        st.caption(
            "依資產所在帳戶統計，並以最新價格"
            "與匯率換算為 TWD。負餘額不納入"
            "圓環圖配置比例。"
        )

    with st.expander(
        "投資持倉配置",
        expanded=False,
    ):
        investment_allocation_dataframe = (
            pd.DataFrame(valuation_rows)
        )

        cash_asset_label = (
            ASSET_TYPE_LABELS.get(
                "cash",
                "cash",
            )
        )

        investment_allocation_dataframe = (
            investment_allocation_dataframe[
                (
                    investment_allocation_dataframe[
                        "資產類型"
                    ]
                    != cash_asset_label
                )
                & (
                    investment_allocation_dataframe[
                        "估值狀態"
                    ]
                    == "已估值"
                )
                & (
                    investment_allocation_dataframe[
                        "TWD 市值"
                    ].notna()
                )
                & (
                    investment_allocation_dataframe[
                        "TWD 市值"
                    ]
                    > 0
                )
            ].copy()
        )

        if investment_allocation_dataframe.empty:
            st.info(
                "目前沒有可計算的股票、ETF、"
                "基金或其他非現金持倉。"
            )

        else:
            investment_allocation_summary = (
                investment_allocation_dataframe
                .groupby(
                    [
                        "資產代號",
                        "資產名稱",
                        "資產類型",
                        "幣別",
                    ],
                    as_index=False,
                )["TWD 市值"]
                .sum()
            )

            investment_allocation_total = (
                investment_allocation_summary[
                    "TWD 市值"
                ].sum()
            )

            investment_allocation_summary[
                "投資配置比例"
            ] = (
                investment_allocation_summary[
                    "TWD 市值"
                ]
                / investment_allocation_total
                * 100
            )

            investment_allocation_summary[
                "投資標的"
            ] = (
                investment_allocation_summary[
                    "資產代號"
                ]
                + "｜"
                + investment_allocation_summary[
                    "資產名稱"
                ]
            )

            investment_allocation_summary = (
                investment_allocation_summary.sort_values(
                    by="TWD 市值",
                    ascending=False,
                )
            )

            investment_hierarchy_dataframe = (
                investment_allocation_summary.copy()
            )

            investment_hierarchy_dataframe[
                "投資組合"
            ] = "全部投資"

            investment_sunburst_chart = (
                px.sunburst(
                    investment_hierarchy_dataframe,
                    path=[
                        "投資組合",
                        "幣別",
                        "投資標的",
                    ],
                    values="TWD 市值",
                    color="幣別",
                )
            )

            investment_sunburst_chart.update_traces(
                textinfo=(
                    "label+percent parent"
                ),
                insidetextorientation="auto",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "TWD 市值：%{value:,.2f}<br>"
                    "占上一層：%{percentParent:.2%}<br>"
                    "占全部投資：%{percentRoot:.2%}"
                    "<extra></extra>"
                ),
            )

            investment_sunburst_chart.update_layout(
                height=520,
                margin={
                    "t": 10,
                    "l": 10,
                    "r": 10,
                    "b": 10,
                },
                legend_title_text="計價幣別",
            )

            st.plotly_chart(
                investment_sunburst_chart,
                use_container_width=True,
                config={
                    "displayModeBar": False,
                },
            )

            st.dataframe(
                investment_allocation_summary[
                    [
                        "資產代號",
                        "資產名稱",
                        "資產類型",
                        "幣別",
                        "TWD 市值",
                        "投資配置比例",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "TWD 市值":
                        st.column_config.NumberColumn(
                            "TWD 市值",
                            format="%.2f",
                        ),
                    "投資配置比例":
                        st.column_config.NumberColumn(
                            "投資配置比例",
                            format="%.2f%%",
                        ),
                },
            )

        st.caption(
            "此處排除現金。中心代表全部投資，"
            "內圈代表資產的計價幣別，外圈代表"
            "各投資標的。點擊任一區塊可以向下"
            "查看，點擊圓心可返回上一層。"
        )

    snapshot_data_complete = (
        not has_missing_data
        and investment_performance_complete
    )

    def performance_snapshot_value(value):
        return (
            value
            if snapshot_data_complete
            else None
        )

    snapshot_payload = {
        "total_assets_twd": (
            total_assets_twd
        ),
        "cash_assets_twd": (
            cash_total_twd
        ),
        "investment_assets_twd": (
            non_cash_total_twd
        ),
        "remaining_cost_twd": (
            performance_snapshot_value(
                investment_cost_twd
            )
        ),
        "unrealized_pnl_twd": (
            performance_snapshot_value(
                investment_unrealized_pnl_twd
            )
        ),
        "realized_pnl_twd": (
            performance_snapshot_value(
                investment_realized_pnl_twd
            )
        ),
        "price_pnl_twd": (
            performance_snapshot_value(
                investment_price_pnl_twd
            )
        ),
        "net_dividend_twd": (
            performance_snapshot_value(
                dividend_net_twd
            )
        ),
        "total_pnl_twd": (
            performance_snapshot_value(
                investment_total_pnl_twd
            )
        ),
        "data_complete": (
            snapshot_data_complete
        ),
    }

    cash_asset_label = (
        ASSET_TYPE_LABELS.get(
            "cash",
            "cash",
        )
    )

    twr_accounts = [
        account
        for account in accounts
        if (
            account.get(
                "include_in_twr",
                False,
            )
            and account.get(
                "is_active",
                True,
            )
        )
    ]

    account_snapshot_rows = []

    for account in twr_accounts:
        account_name = account["name"]

        account_valuation_rows = [
            row
            for row in valuation_rows
            if row.get("帳戶") == account_name
        ]

        account_cash_assets_twd = sum(
            float(row["TWD 市值"])
            for row in account_valuation_rows
            if (
                row.get("資產類型")
                == cash_asset_label
                and row.get("TWD 市值")
                is not None
            )
        )

        account_investment_assets_twd = sum(
            float(row["TWD 市值"])
            for row in account_valuation_rows
            if (
                row.get("資產類型")
                != cash_asset_label
                and row.get("TWD 市值")
                is not None
            )
        )

        missing_price_count = sum(
            1
            for row in account_valuation_rows
            if row.get("估值狀態")
            == "缺少價格"
        )

        missing_fx_count = sum(
            1
            for row in account_valuation_rows
            if row.get("估值狀態")
            == "缺少匯率"
        )

        account_data_complete = not (
            missing_price_count
            or missing_fx_count
        )

        account_snapshot_rows.append(
            {
                "account_id": account["id"],
                "total_assets_twd": (
                    account_cash_assets_twd
                    + account_investment_assets_twd
                ),
                "cash_assets_twd": (
                    account_cash_assets_twd
                ),
                "investment_assets_twd": (
                    account_investment_assets_twd
                ),
                "data_complete": (
                    account_data_complete
                ),
                "missing_price_count": (
                    missing_price_count
                ),
                "missing_fx_count": (
                    missing_fx_count
                ),
            }
        )

    def save_complete_daily_snapshot():
        snapshot_records = (
            save_daily_snapshot(
                supabase,
                **snapshot_payload,
            )
        )

        if not snapshot_records:
            raise RuntimeError(
                "總資產快照已儲存，"
                "但未取得快照 ID。"
            )

        snapshot_id = snapshot_records[0].get(
            "id"
        )

        if not snapshot_id:
            raise RuntimeError(
                "總資產快照缺少 ID。"
            )

        save_account_snapshot_rows(
            supabase,
            snapshot_id=snapshot_id,
            account_rows=account_snapshot_rows,
        )

        return snapshot_records

    with st.expander(
        "每日資產快照",
        expanded=False,
    ):
        st.caption(
            "每天保留一筆總資產與投資績效。"
            "同一天再次儲存會更新當日資料，"
            "不會建立重複紀錄。"
        )

        if snapshot_data_complete:
            st.success(
                "目前資料完整，可以儲存今日快照。"
            )
        else:
            st.warning(
                "目前有部分成本、價格或匯率缺失。"
                "仍可儲存快照，但會被標示為"
                "「資料不完整」。"
            )

        if st.button(
            "儲存／更新今日快照",
            key="save_daily_portfolio_snapshot",
            use_container_width=True,
        ):
            try:
                
                save_complete_daily_snapshot()                

                st.success(
                    "今日資產快照已儲存。"
                )

            except Exception as error:
                st.error(
                    "儲存今日快照失敗："
                    f"{error}"
                )

    try:
        portfolio_snapshots = (
            load_portfolio_snapshots(
                supabase
            )
        )

    except Exception as error:
        portfolio_snapshots = []

        st.error(
            "讀取資產快照失敗："
            f"{error}"
        )

    today_snapshot_date = (
        pd.Timestamp.now(
            tz="America/Los_Angeles"
        ).date()
    )

    has_today_snapshot = any(
        pd.to_datetime(
            snapshot["snapshot_date"]
        ).date()
        == today_snapshot_date
        for snapshot in portfolio_snapshots
    )

    if (
        snapshot_data_complete
        and not has_today_snapshot
    ):
        try:
            
            save_complete_daily_snapshot()

            st.session_state[
                "automatic_snapshot_message"
            ] = (
                "今日資產快照已自動建立。"
            )

            st.rerun()

        except Exception as error:
            st.warning(
                "自動建立今日快照失敗："
                f"{error}"
            )

    automatic_snapshot_message = (
        st.session_state.pop(
            "automatic_snapshot_message",
            None,
        )
    )

    if automatic_snapshot_message:
        st.success(
            automatic_snapshot_message
        )
    
    if portfolio_snapshots:
        trend_section = st.expander(
            "資產歷史趨勢",
            expanded=False,
        )

        snapshot_dataframe = pd.DataFrame(
            portfolio_snapshots
        )

        snapshot_dataframe[
            "snapshot_date"
        ] = pd.to_datetime(
            snapshot_dataframe[
                "snapshot_date"
            ]
        )

        numeric_snapshot_columns = [
            "total_assets_twd",
            "cash_assets_twd",
            "investment_assets_twd",
            "remaining_cost_twd",
            "unrealized_pnl_twd",
            "realized_pnl_twd",
            "price_pnl_twd",
            "net_dividend_twd",
            "total_pnl_twd",
        ]

        for column_name in (
            numeric_snapshot_columns
        ):
            snapshot_dataframe[
                column_name
            ] = pd.to_numeric(
                snapshot_dataframe[
                    column_name
                ],
                errors="coerce",
            )

        complete_snapshot_dataframe = (
            snapshot_dataframe[
                snapshot_dataframe[
                    "data_complete"
                ]
            ].copy()
        )

        if complete_snapshot_dataframe.empty:
            st.info(
                "目前尚未有資料完整的歷史快照。"
            )

        else:
            asset_trend_dataframe = (
                complete_snapshot_dataframe[
                    [
                        "snapshot_date",
                        "total_assets_twd",
                        "cash_assets_twd",
                        "investment_assets_twd",
                    ]
                ]
                .rename(
                    columns={
                        "snapshot_date": "日期",
                        "total_assets_twd": (
                            "總資產"
                        ),
                        "cash_assets_twd": (
                            "現金資產"
                        ),
                        "investment_assets_twd": (
                            "投資資產"
                        ),
                    }
                )
                .set_index("日期")
            )

            trend_section.caption(
                "總資產、現金資產與投資資產"
                "的每日 TWD 變化。"
            )

            trend_section.line_chart(
                asset_trend_dataframe,
                use_container_width=True,
            )

            pnl_trend_dataframe = (
                complete_snapshot_dataframe[
                    [
                        "snapshot_date",
                        "unrealized_pnl_twd",
                        "realized_pnl_twd",
                        "price_pnl_twd",
                        "total_pnl_twd",
                    ]
                ]
                .rename(
                    columns={
                        "snapshot_date": "日期",
                        "unrealized_pnl_twd": (
                            "未實現損益"
                        ),
                        "realized_pnl_twd": (
                            "已實現損益"
                        ),
                        "price_pnl_twd": (
                            "價格總損益"
                        ),
                        "total_pnl_twd": (
                            "含股利總損益"
                        ),
                    }
                )
                .set_index("日期")
            )

            trend_section.caption(
                "投資損益的每日 TWD 變化。"
            )

            trend_section.line_chart(
                pnl_trend_dataframe,
                use_container_width=True,
            )

        with st.expander(
            "查看歷史快照資料",
            expanded=False,
        ):
            history_display_dataframe = (
                snapshot_dataframe[
                    [
                        "snapshot_date",
                        "total_assets_twd",
                        "cash_assets_twd",
                        "investment_assets_twd",
                        "remaining_cost_twd",
                        "unrealized_pnl_twd",
                        "realized_pnl_twd",
                        "price_pnl_twd",
                        "net_dividend_twd",
                        "total_pnl_twd",
                        "data_complete",
                    ]
                ]
                .rename(
                    columns={
                        "snapshot_date": "日期",
                        "total_assets_twd": (
                            "總資產"
                        ),
                        "cash_assets_twd": (
                            "現金資產"
                        ),
                        "investment_assets_twd": (
                            "投資資產"
                        ),
                        "remaining_cost_twd": (
                            "剩餘成本"
                        ),
                        "unrealized_pnl_twd": (
                            "未實現損益"
                        ),
                        "realized_pnl_twd": (
                            "已實現損益"
                        ),
                        "price_pnl_twd": (
                            "價格總損益"
                        ),
                        "net_dividend_twd": (
                            "淨現金股利"
                        ),
                        "total_pnl_twd": (
                            "含股利總損益"
                        ),
                        "data_complete": (
                            "資料完整"
                        ),
                    }
                )
            )

            history_display_dataframe[
                "日期"
            ] = history_display_dataframe[
                "日期"
            ].dt.strftime("%Y-%m-%d")

            st.dataframe(
                history_display_dataframe,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "總資產": (
                        st.column_config.NumberColumn(
                            "總資產",
                            format="%.2f",
                        )
                    ),
                    "現金資產": (
                        st.column_config.NumberColumn(
                            "現金資產",
                            format="%.2f",
                        )
                    ),
                    "投資資產": (
                        st.column_config.NumberColumn(
                            "投資資產",
                            format="%.2f",
                        )
                    ),
                    "剩餘成本": (
                        st.column_config.NumberColumn(
                            "剩餘成本",
                            format="%.2f",
                        )
                    ),
                    "未實現損益": (
                        st.column_config.NumberColumn(
                            "未實現損益",
                            format="%.2f",
                        )
                    ),
                    "已實現損益": (
                        st.column_config.NumberColumn(
                            "已實現損益",
                            format="%.2f",
                        )
                    ),
                    "價格總損益": (
                        st.column_config.NumberColumn(
                            "價格總損益",
                            format="%.2f",
                        )
                    ),
                    "淨現金股利": (
                        st.column_config.NumberColumn(
                            "淨現金股利",
                            format="%.2f",
                        )
                    ),
                    "含股利總損益": (
                        st.column_config.NumberColumn(
                            "含股利總損益",
                            format="%.2f",
                        )
                    ),
                },
            )

    else:
        st.info(
            "目前還沒有歷史快照。"
            "請先儲存今日快照。"
        )

    st.divider()
    st.subheader("投資績效")

    if investment_performance_complete:
        performance_col1, performance_col2, performance_col3 = (
            st.columns(3)
        )

        with performance_col1:
            st.metric(
                "剩餘投資成本參考值",
                f"TWD {investment_cost_twd:,.2f}",
            )

        with performance_col2:
            st.metric(
                "未實現損益參考值",
                (
                    "TWD "
                    f"{investment_unrealized_pnl_twd:,.2f}"
                ),
            )

        with performance_col3:
            st.metric(
                "已實現損益參考值",
                (
                    "TWD "
                    f"{investment_realized_pnl_twd:,.2f}"
                ),
            )

        performance_col4, performance_col5, performance_col6 = (
            st.columns(3)
        )

        with performance_col4:
            st.metric(
                "價格總損益參考值",
                (
                    "TWD "
                    f"{investment_price_pnl_twd:,.2f}"
                ),
            )

        with performance_col5:
            st.metric(
                "累計淨現金股利",
                f"TWD {dividend_net_twd:,.2f}",
            )

        with performance_col6:
            st.metric(
                "含股利總損益參考值",
                (
                    "TWD "
                    f"{investment_total_pnl_twd:,.2f}"
                ),
            )

    else:
        st.warning(
            "部分投資缺少成本、價格或匯率，"
            "暫時無法顯示完整的投資績效。"
        )

    st.caption(
        "目前外幣成本與價格損益依最新匯率換算；"
        "尚未另外拆分交易期間的匯兌損益。"
        "股票股利已反映於持有數量與平均成本，"
        "不會重複加入總損益。"
    )

    if missing_performance_cost_assets:
        st.info(
            "成本資料尚未完整："
            + "、".join(
                sorted(
                    missing_performance_cost_assets
                )
            )
        )

    if missing_performance_fx_currencies:
        st.info(
            "績效換算缺少匯率："
            + "、".join(
                sorted(
                    missing_performance_fx_currencies
                )
            )
        )

    st.divider()
    st.subheader("累計股利收入")

    dividend_col1, dividend_col2, dividend_col3 = (
        st.columns(3)
    )

    with dividend_col1:
        st.metric(
            "累計稅前現金股利",
            f"TWD {dividend_gross_twd:,.2f}",
        )

    with dividend_col2:
        st.metric(
            "累計預扣稅",
            f"TWD {dividend_tax_twd:,.2f}",
        )

    with dividend_col3:
        st.metric(
            "累計淨股利收入",
            f"TWD {dividend_net_twd:,.2f}",
        )

    st.caption(
        f"目前统计 {counted_cash_dividends} 笔"
        "有效现金股利。净股利收入＝"
        "税前股利－预扣税－其他费用。"
        "这些金额仅作为收入统计，"
        "不会再次加进总资产。"
    )

    if missing_dividend_fx_currencies:
        missing_dividend_fx_text = "、".join(
            sorted(missing_dividend_fx_currencies)
        )

        st.warning(
            "下列股利币别缺少 TWD 汇率，"
            "暂时未计入累计股利："
            f"{missing_dividend_fx_text}"
        )

    if missing_price_assets:
        missing_price_text = "、".join(
            sorted(missing_price_assets)
        )

        st.warning(
            "下列資產缺少價格，尚未計入總資產："
            f"{missing_price_text}"
        )

    if missing_fx_currencies:
        missing_fx_text = "、".join(
            sorted(missing_fx_currencies)
        )

        st.warning(
            "下列幣別缺少 TWD 匯率，"
            "相關資產尚未計入總資產："
            f"{missing_fx_text}"
        )

    if not valuation_rows:
        st.info(
            "目前還沒有可計算的資產餘額或持倉。"
        )
        return

    st.divider()
    st.subheader("資產估值明細")

    valuation_dataframe = pd.DataFrame(
        valuation_rows
    )

    valuation_dataframe = (
        valuation_dataframe.sort_values(
            by="TWD 市值",
            ascending=False,
            na_position="last",
        )
    )

    st.dataframe(
        valuation_dataframe,
        width='stretch',
        hide_index=True,
        column_config={
            "數量／餘額":
                st.column_config.NumberColumn(
                    "數量／餘額",
                    format="%.8f",
                ),
            "單位價格":
                st.column_config.NumberColumn(
                    "單位價格",
                    format="%.2f",
                ),
            "原幣市值":
                st.column_config.NumberColumn(
                    "原幣市值",
                    format="%.2f",
                ),
            "匯率":
                st.column_config.NumberColumn(
                    "匯率",
                    format="%.6f",
                ),
            "TWD 市值":
                st.column_config.NumberColumn(
                    "TWD 市值",
                    format="%.2f",
                ),
        },
    )

    st.caption(
        "已封存但仍有餘額或持倉的帳戶與資產，"
        "仍會計入總資產，避免資產因封存而消失。"
    )

    st.divider()
    show_recent_market_change(supabase)
