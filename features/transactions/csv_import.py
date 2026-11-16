import pandas as pd
import streamlit as st

from services.yushan_csv_import import (
    build_yushan_import_payload,
    prepare_yushan_csv_import,
)


IMPORT_TYPE_LABELS = {
    "buy": "買入",
    "sell": "賣出",
    "cash_dividend": "現金股利",
    "stock_dividend": "股票股利",
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


def show_yushan_csv_import_preview(
    supabase,
    accounts,
    assets,
):
    with st.expander(
        "玉山證券歷史交易 CSV 匯入",
        expanded=False,
    ):
        st.caption(
            "先解析、核對交易與試算現金。"
            "目前不會新增、修改或刪除資料。"
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
            index=_default_index(
                active_accounts,
                "玉山證券",
            ),
            format_func=_format_account,
            key="yushan_csv_source_account",
        )

        settlement_account = st.selectbox(
            "連動現金帳戶",
            options=active_accounts,
            index=_default_index(
                active_accounts,
                "玉山銀行 臺幣",
            ),
            format_func=_format_account,
            key="yushan_csv_settlement_account",
        )

        cash_asset = st.selectbox(
            "連動現金資產",
            options=active_cash_assets,
            index=_default_index(
                active_cash_assets,
                "新台幣現金",
            ),
            format_func=_format_asset,
            key="yushan_csv_cash_asset",
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
                "預設使用目前系統餘額。"
                "正式匯入時會建立一筆期末校正，"
                "使現金回到此金額。"
            ),
            key="yushan_csv_target_cash_balance",
        )

        uploaded_file = st.file_uploader(
            "選擇修正版玉山交易紀錄 CSV",
            type=["csv"],
            key="yushan_transaction_csv",
        )

        if uploaded_file is None:
            st.info("上傳 CSV 後才會進行預覽。")
            return

        try:
            prepared = prepare_yushan_csv_import(
                uploaded_file
            )

        except Exception as error:
            st.error(f"CSV 解析失敗：{error}")
            return

        summary = prepared["summary"]
        records = prepared["records"].copy()
        asset_rows = prepared["assets"].copy()

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
                    "交易類型": "一般買入",
                    "筆數": summary["buy_count"],
                },
                {
                    "交易類型": "賣出",
                    "筆數": summary["sell_count"],
                },
                {
                    "交易類型": "現金股利",
                    "筆數": summary[
                        "cash_dividend_count"
                    ],
                },
                {
                    "交易類型": "股票股利",
                    "筆數": summary[
                        "stock_dividend_count"
                    ],
                },
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
            + summary["net_cash_delta_twd"]
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
                    "金額 TWD": current_cash_balance,
                },
                {
                    "項目": "歷史買入支出",
                    "金額 TWD": -summary[
                        "buy_outflow_twd"
                    ],
                },
                {
                    "項目": "歷史賣出收入",
                    "金額 TWD": summary[
                        "sell_inflow_twd"
                    ],
                },
                {
                    "項目": "歷史現金股利",
                    "金額 TWD": summary[
                        "dividend_inflow_twd"
                    ],
                },
                {
                    "項目": "校正前試算餘額",
                    "金額 TWD": projected_cash_balance,
                },
                {
                    "項目": "匯入後現金校正",
                    "金額 TWD": adjustment_amount,
                },
                {
                    "項目": "校正後期末餘額",
                    "金額 TWD": final_cash_balance,
                },
            ]
        )

        st.dataframe(
            cash_rows,
            width="stretch",
            hide_index=True,
            column_config={
                "金額 TWD": (
                    st.column_config.NumberColumn(
                        "金額 TWD",
                        format="%.2f",
                    )
                ),
            },
        )

        if projected_cash_balance < 0:
            st.warning(
                "依歷史交易逐筆加入時，校正前現金會"
                f"暫時變成 {projected_cash_balance:,.2f} TWD。"
                "正式匯入會在同一批次加入期末現金校正，"
                "不會讓最終餘額停留在負數。"
            )

        existing_symbols = {
            str(asset.get("symbol") or "").strip()
            for asset in assets
            if asset.get("currency") == "TWD"
        }

        asset_rows["系統狀態"] = (
            asset_rows["symbol"].map(
                lambda symbol: (
                    "已存在"
                    if symbol in existing_symbols
                    else "待新增"
                )
            )
        )

        missing_asset_count = int(
            (asset_rows["系統狀態"] == "待新增").sum()
        )

        st.markdown("### 資產檢查")
        st.caption(
            f"共 {len(asset_rows)} 項；"
            f"其中 {missing_asset_count} 項待新增。"
        )

        asset_display_rows = asset_rows[
            [
                "symbol",
                "name",
                "asset_type",
                "market",
                "external_symbol",
                "系統狀態",
            ]
        ].copy()

        asset_display_rows["asset_type"] = (
            asset_display_rows["asset_type"].map(
                {
                    "stock": "股票",
                    "etf": "ETF",
                }
            )
        )

        st.dataframe(
            asset_display_rows.rename(
                columns={
                    "symbol": "代號",
                    "name": "資產名稱",
                    "asset_type": "資產類型",
                    "market": "市場",
                    "external_symbol": "外部報價代號",
                }
            ),
            width="stretch",
            hide_index=True,
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
                "cash_delta_twd",
                "memo",
            ]
        ].copy()

        preview_rows["import_type"] = (
            preview_rows["import_type"].map(
                IMPORT_TYPE_LABELS
            )
        )

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
                "cash_delta_twd": "現金變動 TWD",
                "memo": "備註",
            }
        )

        st.dataframe(
            preview_rows,
            width="stretch",
            hide_index=True,
        )

        st.success(
            "唯讀預覽完成。"
            "目前尚未寫入任何交易或資產。"
        )

        st.divider()
        st.markdown("### 正式匯入")
        st.warning(
            "正式匯入會以這份 CSV 取代玉山證券目前的"
            "18 筆舊交易，新增缺少的資產，匯入 193 筆"
            "交易，並將玉山銀行現金校正到上方目標。"
            "所有動作會在同一個資料庫交易中完成；"
            "若任何一步失敗，整批都不會生效。"
        )

        confirm_preview = st.checkbox(
            "我已核對交易筆數、資產清單與現金試算。",
            key="confirm_yushan_csv_preview",
        )
        confirm_replace = st.checkbox(
            "我確認以 CSV 永久取代玉山證券目前的 18 筆舊交易。",
            key="confirm_yushan_csv_replace",
        )

        import_disabled = not (
            confirm_preview
            and confirm_replace
            and summary["valid_transaction_count"] == 193
            and summary["asset_count"] == 26
            and missing_asset_count == 23
        )

        if st.button(
            "正式匯入玉山證券歷史交易",
            type="primary",
            width="stretch",
            disabled=import_disabled,
            key="execute_yushan_csv_import",
        ):
            try:
                payload = build_yushan_import_payload(
                    prepared
                )

                response = supabase.rpc(
                    "import_yushan_csv_batch",
                    {
                        "p_source_account_id": (
                            source_account["id"]
                        ),
                        "p_settlement_account_id": (
                            settlement_account["id"]
                        ),
                        "p_cash_asset_id": cash_asset["id"],
                        "p_target_cash_balance": float(
                            target_cash_balance
                        ),
                        "p_expected_old_count": 18,
                        "p_assets": payload["assets"],
                        "p_records": payload["records"],
                    },
                ).execute()

                result = response.data or {}

                st.session_state[
                    "transaction_success_message"
                ] = (
                    "玉山證券歷史交易匯入成功："
                    f'{result.get("created_transactions", 193)} '
                    "筆交易；"
                    f'{result.get("created_assets", 23)} '
                    "項新資產；期末現金 "
                    f'{float(result.get("final_cash_balance", target_cash_balance)):,.2f} '
                    "TWD。"
                )

                st.rerun()

            except Exception as error:
                st.error(
                    "正式匯入失敗，資料庫已取消整批變更："
                    f"{error}"
                )
