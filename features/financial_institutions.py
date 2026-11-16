import pandas as pd
import streamlit as st


INSTITUTION_TYPE_LABELS = {
    "bank": "銀行",
    "securities": "證券公司",
    "broker": "券商",
    "fund_platform": "基金平台",
    "post_office": "郵政機構",
    "other": "其他",
}

INSTITUTION_TYPE_OPTIONS = list(
    INSTITUTION_TYPE_LABELS.keys()
)


def show_financial_institution_manager(supabase):
    st.subheader("金融機構管理")

    st.caption(
        "建立及管理銀行、證券公司、券商與"
        "基金平台。封存機構不會刪除旗下帳戶。"
    )

    success_message = st.session_state.pop(
        "institution_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    delete_success_message = st.session_state.pop(
        "financial_institution_delete_success",
        None,
    )

    if delete_success_message:
        st.success(delete_success_message)

    try:
        institution_response = (
            supabase.table("financial_institutions")
            .select(
                "id, name, institution_type, country, "
                "notes, is_active, created_at, updated_at"
            )
            .order("name")
            .execute()
        )

        institutions = (
            institution_response.data or []
        )

        account_response = (
            supabase.table("accounts")
            .select(
                "id, institution_id, is_active"
            )
            .execute()
        )

        accounts = account_response.data or []

    except Exception as error:
        st.error(
            f"讀取金融機構資料失敗：{error}"
        )
        return

    with st.expander(
        "新增金融機構",
        expanded=False,
    ):
        with st.form(
            "add_financial_institution",
            clear_on_submit=True,
        ):
            institution_name = st.text_input(
                "金融機構名稱",
                placeholder="例如：台新銀行",
            )

            institution_type = st.selectbox(
                "機構類型",
                options=INSTITUTION_TYPE_OPTIONS,
                format_func=lambda value: (
                    INSTITUTION_TYPE_LABELS[value]
                ),
            )

            country = st.text_input(
                "國家或地區",
                placeholder="例如：台灣、美國",
            )

            notes = st.text_area(
                "備註",
                placeholder=(
                    "例如：包含薪轉、外幣及"
                    "基金平台帳戶。"
                ),
            )

            add_submitted = st.form_submit_button(
                "新增金融機構",
                use_container_width=True,
            )

        if add_submitted:
            cleaned_name = institution_name.strip()

            if not cleaned_name:
                st.warning("請輸入金融機構名稱。")

            else:
                try:
                    (
                        supabase.table(
                            "financial_institutions"
                        )
                        .insert(
                            {
                                "name": cleaned_name,
                                "institution_type": (
                                    institution_type
                                ),
                                "country": (
                                    country.strip()
                                    or None
                                ),
                                "notes": (
                                    notes.strip()
                                    or None
                                ),
                            }
                        )
                        .execute()
                    )

                    st.session_state[
                        "institution_success_message"
                    ] = "金融機構新增成功。"

                    st.rerun()

                except Exception as error:
                    st.error(
                        "新增金融機構失敗："
                        f"{error}"
                    )

    st.subheader("目前金融機構")

    if not institutions:
        st.info("目前尚未建立金融機構。")
        return

    total_account_counts = {}
    active_account_counts = {}

    for account in accounts:
        institution_id = account.get(
            "institution_id"
        )

        if not institution_id:
            continue

        total_account_counts[institution_id] = (
            total_account_counts.get(
                institution_id,
                0,
            )
            + 1
        )

        if account.get("is_active"):
            active_account_counts[institution_id] = (
                active_account_counts.get(
                    institution_id,
                    0,
                )
                + 1
            )

    display_rows = []

    for institution in institutions:
        institution_id = institution["id"]

        display_rows.append(
            {
                "金融機構": institution["name"],
                "類型": (
                    INSTITUTION_TYPE_LABELS.get(
                        institution[
                            "institution_type"
                        ],
                        institution[
                            "institution_type"
                        ],
                    )
                ),
                "國家／地區": (
                    institution.get("country")
                    or ""
                ),
                "使用中帳戶": (
                    active_account_counts.get(
                        institution_id,
                        0,
                    )
                ),
                "全部帳戶": (
                    total_account_counts.get(
                        institution_id,
                        0,
                    )
                ),
                "狀態": (
                    "使用中"
                    if institution["is_active"]
                    else "已封存"
                ),
                "備註": (
                    institution.get("notes")
                    or ""
                ),
            }
        )

    institution_dataframe = pd.DataFrame(
        display_rows
    )

    st.dataframe(
        institution_dataframe,
        use_container_width=True,
        hide_index=True,
    )

    institution_map = {
        institution["id"]: institution
        for institution in institutions
    }

    def format_institution(institution_id):
        institution = institution_map[
            institution_id
        ]

        status = (
            "使用中"
            if institution["is_active"]
            else "已封存"
        )

        institution_type = institution["institution_type"]
        type_label = INSTITUTION_TYPE_LABELS.get(
            institution_type,
            institution_type,
        )

        return (
            f'{institution["name"]}｜'
            f"{type_label}｜{status}"
        )

    with st.expander(
        "調整帳戶所屬金融機構",
        expanded=False,
    ):
        st.caption(
            "只會修改帳戶的上層金融機構，不會改變帳戶、"
            "資產、交易或歷史紀錄。"
        )

        try:
            account_response = (
                supabase.table("accounts")
                .select(
                    "id, name, institution_id, "
                    "institution, is_active"
                )
                .order("name")
                .execute()
            )
            assignment_accounts = account_response.data or []

        except Exception as exc:
            st.error(f"帳戶資料讀取失敗：{exc}")
            assignment_accounts = []

        active_assignment_institutions = [
            institution
            for institution in institutions
            if institution.get("is_active", True)
        ]

        assignment_institution_map = {
            institution["id"]: institution
            for institution in active_assignment_institutions
        }

        if not assignment_accounts:
            st.info("目前沒有可調整的帳戶。")

        elif not active_assignment_institutions:
            st.info("目前沒有使用中的金融機構。")

        else:
            assignment_account_map = {
                account["id"]: account
                for account in assignment_accounts
            }

            def format_assignment_account(account_id):
                account = assignment_account_map[account_id]
                current_institution_id = account.get(
                    "institution_id"
                )

                current_institution = (
                    assignment_institution_map.get(
                        current_institution_id
                    )
                )

                if current_institution:
                    current_name = current_institution["name"]
                else:
                    current_name = (
                        account.get("institution")
                        or "尚未歸類"
                    )

                status = (
                    "使用中"
                    if account.get("is_active", True)
                    else "已封存"
                )

                return (
                    f'{account["name"]}｜'
                    f"{current_name}｜{status}"
                )

            selected_assignment_account_id = st.selectbox(
                "選擇要調整的帳戶",
                options=list(assignment_account_map.keys()),
                format_func=format_assignment_account,
                key="institution_assignment_account",
            )

            selected_assignment_account = (
                assignment_account_map[
                    selected_assignment_account_id
                ]
            )

            current_assignment_institution_id = (
                selected_assignment_account.get(
                    "institution_id"
                )
            )

            target_institution_ids = [
                institution["id"]
                for institution
                in active_assignment_institutions
                if institution["id"]
                != current_assignment_institution_id
            ]

            if not target_institution_ids:
                st.info("目前沒有其他可轉移的金融機構。")

            else:
                def format_target_institution(
                    institution_id
                ):
                    institution = (
                        assignment_institution_map[
                            institution_id
                        ]
                    )

                    institution_type = institution[
                        "institution_type"
                    ]

                    type_label = (
                        INSTITUTION_TYPE_LABELS.get(
                            institution_type,
                            institution_type,
                        )
                    )

                    return (
                        f'{institution["name"]}｜'
                        f"{type_label}"
                    )

                with st.form(
                    "account_institution_assignment_form"
                ):
                    target_institution_id = st.selectbox(
                        "移動至",
                        options=target_institution_ids,
                        format_func=(
                            format_target_institution
                        ),
                    )

                    assignment_submitted = (
                        st.form_submit_button(
                            "確認移動帳戶",
                            type="primary",
                            use_container_width=True,
                        )
                    )

                if assignment_submitted:
                    target_institution = (
                        assignment_institution_map[
                            target_institution_id
                        ]
                    )

                    try:
                        (
                            supabase.table("accounts")
                            .update(
                                {
                                    "institution_id": (
                                        target_institution_id
                                    ),
                                    # 暫時同步舊欄位，
                                    # 確保既有功能相容
                                    "institution": (
                                        target_institution[
                                            "name"
                                        ]
                                    ),
                                }
                            )
                            .eq(
                                "id",
                                selected_assignment_account_id,
                            )
                            .execute()
                        )

                        st.success(
                            f'已將「'
                            f'{selected_assignment_account["name"]}'
                            f'」移至「'
                            f'{target_institution["name"]}'
                            f'」。'
                        )
                        st.rerun()

                    except Exception as exc:
                        st.error(
                            f"帳戶移動失敗：{exc}"
                        )

    with st.expander(
        "編輯或封存金融機構",
        expanded=False,
    ):
        selected_institution_id = st.selectbox(
            "選擇金融機構",
            options=list(institution_map.keys()),
            format_func=format_institution,
            key="edit_financial_institution",
        )

        selected_institution = institution_map[
            selected_institution_id
        ]

        current_type = selected_institution[
            "institution_type"
        ]

        with st.form(
            f"edit_institution_"
            f"{selected_institution_id}"
        ):
            edited_name = st.text_input(
                "金融機構名稱",
                value=selected_institution["name"],
            )

            edited_type = st.selectbox(
                "機構類型",
                options=INSTITUTION_TYPE_OPTIONS,
                format_func=lambda value: (
                    INSTITUTION_TYPE_LABELS[value]
                ),
                index=(
                    INSTITUTION_TYPE_OPTIONS.index(
                        current_type
                    )
                ),
            )

            edited_country = st.text_input(
                "國家或地區",
                value=(
                    selected_institution.get(
                        "country"
                    )
                    or ""
                ),
            )

            edited_notes = st.text_area(
                "備註",
                value=(
                    selected_institution.get("notes")
                    or ""
                ),
            )

            edit_submitted = st.form_submit_button(
                "儲存金融機構修改",
                use_container_width=True,
            )

        if edit_submitted:
            cleaned_name = edited_name.strip()

            if not cleaned_name:
                st.warning("金融機構名稱不可空白。")

            else:
                try:
                    (
                        supabase.table(
                            "financial_institutions"
                        )
                        .update(
                            {
                                "name": cleaned_name,
                                "institution_type": (
                                    edited_type
                                ),
                                "country": (
                                    edited_country.strip()
                                    or None
                                ),
                                "notes": (
                                    edited_notes.strip()
                                    or None
                                ),
                            }
                        )
                        .eq(
                            "id",
                            selected_institution_id,
                        )
                        .execute()
                    )

                    st.session_state[
                        "institution_success_message"
                    ] = "金融機構修改成功。"

                    st.rerun()

                except Exception as error:
                    st.error(
                        "修改金融機構失敗："
                        f"{error}"
                    )

        new_status = not selected_institution[
            "is_active"
        ]

        action_label = (
            "恢復金融機構"
            if new_status
            else "封存金融機構"
        )

        if st.button(
            action_label,
            use_container_width=True,
            key=(
                "toggle_institution_"
                f"{selected_institution_id}"
            ),
        ):
            try:
                (
                    supabase.table(
                        "financial_institutions"
                    )
                    .update(
                        {
                            "is_active": new_status,
                        }
                    )
                    .eq(
                        "id",
                        selected_institution_id,
                    )
                    .execute()
                )

                st.session_state[
                    "institution_success_message"
                ] = (
                    "金融機構狀態更新成功。"
                )

                st.rerun()

            except Exception as error:
                st.error(
                    "更新金融機構狀態失敗："
                    f"{error}"
                )

    with st.expander(
        "刪除空的金融機構",
        expanded=False,
    ):
        st.caption(
            "只有完全沒有帳戶歸屬的金融機構才能刪除。"
            "刪除金融機構不會刪除任何帳戶、資產或交易。"
        )

        try:
            delete_institution_response = (
                supabase.table("financial_institutions")
                .select(
                    "id, name, institution_type, is_active"
                )
                .order("name")
                .execute()
            )

            delete_account_response = (
                supabase.table("accounts")
                .select(
                    "id, name, institution_id, "
                    "institution, is_active"
                )
                .execute()
            )

            delete_institutions = (
                delete_institution_response.data or []
            )
            delete_accounts = (
                delete_account_response.data or []
            )

        except Exception as exc:
            st.error(f"刪除檢查資料讀取失敗：{exc}")
            delete_institutions = []
            delete_accounts = []

        empty_institutions = []

        for institution in delete_institutions:
            institution_id = institution["id"]
            institution_name = institution["name"]

            linked_accounts = [
                account
                for account in delete_accounts
                if (
                    account.get("institution_id")
                    == institution_id
                )
                or (
                    not account.get("institution_id")
                    and account.get("institution")
                    == institution_name
                )
            ]

            if not linked_accounts:
                empty_institutions.append(institution)

        if not empty_institutions:
            st.info(
                "目前沒有可以刪除的空金融機構。"
            )

        else:
            empty_institution_map = {
                institution["id"]: institution
                for institution in empty_institutions
            }

            def format_empty_institution(
                institution_id
            ):
                institution = empty_institution_map[
                    institution_id
                ]

                institution_type = institution[
                    "institution_type"
                ]

                type_label = (
                    INSTITUTION_TYPE_LABELS.get(
                        institution_type,
                        institution_type,
                    )
                )

                status = (
                    "使用中"
                    if institution.get("is_active", True)
                    else "已封存"
                )

                return (
                    f'{institution["name"]}｜'
                    f"{type_label}｜{status}"
                )

            with st.form(
                "delete_empty_institution_form"
            ):
                delete_institution_id = st.selectbox(
                    "選擇要刪除的金融機構",
                    options=list(
                        empty_institution_map.keys()
                    ),
                    format_func=format_empty_institution,
                )

                selected_delete_institution = (
                    empty_institution_map[
                        delete_institution_id
                    ]
                )

                delete_confirmation = st.checkbox(
                    f'我確認要永久刪除「'
                    f'{selected_delete_institution["name"]}'
                    f'」金融機構。',
                )

                delete_submitted = (
                    st.form_submit_button(
                        "永久刪除金融機構",
                        type="primary",
                        use_container_width=True,
                    )
                )

            if delete_submitted:
                if not delete_confirmation:
                    st.warning(
                        "請先勾選確認，再執行永久刪除。"
                    )

                else:
                    # 按下按鈕後再次檢查，避免頁面開啟期間
                    # 有帳戶被移入該金融機構。
                    try:
                        final_account_response = (
                            supabase.table("accounts")
                            .select("id")
                            .eq(
                                "institution_id",
                                delete_institution_id,
                            )
                            .execute()
                        )

                        final_linked_accounts = (
                            final_account_response.data or []
                        )

                        if final_linked_accounts:
                            st.error(
                                "此金融機構目前已有帳戶，"
                                "因此不能刪除。"
                            )

                        else:
                            (
                                supabase.table(
                                    "financial_institutions"
                                )
                                .delete()
                                .eq(
                                    "id",
                                    delete_institution_id,
                                )
                                .execute()
                            )

                            st.session_state[
                                "financial_institution_delete_success"
                            ] = (
                                f'已刪除金融機構「'
                                f'{selected_delete_institution["name"]}'
                                f'」。'
                            )

                            st.rerun()

                    except Exception as exc:
                        st.error(
                            f"金融機構刪除失敗：{exc}"
                        )