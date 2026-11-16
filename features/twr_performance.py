import pandas as pd
import streamlit as st

from features.twr_cash_flows import (
    show_twr_cash_flow_manager,
)
from services.twr import calculate_twr
from services.benchmark_performance import (
    BENCHMARK_OPTIONS,
    build_benchmark_comparison,
)


def _load_twr_data(supabase):
    snapshots_response = (
        supabase
        .table("portfolio_snapshots")
        .select(
            "id, snapshot_date, data_complete"
        )
        .order(
            "snapshot_date"
        )
        .execute()
    )

    account_snapshots_response = (
        supabase
        .table("portfolio_snapshot_accounts")
        .select(
            "snapshot_id, account_id, "
            "total_assets_twd, data_complete"
        )
        .execute()
    )

    cash_flows_response = (
        supabase
        .table("portfolio_cash_flows")
        .select(
            "id, flow_at, flow_type, "
            "amount, currency, amount_twd, "
            "source_account_id, "
            "destination_account_id, notes"
        )
        .order(
            "flow_at"
        )
        .execute()
    )

    fx_rates_response = (
        supabase
        .table("fx_rates")
        .select(
            "from_currency, to_currency, "
            "rate, rate_date, source"
        )
        .order(
            "rate_date"
        )
        .execute()
    )

    return (
        snapshots_response.data or [],
        account_snapshots_response.data or [],
        cash_flows_response.data or [],
        fx_rates_response.data or [],
    )


def _build_twr_snapshot_rows(
    snapshots,
    account_snapshots,
):
    snapshot_map = {
        snapshot["id"]: snapshot
        for snapshot in snapshots
    }

    summary_map = {}

    for row in account_snapshots:
        snapshot_id = row.get("snapshot_id")

        if snapshot_id not in snapshot_map:
            continue

        snapshot = snapshot_map[snapshot_id]

        summary = summary_map.setdefault(
            snapshot_id,
            {
                "snapshot_date": snapshot[
                    "snapshot_date"
                ],
                "total_assets_twd": 0.0,
                "account_count": 0,
                "data_complete": bool(
                    snapshot.get(
                        "data_complete",
                        True,
                    )
                ),
            },
        )

        summary["total_assets_twd"] += float(
            row.get("total_assets_twd") or 0
        )

        summary["account_count"] += 1

        if not row.get("data_complete", True):
            summary["data_complete"] = False

    rows = list(summary_map.values())

    rows.sort(
        key=lambda row: row["snapshot_date"]
    )

    return rows


def show_twr_performance(supabase):
    st.subheader("TWR 時間加權報酬率")

    st.caption(
        "僅計算已勾選納入 TWR 的投資帳戶。"
        "帳戶內持有的現金、股票、ETF 及基金都會納入期末價值；"
        "只有跨越投資組合邊界的投入或取回才記為外部資金流。"
    )

    try:
        (
            snapshots,
            account_snapshots,
            cash_flows,
            fx_rates,
        ) = _load_twr_data(
            supabase
        )

    except Exception as error:
        st.error(
            f"讀取 TWR 資料失敗：{error}"
        )
        return

    twr_snapshot_rows = (
        _build_twr_snapshot_rows(
            snapshots,
            account_snapshots,
        )
    )

    complete_snapshot_rows = [
        row
        for row in twr_snapshot_rows
        if row["data_complete"]
    ]

    first_column, second_column, third_column = (
        st.columns(3)
    )

    first_column.metric(
        "有效快照日期",
        len(complete_snapshot_rows),
    )

    second_column.metric(
        "外部資金流筆數",
        len(cash_flows),
    )

    latest_value = (
        complete_snapshot_rows[-1][
            "total_assets_twd"
        ]
        if complete_snapshot_rows
        else None
    )

    third_column.metric(
        "最新 TWR 組合價值",
        (
            f"NT$ {latest_value:,.2f}"
            if latest_value is not None
            else "尚無資料"
        ),
    )

    if len(complete_snapshot_rows) < 2:
        st.info(
            "目前已建立 TWR 基準快照，但至少需要兩個不同日期的"
            "完整快照，才能計算第一個期間報酬率。"
        )

    else:
        try:
            twr_result = calculate_twr(
                complete_snapshot_rows,
                cash_flows,
            )

        except Exception as error:
            st.error(
                f"TWR 計算失敗：{error}"
            )

        else:
            twr_value = twr_result.get("twr")
            period_rows = (
                twr_result.get("period_rows")
                or []
            )
            warnings = (
                twr_result.get("warnings")
                or []
            )

            if twr_value is not None:
                st.metric(
                    "累積 TWR",
                    f"{twr_value:.2%}",
                )

            for warning in warnings:
                st.warning(warning)

            if period_rows:
                display_rows = []

                cumulative_return = 1.0

                for row in period_rows:
                    period_return = row.get(
                        "區間報酬率"
                    )

                    if period_return is not None:
                        cumulative_return *= (
                            1 + float(
                                period_return
                            )
                        )

                        cumulative_twr = (
                            cumulative_return - 1
                        )

                    else:
                        cumulative_twr = None

                    display_rows.append(
                        {
                            "開始日期": row.get(
                                "開始日期"
                            ),
                            "結束日期": row.get(
                                "結束日期"
                            ),
                            "期初價值 TWD": row.get(
                                "期初價值 TWD"
                            ),
                            "期末價值 TWD": row.get(
                                "期末價值 TWD"
                            ),
                            "外部投入 TWD": row.get(
                                "外部投入 TWD"
                            ),
                            "外部取回 TWD": row.get(
                                "外部取回 TWD"
                            ),
                            "投資損益 TWD": row.get(
                                "投資損益 TWD"
                            ),
                            "區間報酬率": (
                                float(period_return) * 100
                                if period_return is not None
                                else None
                            ),
                            "累積 TWR": (
                                cumulative_twr * 100
                                if cumulative_twr is not None
                                else None
                            ),
                            "狀態": row.get(
                                "狀態"
                            ),
                        }
                    )

                period_dataframe = pd.DataFrame(
                    display_rows
                )

                st.dataframe(
                    period_dataframe,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "期初價值 TWD":
                            st.column_config.NumberColumn(
                                format="%.2f",
                            ),
                        "期末價值 TWD":
                            st.column_config.NumberColumn(
                                format="%.2f",
                            ),
                        "外部投入 TWD":
                            st.column_config.NumberColumn(
                                format="%.2f",
                            ),
                        "外部取回 TWD":
                            st.column_config.NumberColumn(
                                format="%.2f",
                            ),
                        "投資損益 TWD":
                            st.column_config.NumberColumn(
                                format="%.2f",
                            ),
                        "區間報酬率":
                            st.column_config.NumberColumn(
                                format="%.2f%%",
                            ),
                        "累積 TWR":
                            st.column_config.NumberColumn(
                                format="%.2f%%",
                            ),
                    },
                )

                st.markdown(
                    "### TWR 與大盤比較"
                )

                st.caption(
                    "投資組合與基準均從共同起始日"
                    "標準化為 100。VT 與 SPY 會使用"
                    "當日或之前最近的 USD/TWD 匯率；"
                    "基準價格為含股利與分割調整後價格。"
                )

                selected_benchmark = (
                    st.selectbox(
                        "比較基準",
                        options=list(
                            BENCHMARK_OPTIONS.keys()
                        ),
                        format_func=lambda key: (
                            BENCHMARK_OPTIONS[
                                key
                            ]["label"]
                        ),
                        key=(
                            "selected_twr_benchmark"
                        ),
                    )
                )

                try:
                    benchmark_result = (
                        build_benchmark_comparison(
                            complete_snapshot_rows,
                            period_rows,
                            fx_rates,
                            selected_benchmark,
                        )
                    )

                except Exception as error:
                    st.warning(
                        "目前無法建立大盤比較："
                        f"{error}"
                    )

                else:
                    for warning in (
                        benchmark_result.get(
                            "warnings"
                        )
                        or []
                    ):
                        st.warning(warning)

                    comparison_rows = (
                        benchmark_result.get(
                            "comparison_rows"
                        )
                        or []
                    )

                    if len(comparison_rows) < 2:
                        st.info(
                            "至少需要兩個可比較日期，"
                            "才能顯示投資組合與大盤"
                            "的績效比較。"
                        )

                    else:
                        latest_comparison = (
                            comparison_rows[-1]
                        )

                        portfolio_return = (
                            latest_comparison[
                                "投資組合累積 TWR"
                            ]
                        )

                        benchmark_return = (
                            latest_comparison[
                                "基準累積報酬率"
                            ]
                        )

                        excess_return = (
                            latest_comparison[
                                "超額報酬"
                            ]
                        )

                        (
                            portfolio_column,
                            benchmark_column,
                            excess_column,
                        ) = st.columns(3)

                        portfolio_column.metric(
                            "投資組合累積 TWR",
                            (
                                f"{portfolio_return:.2%}"
                                if portfolio_return
                                is not None
                                else "—"
                            ),
                        )

                        benchmark_column.metric(
                            (
                                BENCHMARK_OPTIONS[
                                    selected_benchmark
                                ]["label"]
                            ),
                            (
                                f"{benchmark_return:.2%}"
                            ),
                        )

                        excess_column.metric(
                            "超額報酬",
                            (
                                f"{excess_return:+.2%}"
                                if excess_return
                                is not None
                                else "—"
                            ),
                            help=(
                                "投資組合累積 TWR "
                                "減去基準累積報酬率。"
                            ),
                        )

                        chart_rows = []

                        for row in comparison_rows:
                            chart_rows.append(
                                {
                                    "日期": row[
                                        "日期"
                                    ],
                                    "投資組合": row[
                                        "投資組合指數"
                                    ],
                                    "大盤基準": row[
                                        "基準指數"
                                    ],
                                }
                            )

                        comparison_chart = (
                            pd.DataFrame(
                                chart_rows
                            )
                        )

                        comparison_chart[
                            "日期"
                        ] = pd.to_datetime(
                            comparison_chart[
                                "日期"
                            ]
                        )

                        comparison_chart = (
                            comparison_chart
                            .set_index("日期")
                        )

                        st.line_chart(
                            comparison_chart,
                            y=[
                                "投資組合",
                                "大盤基準",
                            ],
                        )

                        comparison_display_rows = []

                        for row in comparison_rows:
                            comparison_display_rows.append(
                                {
                                    "日期": row[
                                        "日期"
                                    ],
                                    "投資組合累積 TWR":
                                        (
                                            row[
                                                "投資組合累積 TWR"
                                            ]
                                            * 100
                                            if row[
                                                "投資組合累積 TWR"
                                            ]
                                            is not None
                                            else None
                                        ),
                                    "基準累積報酬率":
                                        (
                                            row[
                                                "基準累積報酬率"
                                            ]
                                            * 100
                                        ),
                                    "超額報酬":
                                        (
                                            row[
                                                "超額報酬"
                                            ]
                                            * 100
                                            if row[
                                                "超額報酬"
                                            ]
                                            is not None
                                            else None
                                        ),
                                    "投資組合指數":
                                        row[
                                            "投資組合指數"
                                        ],
                                    "基準指數":
                                        row[
                                            "基準指數"
                                        ],
                                    "基準價格日期":
                                        row[
                                            "基準價格日期"
                                        ],
                                    "基準調整後價格":
                                        row[
                                            "基準調整後價格"
                                        ],
                                    "匯率日期":
                                        row[
                                            "匯率日期"
                                        ],
                                    "匯率":
                                        row["匯率"],
                                }
                            )

                        with st.expander(
                            "查看大盤比較明細",
                            expanded=False,
                        ):
                            st.dataframe(
                                pd.DataFrame(
                                    comparison_display_rows
                                ),
                                width="stretch",
                                hide_index=True,
                                column_config={
                                    "投資組合累積 TWR":
                                        st.column_config.NumberColumn(
                                            format="%.2f%%",
                                        ),
                                    "基準累積報酬率":
                                        st.column_config.NumberColumn(
                                            format="%.2f%%",
                                        ),
                                    "超額報酬":
                                        st.column_config.NumberColumn(
                                            format="%.2f%%",
                                        ),
                                    "投資組合指數":
                                        st.column_config.NumberColumn(
                                            format="%.4f",
                                        ),
                                    "基準指數":
                                        st.column_config.NumberColumn(
                                            format="%.4f",
                                        ),
                                    "基準調整後價格":
                                        st.column_config.NumberColumn(
                                            format="%.6f",
                                        ),
                                    "匯率":
                                        st.column_config.NumberColumn(
                                            format="%.6f",
                                        ),
                                },
                            )

    with st.expander(
        "查看 TWR 快照紀錄",
        expanded=False,
    ):
        if twr_snapshot_rows:
            snapshot_dataframe = pd.DataFrame(
                twr_snapshot_rows
            )

            snapshot_dataframe = (
                snapshot_dataframe.rename(
                    columns={
                        "snapshot_date":
                            "快照日期",
                        "total_assets_twd":
                            "投資組合價值 TWD",
                        "account_count":
                            "帳戶數量",
                        "data_complete":
                            "資料完整",
                    }
                )
            )

            st.dataframe(
                snapshot_dataframe,
                width="stretch",
                hide_index=True,
                column_config={
                    "投資組合價值 TWD":
                        st.column_config.NumberColumn(
                            format="%.2f",
                        ),
                },
            )

        else:
            st.info(
                "目前尚無投資帳戶快照。"
            )

    st.divider()

    show_twr_cash_flow_manager(
        supabase
    )