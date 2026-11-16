import pandas as pd
import streamlit as st

from services.portfolio_valuation import (
    calculate_portfolio_valuation,
)


def _load_table(supabase, table_name):
    response = (
        supabase.table(table_name)
        .select("*")
        .execute()
    )
    return response.data or []


def show_institution_overview(supabase):
    st.subheader("金融機構與帳戶總覽")
    st.caption(
        "依金融機構彙整旗下帳戶及資產價值。"
        "機構與帳戶合計均換算為 TWD；"
        "資產明細同時保留原始幣別。"
    )

    try:
        institutions = _load_table(
            supabase,
            "financial_institutions",
        )
        accounts = _load_table(
            supabase,
            "accounts",
        )
        assets = _load_table(
            supabase,
            "assets",
        )
        entries = _load_table(
            supabase,
            "transaction_entries",
        )
        prices = _load_table(
            supabase,
            "asset_prices",
        )
        fx_rates = _load_table(
            supabase,
            "fx_rates",
        )

    except Exception as exc:
        st.error(
            f"金融機構總覽資料讀取失敗：{exc}"
        )
        return

    if not accounts:
        st.info("目前尚未建立帳戶。")
        return

    try:
        valuation_result = (
            calculate_portfolio_valuation(
                accounts=accounts,
                assets=assets,
                entries=entries,
                prices=prices,
                fx_rates=fx_rates,
            )
        )
    except Exception as exc:
        st.error(f"資產估值失敗：{exc}")
        return

    valuation_rows = valuation_result.get(
        "valuation_rows",
        [],
    )

    missing_price_assets = valuation_result.get(
        "missing_price_assets",
        [],
    )
    missing_fx_currencies = valuation_result.get(
        "missing_fx_currencies",
        [],
    )

    # 目前估值服務的明細以帳戶名稱識別。
    # 建立帳戶名稱對應，供階層總覽分組使用。
    account_value_map = {}
    account_asset_rows = {}

    for row in valuation_rows:
        account_name = row.get("帳戶", "")

        if not account_name:
            continue

        account_asset_rows.setdefault(
            account_name,
            [],
        ).append(row)

        market_value_twd = row.get("TWD 市值")

        if market_value_twd is not None:
            account_value_map[account_name] = (
                account_value_map.get(
                    account_name,
                    0.0,
                )
                + float(market_value_twd)
            )

    active_accounts = [
        account
        for account in accounts
        if account.get("is_active", True)
    ]

    institution_map = {
        institution["id"]: institution
        for institution in institutions
    }

    accounts_by_institution = {}

    for account in active_accounts:
        institution_id = account.get(
            "institution_id"
        )

        if institution_id in institution_map:
            group_key = institution_id
        else:
            group_key = "__unassigned__"

        accounts_by_institution.setdefault(
            group_key,
            [],
        ).append(account)

    if not accounts_by_institution:
        st.info("目前沒有使用中的帳戶。")
        return

    if missing_price_assets:
        st.warning(
            "部分資產缺少價格，因此相關帳戶及金融機構"
            "的合計可能不完整："
            + "、".join(missing_price_assets)
        )

    if missing_fx_currencies:
        st.warning(
            "部分幣別缺少匯率，因此相關帳戶及金融機構"
            "的合計可能不完整："
            + "、".join(missing_fx_currencies)
        )

    institution_groups = []

    for group_key, group_accounts in (
        accounts_by_institution.items()
    ):
        if group_key == "__unassigned__":
            institution_name = "尚未歸類"
            institution_type = "未設定"
        else:
            institution = institution_map[
                group_key
            ]
            institution_name = institution["name"]
            institution_type = institution.get(
                "institution_type",
                "other",
            )

        institution_total = sum(
            account_value_map.get(
                account["name"],
                0.0,
            )
            for account in group_accounts
        )

        institution_groups.append(
            {
                "group_key": group_key,
                "institution_name": (
                    institution_name
                ),
                "institution_type": (
                    institution_type
                ),
                "accounts": group_accounts,
                "total_twd": institution_total,
            }
        )

    institution_groups.sort(
        key=lambda group: group["total_twd"],
        reverse=True,
    )

    summary_rows = []

    for group in institution_groups:
        summary_rows.append(
            {
                "金融機構": (
                    group["institution_name"]
                ),
                "帳戶數量": len(
                    group["accounts"]
                ),
                "合計 TWD": group["total_twd"],
            }
        )

    st.dataframe(
        pd.DataFrame(summary_rows),
        width="stretch",
        hide_index=True,
        column_config={
            "帳戶數量": st.column_config.NumberColumn(
                "帳戶數量",
                format="%d",
            ),
            "合計 TWD": st.column_config.NumberColumn(
                "合計 TWD",
                format="%.2f",
            ),
        },
    )

    st.markdown("### 金融機構明細")

    for group_index, group in enumerate(
        institution_groups
    ):
        institution_name = group[
            "institution_name"
        ]
        institution_total = group["total_twd"]
        group_accounts = group["accounts"]

        expander_label = (
            f"{institution_name}｜"
            f"{institution_total:,.2f} TWD｜"
            f"{len(group_accounts)} 個帳戶"
        )

        with st.expander(
            expander_label,
            expanded=False,
        ):
            account_rows = []

            for account in sorted(
                group_accounts,
                key=lambda item: item["name"],
            ):
                account_name = account["name"]
                asset_rows = account_asset_rows.get(
                    account_name,
                    [],
                )

                incomplete_count = sum(
                    1
                    for row in asset_rows
                    if row.get("估值狀態")
                    != "已估值"
                )

                account_rows.append(
                    {
                        "帳戶": account_name,
                        "帳戶類型": account.get(
                            "account_type",
                            "",
                        ),
                        "主要幣別": account.get(
                            "base_currency",
                            "",
                        ),
                        "資產項目": len(asset_rows),
                        "帳戶價值 TWD": (
                            account_value_map.get(
                                account_name,
                                0.0,
                            )
                        ),
                        "未完成估值": (
                            incomplete_count
                        ),
                    }
                )

            st.dataframe(
                pd.DataFrame(account_rows),
                width="stretch",
                hide_index=True,
                column_config={
                    "資產項目":
                        st.column_config.NumberColumn(
                            "資產項目",
                            format="%d",
                        ),
                    "帳戶價值 TWD":
                        st.column_config.NumberColumn(
                            "帳戶價值 TWD",
                            format="%.2f",
                        ),
                    "未完成估值":
                        st.column_config.NumberColumn(
                            "未完成估值",
                            format="%d",
                        ),
                },
            )

            account_options = [
                account["name"]
                for account in sorted(
                    group_accounts,
                    key=lambda item: item["name"],
                )
            ]

            selected_account_name = st.selectbox(
                "查看帳戶資產",
                options=account_options,
                key=(
                    "institution_overview_account_"
                    f"{group_index}"
                ),
            )

            selected_asset_rows = (
                account_asset_rows.get(
                    selected_account_name,
                    [],
                )
            )

            if not selected_asset_rows:
                st.info(
                    "此帳戶目前沒有可顯示的"
                    "資產餘額或持倉。"
                )

            else:
                asset_dataframe = pd.DataFrame(
                    selected_asset_rows
                )

                visible_columns = [
                    "資產類型",
                    "資產代號",
                    "資產名稱",
                    "數量／餘額",
                    "幣別",
                    "單位價格",
                    "原幣市值",
                    "匯率",
                    "TWD 市值",
                    "估值狀態",
                ]

                visible_columns = [
                    column
                    for column in visible_columns
                    if column
                    in asset_dataframe.columns
                ]

                asset_dataframe = (
                    asset_dataframe[
                        visible_columns
                    ]
                )

                st.dataframe(
                    asset_dataframe,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "數量／餘額":
                            st.column_config.NumberColumn(
                                "數量／餘額",
                                format="%.6f",
                            ),
                        "單位價格":
                            st.column_config.NumberColumn(
                                "單位價格",
                                format="%.4f",
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