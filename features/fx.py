import pandas as pd
import requests
import streamlit as st

from config import FX_SOURCE_LABELS
from services.market_data import (
    fetch_frankfurter_rates,
)

def show_fx_manager(supabase):
    st.subheader("匯率管理")
    st.caption(
        "系統會在開啟此頁面時，自動檢查最新外部匯率。"
        "匯率表示 1 單位外幣可兌換多少 TWD；"
        "手動輸入可用於更正或備援。"
    )

    success_message = st.session_state.pop(
        "fx_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    try:
        assets_response = (
            supabase.table("assets")
            .select(
                "currency, asset_type, is_active"
            )
            .eq("asset_type", "cash")
            .eq("is_active", True)
            .execute()
        )

        cash_assets = assets_response.data or []

        rates_response = (
            supabase.table("fx_rates")
            .select(
                "id, from_currency, to_currency, rate, "
                "rate_date, source, created_at, updated_at"
            )
            .eq("to_currency", "TWD")
            .order("rate_date", desc=True)
            .order("created_at", desc=True)
            .execute()
        )

        rates = rates_response.data or []

    except Exception as error:
        st.error(f"讀取匯率資料失敗：{error}")
        return

    foreign_currencies = sorted(
        {
            asset["currency"]
            for asset in cash_assets
            if asset["currency"] != "TWD"
        }
    )

    if not foreign_currencies:
        st.info(
            "目前沒有需要換算成 TWD 的外幣現金資產。"
        )
        return

    try:
        external_rates = fetch_frankfurter_rates(
            tuple(foreign_currencies)
        )

        existing_rate_keys = {
            (
                rate_record["from_currency"],
                rate_record["to_currency"],
                rate_record["rate_date"],
            )
            for rate_record in rates
        }

        new_rate_rows = []

        for currency, external_record in (
            external_rates.items()
        ):
            rate_key = (
                currency,
                "TWD",
                external_record["rate_date"],
            )

            # 同幣別、同日期已有紀錄時不覆蓋。
            # 因此手動更正會優先保留。
            if rate_key in existing_rate_keys:
                continue

            new_rate_rows.append(
                {
                    "from_currency": currency,
                    "to_currency": "TWD",
                    "rate": float(
                        external_record["rate"]
                    ),
                    "rate_date": (
                        external_record["rate_date"]
                    ),
                    "source": "frankfurter",
                }
            )

        if new_rate_rows:
            (
                supabase.table("fx_rates")
                .insert(new_rate_rows)
                .execute()
            )

            st.session_state[
                "fx_success_message"
            ] = (
                f"已自動新增 "
                f"{len(new_rate_rows)} 筆外部匯率。"
            )

            st.rerun()

    except requests.RequestException as error:
        st.warning(
            "目前無法連接外部匯率服務，"
            "將繼續使用上次儲存的匯率。"
        )

    except (KeyError, TypeError, ValueError) as error:
        st.warning(
            f"外部匯率資料格式異常，"
            f"將繼續使用原有資料：{error}"
        )

    except Exception as error:
        st.warning(
            f"自動儲存匯率失敗，"
            f"將繼續使用原有資料：{error}"
        )

    latest_rates = {}

    for rate_record in rates:
        currency = rate_record["from_currency"]

        if currency not in latest_rates:
            latest_rates[currency] = rate_record

    with st.expander("新增或更新匯率", expanded=False):
        selected_currency = st.selectbox(
            "外幣",
            options=foreign_currencies,
            key="fx_currency",
        )

        latest_record = latest_rates.get(
            selected_currency
        )

        latest_rate = (
            float(latest_record["rate"])
            if latest_record is not None
            else 1.0
        )

        if latest_record is not None:
            st.caption(
                f"目前最新紀錄：1 {selected_currency} = "
                f"{latest_rate:,.6f} TWD，"
                f'日期 {latest_record["rate_date"]}'
            )
        else:
            st.caption(
                f"{selected_currency} 尚未建立匯率紀錄。"
            )

        with st.form(
            f"fx_rate_form_{selected_currency}"
        ):
            entered_rate = st.number_input(
                f"1 {selected_currency} = 多少 TWD",
                min_value=0.000001,
                value=latest_rate,
                step=0.01,
                format="%.6f",
            )

            rate_date = st.date_input(
                "匯率日期",
                value="today",
            )

            submitted = st.form_submit_button(
                "儲存匯率",
                width='stretch',
            )

        if submitted:
            rate_date_text = rate_date.isoformat()

            existing_record = next(
                (
                    rate_record
                    for rate_record in rates
                    if (
                        rate_record["from_currency"]
                        == selected_currency
                        and rate_record["to_currency"]
                        == "TWD"
                        and rate_record["rate_date"]
                        == rate_date_text
                    )
                ),
                None,
            )

            try:
                if existing_record is None:
                    (
                        supabase.table("fx_rates")
                        .insert(
                            {
                                "from_currency": (
                                    selected_currency
                                ),
                                "to_currency": "TWD",
                                "rate": float(entered_rate),
                                "rate_date": rate_date_text,
                                "source": "manual",
                            }
                        )
                        .execute()
                    )

                    message = "匯率新增成功。"

                else:
                    (
                        supabase.table("fx_rates")
                        .update(
                            {
                                "rate": float(entered_rate),
                                "source": "manual",
                                "updated_at": (
                                    pd.Timestamp.now(
                                        tz="America/Los_Angeles"
                                    ).isoformat()
                                ),
                            }
                        )
                        .eq("id", existing_record["id"])
                        .execute()
                    )

                    message = "當日匯率更新成功。"

                st.session_state[
                    "fx_success_message"
                ] = message

                st.rerun()

            except Exception as error:
                st.error(f"儲存匯率失敗：{error}")

    st.divider()
    st.subheader("目前使用匯率")

    current_rate_rows = []

    for currency in foreign_currencies:
        rate_record = latest_rates.get(currency)

        if rate_record is None:
            current_rate_rows.append(
                {
                    "外幣": currency,
                    "換算基準": "TWD",
                    "匯率": None,
                    "匯率日期": "",
                    "來源": "",
                    "狀態": "尚未輸入",
                }
            )

        else:
            current_rate_rows.append(
                {
                    "外幣": currency,
                    "換算基準": "TWD",
                    "匯率": float(rate_record["rate"]),
                    "匯率日期": rate_record["rate_date"],
                    "來源": FX_SOURCE_LABELS.get(
                        rate_record["source"],
                        rate_record["source"],
                    ),
                    "狀態": "可使用",
                }
            )

    current_rate_dataframe = pd.DataFrame(
        current_rate_rows
    )

    st.dataframe(
        current_rate_dataframe,
        width='stretch',
        hide_index=True,
        column_config={
            "匯率": st.column_config.NumberColumn(
                "匯率",
                format="%.6f",
            )
        },
    )

    if rates:
        with st.expander("查看匯率歷史"):
            history_rows = []

            for rate_record in rates:
                history_rows.append(
                    {
                        "外幣": rate_record["from_currency"],
                        "換算基準": rate_record["to_currency"],
                        "匯率": float(rate_record["rate"]),
                        "匯率日期": rate_record["rate_date"],
                        "來源": FX_SOURCE_LABELS.get(
                            rate_record["source"],
                            rate_record["source"],
                        ),
                    }
                )

            history_dataframe = pd.DataFrame(
                history_rows
            )

            st.dataframe(
                history_dataframe,
                width='stretch',
                hide_index=True,
                column_config={
                    "匯率": st.column_config.NumberColumn(
                        "匯率",
                        format="%.6f",
                    )
                },
            )