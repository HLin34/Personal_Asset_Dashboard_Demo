import pandas as pd
import streamlit as st

from services.market_data import (
    fetch_yahoo_asset_price,
)
from services.standard_csv_import import (
    build_standard_import_payload,
    prepare_standard_csv_import,
    resolve_asset_metadata,
    validate_asset_metadata,
)


IMPORT_TYPE_LABELS = {
    "buy": "買入",
    "sell": "賣出",
    "cash_dividend": "現金股利",
    "stock_dividend": "股票股利",
}

RESOLUTION_LABELS = {
    "existing": "已存在",
    "existing_updated": "既有資產待同步",
    "auto": "自動辨識",
    "ambiguous": "需確認",
    "unresolved": "未解決",
    "pending": "待處理",
}


def _default_index(options, preferred_name):
    for index, option in enumerate(options):
        if option.get("name") == preferred_name:
            return index

    return 0


def _format_account(account):
    institution = account.get("institution") or ""

    if institution:
        return f'{account["name"]}｜{institution}'

    return account["name"]


def _format_asset(asset):
    return (
        f'{asset["symbol"]}｜{asset["name"]}'
        f'｜{asset["currency"]}'
    )


def _load_balance(
    supabase,
    account_id,
    asset_id,
):
    response = (
        supabase.table("transaction_entries")
        .select("quantity_delta")
        .eq("account_id", account_id)
        .eq("asset_id", asset_id)
        .execute()
    )

    return sum(
        float(entry.get("quantity_delta") or 0)
        for entry in (response.data or [])
    )


def _quote_fetcher(external_symbol):
    return fetch_yahoo_asset_price(
        external_symbol
    )


def show_general_csv_import_preview(
    supabase,
    accounts,
    assets,
):
    with st.expander(
        "通用證券交易 CSV 匯入",
        expanded=False,
    ):
        st.caption(
            "支援台股與美股的標準 CSV。"
            "先預覽交易、自動辨識市場與報價代號，"
            "確認後才會整批寫入。"
        )

        active_accounts = [
            account
            for account in accounts
            if account.get("is_active")
        ]
        active_cash_assets = [
            asset
            for asset in assets
            if (
                asset.get("is_active")
                and asset.get("asset_type") == "cash"
            )
        ]

        if not active_accounts:
            st.warning("目前沒有使用中的帳戶。")
            return

        if not active_cash_assets:
            st.warning("目前沒有使用中的現金資產。")
            return

        source_account = st.selectbox(
            "交易所屬證券帳戶",
            options=active_accounts,
            format_func=_format_account,
            key="general_csv_source_account",
        )

        currencies = sorted(
            {
                str(asset.get("currency") or "")
                .strip()
                .upper()
                for asset in active_cash_assets
                if asset.get("currency")
            }
        )
        preferred_currency = str(
            source_account.get("base_currency") or ""
        ).upper()
        currency_index = (
            currencies.index(preferred_currency)
            if preferred_currency in currencies
            else 0
        )
        import_currency = st.selectbox(
            "交易與現金幣別",
            options=currencies,
            index=currency_index,
            key="general_csv_currency",
        )

        settlement_account = st.selectbox(
            "連動現金帳戶",
            options=active_accounts,
            format_func=_format_account,
            key="general_csv_settlement_account",
        )

        currency_cash_assets = [
            asset
            for asset in active_cash_assets
            if str(asset.get("currency") or "").upper()
            == import_currency
        ]

        if not currency_cash_assets:
            st.warning(
                f"尚未建立 {import_currency} 現金資產。"
            )
            return

        cash_asset = st.selectbox(
            "連動現金資產",
            options=currency_cash_assets,
            format_func=_format_asset,
            key="general_csv_cash_asset",
        )

        try:
            current_cash_balance = _load_balance(
                supabase,
                settlement_account["id"],
                cash_asset["id"],
            )
        except Exception as error:
            st.error(
                "讀取目前現金餘額失敗："
                f"{error}"
            )
            return

        target_cash_balance = st.number_input(
            "匯入完成後的目標現金餘額",
            value=float(current_cash_balance),
            step=1000.0,
            format="%.2f",
            help=(
                "正式匯入會在同一批次建立期末校正，"
                "使連動現金回到這個金額。"
            ),
            key=(
                "general_csv_target_cash_balance_"
                f'{settlement_account["id"]}_'
                f'{cash_asset["id"]}'
            ),
        )

        uploaded_file = st.file_uploader(
            "選擇標準交易紀錄 CSV",
            type=["csv"],
            key="general_transaction_csv",
        )

        if uploaded_file is None:
            st.info("CSV 上傳後才會進行預覽。")
            return

        try:
            prepared = prepare_standard_csv_import(
                uploaded_file,
                currency=import_currency,
            )
            resolved_assets = resolve_asset_metadata(
                prepared["assets"],
                assets,
                _quote_fetcher,
            )
        except Exception as error:
            st.error(f"CSV 解析失敗：{error}")
            return

        summary = prepared["summary"]
        records = prepared["records"].copy()

        st.markdown("### 檔案檢查")
        metric_columns = st.columns(4)
        metric_columns[0].metric(
            "有效交易",
            f'{summary["valid_transaction_count"]:,} 筆',
        )
        metric_columns[1].metric(
            "涵蓋資產",
            f'{summary["asset_count"]:,} 項',
        )
        metric_columns[2].metric(
            "起始日期",
            summary["start_date"],
        )
        metric_columns[3].metric(
            "結束日期",
            summary["end_date"],
        )

        count_rows = pd.DataFrame(
            [
                {
                    "交易類型": label,
                    "筆數": summary[key],
                }
                for label, key in [
                    ("一般買入", "buy_count"),
                    ("賣出", "sell_count"),
                    ("現金股利", "cash_dividend_count"),
                    ("股票股利", "stock_dividend_count"),
                ]
            ]
        )
        st.dataframe(
            count_rows,
            width="stretch",
            hide_index=True,
        )

        st.markdown("### 現金試算")
        projected_cash_balance = (
            current_cash_balance
            + summary["net_cash_delta"]
        )
        adjustment_amount = (
            float(target_cash_balance)
            - projected_cash_balance
        )
        final_cash_balance = (
            projected_cash_balance
            + adjustment_amount
        )
        cash_rows = pd.DataFrame(
            [
                {
                    "項目": "目前系統現金餘額",
                    f"金額 {import_currency}": current_cash_balance,
                },
                {
                    "項目": "歷史買入支出",
                    f"金額 {import_currency}": -summary["buy_outflow"],
                },
                {
                    "項目": "歷史賣出收入",
                    f"金額 {import_currency}": summary["sell_inflow"],
                },
                {
                    "項目": "歷史現金股利",
                    f"金額 {import_currency}": summary["dividend_inflow"],
                },
                {
                    "項目": "校正前試算餘額",
                    f"金額 {import_currency}": projected_cash_balance,
                },
                {
                    "項目": "匯入後現金校正",
                    f"金額 {import_currency}": adjustment_amount,
                },
                {
                    "項目": "校正後期末餘額",
                    f"金額 {import_currency}": final_cash_balance,
                },
            ]
        )
        st.dataframe(
            cash_rows,
            width="stretch",
            hide_index=True,
        )

        if projected_cash_balance < 0:
            st.warning(
                "加入歷史交易後，校正前現金會暫時為 "
                f"{projected_cash_balance:,.2f} {import_currency}。"
                "正式匯入會在同一資料庫交易中完成校正，"
                "最終餘額不會留在負數。"
            )

        st.markdown("### 資產與報價代號")
        st.caption(
            "台股會依序測試 .TW 與 .TWO；"
            "美股會先使用原始代號，"
            "再嘗試將小數點改為連字號。"
        )

        editor_rows = resolved_assets[
            [
                "symbol",
                "name",
                "asset_type",
                "currency",
                "market",
                "external_symbol",
                "price_source",
                "resolution_status",
                "resolution_note",
            ]
        ].copy()
        editor_rows["resolution_status"] = editor_rows[
            "resolution_status"
        ].map(RESOLUTION_LABELS).fillna(
            editor_rows["resolution_status"]
        )

        edited_assets = st.data_editor(
            editor_rows,
            width="stretch",
            hide_index=True,
            disabled=[
                "symbol",
                "currency",
                "resolution_status",
                "resolution_note",
            ],
            column_config={
                "symbol": "代號",
                "name": "資產名稱",
                "asset_type": st.column_config.SelectboxColumn(
                    "資產類型",
                    options=["stock", "etf"],
                ),
                "currency": "幣別",
                "market": st.column_config.SelectboxColumn(
                    "市場",
                    options=["", "TWSE", "TPEX", "US", "OTHER"],
                ),
                "external_symbol": "外部報價代號",
                "price_source": st.column_config.SelectboxColumn(
                    "價格來源",
                    options=["yfinance", "manual"],
                ),
                "resolution_status": "辨識狀態",
                "resolution_note": "說明",
            },
            key=(
                "general_csv_asset_editor_"
                f'{prepared["file_fingerprint"]}_'
                f"{import_currency}"
            ),
        )
        validated_assets, asset_errors = (
            validate_asset_metadata(edited_assets)
        )

        if asset_errors:
            st.warning(
                "資產設定尚未完成："
                + "；".join(asset_errors)
            )

        st.markdown("### 交易預覽")
        preview_rows = records[
            [
                "source_row",
                "transaction_date",
                "import_type",
                "symbol",
                "asset_name",
                "quantity_delta",
                "unit_price",
                "fee_amount",
                "tax_amount",
                "cash_delta",
                "memo",
            ]
        ].copy()
        preview_rows["import_type"] = preview_rows[
            "import_type"
        ].map(IMPORT_TYPE_LABELS)
        preview_rows = preview_rows.rename(
            columns={
                "source_row": "CSV 列",
                "transaction_date": "交易日期",
                "import_type": "交易類型",
                "symbol": "代號",
                "asset_name": "資產名稱",
                "quantity_delta": "數量變動",
                "unit_price": "成交價格",
                "fee_amount": "費用",
                "tax_amount": "交易稅",
                "cash_delta": f"現金變動 {import_currency}",
                "memo": "備註",
            }
        )
        st.dataframe(
            preview_rows,
            width="stretch",
            hide_index=True,
        )

        if not asset_errors:
            st.success(
                "唯讀預覽完成。"
                "目前尚未寫入任何資料。"
            )

        st.divider()
        st.markdown("### 正式匯入")
        st.warning(
            "通用版只會新增資產與交易，"
            "不會刪除或取代帳戶中的既有資料。"
            "同一份 CSV 對同一證券帳戶只能匯入一次。"
        )
        confirm_import = st.checkbox(
            "我已核對交易、資產、報價代號與現金試算。",
            key=(
                "confirm_general_csv_"
                f'{prepared["file_fingerprint"]}'
            ),
        )

        if st.button(
            "正式匯入這份證券交易 CSV",
            type="primary",
            width="stretch",
            disabled=(
                not confirm_import
                or bool(asset_errors)
            ),
            key=(
                "execute_general_csv_import_"
                f'{prepared["file_fingerprint"]}'
            ),
        ):
            try:
                payload = build_standard_import_payload(
                    prepared,
                    validated_assets,
                    source_account_id=source_account["id"],
                )
                response = supabase.rpc(
                    "import_broker_csv_batch",
                    {
                        "p_source_account_id": source_account["id"],
                        "p_settlement_account_id": settlement_account["id"],
                        "p_cash_asset_id": cash_asset["id"],
                        "p_import_label": source_account["name"],
                        "p_import_currency": import_currency,
                        "p_target_cash_balance": float(
                            target_cash_balance
                        ),
                        "p_batch_reference": payload[
                            "batch_reference"
                        ],
                        "p_assets": payload["assets"],
                        "p_records": payload["records"],
                    },
                ).execute()
                result = response.data or {}
                st.session_state[
                    "transaction_success_message"
                ] = (
                    f'{source_account["name"]} CSV 匯入成功：'
                    f'{result.get("created_transactions", summary["valid_transaction_count"])} '
                    "筆交易；"
                    f'{result.get("created_assets", 0)} '
                    "項新資產；期末現金 "
                    f'{float(result.get("final_cash_balance", target_cash_balance)):,.2f} '
                    f"{import_currency}。"
                )
                st.rerun()
            except Exception as error:
                st.error(
                    "正式匯入失敗，資料庫已取消整批變更："
                    f"{error}"
                )
