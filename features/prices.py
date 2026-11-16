import pandas as pd
import streamlit as st

from config import  (
    ASSET_TYPE_LABELS,
    PRICE_SOURCE_LABELS,
)
from services.market_data import (
    fetch_external_asset_price,
)

def show_price_manager(supabase):
    st.subheader("資產價格")
    st.caption(
        "記錄股票、ETF、基金與加密貨幣的單位價格。"
        "價格以該資產原始幣別表示。"
    )

    success_message = st.session_state.pop(
        "price_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    price_source_labels = {
        **PRICE_SOURCE_LABELS,

        # 相容以前可能保存的來源名稱
        "yahoo": "Yahoo Finance",
    }

    investment_asset_types = {
        "stock",
        "etf",
        "fund",
        "crypto",
    }

    try:
        assets_response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, currency, "
                "external_symbol, price_source, is_active"
            )
            .order("created_at")
            .execute()
        )

        prices_response = (
            supabase.table("asset_prices")
            .select(
                "id, asset_id, price, price_date, currency, "
                "source, created_at, updated_at"
            )
            .order("price_date", desc=True)
            .order("updated_at", desc=True)
            .execute()
        )

        assets = assets_response.data or []
        prices = prices_response.data or []

    except Exception as error:
        st.error(f"讀取價格資料失敗：{error}")
        return

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    active_investment_assets = [
        asset
        for asset in assets
        if (
            asset["is_active"]
            and asset["asset_type"]
            in investment_asset_types
        )
    ]

    latest_prices = {}

    for price_record in prices:
        asset_id = price_record["asset_id"]

        if asset_id not in latest_prices:
            latest_prices[asset_id] = price_record

    if not active_investment_assets:
        st.warning(
            "請先在「資產」分頁建立至少一個"
            "使用中的股票、ETF、基金或加密貨幣。"
        )

    else:
        asset_ids = [
            asset["id"]
            for asset in active_investment_assets
        ]

        def format_price_asset(asset_id):
            selected = next(
                asset
                for asset in active_investment_assets
                if asset["id"] == asset_id
            )

            asset_type_label = ASSET_TYPE_LABELS.get(
                selected["asset_type"],
                selected["asset_type"],
            )

            return (
                f'{selected["symbol"]} | '
                f'{selected["name"]} | '
                f"{asset_type_label}"
            )

        with st.expander(
            "新增或更正價格",
            expanded=False,
        ):
            selected_asset_id = st.selectbox(
                "資產",
                options=asset_ids,
                format_func=format_price_asset,
                key="price_asset_id",
            )

            selected_asset = next(
                asset
                for asset in active_investment_assets
                if asset["id"] == selected_asset_id
            )

            latest_record = latest_prices.get(
                selected_asset_id
            )

            latest_price = (
                float(latest_record["price"])
                if latest_record is not None
                else 1.0
            )

            if latest_record is None:
                st.caption(
                    f'{selected_asset["symbol"]} '
                    "目前還沒有價格紀錄。"
                )

            else:
                latest_source = price_source_labels.get(
                    latest_record["source"],
                    latest_record["source"],
                )

                st.caption(
                    f'目前最新紀錄：'
                    f'{selected_asset["currency"]} '
                    f'{latest_price:,.6f}，'
                    f'日期 {latest_record["price_date"]}，'
                    f"來源 {latest_source}"
                )

            external_symbol = (
                selected_asset["external_symbol"] or ""
            ).strip()

            selected_price_source = (
                selected_asset.get("price_source")
                or "manual"
            )

            fetch_button_labels = {
                "yahoo": "取得 Yahoo Finance 最新價格",
                "yfinance": "取得 Yahoo Finance 最新價格",
                "yuanta_fund": "取得元大投信最新淨值",
                "franklin_fund": (
                    "取得 Franklin Templeton 最新淨值"
                ),
                "schroders_fund": "取得施羅德最新淨值",
            }

            if selected_price_source == "manual":
                st.info(
                    "這項資產目前設定為手動輸入價格。"
                    "若要使用自動報價，請先到「資產」"
                    "分頁修改價格來源。"
                )

            elif not external_symbol:
                st.info(
                    "這項資產尚未設定外部報價代號或基金 ISIN。"
                    "請先到「資產」分頁編輯資產。"
                )

            elif selected_price_source not in fetch_button_labels:
                st.warning(
                    "目前尚未支援這項價格來源："
                    f"{selected_price_source}"
                )

            else:
                source_label = price_source_labels.get(
                    selected_price_source,
                    selected_price_source,
                )

                st.caption(
                    f"外部報價代號：{external_symbol}｜"
                    f"價格來源：{source_label}"
                )

                if st.button(
                    fetch_button_labels[selected_price_source],
                    key=(
                        "fetch_external_price_"
                        f"{selected_asset_id}"
                    ),
                    width="stretch",
                ):
                    try:
                        with st.spinner(
                            "正在取得外部價格..."
                        ):
                            fetched_price = (
                                fetch_external_asset_price(
                                    selected_asset
                                )
                            )

                        fetched_date = (
                            fetched_price["price_date"]
                        )

                        fetched_value = float(
                            fetched_price["price"]
                        )

                        fetched_source = (
                            fetched_price["source"]
                        )

                        returned_currency = (
                            fetched_price.get("currency")
                        )

                        if (
                            returned_currency
                            and returned_currency
                            != selected_asset["currency"]
                        ):
                            raise ValueError(
                                "外部資料計價幣別為 "
                                f"{returned_currency}，"
                                "但資產設定為 "
                                f'{selected_asset["currency"]}。'
                            )

                        existing_external_record = next(
                            (
                                price_record
                                for price_record in prices
                                if (
                                    price_record["asset_id"]
                                    == selected_asset_id
                                    and price_record[
                                        "price_date"
                                    ]
                                    == fetched_date
                                )
                            ),
                            None,
                        )

                        if (
                            existing_external_record is not None
                            and existing_external_record["source"]
                            == "manual"
                        ):
                            st.info(
                                "已取得外部價格："
                                f'{selected_asset["currency"]} '
                                f"{fetched_value:,.6f}，"
                                f"日期 {fetched_date}。"
                                "但同一天已有手動價格，"
                                "因此保留手動紀錄，"
                                "沒有自動覆蓋。"
                            )

                        else:
                            current_timestamp = (
                                pd.Timestamp.now(
                                    tz="America/Los_Angeles"
                                ).isoformat()
                            )

                            if existing_external_record is None:
                                (
                                    supabase
                                    .table("asset_prices")
                                    .insert(
                                        {
                                            "asset_id": (
                                                selected_asset_id
                                            ),
                                            "price": fetched_value,
                                            "price_date": (
                                                fetched_date
                                            ),
                                            "currency": (
                                                selected_asset[
                                                    "currency"
                                                ]
                                            ),
                                            "source": (
                                                fetched_source
                                            ),
                                        }
                                    )
                                    .execute()
                                )

                            else:
                                (
                                    supabase
                                    .table("asset_prices")
                                    .update(
                                        {
                                            "price": fetched_value,
                                            "currency": (
                                                selected_asset[
                                                    "currency"
                                                ]
                                            ),
                                            "source": (
                                                fetched_source
                                            ),
                                            "updated_at": (
                                                current_timestamp
                                            ),
                                        }
                                    )
                                    .eq(
                                        "id",
                                        existing_external_record[
                                            "id"
                                        ],
                                    )
                                    .execute()
                                )

                            st.session_state[
                                "price_success_message"
                            ] = (
                                "外部價格更新成功："
                                f'{selected_asset["symbol"]} '
                                f'{selected_asset["currency"]} '
                                f"{fetched_value:,.6f}，"
                                f"價格日期 {fetched_date}。"
                            )

                            st.rerun()

                    except Exception as error:
                        st.error(
                            "取得外部價格失敗："
                            f"{error}"
                        )

            with st.form(
                f"asset_price_form_{selected_asset_id}"
            ):
                entered_price = st.number_input(
                    (
                        "單位價格 "
                        f'({selected_asset["currency"]})'
                    ),
                    min_value=0.000001,
                    value=latest_price,
                    step=0.01,
                    format="%.6f",
                )

                price_date = st.date_input(
                    "價格日期",
                    value="today",
                    key=(
                        "asset_price_date_"
                        f"{selected_asset_id}"
                    ),
                )

                submitted = st.form_submit_button(
                    "儲存價格",
                    width='stretch',
                )

            if submitted:
                price_date_text = (
                    price_date.isoformat()
                )

                existing_record = next(
                    (
                        price_record
                        for price_record in prices
                        if (
                            price_record["asset_id"]
                            == selected_asset_id
                            and price_record["price_date"]
                            == price_date_text
                        )
                    ),
                    None,
                )

                try:
                    if existing_record is None:
                        (
                            supabase
                            .table("asset_prices")
                            .insert(
                                {
                                    "asset_id": (
                                        selected_asset_id
                                    ),
                                    "price": float(
                                        entered_price
                                    ),
                                    "price_date": (
                                        price_date_text
                                    ),
                                    "currency": (
                                        selected_asset[
                                            "currency"
                                        ]
                                    ),
                                    "source": "manual",
                                }
                            )
                            .execute()
                        )

                        message = "資產價格新增成功。"

                    else:
                        (
                            supabase
                            .table("asset_prices")
                            .update(
                                {
                                    "price": float(
                                        entered_price
                                    ),
                                    "currency": (
                                        selected_asset[
                                            "currency"
                                        ]
                                    ),
                                    "source": "manual",
                                    "updated_at": (
                                        pd.Timestamp.now(
                                            tz=(
                                                "America/"
                                                "Los_Angeles"
                                            )
                                        ).isoformat()
                                    ),
                                }
                            )
                            .eq(
                                "id",
                                existing_record["id"],
                            )
                            .execute()
                        )

                        message = "當日資產價格更新成功。"

                    st.session_state[
                        "price_success_message"
                    ] = message

                    st.rerun()

                except Exception as error:
                    st.error(
                        f"儲存資產價格失敗：{error}"
                    )

    st.divider()
    st.subheader("目前使用價格")

    current_price_rows = []

    for asset in active_investment_assets:
        price_record = latest_prices.get(asset["id"])

        if price_record is None:
            current_price_rows.append(
                {
                    "資產代號": asset["symbol"],
                    "資產名稱": asset["name"],
                    "資產類型": ASSET_TYPE_LABELS.get(
                        asset["asset_type"],
                        asset["asset_type"],
                    ),
                    "幣別": asset["currency"],
                    "單位價格": None,
                    "價格日期": "",
                    "來源": "",
                    "狀態": "尚無價格",
                }
            )

        else:
            current_price_rows.append(
                {
                    "資產代號": asset["symbol"],
                    "資產名稱": asset["name"],
                    "資產類型": ASSET_TYPE_LABELS.get(
                        asset["asset_type"],
                        asset["asset_type"],
                    ),
                    "幣別": price_record["currency"],
                    "單位價格": float(
                        price_record["price"]
                    ),
                    "價格日期": (
                        price_record["price_date"]
                    ),
                    "來源": price_source_labels.get(
                        price_record["source"],
                        price_record["source"],
                    ),
                    "狀態": "可使用",
                }
            )

    if not current_price_rows:
        st.info("目前沒有可顯示的非現金資產。")

    else:
        current_price_dataframe = pd.DataFrame(
            current_price_rows
        )

        st.dataframe(
            current_price_dataframe,
            width='stretch',
            hide_index=True,
            column_config={
                "單位價格": st.column_config.NumberColumn(
                    "單位價格",
                    format="%.6f",
                )
            },
        )

    if prices:
        with st.expander("查看價格歷史"):
            history_rows = []

            for price_record in prices:
                asset = asset_map.get(
                    price_record["asset_id"]
                )

                if asset is None:
                    continue

                history_rows.append(
                    {
                        "資產代號": asset["symbol"],
                        "資產名稱": asset["name"],
                        "單位價格": float(
                            price_record["price"]
                        ),
                        "幣別": price_record["currency"],
                        "價格日期": (
                            price_record["price_date"]
                        ),
                        "來源": price_source_labels.get(
                            price_record["source"],
                            price_record["source"],
                        ),
                    }
                )

            if history_rows:
                history_dataframe = pd.DataFrame(
                    history_rows
                )

                st.dataframe(
                    history_dataframe,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "單位價格":
                            st.column_config.NumberColumn(
                                "單位價格",
                                format="%.6f",
                            )
                    },
                )
