from datetime import datetime
from datetime import time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


SEATTLE_TIMEZONE = ZoneInfo(
    "America/Los_Angeles"
)

FLOW_TYPE_LABELS = {
    "contribution": "外部投入",
    "withdrawal": "外部取回",
}

CURRENCY_OPTIONS = [
    "TWD",
    "USD",
    "JPY",
    "EUR",
    "CNY",
    "HKD",
]


def show_twr_cash_flow_manager(
    supabase,
):
    st.subheader("TWR 外部資金流管理")

    st.caption(
        "只記錄資金跨越 TWR 投資組合邊界的情況。"
        "投資帳戶內的買賣、股利再投資及現金轉換"
        "不需要記錄。"
    )

    success_message = st.session_state.pop(
        "twr_cash_flow_success",
        None,
    )

    if success_message:
        st.success(success_message)

    try:
        account_response = (
            supabase.table("accounts")
            .select(
                "id, name, institution, "
                "include_in_twr, is_active"
            )
            .eq("is_active", True)
            .order("name")
            .execute()
        )

        accounts = account_response.data or []

        flow_response = (
            supabase.table(
                "portfolio_cash_flows"
            )
            .select(
                "id, flow_at, flow_type, "
                "amount, currency, amount_twd, "
                "source_account_id, "
                "destination_account_id, "
                "notes, created_at"
            )
            .order("flow_at", desc=True)
            .execute()
        )

        cash_flows = flow_response.data or []

    except Exception as error:
        st.error(
            f"TWR 資金流資料讀取失敗：{error}"
        )
        return

    account_map = {
        account["id"]: account
        for account in accounts
    }

    twr_account_ids = [
        account["id"]
        for account in accounts
        if account.get(
            "include_in_twr",
            False,
        )
    ]

    outside_account_ids = [
        account["id"]
        for account in accounts
        if not account.get(
            "include_in_twr",
            False,
        )
    ]

    def format_account(account_id):
        if account_id is None:
            return "其他／未追蹤帳戶"

        account = account_map[account_id]

        institution = (
            account.get("institution")
            or "未指定金融機構"
        )

        return (
            f'{institution}｜'
            f'{account["name"]}'
        )

    if not twr_account_ids:
        st.warning(
            "目前沒有任何帳戶納入 TWR，"
            "請先在帳戶管理中設定。"
        )
        return

    flow_type = st.radio(
        "資金流類型",
        options=[
            "contribution",
            "withdrawal",
        ],
        format_func=lambda value: (
            FLOW_TYPE_LABELS[value]
        ),
        horizontal=True,
        key="new_twr_flow_type",
    )

    with st.expander(
        "新增外部資金流",
        expanded=False,
    ):
        with st.form(
            "add_twr_cash_flow_form",
            clear_on_submit=True,
        ):
            flow_date = st.date_input(
                "資金流日期",
            )

            flow_time = st.time_input(
                "大概時間",
                value=time(12, 0),
                help=(
                    "若不知道精確時間，可保留中午 12:00。"
                    "每日快照下，日期比精確分鐘更重要。"
                ),
            )

            if flow_type == "contribution":
                source_account_id = st.selectbox(
                    "資金來源",
                    options=(
                        [None]
                        + outside_account_ids
                    ),
                    format_func=format_account,
                )

                destination_account_id = (
                    st.selectbox(
                        "流入的 TWR 帳戶",
                        options=twr_account_ids,
                        format_func=format_account,
                    )
                )

            else:
                source_account_id = st.selectbox(
                    "流出的 TWR 帳戶",
                    options=twr_account_ids,
                    format_func=format_account,
                )

                destination_account_id = (
                    st.selectbox(
                        "資金去向",
                        options=(
                            [None]
                            + outside_account_ids
                        ),
                        format_func=format_account,
                    )
                )

            currency = st.selectbox(
                "原始幣別",
                options=CURRENCY_OPTIONS,
            )

            amount = st.number_input(
                "原幣金額",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.4f",
            )

            amount_twd_input = st.number_input(
                "當日換算 TWD 金額",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
                help=(
                    "若原始幣別是 TWD，可留為 0，"
                    "系統會直接使用原幣金額。"
                ),
            )

            notes = st.text_area(
                "備註",
                placeholder=(
                    "例如：BofA 匯入 Firstrade；"
                    "玉山銀行支付台股交割款"
                ),
            )

            submitted = st.form_submit_button(
                "新增外部資金流",
                type="primary",
                use_container_width=True,
            )

        if submitted:
            amount = float(amount)

            if currency == "TWD":
                amount_twd = amount
            else:
                amount_twd = float(
                    amount_twd_input
                )

            if amount <= 0:
                st.warning(
                    "原幣金額必須大於零。"
                )

            elif amount_twd <= 0:
                st.warning(
                    "非 TWD 資金流必須輸入"
                    "當日換算 TWD 金額。"
                )

            else:
                flow_at = datetime.combine(
                    flow_date,
                    flow_time,
                    tzinfo=SEATTLE_TIMEZONE,
                )

                payload = {
                    "flow_at": (
                        flow_at.isoformat()
                    ),
                    "flow_type": flow_type,
                    "amount": amount,
                    "currency": currency,
                    "amount_twd": amount_twd,
                    "source_account_id": (
                        source_account_id
                    ),
                    "destination_account_id": (
                        destination_account_id
                    ),
                    "notes": (
                        notes.strip()
                        if notes.strip()
                        else None
                    ),
                }

                try:
                    (
                        supabase.table(
                            "portfolio_cash_flows"
                        )
                        .insert(payload)
                        .execute()
                    )

                    st.session_state[
                        "twr_cash_flow_success"
                    ] = (
                        "TWR 外部資金流新增成功。"
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        "新增 TWR 外部資金流失敗："
                        f"{error}"
                    )

    st.markdown("### 外部資金流紀錄")

    if not cash_flows:
        st.info(
            "目前尚未建立外部資金流。"
            "若基準快照後沒有新增投入或取回，"
            "這是正常的。"
        )
        return

    display_rows = []

    for flow in cash_flows:
        source_name = format_account(
            flow.get("source_account_id")
        )

        destination_name = format_account(
            flow.get(
                "destination_account_id"
            )
        )

        display_rows.append(
            {
                "日期時間": flow["flow_at"],
                "類型": FLOW_TYPE_LABELS.get(
                    flow["flow_type"],
                    flow["flow_type"],
                ),
                "來源": source_name,
                "去向": destination_name,
                "原幣金額": float(
                    flow["amount"]
                ),
                "幣別": flow["currency"],
                "TWD 金額": float(
                    flow["amount_twd"]
                ),
                "備註": flow.get("notes") or "",
            }
        )

    st.dataframe(
        pd.DataFrame(display_rows),
        width="stretch",
        hide_index=True,
        column_config={
            "原幣金額":
                st.column_config.NumberColumn(
                    "原幣金額",
                    format="%.4f",
                ),
            "TWD 金額":
                st.column_config.NumberColumn(
                    "TWD 金額",
                    format="%.2f",
                ),
        },
    )

    with st.expander(
        "編輯外部資金流",
        expanded=False,
    ):
        edit_flow_map = {
            flow["id"]: flow
            for flow in cash_flows
        }

        def format_edit_flow(flow_id):
            flow = edit_flow_map[flow_id]

            flow_label = FLOW_TYPE_LABELS.get(
                flow["flow_type"],
                flow["flow_type"],
            )

            return (
                f'{flow["flow_at"][:10]} | '
                f"{flow_label} | "
                f'NT$ {float(flow["amount_twd"]):,.2f}'
            )

        selected_edit_flow_id = st.selectbox(
            "選擇要編輯的紀錄",
            options=list(edit_flow_map.keys()),
            format_func=format_edit_flow,
            key="selected_edit_twr_flow_id",
        )

        selected_edit_flow = edit_flow_map[
            selected_edit_flow_id
        ]

        original_flow_type = (
            selected_edit_flow["flow_type"]
        )

        edit_flow_type = st.radio(
            "資金流類型",
            options=[
                "contribution",
                "withdrawal",
            ],
            index=(
                0
                if original_flow_type
                == "contribution"
                else 1
            ),
            format_func=lambda value: (
                FLOW_TYPE_LABELS[value]
            ),
            horizontal=True,
            key=(
                "edit_twr_flow_type_"
                f"{selected_edit_flow_id}"
            ),
        )

        flow_at_text = str(
            selected_edit_flow["flow_at"]
        ).replace(
            "Z",
            "+00:00",
        )

        original_flow_at = (
            datetime.fromisoformat(
                flow_at_text
            )
        )

        if original_flow_at.tzinfo is None:
            original_flow_at = (
                original_flow_at.replace(
                    tzinfo=SEATTLE_TIMEZONE
                )
            )
        else:
            original_flow_at = (
                original_flow_at.astimezone(
                    SEATTLE_TIMEZONE
                )
            )

        original_source_id = (
            selected_edit_flow.get(
                "source_account_id"
            )
        )

        original_destination_id = (
            selected_edit_flow.get(
                "destination_account_id"
            )
        )

        if edit_flow_type == "contribution":
            edit_source_options = [
                None,
                *outside_account_ids,
            ]

            edit_destination_options = list(
                twr_account_ids
            )

            default_source_id = (
                original_source_id
                if original_source_id
                in edit_source_options
                else None
            )

            default_destination_id = (
                original_destination_id
                if original_destination_id
                in edit_destination_options
                else (
                    edit_destination_options[0]
                    if edit_destination_options
                    else None
                )
            )

        else:
            edit_source_options = list(
                twr_account_ids
            )

            edit_destination_options = [
                None,
                *outside_account_ids,
            ]

            default_source_id = (
                original_source_id
                if original_source_id
                in edit_source_options
                else (
                    edit_source_options[0]
                    if edit_source_options
                    else None
                )
            )

            default_destination_id = (
                original_destination_id
                if original_destination_id
                in edit_destination_options
                else None
            )

        currency_options = list(
            CURRENCY_OPTIONS
        )

        original_currency = (
            selected_edit_flow.get(
                "currency"
            )
            or "TWD"
        )

        if (
            original_currency
            not in currency_options
        ):
            currency_options.append(
                original_currency
            )

        with st.form(
            "edit_twr_cash_flow_form_"
            f"{selected_edit_flow_id}"
        ):
            edited_flow_date = st.date_input(
                "資金流日期",
                value=original_flow_at.date(),
            )

            edited_flow_time = st.time_input(
                "大概時間",
                value=original_flow_at.time().replace(
                    tzinfo=None,
                ),
                help=(
                    "若不知道精確時間，可使用中午 "
                    "12:00。"
                ),
            )

            edited_source_id = st.selectbox(
                "資金來源",
                options=edit_source_options,
                index=edit_source_options.index(
                    default_source_id
                ),
                format_func=format_account,
                help=(
                    "投入時通常是投資組合外的銀行帳戶；"
                    "取回時則是 TWR 投資帳戶。"
                ),
            )

            edited_destination_id = (
                st.selectbox(
                    "資金目的地",
                    options=(
                        edit_destination_options
                    ),
                    index=(
                        edit_destination_options.index(
                            default_destination_id
                        )
                    ),
                    format_func=format_account,
                    help=(
                        "投入時是 TWR 投資帳戶；"
                        "取回時通常是投資組合外帳戶。"
                    ),
                )
            )

            edited_currency = st.selectbox(
                "原始幣別",
                options=currency_options,
                index=currency_options.index(
                    original_currency
                ),
            )

            edited_amount = st.number_input(
                "原幣金額",
                min_value=0.0,
                value=float(
                    selected_edit_flow.get(
                        "amount"
                    )
                    or 0
                ),
                step=1.0,
                format="%.4f",
            )

            edited_amount_twd_input = (
                st.number_input(
                    "換算後 TWD 金額",
                    min_value=0.0,
                    value=float(
                        selected_edit_flow.get(
                            "amount_twd"
                        )
                        or 0
                    ),
                    step=1.0,
                    format="%.2f",
                    disabled=(
                        edited_currency == "TWD"
                    ),
                    help=(
                        "若原始幣別為 TWD，系統會直接"
                        "使用原幣金額。外幣請填入資金流"
                        "發生時的 TWD 換算金額。"
                    ),
                )
            )

            edited_notes = st.text_area(
                "備註",
                value=(
                    selected_edit_flow.get(
                        "notes"
                    )
                    or ""
                ),
            )

            edit_submitted = (
                st.form_submit_button(
                    "儲存外部資金流修改",
                    type="primary",
                    width="stretch",
                )
            )

        if edit_submitted:
            edited_amount = float(
                edited_amount
            )

            if edited_currency == "TWD":
                edited_amount_twd = (
                    edited_amount
                )
            else:
                edited_amount_twd = float(
                    edited_amount_twd_input
                )

            if edited_amount <= 0:
                st.warning(
                    "原幣金額必須大於 0。"
                )

            elif edited_amount_twd <= 0:
                st.warning(
                    "換算後 TWD 金額必須大於 0。"
                )

            elif (
                edit_flow_type
                == "contribution"
                and edited_destination_id
                is None
            ):
                st.warning(
                    "投入資金必須指定目的投資帳戶。"
                )

            elif (
                edit_flow_type
                == "withdrawal"
                and edited_source_id is None
            ):
                st.warning(
                    "取回資金必須指定來源投資帳戶。"
                )

            else:
                edited_flow_at = datetime.combine(
                    edited_flow_date,
                    edited_flow_time,
                    tzinfo=SEATTLE_TIMEZONE,
                )

                update_payload = {
                    "flow_at": (
                        edited_flow_at.isoformat()
                    ),
                    "flow_type": edit_flow_type,
                    "amount": edited_amount,
                    "currency": edited_currency,
                    "amount_twd": (
                        edited_amount_twd
                    ),
                    "source_account_id": (
                        edited_source_id
                    ),
                    "destination_account_id": (
                        edited_destination_id
                    ),
                    "notes": (
                        edited_notes.strip()
                        or None
                    ),
                    "updated_at": (
                        datetime.now(
                            SEATTLE_TIMEZONE
                        ).isoformat()
                    ),
                }

                try:
                    (
                        supabase
                        .table(
                            "portfolio_cash_flows"
                        )
                        .update(
                            update_payload
                        )
                        .eq(
                            "id",
                            selected_edit_flow_id,
                        )
                        .execute()
                    )

                    st.session_state[
                        "twr_cash_flow_success"
                    ] = (
                        "TWR 外部資金流修改成功。"
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        "修改 TWR 外部資金流失敗："
                        f"{error}"
                    )

    with st.expander(
        "刪除外部資金流",
        expanded=False,
    ):
        flow_map = {
            flow["id"]: flow
            for flow in cash_flows
        }

        def format_delete_flow(flow_id):
            flow = flow_map[flow_id]

            label = FLOW_TYPE_LABELS.get(
                flow["flow_type"],
                flow["flow_type"],
            )

            return (
                f'{str(flow["flow_at"])[:10]}｜'
                f'{label}｜'
                f'{float(flow["amount_twd"]):,.2f} TWD'
            )

        selected_flow_id = st.selectbox(
            "選擇要刪除的紀錄",
            options=list(flow_map.keys()),
            format_func=format_delete_flow,
        )

        confirm_delete = st.checkbox(
            "我確認要刪除此筆外部資金流。",
            key="confirm_delete_twr_flow",
        )

        if st.button(
            "刪除外部資金流",
            type="primary",
            use_container_width=True,
        ):
            if not confirm_delete:
                st.warning(
                    "請先勾選刪除確認。"
                )
            else:
                try:
                    (
                        supabase.table(
                            "portfolio_cash_flows"
                        )
                        .delete()
                        .eq(
                            "id",
                            selected_flow_id,
                        )
                        .execute()
                    )

                    st.session_state[
                        "twr_cash_flow_success"
                    ] = (
                        "TWR 外部資金流已刪除。"
                    )

                    st.rerun()

                except Exception as error:
                    st.error(
                        "刪除外部資金流失敗："
                        f"{error}"
                    )