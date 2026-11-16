import pandas as pd
import streamlit as st

from config import (
    ACCOUNT_TYPE_LABELS,
    ACCOUNT_TYPE_OPTIONS,
    CURRENCY_OPTIONS,
)

from features.financial_institutions import (
    show_financial_institution_manager,
)

def show_account_manager(supabase):
    st.subheader("帳戶管理")
    st.caption("建立銀行、券商及基金平台帳戶。請勿輸入完整帳號或卡號。")

    success_message = st.session_state.pop(
        "account_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    if success_message:
        st.success(success_message)

    st.divider()

    show_financial_institution_manager(
        supabase
    )

    st.divider()

    try:
        institution_response = (
            supabase.table("financial_institutions")
            .select(
                "id, name, institution_type, "
                "is_active"
            )
            .order("name")
            .execute()
        )

        institutions = (
            institution_response.data or []
        )

    except Exception as error:
        st.error(
            f"讀取金融機構失敗：{error}"
        )
        institutions = []

    institution_map = {
        institution["id"]: institution
        for institution in institutions
    }

    active_institution_ids = [
        institution["id"]
        for institution in institutions
        if institution.get("is_active", True)
    ]

    def format_institution_option(
        institution_id
    ):
        institution = institution_map[
            institution_id
        ]

        status = (
            ""
            if institution.get("is_active", True)
            else "｜已封存"
        )

        return (
            f'{institution["name"]}｜'
            f'{institution["institution_type"]}'
            f"{status}"
        )

    with st.expander("新增帳戶", expanded=False):
        with st.form("add_account_form", clear_on_submit=True):
            account_name = st.text_input(
                "帳戶名稱",
                placeholder="例如：BofA Checking",
            )

            selected_institution_id = (
                st.selectbox(
                    "金融機構",
                    options=active_institution_ids,
                    format_func=(
                        format_institution_option
                    ),
                )
            )

            account_type = st.selectbox(
                "帳戶類型",
                options=ACCOUNT_TYPE_OPTIONS,
                format_func=lambda value: ACCOUNT_TYPE_LABELS[value],
            )

            base_currency = st.selectbox(
                "主要幣別",
                options=CURRENCY_OPTIONS,
            )

            include_in_twr = st.checkbox(
                "納入 TWR 投資績效",
                value=False,
                help=(
                    "勾選後，此帳戶內的投資與現金"
                    "都會納入時間加權報酬率。"
                    "生活用銀行帳戶通常不勾選。"
                ),
            )        

            submitted = st.form_submit_button(
                "新增帳戶",
                width='stretch',
            )

        if submitted:
            cleaned_name = account_name.strip()

            if not cleaned_name:
                st.warning("請輸入帳戶名稱。")
            else:
                try:
                    supabase.table("accounts").insert(
                        {
                            "name": cleaned_name,
                            "institution_id": (
                                selected_institution_id
                            ),
                            "institution": (
                                institution_map[
                                    selected_institution_id
                                ]["name"]
                            ),
                            "account_type": account_type,
                            "base_currency": base_currency,
                            "include_in_twr": (
                                include_in_twr
                            ),
                        }
                    ).execute()

                    st.success("帳戶新增成功。")

                except Exception as error:
                    st.error(f"新增帳戶失敗：{error}")

    try:
        response = (
            supabase.table("accounts")
            .select(
                "id, name, institution_id, institution, "
                "account_type, base_currency, "
                "include_in_twr, is_active, created_at"
            )
            .order("created_at")
            .execute()
        )

        accounts = response.data or []

    except Exception as error:
        st.error(f"讀取帳戶失敗：{error}")
        return

    st.divider()
    st.subheader("目前帳戶")

    if not accounts:
        st.info("目前還沒有帳戶，請先在上方新增。")
        return

    display_data = []

    for account in accounts:
        display_data.append(
            {
                "帳戶名稱": account["name"],
                "金融機構": account["institution"] or "",
                "帳戶類型": ACCOUNT_TYPE_LABELS.get(
                    account["account_type"],
                    account["account_type"],
                ),
                "主要幣別": account["base_currency"],
                "納入 TWR": (
                    "是"
                    if account.get(
                        "include_in_twr",
                        False,
                    )
                    else "否"
                ),
                "狀態": (
                    "使用中"
                    if account["is_active"]
                    else "已封存"
                ),
                "建立時間": account["created_at"],
            }
        )

    account_dataframe = pd.DataFrame(display_data)

    account_dataframe["建立時間"] = pd.to_datetime(
        account_dataframe["建立時間"]
    ).dt.strftime("%Y-%m-%d")

    st.dataframe(
        account_dataframe,
        width='stretch',
        hide_index=True,
    )

    with st.expander("編輯帳戶"):
        edit_account_ids = [
            account["id"]
            for account in accounts
        ]

        def format_edit_account(account_id):
            selected = next(
                account
                for account in accounts
                if account["id"] == account_id
            )

            institution_name = (
                selected["institution"]
                if selected["institution"]
                else "未指定機構"
            )

            return (
                f'{selected["name"]} | '
                f"{institution_name}"
            )

        selected_edit_account_id = st.selectbox(
            "選擇要編輯的帳戶",
            options=edit_account_ids,
            format_func=format_edit_account,
            key="selected_edit_account_id",
        )

        selected_edit_account = next(
            account
            for account in accounts
            if account["id"] == selected_edit_account_id
        )

        try:
            account_type_index = ACCOUNT_TYPE_OPTIONS.index(
                selected_edit_account["account_type"]
            )
        except ValueError:
            account_type_index = 0

        try:
            currency_index = CURRENCY_OPTIONS.index(
                selected_edit_account["base_currency"]
            )
        except ValueError:
            currency_index = 0

        edit_institution_ids = list(
            active_institution_ids
        )

        current_edit_institution_id = (
            selected_edit_account.get(
                "institution_id"
            )
        )

        # 若帳戶目前屬於已封存機構，
        # 編輯時仍保留該選項。
        if (
            current_edit_institution_id
            in institution_map
            and current_edit_institution_id
            not in edit_institution_ids
        ):
            edit_institution_ids.append(
                current_edit_institution_id
            )

        if (
            current_edit_institution_id
            in edit_institution_ids
        ):
            edit_institution_index = (
                edit_institution_ids.index(
                    current_edit_institution_id
                )
            )
        else:
            edit_institution_index = 0

        with st.form(
            f"edit_account_form_{selected_edit_account_id}"
        ):
            edited_name = st.text_input(
                "帳戶名稱",
                value=selected_edit_account["name"],
            )

            edited_institution_id = st.selectbox(
                "金融機構",
                options=edit_institution_ids,
                index=edit_institution_index,
                format_func=(
                    format_institution_option
                ),
                key=(
                    "edited_account_institution_"
                    f"{selected_edit_account_id}"
                ),
            )

            edited_account_type = st.selectbox(
                "帳戶類型",
                options=ACCOUNT_TYPE_OPTIONS,
                index=account_type_index,
                format_func=lambda value: ACCOUNT_TYPE_LABELS[value],
            )

            edited_base_currency = st.selectbox(
                "主要幣別",
                options=CURRENCY_OPTIONS,
                index=currency_index,
            )

            edited_include_in_twr = st.checkbox(
                "納入 TWR 投資績效",
                value=selected_edit_account.get(
                    "include_in_twr",
                    False,
                ),
                help=(
                    "帳戶內的證券及現金都會納入 "
                    "TWR；帳戶與投資組合外部之間"
                    "的資金移動則記為外部現金流。"
                ),
                key=(
                    "edited_include_in_twr_"
                    f"{selected_edit_account_id}"
                ),
            )

            edit_submitted = st.form_submit_button(
                "儲存修改",
                width='stretch',
            )

        if edit_submitted:
            cleaned_edited_name = edited_name.strip()

            if not cleaned_edited_name:
                st.warning("帳戶名稱不能留白。")

            else:
                try:
                    (
                        supabase.table("accounts")
                        .update(
                            {
                                "name": cleaned_edited_name,
                                "institution_id": (
                                    edited_institution_id
                                ),
                                "institution": (
                                    institution_map[
                                        edited_institution_id
                                    ]["name"]
                                ),
                                "account_type": edited_account_type,
                                "base_currency": edited_base_currency,
                                "include_in_twr": (
                                    edited_include_in_twr
                                ),
                            }
                        )
                        .eq("id", selected_edit_account_id)
                        .execute()
                    )

                    st.session_state[
                        "account_success_message"
                    ] = "帳戶資料修改成功。"

                    st.rerun()

                except Exception as error:
                    st.error(f"修改帳戶失敗：{error}")

    st.divider()

    with st.expander("封存或恢復帳戶"):    
        account_ids = [account["id"] for account in accounts]

        def format_account(account_id):
            selected = next(
                account
                for account in accounts
                if account["id"] == account_id
            )

            institution_name = (
                selected["institution"]
                if selected["institution"]
                else "未指定機構"
            )

            status = (
                "使用中"
                if selected["is_active"]
                else "已封存"
            )

            return (
                f'{selected["name"]} | '
                f"{institution_name} | {status}"
            )

        selected_account_id = st.selectbox(
            "選擇帳戶",
            options=account_ids,
            format_func=format_account,
        )

        selected_account = next(
            account
            for account in accounts
            if account["id"] == selected_account_id
        )

        new_status = not selected_account["is_active"]

        action_label = (
            "恢復帳戶"
            if new_status
            else "封存帳戶"
        )

        if st.button(
            action_label,
            width='stretch',
        ):
            try:
                (
                    supabase.table("accounts")
                    .update({"is_active": new_status})
                    .eq("id", selected_account_id)
                    .execute()
                )

                st.rerun()

            except Exception as error:
                st.error(f"更新帳戶失敗：{error}")