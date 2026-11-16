import pandas as pd
import streamlit as st

from config import (
    ASSET_TYPE_LABELS,
    ASSET_TYPE_OPTIONS,
    CURRENCY_OPTIONS,
    PRICE_SOURCE_LABELS,
    PRICE_SOURCE_OPTIONS,
)

def show_asset_manager(supabase):
    st.subheader("資產管理")
    st.caption(
        "建立現金、股票、ETF、基金、加密貨幣及其他資產的基本資料。"
    )

    success_message = st.session_state.pop(
        "asset_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    with st.expander("新增資產", expanded=False):
        with st.form(
            "add_asset_form",
            clear_on_submit=True,
        ):
            symbol = st.text_input(
                "資產代號",
                placeholder="例如：USD、AAPL、VOO",
            )

            name = st.text_input(
                "資產名稱",
                placeholder="例如：美元現金、Apple、Vanguard S&P 500 ETF",
            )

            asset_type = st.selectbox(
                "資產類型",
                options=ASSET_TYPE_OPTIONS,
                format_func=lambda value: ASSET_TYPE_LABELS[value],
            )

            currency = st.selectbox(
                "計價幣別",
                options=CURRENCY_OPTIONS,
            )

            market = st.text_input(
                "市場",
                placeholder="例如：NASDAQ、NYSE、TWSE；現金可留白",
            )

            external_symbol = st.text_input(
                "外部報價代號（選填）",
                placeholder=(
                    "例如 AAPL、2330.TW、BTC-USD；"
                    "官方基金淨值請輸入 ISIN"
                ),
                help=(
                    "Yahoo Finance 資產填入 Yahoo 報價代號，"
                    "例如 BTC-USD；官方基金淨值來源請填入 ISIN。"
                ),
            )

            price_source = st.selectbox(
                "價格來源",
                options=PRICE_SOURCE_OPTIONS,
                format_func=lambda value: (
                    PRICE_SOURCE_LABELS[value]
                ),
                help=(
                    "現金與沒有自動報價的資產請選手動輸入。"
                ),
            )

            submitted = st.form_submit_button(
                "新增資產",
                width='stretch',
            )

        if submitted:
            cleaned_symbol = symbol.strip().upper()
            cleaned_name = name.strip()
            cleaned_market = market.strip().upper()
            cleaned_external_symbol = (
                external_symbol.strip()
            )

            if not cleaned_symbol:
                st.warning("請輸入資產代號。")

            elif not cleaned_name:
                st.warning("請輸入資產名稱。")

            elif (
                asset_type != "cash"
                and price_source != "manual"
                and not cleaned_external_symbol
            ):
                st.warning(
                    "使用自動價格來源時，"
                    "請輸入外部報價代號或基金 ISIN。"
                )

            else:
                try:
                    supabase.table("assets").insert(
                        {
                            "symbol": cleaned_symbol,
                            "name": cleaned_name,
                            "asset_type": asset_type,
                            "currency": currency,
                            "market": cleaned_market,
                            "external_symbol": (
                                cleaned_external_symbol
                                if cleaned_external_symbol
                                else None
                            ),
                            "price_source": (
                                "manual"
                                if asset_type == "cash"
                                else price_source
                            ),
                        }
                    ).execute()

                    st.session_state[
                        "asset_success_message"
                    ] = "資產新增成功。"

                    st.rerun()

                except Exception as error:
                    st.error(f"新增資產失敗：{error}")

    try:
        response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, currency, "
                "market, external_symbol, price_source, "
                "is_active, created_at"
            )
            .order("created_at")
            .execute()
        )

        assets = response.data or []

    except Exception as error:
        st.error(f"讀取資產失敗：{error}")
        return

    st.divider()
    st.subheader("目前資產")

    if not assets:
        st.info("目前還沒有資產，請先在上方新增。")
        return

    display_data = []

    for asset in assets:
        display_data.append(
            {
                "代號": asset["symbol"],
                "資產名稱": asset["name"],
                "資產類型": ASSET_TYPE_LABELS.get(
                    asset["asset_type"],
                    asset["asset_type"],
                ),
                "計價幣別": asset["currency"],
                "市場": asset["market"] or "",
                "外部報價代號": asset["external_symbol"] or "",
                "價格來源": PRICE_SOURCE_LABELS.get(
                    asset["price_source"],
                    asset["price_source"],
                ),
                "狀態": (
                    "使用中"
                    if asset["is_active"]
                    else "已封存"
                ),
                "建立時間": asset["created_at"],
            }
        )

    asset_dataframe = pd.DataFrame(display_data)

    asset_dataframe["建立時間"] = pd.to_datetime(
        asset_dataframe["建立時間"]
    ).dt.strftime("%Y-%m-%d")

    st.dataframe(
        asset_dataframe,
        width='stretch',
        hide_index=True,
    )

    st.divider()

    with st.expander("編輯資產"):
        asset_ids = [
            asset["id"]
            for asset in assets
        ]

        def format_edit_asset(asset_id):
            selected = next(
                asset
                for asset in assets
                if asset["id"] == asset_id
            )

            return (
                f'{selected["symbol"]} | '
                f'{selected["name"]} | '
                f'{selected["currency"]}'
            )

        selected_edit_asset_id = st.selectbox(
            "選擇要編輯的資產",
            options=asset_ids,
            format_func=format_edit_asset,
            key="selected_edit_asset_id",
        )

        selected_edit_asset = next(
            asset
            for asset in assets
            if asset["id"] == selected_edit_asset_id
        )

        try:
            asset_type_index = ASSET_TYPE_OPTIONS.index(
                selected_edit_asset["asset_type"]
            )
        except ValueError:
            asset_type_index = 0

        try:
            currency_index = CURRENCY_OPTIONS.index(
                selected_edit_asset["currency"]
            )
        except ValueError:
            currency_index = 0

        current_price_source = (
            selected_edit_asset.get("price_source")
            or "manual"
        )

        # 相容以前可能保存的 yahoo 名稱
        if current_price_source == "yahoo":
            current_price_source = "yfinance"

        try:
            price_source_index = (
                PRICE_SOURCE_OPTIONS.index(
                    current_price_source
                )
            )
        except ValueError:
            price_source_index = 0

        with st.form(
            f"edit_asset_form_{selected_edit_asset_id}"
        ):
            edited_symbol = st.text_input(
                "資產代號",
                value=selected_edit_asset["symbol"],
            )

            edited_name = st.text_input(
                "資產名稱",
                value=selected_edit_asset["name"],
            )

            edited_asset_type = st.selectbox(
                "資產類型",
                options=ASSET_TYPE_OPTIONS,
                index=asset_type_index,
                format_func=lambda value: ASSET_TYPE_LABELS[value],
            )

            edited_currency = st.selectbox(
                "計價幣別",
                options=CURRENCY_OPTIONS,
                index=currency_index,
            )

            edited_market = st.text_input(
                "市場",
                value=selected_edit_asset["market"] or "",
                placeholder="例如：NASDAQ、NYSE、TWSE；現金可留白",
            )

            edited_external_symbol = st.text_input(
                "外部報價代號（選填）",
                value=(
                    selected_edit_asset["external_symbol"]
                    or ""
                ),
                help=(
                    "Yahoo Finance 資產填入 Yahoo 報價代號，"
                    "例如 BTC-USD；官方基金淨值來源請填入 ISIN。"
                ),
            )

            edited_price_source = st.selectbox(
                "價格來源",
                options=PRICE_SOURCE_OPTIONS,
                index=price_source_index,
                format_func=lambda value: (
                    PRICE_SOURCE_LABELS[value]
                ),
            )

            edit_submitted = st.form_submit_button(
                "儲存修改",
                width='stretch',
            )

        if edit_submitted:
            cleaned_edited_symbol = (
                edited_symbol.strip().upper()
            )

            cleaned_edited_name = edited_name.strip()

            cleaned_edited_market = (
                edited_market.strip().upper()
            )

            cleaned_edited_external_symbol = (
                edited_external_symbol.strip()
            )

            if not cleaned_edited_symbol:
                st.warning("資產代號不能留白。")

            elif not cleaned_edited_name:
                st.warning("資產名稱不能留白。")

            elif (
                edited_asset_type != "cash"
                and edited_price_source != "manual"
                and not cleaned_edited_external_symbol
            ):
                st.warning(
                    "使用自動價格來源時，"
                    "請輸入外部報價代號或基金 ISIN。"
                )

            else:
                try:
                    (
                        supabase.table("assets")
                        .update(
                            {
                                "symbol": cleaned_edited_symbol,
                                "name": cleaned_edited_name,
                                "asset_type": edited_asset_type,
                                "currency": edited_currency,
                                "market": cleaned_edited_market,
                                "external_symbol": (
                                    cleaned_edited_external_symbol
                                    if cleaned_edited_external_symbol
                                    else None
                                ),
                                "price_source": (
                                    "manual"
                                    if edited_asset_type == "cash"
                                    else edited_price_source
                                ),
                            }
                        )
                        .eq("id", selected_edit_asset_id)
                        .execute()
                    )

                    st.session_state[
                        "asset_success_message"
                    ] = "資產資料修改成功。"

                    st.rerun()

                except Exception as error:
                    st.error(f"修改資產失敗：{error}")
        st.divider()

    with st.expander("封存或恢復資產"):
        status_asset_ids = [
            asset["id"]
            for asset in assets
        ]

        def format_status_asset(asset_id):
            selected = next(
                asset
                for asset in assets
                if asset["id"] == asset_id
            )

            status = (
                "使用中"
                if selected["is_active"]
                else "已封存"
            )

            return (
                f'{selected["symbol"]} | '
                f'{selected["name"]} | '
                f"{status}"
            )

        selected_status_asset_id = st.selectbox(
            "選擇資產",
            options=status_asset_ids,
            format_func=format_status_asset,
            key="selected_status_asset_id",
        )

        selected_status_asset = next(
            asset
            for asset in assets
            if asset["id"] == selected_status_asset_id
        )

        new_status = not selected_status_asset["is_active"]

        action_label = (
            "恢復資產"
            if new_status
            else "封存資產"
        )

        if st.button(
            action_label,
            width='stretch',
            key="change_asset_status_button",
        ):
            try:
                (
                    supabase.table("assets")
                    .update({"is_active": new_status})
                    .eq("id", selected_status_asset_id)
                    .execute()
                )

                st.session_state[
                    "asset_success_message"
                ] = f"{action_label}成功。"

                st.rerun()

            except Exception as error:
                st.error(f"更新資產狀態失敗：{error}")
