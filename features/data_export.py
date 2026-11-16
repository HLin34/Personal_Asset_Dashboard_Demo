from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from services.data_exports import (
    dataframe_to_csv_bytes,
    dataframes_to_excel_bytes,
    dataframes_to_zip_bytes,
)

from services.data_imports import (
    analyze_restore_conflicts,
    build_add_only_restore_plan,
    execute_add_only_restore,
    validate_backup_zip,
)

from services.portfolio_valuation import (
    calculate_portfolio_valuation,
)

from services.performance_reports import (
    build_investment_performance_reports,
)


EXPORT_TABLES = (
    {
        "table_name": "accounts",
        "label": "帳戶",
        "excel_sheet": "帳戶",
    },
    {
        "table_name": "assets",
        "label": "資產",
        "excel_sheet": "資產",
    },
    {
        "table_name": "transactions",
        "label": "交易主紀錄",
        "excel_sheet": "交易主紀錄",
    },
    {
        "table_name": "transaction_entries",
        "label": "交易明細",
        "excel_sheet": "交易明細",
    },
    {
        "table_name": "asset_prices",
        "label": "資產價格",
        "excel_sheet": "資產價格",
    },
    {
        "table_name": "fx_rates",
        "label": "匯率",
        "excel_sheet": "匯率",
    },
    {
        "table_name": "broker_fee_settings",
        "label": "券商費率設定",
        "excel_sheet": "券商費率",
    },
    {
        "table_name": "portfolio_snapshots",
        "label": "資產快照",
        "excel_sheet": "資產快照",
    },
)

def _dataframe_to_records(dataframe):
    """
    將 DataFrame 轉回資料庫形式的 records，
    並把 Pandas NaN／NaT 還原成 None。
    """
    normalized_dataframe = (
        dataframe.astype(object)
        .where(
            pd.notna(dataframe),
            None,
        )
    )

    return normalized_dataframe.to_dict(
        orient="records"
    )


def _fetch_all_rows(
    supabase,
    table_name,
    page_size=1000,
):
    """
    分頁讀取資料表，避免只取得 Supabase
    預設回傳的前 1,000 筆資料。
    """
    all_rows = []
    start_index = 0

    while True:
        end_index = (
            start_index
            + page_size
            - 1
        )

        response = (
            supabase.table(table_name)
            .select("*")
            .range(
                start_index,
                end_index,
            )
            .execute()
        )

        page_rows = response.data or []

        all_rows.extend(page_rows)

        if len(page_rows) < page_size:
            break

        start_index += page_size

    return all_rows


def _load_export_data(supabase):
    """
    讀取所有已知資料表。

    單一資料表讀取失敗時，記錄錯誤並繼續
    處理其他資料表。
    """
    loaded_tables = {}
    loading_errors = []

    for table_config in EXPORT_TABLES:
        table_name = table_config["table_name"]

        try:
            rows = _fetch_all_rows(
                supabase,
                table_name,
            )

            loaded_tables[table_name] = {
                "config": table_config,
                "dataframe": pd.DataFrame(
                    rows
                ),
            }

        except Exception as error:
            loading_errors.append(
                {
                    "table_name": table_name,
                    "label": table_config[
                        "label"
                    ],
                    "error": str(error),
                }
            )

    return loaded_tables, loading_errors


def show_data_export_manager(supabase):
    st.subheader("資料匯出與備份")

    st.caption(
        "可下載單一 CSV、完整 Excel 活頁簿，"
        "或包含原始資料表的 ZIP 備份。"
        "匯出內容包含個人財務資料，請妥善保管。"
    )

    restore_success_message = st.session_state.pop(
        "restore_success_message",
        None,
    )

    if restore_success_message:
        st.success(restore_success_message)

    with st.spinner("正在讀取可匯出的資料……"):
        (
            loaded_tables,
            loading_errors,
        ) = _load_export_data(
            supabase
        )

    if loading_errors:
        with st.expander(
            "部分資料表無法讀取",
            expanded=False,
        ):
            st.warning(
                "下列資料表未納入本次匯出。"
                "如果該功能尚未建立，可以忽略。"
            )

            for error_record in loading_errors:
                st.write(
                    f'- {error_record["label"]} '
                    f'(`{error_record["table_name"]}`)：'
                    f'{error_record["error"]}'
                )

    if not loaded_tables:
        st.error(
            "目前沒有成功讀取任何資料表，"
            "無法建立匯出檔案。"
        )
        return

    valuation_report = None
    valuation_report_error = None

    required_valuation_tables = {
        "accounts",
        "assets",
        "transaction_entries",
        "asset_prices",
        "fx_rates",
    }

    missing_valuation_tables = (
        required_valuation_tables
        - set(loaded_tables.keys())
    )

    if missing_valuation_tables:
        valuation_report_error = (
            "缺少建立資產估值報表所需的資料表："
            + "、".join(
                sorted(
                    missing_valuation_tables
                )
            )
        )

    else:
        try:
            valuation_report = (
                calculate_portfolio_valuation(
                    accounts=_dataframe_to_records(
                        loaded_tables[
                            "accounts"
                        ]["dataframe"]
                    ),
                    assets=_dataframe_to_records(
                        loaded_tables[
                            "assets"
                        ]["dataframe"]
                    ),
                    entries=_dataframe_to_records(
                        loaded_tables[
                            "transaction_entries"
                        ]["dataframe"]
                    ),
                    prices=_dataframe_to_records(
                        loaded_tables[
                            "asset_prices"
                        ]["dataframe"]
                    ),
                    fx_rates=_dataframe_to_records(
                        loaded_tables[
                            "fx_rates"
                        ]["dataframe"]
                    ),
                )
            )

        except Exception as error:
            valuation_report_error = str(error)

    if valuation_report_error:
        st.warning(
            "可讀版資產估值報表暫時無法建立："
            f"{valuation_report_error}。"
            "原始 CSV、Excel 工作表與 ZIP 備份"
            "仍可正常下載。"
        )    

    export_datetime = datetime.now(
        ZoneInfo("America/Los_Angeles")
    )

    export_date_text = (
        export_datetime.strftime(
            "%Y-%m-%d"
        )
    )

    performance_report = None
    performance_report_error = None

    required_performance_tables = {
        "accounts",
        "assets",
        "transactions",
        "transaction_entries",
        "asset_prices",
        "fx_rates",
    }

    missing_performance_tables = (
        required_performance_tables
        - set(loaded_tables.keys())
    )

    if missing_performance_tables:
        performance_report_error = (
            "缺少建立投資績效報表所需的資料表："
            + "、".join(
                sorted(
                    missing_performance_tables
                )
            )
        )

    else:
        try:
            performance_report = (
                build_investment_performance_reports(
                    accounts=_dataframe_to_records(
                        loaded_tables[
                            "accounts"
                        ]["dataframe"]
                    ),
                    assets=_dataframe_to_records(
                        loaded_tables[
                            "assets"
                        ]["dataframe"]
                    ),
                    transactions=_dataframe_to_records(
                        loaded_tables[
                            "transactions"
                        ]["dataframe"]
                    ),
                    entries=_dataframe_to_records(
                        loaded_tables[
                            "transaction_entries"
                        ]["dataframe"]
                    ),
                    prices=_dataframe_to_records(
                        loaded_tables[
                            "asset_prices"
                        ]["dataframe"]
                    ),
                    fx_rates=_dataframe_to_records(
                        loaded_tables[
                            "fx_rates"
                        ]["dataframe"]
                    ),
                    valuation_date=(
                        export_datetime.date()
                    ),
                )
            )

        except Exception as error:
            performance_report_error = str(
                error
            )

    if performance_report_error:
        st.warning(
            "投資績效匯出報表暫時無法建立："
            f"{performance_report_error}。"
            "其他匯出與原始 ZIP 備份仍可正常使用。"
        )

    performance_dataframe = pd.DataFrame()
    annual_dividend_dataframe = (
        pd.DataFrame()
    )
    xirr_cash_flow_dataframe = (
        pd.DataFrame()
    )

    if performance_report is not None:
        performance_dataframe = pd.DataFrame(
            performance_report[
                "performance_rows"
            ]
        )

        performance_dataframe = (
            performance_dataframe.drop(
                columns=[
                    "account_id",
                    "asset_id",
                ],
                errors="ignore",
            )
        )

        annual_dividend_dataframe = (
            pd.DataFrame(
                performance_report[
                    "annual_dividend_rows"
                ]
            )
        )

        xirr_cash_flow_dataframe = (
            pd.DataFrame(
                performance_report[
                    "xirr_cash_flow_rows"
                ]
            )
        )

    st.subheader("本次匯出內容")

    summary_rows = []

    for table_name, table_record in (
        loaded_tables.items()
    ):
        config = table_record["config"]
        dataframe = table_record[
            "dataframe"
        ]

        summary_rows.append(
            {
                "資料類別": config["label"],
                "資料表": table_name,
                "資料筆數": len(dataframe),
                "欄位數量": len(
                    dataframe.columns
                ),
            }
        )

    summary_dataframe = pd.DataFrame(
        summary_rows
    )

    st.dataframe(
        summary_dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "資料筆數": (
                st.column_config.NumberColumn(
                    "資料筆數",
                    format="%d",
                )
            ),
            "欄位數量": (
                st.column_config.NumberColumn(
                    "欄位數量",
                    format="%d",
                )
            ),
        },
    )

    st.divider()
    st.subheader("下載單一 CSV")

    csv_datasets = {}

    if valuation_report is not None:
        csv_datasets[
            "report_asset_overview"
        ] = {
            "label": "資產總覽",
            "filename": "asset_overview",
            "dataframe": pd.DataFrame(
                valuation_report[
                    "overview_rows"
                ]
            ),
        }

        csv_datasets[
            "report_account_balances"
        ] = {
            "label": "帳戶目前餘額",
            "filename": "account_balances",
            "dataframe": pd.DataFrame(
                valuation_report[
                    "account_summary_rows"
                ]
            ),
        }

        csv_datasets[
            "report_asset_valuation"
        ] = {
            "label": "資產估值明細",
            "filename": "asset_valuation",
            "dataframe": pd.DataFrame(
                valuation_report[
                    "valuation_rows"
                ]
            ),
        }

    if performance_report is not None:
        csv_datasets[
            "report_investment_performance"
        ] = {
            "label": "投資績效",
            "filename": (
                "investment_performance"
            ),
            "dataframe": (
                performance_dataframe
            ),
        }

        csv_datasets[
            "report_annual_dividends"
        ] = {
            "label": "年度股利",
            "filename": (
                "annual_dividends"
            ),
            "dataframe": (
                annual_dividend_dataframe
            ),
        }

        csv_datasets[
            "report_xirr_cash_flows"
        ] = {
            "label": "XIRR 現金流",
            "filename": (
                "xirr_cash_flows"
            ),
            "dataframe": (
                xirr_cash_flow_dataframe
            ),
        }

    for table_name, table_record in (
        loaded_tables.items()
    ):
        csv_datasets[
            f"raw_{table_name}"
        ] = {
            "label": (
                "原始資料－"
                + table_record[
                    "config"
                ]["label"]
            ),
            "filename": table_name,
            "dataframe": table_record[
                "dataframe"
            ],
        }

    available_dataset_keys = list(
        csv_datasets.keys()
    )

    def format_dataset_name(dataset_key):
        return csv_datasets[
            dataset_key
        ]["label"]

    selected_dataset_key = st.selectbox(
        "選擇資料類別",
        options=available_dataset_keys,
        format_func=format_dataset_name,
        key="export_selected_dataset",
    )

    selected_dataset = csv_datasets[
        selected_dataset_key
    ]

    selected_dataframe = selected_dataset[
        "dataframe"
    ]

    selected_label = selected_dataset[
        "label"
    ]

    selected_filename = selected_dataset[
        "filename"
    ]

    st.caption(
        f"{selected_label}："
        f"{len(selected_dataframe):,} 筆資料"
    )

    csv_bytes = dataframe_to_csv_bytes(
        selected_dataframe,
        protect_formulas=True,
    )

    st.download_button(
        label=f"下載 {selected_label} CSV",
        data=csv_bytes,
        file_name=(
            f"{selected_filename}_"
            f"{export_date_text}.csv"
        ),
        mime="text/csv",
        use_container_width=True,
        key="download_single_csv",
    )

    st.divider()
    st.subheader("下載完整 Excel 報表")

    st.caption(
        "Excel 包含資產總覽、帳戶餘額、"
        "資產估值、投資績效、年度股利、"
        "XIRR 現金流及各張原始資料表。"
    )

    excel_dataframes = {
        "匯出說明": pd.DataFrame(
            [
                {
                    "項目": "匯出時間",
                    "內容": (
                        export_datetime.isoformat()
                    ),
                },
                {
                    "項目": "時區",
                    "內容": (
                        "America/Los_Angeles"
                    ),
                },
                {
                    "項目": "用途",
                    "內容": (
                        "個人資產資料閱讀與分析"
                    ),
                },
                {
                    "項目": "注意事項",
                    "內容": (
                        "不同幣別不應直接相加"
                    ),
                },
            ]
        )
    }

    if valuation_report is not None:
        excel_dataframes[
            "資產總覽"
        ] = pd.DataFrame(
            valuation_report[
                "overview_rows"
            ]
        )

        excel_dataframes[
            "帳戶目前餘額"
        ] = pd.DataFrame(
            valuation_report[
                "account_summary_rows"
            ]
        )

        excel_dataframes[
            "資產估值明細"
        ] = pd.DataFrame(
            valuation_report[
                "valuation_rows"
            ]
        )

    if performance_report is not None:
        excel_dataframes[
            "投資績效"
        ] = performance_dataframe

        excel_dataframes[
            "年度股利"
        ] = annual_dividend_dataframe

        excel_dataframes[
            "XIRR現金流"
        ] = xirr_cash_flow_dataframe    
    
    for table_record in (
        loaded_tables.values()
    ):
        sheet_name = table_record[
            "config"
        ]["excel_sheet"]

        excel_dataframes[sheet_name] = (
            table_record["dataframe"]
        )

    try:
        excel_bytes = (
            dataframes_to_excel_bytes(
                excel_dataframes
            )
        )

        st.download_button(
            label="下載完整 Excel 報表",
            data=excel_bytes,
            file_name=(
                "personal_asset_report_"
                f"{export_date_text}.xlsx"
            ),
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
            use_container_width=True,
            key="download_complete_excel",
        )

    except Exception as error:
        st.error(
            f"建立 Excel 報表失敗：{error}"
        )

    st.divider()
    st.subheader("下載完整原始資料備份")

    st.caption(
        "ZIP 內每張 Supabase 資料表各有一個 "
        "CSV 與還原用 JSON，並附帶 manifest.json。"
        "此版本保留原始 UUID 與關聯欄位，"
        "較適合未來移轉或還原資料。"
    )

    backup_dataframes = {
        table_name: table_record[
            "dataframe"
        ]
        for table_name, table_record
        in loaded_tables.items()
    }

    try:
        zip_bytes = (
            dataframes_to_zip_bytes(
                backup_dataframes
            )
        )

        st.download_button(
            label="下載完整 ZIP 備份",
            data=zip_bytes,
            file_name=(
                "personal_asset_backup_"
                f"{export_date_text}.zip"
            ),
            mime="application/zip",
            use_container_width=True,
            key="download_complete_zip",
        )

    except Exception as error:
        st.error(
            f"建立 ZIP 備份失敗：{error}"
        )

    st.info(
        "Excel 報表適合閱讀；ZIP 原始備份"
        "才是未來移轉或資料還原時應優先保留的版本。"
    )

    st.divider()
    st.subheader("檢查 ZIP 備份")

    st.caption(
        "上傳先前下載的 ZIP 備份，檢查格式、"
        "資料表、欄位及筆數是否完整。"
        "此功能只會讀取與預覽檔案，"
        "不會修改或寫入 Supabase。"
    )

    uploaded_backup = st.file_uploader(
        "選擇 ZIP 備份",
        type=["zip"],
        accept_multiple_files=False,
        key="backup_validation_zip",
    )

    if uploaded_backup is not None:
        with st.spinner("正在檢查備份……"):
            validation_result = (
                validate_backup_zip(
                    uploaded_backup.getvalue()
                )
            )

        if validation_result["is_valid"]:
            st.success(
                "備份檢查完成：格式、欄位與資料筆數均正常。"
            )
        else:
            st.error(
                "備份未通過檢查，請勿用於資料還原。"
            )

        if validation_result["errors"]:
            with st.expander(
                "查看檢查錯誤",
                expanded=True,
            ):
                for error_message in validation_result[
                    "errors"
                ]:
                    st.error(error_message)

        if validation_result["warnings"]:
            with st.expander(
                "查看檢查提醒",
                expanded=False,
            ):
                for warning_message in validation_result[
                    "warnings"
                ]:
                    st.warning(warning_message)

        manifest = validation_result["manifest"] or {}
        table_records = validation_result["tables"]

        total_row_count = sum(
            table_record["row_count"]
            for table_record in table_records.values()
        )

        metric_col1, metric_col2, metric_col3 = (
            st.columns(3)
        )

        with metric_col1:
            st.metric(
                "備份版本",
                manifest.get("version", "—"),
            )

        with metric_col2:
            st.metric(
                "資料表數量",
                len(table_records),
            )

        with metric_col3:
            st.metric(
                "資料總筆數",
                f"{total_row_count:,}",
            )

        created_at_utc = manifest.get(
            "created_at_utc"
        )

        if created_at_utc:
            st.caption(
                f"備份建立時間（UTC）：{created_at_utc}"
            )

        if validation_result["summary_rows"]:
            st.dataframe(
                pd.DataFrame(
                    validation_result[
                        "summary_rows"
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )

        if table_records:
            table_names = list(table_records.keys())

            selected_table_name = st.selectbox(
                "預覽資料表",
                options=table_names,
                format_func=lambda table_name: (
                    f"{table_name} "
                    f"({table_records[table_name]['row_count']:,} 筆)"
                ),
                key="backup_preview_table",
            )

            selected_table = table_records[
                selected_table_name
            ]

            st.caption(
                "預覽最多顯示前 100 筆；"
                "空白值會以空白文字呈現。"
            )

            st.dataframe(
                selected_table["preview"],
                use_container_width=True,
                hide_index=True,
            )

        if validation_result["is_valid"]:
            st.divider()
            st.subheader("還原衝突分析")

            st.caption(
                "依每筆資料的 id 比較備份與目前 Supabase。"
                "分析會忽略 user_id，但會比較其他資料內容、"
                "日期及更新時間。此步驟仍然不會寫入資料庫。"
            )

            current_table_dataframes = {
                table_name: table_record[
                    "dataframe"
                ]
                for table_name, table_record
                in loaded_tables.items()
            }

            with st.spinner(
                "正在比較備份與目前資料……"
            ):
                restore_analysis = (
                    analyze_restore_conflicts(
                        table_records,
                        current_table_dataframes,
                    )
                )

            if restore_analysis["errors"]:
                st.error(
                    "部分資料無法安全比較，"
                    "目前不能進入正式還原步驟。"
                )

                with st.expander(
                    "查看分析错误",
                    expanded=True,
                ):
                    for error_message in (
                        restore_analysis["errors"]
                    ):
                        st.error(error_message)

            if restore_analysis["warnings"]:
                with st.expander(
                    "查看欄位結構提醒",
                    expanded=False,
                ):
                    for warning_message in (
                        restore_analysis["warnings"]
                    ):
                        st.warning(warning_message)

            restore_totals = restore_analysis[
                "totals"
            ]

            (
                restore_col1,
                restore_col2,
                restore_col3,
                restore_col4,
            ) = st.columns(4)

            with restore_col1:
                st.metric(
                    "可新增",
                    f"{restore_totals['new']:,}",
                )

            with restore_col2:
                st.metric(
                    "已存在且相同",
                    f"{restore_totals['existing']:,}",
                )

            with restore_col3:
                st.metric(
                    "內容衝突",
                    f"{restore_totals['conflict']:,}",
                )

            with restore_col4:
                st.metric(
                    "僅存在目前資料庫",
                    f"{restore_totals['current_only']:,}",
                )

            if restore_analysis["summary_rows"]:
                st.dataframe(
                    pd.DataFrame(
                        restore_analysis[
                            "summary_rows"
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

            detail_dataframe = pd.DataFrame(
                restore_analysis["detail_rows"]
            )

            if not detail_dataframe.empty:
                detail_filter = st.selectbox(
                    "查看逐筆比較結果",
                    options=[
                        "全部",
                        "可新增",
                        "已存在且相同",
                        "內容衝突",
                    ],
                    key="restore_analysis_filter",
                )

                if detail_filter == "全部":
                    filtered_detail_dataframe = (
                        detail_dataframe
                    )
                else:
                    filtered_detail_dataframe = (
                        detail_dataframe[
                            detail_dataframe["分類"]
                            == detail_filter
                        ]
                    )

                st.dataframe(
                    filtered_detail_dataframe,
                    use_container_width=True,
                    hide_index=True,
                )

            conflict_records = restore_analysis[
                "conflicts"
            ]

            if conflict_records:
                with st.expander(
                    "查看內容衝突差異",
                    expanded=False,
                ):
                    conflict_indexes = list(
                        range(len(conflict_records))
                    )

                    selected_conflict_index = (
                        st.selectbox(
                            "選擇衝突資料",
                            options=conflict_indexes,
                            format_func=lambda index: (
                                f"{conflict_records[index]['table_name']}"
                                " | "
                                f"{conflict_records[index]['id']}"
                            ),
                            key="restore_conflict_record",
                        )
                    )

                    selected_conflict = (
                        conflict_records[
                            selected_conflict_index
                        ]
                    )

                    st.dataframe(
                        pd.DataFrame(
                            selected_conflict[
                                "differences"
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

            st.info(
                "目前僅完成比較與預覽；"
                "沒有任何資料被新增、覆蓋或刪除。"
            )

            st.divider()
            st.subheader("僅新增還原")

            if not validation_result[
                "restore_capable"
            ]:
                st.warning(
                    "版本 1／2 備份只能檢查與分析。"
                    "請先下載新版版本 3 備份，"
                    "其 JSON 才能精確保留 NULL、"
                    "空字串、布林值與數字型別。"
                )

            else:
                restore_plan = (
                    build_add_only_restore_plan(
                        table_records,
                        restore_analysis,
                    )
                )

                if not restore_plan["is_valid"]:
                    st.error(
                        "目前不符合僅新增還原條件。"
                    )

                    for plan_error in restore_plan[
                        "errors"
                    ]:
                        st.error(plan_error)

                elif restore_plan["total_rows"] == 0:
                    st.success(
                        "目前沒有缺少的資料，"
                        "不需要執行還原。"
                    )

                else:
                    st.warning(
                        "此模式只新增缺少的資料；"
                        "不會更新、覆蓋或刪除既有資料。"
                    )

                    st.dataframe(
                        pd.DataFrame(
                            restore_plan[
                                "summary_rows"
                            ]
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                    restore_total_rows = (
                        restore_plan["total_rows"]
                    )

                    confirmation_text = (
                        f"RESTORE {restore_total_rows}"
                    )

                    st.caption(
                        "為避免誤觸，請輸入："
                        f"{confirmation_text}"
                    )

                    entered_confirmation = (
                        st.text_input(
                            "確認還原",
                            key=(
                                "add_only_restore_"
                                "confirmation"
                            ),
                        )
                    )

                    restore_button_disabled = (
                        entered_confirmation.strip()
                        != confirmation_text
                    )

                    if st.button(
                        (
                            "僅新增還原 "
                            f"{restore_total_rows:,} 筆資料"
                        ),
                        type="primary",
                        use_container_width=True,
                        disabled=(
                            restore_button_disabled
                        ),
                        key="execute_add_only_restore",
                    ):
                        with st.spinner(
                            "正在依關聯順序新增資料……"
                        ):
                            restore_result = (
                                execute_add_only_restore(
                                    supabase,
                                    restore_plan,
                                )
                            )

                        if restore_result["success"]:
                            st.session_state[
                                "restore_success_message"
                            ] = (
                                "僅新增還原完成，共新增 "
                                f"{restore_result['inserted_rows']:,} "
                                "筆資料。"
                            )

                            st.rerun()

                        else:
                            st.error(
                                "還原中途停止。已成功新增的資料"
                                "不會被回滾或重複覆蓋；請重新分析後"
                                "再次執行，即可繼續剩餘資料。"
                            )

                            for restore_error in (
                                restore_result["errors"]
                            ):
                                st.error(restore_error)

                            if restore_result[
                                "table_results"
                            ]:
                                st.dataframe(
                                    pd.DataFrame(
                                        restore_result[
                                            "table_results"
                                        ]
                                    ),
                                    use_container_width=True,
                                    hide_index=True,
                                )
