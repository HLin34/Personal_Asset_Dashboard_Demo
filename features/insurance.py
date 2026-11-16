from datetime import date

import pandas as pd
import streamlit as st


INSURANCE_GROUP_STATUS_LABELS = {
    "active": "保障中",
    "paid_up": "已繳清",
    "expired": "已到期",
    "terminated": "已終止",
    "surrendered": "已解約",
    "unknown": "待確認",
}

INSURANCE_GROUP_STATUS_OPTIONS = list(
    INSURANCE_GROUP_STATUS_LABELS.keys()
)


PAYMENT_FREQUENCY_LABELS = {
    "unknown": "待確認",
    "monthly": "月繳",
    "quarterly": "季繳",
    "semiannual": "半年繳",
    "annual": "年繳",
    "single": "躉繳",
}

PAYMENT_FREQUENCY_OPTIONS = list(
    PAYMENT_FREQUENCY_LABELS.keys()
)


INSURANCE_CURRENCY_OPTIONS = [
    "TWD",
    "USD",
    "JPY",
    "CNY",
    "EUR",
    "GBP",
    "AUD",
    "CAD",
    "HKD",
]

CONTRACT_ROLE_LABELS = {
    "main": "主約",
    "rider": "附約",
}

CONTRACT_ROLE_OPTIONS = list(
    CONTRACT_ROLE_LABELS.keys()
)


INSURANCE_CATEGORY_LABELS = {
    "life": "壽險",
    "medical": "醫療",
    "hospitalization": "住院醫療",
    "surgery": "手術醫療",
    "critical_illness": "重大疾病",
    "cancer": "癌症",
    "disability": "失能",
    "accident": "意外",
    "long_term_care": "長期照護",
    "premium_waiver": "保費豁免",
    "annuity": "年金",
    "savings": "儲蓄型",
    "investment_linked": "投資型",
    "other": "其他",
}

BENEFIT_TYPE_LABELS = {
    "death": "身故保障",
    "disability": "失能保障",
    "hospital_daily": "住院日額",
    "icu": "加護病房",
    "outpatient": "門診醫療",
    "emergency": "急診／緊急醫療",
    "surgery": "手術醫療",
    "critical_illness": "重大疾病",
    "cancer": "癌症保障",
    "accident": "意外保障",
    "long_term_care": "長期照護",
    "premium_waiver": "保費豁免",
    "maturity": "滿期給付",
    "surrender": "解約權益",
    "policy_loan": "保單借款",
    "other": "其他",
}

BENEFIT_TYPE_OPTIONS = list(
    BENEFIT_TYPE_LABELS.keys()
)

INSURANCE_CATEGORY_OPTIONS = list(
    INSURANCE_CATEGORY_LABELS.keys()
)


VERIFICATION_STATUS_LABELS = {
    "confirmed": "已確認",
    "partially_confirmed": "部分確認",
    "pending": "待確認",
}

VERIFICATION_STATUS_OPTIONS = list(
    VERIFICATION_STATUS_LABELS.keys()
)


PREMIUM_WAIVER_STATUS_LABELS = {
    "not_applicable": "不適用",
    "not_waived": "尚未豁免",
    "waived": "已進入豁免",
    "unknown": "待確認",
}

PREMIUM_WAIVER_STATUS_OPTIONS = list(
    PREMIUM_WAIVER_STATUS_LABELS.keys()
)

INSURANCE_VALUE_TYPE_LABELS = {
    "cash_value": "保單現金價值",
    "surrender_value": "解約金",
    "policy_reserve": "保單價值準備金",
    "account_value": "保單帳戶價值",
    "maturity_value": "滿期價值",
    "loan_balance": "保單借款餘額",
    "other": "其他價值",
}

INSURANCE_VALUE_TYPE_OPTIONS = list(
    INSURANCE_VALUE_TYPE_LABELS.keys()
)

INSURANCE_VALUE_STATUS_LABELS = {
    "confirmed": "已確認",
    "partially_confirmed": "部分確認",
    "pending": "待確認",
}

INSURANCE_VALUE_STATUS_OPTIONS = list(
    INSURANCE_VALUE_STATUS_LABELS.keys()
)

def _date_to_text(value):
    if value is None:
        return None

    if isinstance(value, date):
        return value.isoformat()

    return str(value)

def _parse_database_date(value):
    if not value:
        return None

    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None

def _display_date(value):
    if not value:
        return "未設定"

    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _display_amount(value, currency):
    if value is None:
        return "未記錄"

    try:
        amount = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"{amount:,.2f} {currency}"


def _parse_optional_amount(value):
    cleaned_value = value.strip().replace(",", "")

    if not cleaned_value:
        return None

    try:
        parsed_value = float(cleaned_value)
    except ValueError:
        raise ValueError(
            "年繳保費必須是數字，或保持空白。"
        )

    if parsed_value < 0:
        raise ValueError("年繳保費不能小於零。")

    return parsed_value


def _load_insurance_data(supabase):
    groups_response = (
        supabase.table("insurance_policy_groups")
        .select(
            "id, group_name, insurer, policy_number_hint, "
            "policyholder_role, primary_insured_role, "
            "effective_date, premium_end_date, "
            "coverage_end_date, currency, "
            "payment_frequency, annual_premium, "
            "status, notes, created_at, updated_at"
        )
        .order("created_at", desc=True)
        .execute()
    )

    policies_response = (
        supabase.table("insurance_policies")
        .select(
            "id, policy_group_id, parent_policy_id, "
            "product_code, product_name, contract_role, "
            "insurance_category, insured_role, "
            "coverage_amount, currency, coverage_unit, "
            "effective_date, premium_end_date, "
            "coverage_end_date, status, "
            "premium_waiver_status, "
            "verification_status, notes, "
            "created_at, updated_at"
        )
        .order("created_at")
        .execute()
    )

    benefits_response = (
        supabase.table("insurance_benefits")
        .select(
            "id, policy_id, benefit_type, "
            "benefit_name, benefit_amount, currency, "
            "benefit_unit, calculation_formula, "
            "benefit_summary, eligibility_conditions, "
            "benefit_limits, waiting_period, "
            "source_document, source_clause, "
            "verification_status, sort_order, notes, "
            "created_at, updated_at"
        )
        .order("sort_order")
        .order("created_at")
        .execute()
    )

    values_response = (
        supabase.table("insurance_policy_values")
        .select(
            "id, policy_group_id, valuation_date, "
            "value_type, amount, currency"
        )
        .order("valuation_date", desc=True)
        .execute()
    )

    return (
        groups_response.data or [],
        policies_response.data or [],
        benefits_response.data or [],
        values_response.data or [],
    )


def _show_insurance_summary(
    groups,
    policies,
    benefits,
    policy_values,
):
    active_group_count = sum(
        1
        for group in groups
        if group["status"] == "active"
    )

    confirmed_policy_count = sum(
        1
        for policy in policies
        if policy["verification_status"] == "confirmed"
    )

    pending_benefit_count = sum(
        1
        for benefit in benefits
        if benefit["verification_status"] != "confirmed"
    )

    summary_col1, summary_col2, summary_col3, summary_col4 = (
        st.columns(4)
    )

    with summary_col1:
        st.metric(
            "保障中保單組合",
            active_group_count,
        )

    with summary_col2:
        st.metric(
            "主約與附約",
            len(policies),
        )

    with summary_col3:
        st.metric(
            "已確認險種",
            confirmed_policy_count,
        )

    with summary_col4:
        st.metric(
            "待確認權益",
            pending_benefit_count,
            help=(
                "尚未依正式保單或條款完整確認的保障權益。"
            ),
        )

    if policy_values:
        latest_value_date = max(
            value_record["valuation_date"]
            for value_record in policy_values
            if value_record.get("valuation_date")
        )

        st.caption(
            f"目前已有 {len(policy_values)} 筆保單價值紀錄；"
            f"最新資料日期為 {latest_value_date}。"
            "這些金額不會自動納入總資產。"
        )


def _show_add_policy_group(supabase):
    with st.expander(
        "新增保單組合",
        expanded=False,
    ):
        st.caption(
            "一份主約及附加於該主約的附約，"
            "應建立為同一個保單組合。"
        )

        with st.form(
            "add_insurance_policy_group_form",
            clear_on_submit=True,
        ):
            form_col1, form_col2 = st.columns(2)

            with form_col1:
                group_name = st.text_input(
                    "保單組合名稱",
                    placeholder=(
                        "例如：三商美邦 20AWL 保單組合"
                    ),
                )

                insurer = st.text_input(
                    "保險公司",
                    placeholder="例如：三商美邦人壽",
                )

                policy_number_hint = st.text_input(
                    "保單識別（選填）",
                    placeholder="建議只填末四碼或自訂代稱",
                    help=(
                        "不建議在系統中保存完整保單號碼。"
                    ),
                )

                currency = st.selectbox(
                    "保單幣別",
                    options=INSURANCE_CURRENCY_OPTIONS,
                    index=0,
                )

                status = st.selectbox(
                    "保單狀態",
                    options=INSURANCE_GROUP_STATUS_OPTIONS,
                    format_func=lambda value: (
                        INSURANCE_GROUP_STATUS_LABELS[value]
                    ),
                )

            with form_col2:
                policyholder_role = st.text_input(
                    "要保人角色（選填）",
                    placeholder="例如：家人、本人",
                )

                primary_insured_role = st.text_input(
                    "主要被保險人角色（選填）",
                    placeholder="例如：本人",
                )

                payment_frequency = st.selectbox(
                    "繳費頻率",
                    options=PAYMENT_FREQUENCY_OPTIONS,
                    format_func=lambda value: (
                        PAYMENT_FREQUENCY_LABELS[value]
                    ),
                )

                annual_premium_text = st.text_input(
                    "年繳保費（選填）",
                    placeholder=(
                        "不確定或不重要時可保持空白"
                    ),
                )

            date_col1, date_col2, date_col3 = st.columns(3)

            with date_col1:
                effective_date = st.date_input(
                    "契約生效日（選填）",
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col2:
                premium_end_date = st.date_input(
                    "繳費終日（選填）",
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col3:
                coverage_end_date = st.date_input(
                    "保障終日（選填）",
                    value=None,
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            notes = st.text_area(
                "備註（選填）",
                placeholder=(
                    "例如：保費資料待確認、"
                    "保障內容以正式條款為準"
                ),
            )

            submitted = st.form_submit_button(
                "新增保單組合",
                use_container_width=True,
            )

        if submitted:
            cleaned_group_name = group_name.strip()
            cleaned_insurer = insurer.strip()

            if not cleaned_group_name:
                st.warning("請輸入保單組合名稱。")
                return

            if not cleaned_insurer:
                st.warning("請輸入保險公司。")
                return

            if (
                premium_end_date is not None
                and effective_date is not None
                and premium_end_date < effective_date
            ):
                st.warning(
                    "繳費終日不能早於契約生效日。"
                )
                return

            if (
                coverage_end_date is not None
                and effective_date is not None
                and coverage_end_date < effective_date
            ):
                st.warning(
                    "保障終日不能早於契約生效日。"
                )
                return

            try:
                annual_premium = _parse_optional_amount(
                    annual_premium_text
                )

                (
                    supabase.table(
                        "insurance_policy_groups"
                    )
                    .insert(
                        {
                            "group_name": cleaned_group_name,
                            "insurer": cleaned_insurer,
                            "policy_number_hint": (
                                policy_number_hint.strip()
                                or None
                            ),
                            "policyholder_role": (
                                policyholder_role.strip()
                                or None
                            ),
                            "primary_insured_role": (
                                primary_insured_role.strip()
                                or None
                            ),
                            "effective_date": _date_to_text(
                                effective_date
                            ),
                            "premium_end_date": _date_to_text(
                                premium_end_date
                            ),
                            "coverage_end_date": _date_to_text(
                                coverage_end_date
                            ),
                            "currency": currency,
                            "payment_frequency": (
                                payment_frequency
                            ),
                            "annual_premium": annual_premium,
                            "status": status,
                            "notes": notes.strip() or None,
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "insurance_success_message"
                ] = "保單組合新增成功。"

                st.rerun()

            except ValueError as error:
                st.warning(str(error))

            except Exception as error:
                st.error(
                    f"新增保單組合失敗：{error}"
                )

def _show_edit_policy_group(
    supabase,
    groups,
):
    with st.expander(
        "編輯保單組合",
        expanded=False,
    ):
        if not groups:
            st.info("目前沒有可以編輯的保單組合。")
            return

        group_ids = [
            group["id"]
            for group in groups
        ]

        group_by_id = {
            group["id"]: group
            for group in groups
        }

        def format_group(group_id):
            group = group_by_id[group_id]

            return (
                f'{group["insurer"]}｜'
                f'{group["group_name"]}'
            )

        selected_group_id = st.selectbox(
            "選擇保單組合",
            options=group_ids,
            format_func=format_group,
            key="edit_insurance_group_id",
        )

        selected_group = group_by_id[
            selected_group_id
        ]

        current_status = selected_group.get(
            "status",
            "active",
        )

        if (
            current_status
            not in INSURANCE_GROUP_STATUS_OPTIONS
        ):
            current_status = "unknown"

        current_frequency = selected_group.get(
            "payment_frequency",
            "unknown",
        )

        if (
            current_frequency
            not in PAYMENT_FREQUENCY_OPTIONS
        ):
            current_frequency = "unknown"

        current_currency = selected_group.get(
            "currency",
            "TWD",
        )

        if current_currency not in INSURANCE_CURRENCY_OPTIONS:
            current_currency = "TWD"

        existing_annual_premium = selected_group.get(
            "annual_premium"
        )

        if existing_annual_premium is None:
            annual_premium_default = ""
        else:
            annual_premium_default = str(
                existing_annual_premium
            )

        with st.form(
            f"edit_insurance_group_form_"
            f"{selected_group_id}"
        ):
            form_col1, form_col2 = st.columns(2)

            with form_col1:
                edited_group_name = st.text_input(
                    "保單組合名稱",
                    value=(
                        selected_group.get("group_name")
                        or ""
                    ),
                )

                edited_insurer = st.text_input(
                    "保險公司",
                    value=(
                        selected_group.get("insurer")
                        or ""
                    ),
                )

                edited_policy_number_hint = st.text_input(
                    "保單識別（選填）",
                    value=(
                        selected_group.get(
                            "policy_number_hint"
                        )
                        or ""
                    ),
                    help=(
                        "建議只保存末四碼或自訂代稱。"
                    ),
                )

                edited_currency = st.selectbox(
                    "保單幣別",
                    options=INSURANCE_CURRENCY_OPTIONS,
                    index=(
                        INSURANCE_CURRENCY_OPTIONS.index(
                            current_currency
                        )
                    ),
                )

                edited_status = st.selectbox(
                    "保單狀態",
                    options=(
                        INSURANCE_GROUP_STATUS_OPTIONS
                    ),
                    index=(
                        INSURANCE_GROUP_STATUS_OPTIONS.index(
                            current_status
                        )
                    ),
                    format_func=lambda value: (
                        INSURANCE_GROUP_STATUS_LABELS[value]
                    ),
                )

            with form_col2:
                edited_policyholder_role = st.text_input(
                    "要保人角色（選填）",
                    value=(
                        selected_group.get(
                            "policyholder_role"
                        )
                        or ""
                    ),
                )

                edited_primary_insured_role = (
                    st.text_input(
                        "主要被保險人角色（選填）",
                        value=(
                            selected_group.get(
                                "primary_insured_role"
                            )
                            or ""
                        ),
                    )
                )

                edited_payment_frequency = st.selectbox(
                    "繳費頻率",
                    options=PAYMENT_FREQUENCY_OPTIONS,
                    index=(
                        PAYMENT_FREQUENCY_OPTIONS.index(
                            current_frequency
                        )
                    ),
                    format_func=lambda value: (
                        PAYMENT_FREQUENCY_LABELS[value]
                    ),
                )

                edited_annual_premium_text = st.text_input(
                    "年繳保費（選填）",
                    value=annual_premium_default,
                )

            date_col1, date_col2, date_col3 = (
                st.columns(3)
            )

            with date_col1:
                edited_effective_date = st.date_input(
                    "契約生效日（選填）",
                    value=_parse_database_date(
                        selected_group.get(
                            "effective_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col2:
                edited_premium_end_date = st.date_input(
                    "繳費終日（選填）",
                    value=_parse_database_date(
                        selected_group.get(
                            "premium_end_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col3:
                edited_coverage_end_date = st.date_input(
                    "保障終日（選填）",
                    value=_parse_database_date(
                        selected_group.get(
                            "coverage_end_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            edited_notes = st.text_area(
                "備註（選填）",
                value=(
                    selected_group.get("notes")
                    or ""
                ),
            )

            submitted = st.form_submit_button(
                "儲存保單組合修改",
                use_container_width=True,
            )

        if not submitted:
            return

        cleaned_group_name = (
            edited_group_name.strip()
        )

        cleaned_insurer = edited_insurer.strip()

        if not cleaned_group_name:
            st.warning("請輸入保單組合名稱。")
            return

        if not cleaned_insurer:
            st.warning("請輸入保險公司。")
            return

        if (
            edited_effective_date is not None
            and edited_premium_end_date is not None
            and edited_premium_end_date
            < edited_effective_date
        ):
            st.warning(
                "繳費終日不能早於契約生效日。"
            )
            return

        if (
            edited_effective_date is not None
            and edited_coverage_end_date is not None
            and edited_coverage_end_date
            < edited_effective_date
        ):
            st.warning(
                "保障終日不能早於契約生效日。"
            )
            return

        try:
            edited_annual_premium = (
                _parse_optional_amount(
                    edited_annual_premium_text
                )
            )

            (
                supabase.table(
                    "insurance_policy_groups"
                )
                .update(
                    {
                        "group_name": cleaned_group_name,
                        "insurer": cleaned_insurer,
                        "policy_number_hint": (
                            edited_policy_number_hint.strip()
                            or None
                        ),
                        "policyholder_role": (
                            edited_policyholder_role.strip()
                            or None
                        ),
                        "primary_insured_role": (
                            edited_primary_insured_role.strip()
                            or None
                        ),
                        "effective_date": _date_to_text(
                            edited_effective_date
                        ),
                        "premium_end_date": _date_to_text(
                            edited_premium_end_date
                        ),
                        "coverage_end_date": _date_to_text(
                            edited_coverage_end_date
                        ),
                        "currency": edited_currency,
                        "payment_frequency": (
                            edited_payment_frequency
                        ),
                        "annual_premium": (
                            edited_annual_premium
                        ),
                        "status": edited_status,
                        "notes": (
                            edited_notes.strip()
                            or None
                        ),
                    }
                )
                .eq("id", selected_group_id)
                .execute()
            )

            st.session_state[
                "insurance_success_message"
            ] = "保單組合修改成功。"

            st.rerun()

        except ValueError as error:
            st.warning(str(error))

        except Exception as error:
            st.error(
                f"修改保單組合失敗：{error}"
            )

def _show_policy_manager(
    supabase,
    groups,
    policies,
):
    st.divider()
    st.subheader("主約與附約管理")

    if not groups:
        st.info(
            "請先建立保單組合，才能新增主約或附約。"
        )
        return

    group_by_id = {
        group["id"]: group
        for group in groups
    }

    group_ids = list(group_by_id.keys())

    def format_group(group_id):
        group = group_by_id[group_id]

        return (
            f'{group["insurer"]}｜'
            f'{group["group_name"]}'
        )

    with st.expander(
        "新增主約或附約",
        expanded=False,
    ):
        selected_group_id = st.selectbox(
            "所屬保單組合",
            options=group_ids,
            format_func=format_group,
            key="new_policy_group_id",
        )

        selected_group = group_by_id[
            selected_group_id
        ]

        main_policies = [
            policy
            for policy in policies
            if (
                policy["policy_group_id"]
                == selected_group_id
                and policy["contract_role"] == "main"
            )
        ]

        main_policy_by_id = {
            policy["id"]: policy
            for policy in main_policies
        }

        parent_options = [None] + list(
            main_policy_by_id.keys()
        )

        def format_parent_policy(policy_id):
            if policy_id is None:
                return "不適用／尚未選擇"

            policy = main_policy_by_id[policy_id]

            product_code = (
                policy.get("product_code")
                or "無商品代碼"
            )

            return (
                f'{product_code}｜'
                f'{policy["product_name"]}'
            )

        group_currency = selected_group.get(
            "currency",
            "TWD",
        )

        if (
            group_currency
            not in INSURANCE_CURRENCY_OPTIONS
        ):
            group_currency = "TWD"

        with st.form(
            f"add_insurance_policy_form_"
            f"{selected_group_id}",
            clear_on_submit=True,
        ):
            basic_col1, basic_col2 = st.columns(2)

            with basic_col1:
                product_code = st.text_input(
                    "商品代碼（選填）",
                    placeholder="例如：20AWL",
                )

                product_name = st.text_input(
                    "商品名稱",
                    placeholder="例如：祥安終身壽險",
                )

                contract_role = st.selectbox(
                    "契約角色",
                    options=CONTRACT_ROLE_OPTIONS,
                    format_func=lambda value: (
                        CONTRACT_ROLE_LABELS[value]
                    ),
                )

                parent_policy_id = st.selectbox(
                    "所屬主約",
                    options=parent_options,
                    format_func=format_parent_policy,
                    help=(
                        "建立主約時選擇不適用；"
                        "建立附約時必須選擇所屬主約。"
                    ),
                )

            with basic_col2:
                insurance_category = st.selectbox(
                    "保險類型",
                    options=INSURANCE_CATEGORY_OPTIONS,
                    format_func=lambda value: (
                        INSURANCE_CATEGORY_LABELS[value]
                    ),
                )

                insured_role = st.text_input(
                    "被保險人角色（選填）",
                    value=(
                        selected_group.get(
                            "primary_insured_role"
                        )
                        or ""
                    ),
                    placeholder="例如：本人、要保人",
                )

                policy_status = st.selectbox(
                    "險種狀態",
                    options=(
                        INSURANCE_GROUP_STATUS_OPTIONS
                    ),
                    format_func=lambda value: (
                        INSURANCE_GROUP_STATUS_LABELS[value]
                    ),
                )

                verification_status = st.selectbox(
                    "資料確認狀態",
                    options=VERIFICATION_STATUS_OPTIONS,
                    index=2,
                    format_func=lambda value: (
                        VERIFICATION_STATUS_LABELS[value]
                    ),
                )

            amount_col1, amount_col2, amount_col3 = (
                st.columns(3)
            )

            with amount_col1:
                coverage_amount_text = st.text_input(
                    "保額或計算基準（選填）",
                    placeholder="例如：100000、1000",
                )

            with amount_col2:
                policy_currency = st.selectbox(
                    "幣別",
                    options=INSURANCE_CURRENCY_OPTIONS,
                    index=(
                        INSURANCE_CURRENCY_OPTIONS.index(
                            group_currency
                        )
                    ),
                )

            with amount_col3:
                coverage_unit = st.text_input(
                    "金額單位或性質（選填）",
                    placeholder=(
                        "例如：基本保額、每日、計算基準"
                    ),
                )

            date_col1, date_col2, date_col3 = (
                st.columns(3)
            )

            with date_col1:
                policy_effective_date = st.date_input(
                    "險種生效日（選填）",
                    value=_parse_database_date(
                        selected_group.get(
                            "effective_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col2:
                policy_premium_end_date = st.date_input(
                    "險種繳費終日（選填）",
                    value=_parse_database_date(
                        selected_group.get(
                            "premium_end_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col3:
                policy_coverage_end_date = st.date_input(
                    "險種保障終日（選填）",
                    value=_parse_database_date(
                        selected_group.get(
                            "coverage_end_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            premium_waiver_status = st.selectbox(
                "目前保費豁免狀態",
                options=PREMIUM_WAIVER_STATUS_OPTIONS,
                format_func=lambda value: (
                    PREMIUM_WAIVER_STATUS_LABELS[value]
                ),
                help=(
                    "這裡記錄目前是否已啟動豁免，"
                    "不是判斷該商品是否具有豁免保障。"
                ),
            )

            policy_notes = st.text_area(
                "險種備註（選填）",
                placeholder=(
                    "例如：保障內容已依正式條款確認；"
                    "實際給付仍以契約條款為準。"
                ),
            )

            submitted = st.form_submit_button(
                "新增主約或附約",
                use_container_width=True,
            )

        if submitted:
            cleaned_product_name = (
                product_name.strip()
            )

            if not cleaned_product_name:
                st.warning("請輸入商品名稱。")
                return

            if (
                contract_role == "rider"
                and parent_policy_id is None
            ):
                st.warning(
                    "建立附約時，必須選擇所屬主約。"
                )
                return

            if contract_role == "main":
                parent_policy_id = None

            if (
                policy_effective_date is not None
                and policy_premium_end_date is not None
                and policy_premium_end_date
                < policy_effective_date
            ):
                st.warning(
                    "險種繳費終日不能早於生效日。"
                )
                return

            if (
                policy_effective_date is not None
                and policy_coverage_end_date is not None
                and policy_coverage_end_date
                < policy_effective_date
            ):
                st.warning(
                    "險種保障終日不能早於生效日。"
                )
                return

            try:
                coverage_amount = (
                    _parse_optional_amount(
                        coverage_amount_text
                    )
                )

                (
                    supabase.table(
                        "insurance_policies"
                    )
                    .insert(
                        {
                            "policy_group_id": (
                                selected_group_id
                            ),
                            "parent_policy_id": (
                                parent_policy_id
                            ),
                            "product_code": (
                                product_code.strip()
                                or None
                            ),
                            "product_name": (
                                cleaned_product_name
                            ),
                            "contract_role": (
                                contract_role
                            ),
                            "insurance_category": (
                                insurance_category
                            ),
                            "insured_role": (
                                insured_role.strip()
                                or None
                            ),
                            "coverage_amount": (
                                coverage_amount
                            ),
                            "currency": (
                                policy_currency
                            ),
                            "coverage_unit": (
                                coverage_unit.strip()
                                or None
                            ),
                            "effective_date": (
                                _date_to_text(
                                    policy_effective_date
                                )
                            ),
                            "premium_end_date": (
                                _date_to_text(
                                    policy_premium_end_date
                                )
                            ),
                            "coverage_end_date": (
                                _date_to_text(
                                    policy_coverage_end_date
                                )
                            ),
                            "status": policy_status,
                            "premium_waiver_status": (
                                premium_waiver_status
                            ),
                            "verification_status": (
                                verification_status
                            ),
                            "notes": (
                                policy_notes.strip()
                                or None
                            ),
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "insurance_success_message"
                ] = (
                    "主約新增成功。"
                    if contract_role == "main"
                    else "附約新增成功。"
                )

                st.rerun()

            except ValueError as error:
                st.warning(str(error))

            except Exception as error:
                st.error(
                    f"新增主約或附約失敗：{error}"
                )

    st.subheader("目前主約與附約")

    if not policies:
        st.info(
            "目前尚未建立主約或附約。"
            "請先建立主約，再建立附約。"
        )
        return

    policy_by_id = {
        policy["id"]: policy
        for policy in policies
    }

    display_rows = []

    for policy in policies:
        group = group_by_id.get(
            policy["policy_group_id"]
        )

        if group is None:
            continue

        parent_policy = policy_by_id.get(
            policy.get("parent_policy_id")
        )

        if parent_policy is None:
            parent_display = ""
        else:
            parent_code = (
                parent_policy.get("product_code")
                or ""
            )

            parent_display = (
                f"{parent_code} "
                f'{parent_policy["product_name"]}'
            ).strip()

        amount = policy.get("coverage_amount")
        currency = policy.get("currency") or ""

        if amount is None:
            amount_display = ""
        else:
            amount_display = (
                f"{float(amount):,.2f} {currency}"
            )

        display_rows.append(
            {
                "保單組合": group["group_name"],
                "商品代碼": (
                    policy.get("product_code")
                    or ""
                ),
                "商品名稱": policy["product_name"],
                "主約／附約": (
                    CONTRACT_ROLE_LABELS.get(
                        policy["contract_role"],
                        policy["contract_role"],
                    )
                ),
                "所屬主約": parent_display,
                "保險類型": (
                    INSURANCE_CATEGORY_LABELS.get(
                        policy["insurance_category"],
                        policy["insurance_category"],
                    )
                ),
                "被保險人": (
                    policy.get("insured_role")
                    or ""
                ),
                "保額／基準": amount_display,
                "金額性質": (
                    policy.get("coverage_unit")
                    or ""
                ),
                "保障終日": _display_date(
                    policy.get("coverage_end_date")
                ),
                "資料狀態": (
                    VERIFICATION_STATUS_LABELS.get(
                        policy[
                            "verification_status"
                        ],
                        policy[
                            "verification_status"
                        ],
                    )
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(display_rows),
        use_container_width=True,
        hide_index=True,
    )

def _show_edit_policy(
    supabase,
    groups,
    policies,
):
    with st.expander(
        "編輯主約或附約",
        expanded=False,
    ):
        if not policies:
            st.info("目前沒有可以編輯的主約或附約。")
            return

        group_by_id = {
            group["id"]: group
            for group in groups
        }

        policy_by_id = {
            policy["id"]: policy
            for policy in policies
        }

        policy_ids = list(policy_by_id.keys())

        def format_policy(policy_id):
            policy = policy_by_id[policy_id]
            group = group_by_id.get(
                policy["policy_group_id"],
                {},
            )

            code = policy.get("product_code") or "無代碼"
            role = CONTRACT_ROLE_LABELS.get(
                policy["contract_role"],
                policy["contract_role"],
            )

            return (
                f'{group.get("group_name", "未知組合")}｜'
                f"{code}｜{policy['product_name']}｜{role}"
            )

        selected_policy_id = st.selectbox(
            "選擇主約或附約",
            options=policy_ids,
            format_func=format_policy,
            key="edit_insurance_policy_id",
        )

        selected_policy = policy_by_id[
            selected_policy_id
        ]

        selected_group_id = selected_policy[
            "policy_group_id"
        ]

        selected_group = group_by_id.get(
            selected_group_id,
            {},
        )

        contract_role = selected_policy[
            "contract_role"
        ]

        main_policies = [
            policy
            for policy in policies
            if (
                policy["policy_group_id"]
                == selected_group_id
                and policy["contract_role"] == "main"
                and policy["id"] != selected_policy_id
            )
        ]

        main_policy_by_id = {
            policy["id"]: policy
            for policy in main_policies
        }

        parent_options = [None] + list(
            main_policy_by_id.keys()
        )

        current_parent_id = selected_policy.get(
            "parent_policy_id"
        )

        if current_parent_id in parent_options:
            parent_index = parent_options.index(
                current_parent_id
            )
        else:
            parent_index = 0

        def format_parent(policy_id):
            if policy_id is None:
                return "不適用／尚未選擇"

            policy = main_policy_by_id[policy_id]
            code = policy.get("product_code") or "無代碼"

            return (
                f"{code}｜{policy['product_name']}"
            )

        current_category = selected_policy.get(
            "insurance_category",
            "other",
        )

        if (
            current_category
            not in INSURANCE_CATEGORY_OPTIONS
        ):
            current_category = "other"

        current_currency = selected_policy.get(
            "currency",
            "TWD",
        )

        if (
            current_currency
            not in INSURANCE_CURRENCY_OPTIONS
        ):
            current_currency = "TWD"

        current_status = selected_policy.get(
            "status",
            "active",
        )

        if (
            current_status
            not in INSURANCE_GROUP_STATUS_OPTIONS
        ):
            current_status = "unknown"

        current_verification = selected_policy.get(
            "verification_status",
            "pending",
        )

        if (
            current_verification
            not in VERIFICATION_STATUS_OPTIONS
        ):
            current_verification = "pending"

        current_waiver_status = selected_policy.get(
            "premium_waiver_status",
            "not_applicable",
        )

        if (
            current_waiver_status
            not in PREMIUM_WAIVER_STATUS_OPTIONS
        ):
            current_waiver_status = "unknown"

        existing_amount = selected_policy.get(
            "coverage_amount"
        )

        amount_default = (
            ""
            if existing_amount is None
            else str(existing_amount)
        )

        role_label = CONTRACT_ROLE_LABELS.get(
            contract_role,
            contract_role,
        )

        group_name = selected_group.get(
            "group_name",
            "未知保單組合",
        )

        st.caption(
            f"所屬保單組合：{group_name}｜"
            f"契約角色：{role_label}"
        )

        with st.form(
            f"edit_insurance_policy_form_"
            f"{selected_policy_id}"
        ):
            basic_col1, basic_col2 = st.columns(2)

            with basic_col1:
                edited_product_code = st.text_input(
                    "商品代碼（選填）",
                    value=(
                        selected_policy.get(
                            "product_code"
                        )
                        or ""
                    ),
                )

                edited_product_name = st.text_input(
                    "商品名稱",
                    value=selected_policy[
                        "product_name"
                    ],
                )

                edited_parent_policy_id = st.selectbox(
                    "所屬主約",
                    options=parent_options,
                    index=parent_index,
                    format_func=format_parent,
                    disabled=(contract_role == "main"),
                    help=(
                        "主約不需要選擇；附約必須連結"
                        "同一保單組合內的主約。"
                    ),
                )

                edited_category = st.selectbox(
                    "保險類型",
                    options=INSURANCE_CATEGORY_OPTIONS,
                    index=(
                        INSURANCE_CATEGORY_OPTIONS.index(
                            current_category
                        )
                    ),
                    format_func=lambda value: (
                        INSURANCE_CATEGORY_LABELS[value]
                    ),
                )

            with basic_col2:
                edited_insured_role = st.text_input(
                    "被保險人角色（選填）",
                    value=(
                        selected_policy.get(
                            "insured_role"
                        )
                        or ""
                    ),
                )

                edited_status = st.selectbox(
                    "險種狀態",
                    options=(
                        INSURANCE_GROUP_STATUS_OPTIONS
                    ),
                    index=(
                        INSURANCE_GROUP_STATUS_OPTIONS.index(
                            current_status
                        )
                    ),
                    format_func=lambda value: (
                        INSURANCE_GROUP_STATUS_LABELS[value]
                    ),
                )

                edited_verification = st.selectbox(
                    "資料確認狀態",
                    options=VERIFICATION_STATUS_OPTIONS,
                    index=(
                        VERIFICATION_STATUS_OPTIONS.index(
                            current_verification
                        )
                    ),
                    format_func=lambda value: (
                        VERIFICATION_STATUS_LABELS[value]
                    ),
                )

                edited_waiver_status = st.selectbox(
                    "目前保費豁免狀態",
                    options=(
                        PREMIUM_WAIVER_STATUS_OPTIONS
                    ),
                    index=(
                        PREMIUM_WAIVER_STATUS_OPTIONS.index(
                            current_waiver_status
                        )
                    ),
                    format_func=lambda value: (
                        PREMIUM_WAIVER_STATUS_LABELS[value]
                    ),
                )

            amount_col1, amount_col2, amount_col3 = (
                st.columns(3)
            )

            with amount_col1:
                edited_amount_text = st.text_input(
                    "保額或計算基準（選填）",
                    value=amount_default,
                )

            with amount_col2:
                edited_currency = st.selectbox(
                    "幣別",
                    options=INSURANCE_CURRENCY_OPTIONS,
                    index=(
                        INSURANCE_CURRENCY_OPTIONS.index(
                            current_currency
                        )
                    ),
                )

            with amount_col3:
                edited_coverage_unit = st.text_input(
                    "金額單位或性質（選填）",
                    value=(
                        selected_policy.get(
                            "coverage_unit"
                        )
                        or ""
                    ),
                )

            date_col1, date_col2, date_col3 = (
                st.columns(3)
            )

            with date_col1:
                edited_effective_date = st.date_input(
                    "險種生效日（選填）",
                    value=_parse_database_date(
                        selected_policy.get(
                            "effective_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col2:
                edited_premium_end_date = st.date_input(
                    "險種繳費終日（選填）",
                    value=_parse_database_date(
                        selected_policy.get(
                            "premium_end_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            with date_col3:
                edited_coverage_end_date = st.date_input(
                    "險種保障終日（選填）",
                    value=_parse_database_date(
                        selected_policy.get(
                            "coverage_end_date"
                        )
                    ),
                    min_value=date(1900, 1, 1),
                    max_value=date(2200, 12, 31),
                    format="YYYY/MM/DD",
                )

            edited_notes = st.text_area(
                "險種備註（選填）",
                value=(
                    selected_policy.get("notes")
                    or ""
                ),
            )

            submitted = st.form_submit_button(
                "儲存主約或附約修改",
                use_container_width=True,
            )

        if not submitted:
            return

        cleaned_name = edited_product_name.strip()

        if not cleaned_name:
            st.warning("請輸入商品名稱。")
            return

        if (
            contract_role == "rider"
            and edited_parent_policy_id is None
        ):
            st.warning("附約必須選擇所屬主約。")
            return

        if contract_role == "main":
            edited_parent_policy_id = None

        if (
            edited_effective_date is not None
            and edited_premium_end_date is not None
            and edited_premium_end_date
            < edited_effective_date
        ):
            st.warning("繳費終日不能早於生效日。")
            return

        if (
            edited_effective_date is not None
            and edited_coverage_end_date is not None
            and edited_coverage_end_date
            < edited_effective_date
        ):
            st.warning("保障終日不能早於生效日。")
            return

        try:
            edited_amount = _parse_optional_amount(
                edited_amount_text
            )

            (
                supabase.table("insurance_policies")
                .update(
                    {
                        "parent_policy_id": (
                            edited_parent_policy_id
                        ),
                        "product_code": (
                            edited_product_code.strip()
                            or None
                        ),
                        "product_name": cleaned_name,
                        "insurance_category": (
                            edited_category
                        ),
                        "insured_role": (
                            edited_insured_role.strip()
                            or None
                        ),
                        "coverage_amount": edited_amount,
                        "currency": edited_currency,
                        "coverage_unit": (
                            edited_coverage_unit.strip()
                            or None
                        ),
                        "effective_date": _date_to_text(
                            edited_effective_date
                        ),
                        "premium_end_date": _date_to_text(
                            edited_premium_end_date
                        ),
                        "coverage_end_date": _date_to_text(
                            edited_coverage_end_date
                        ),
                        "status": edited_status,
                        "premium_waiver_status": (
                            edited_waiver_status
                        ),
                        "verification_status": (
                            edited_verification
                        ),
                        "notes": (
                            edited_notes.strip()
                            or None
                        ),
                    }
                )
                .eq("id", selected_policy_id)
                .execute()
            )

            st.session_state[
                "insurance_success_message"
            ] = "主約或附約修改成功。"

            st.rerun()

        except ValueError as error:
            st.warning(str(error))

        except Exception as error:
            st.error(
                f"修改主約或附約失敗：{error}"
            )

def _show_benefit_manager(
    supabase,
    groups,
    policies,
    benefits,
):
    st.divider()
    st.subheader("重點權益摘要")

    st.caption(
        "只需要記錄日後值得快速查閱的重要權益，"
        "不必逐條複製完整保單條款。"
    )

    if not policies:
        st.info(
            "請先建立主約或附約，"
            "才能新增保障權益。"
        )
        return

    group_by_id = {
        group["id"]: group
        for group in groups
    }

    policy_by_id = {
        policy["id"]: policy
        for policy in policies
    }

    policy_ids = list(policy_by_id.keys())

    def format_policy(policy_id):
        policy = policy_by_id[policy_id]

        group = group_by_id.get(
            policy["policy_group_id"],
            {},
        )

        group_name = group.get(
            "group_name",
            "未知保單組合",
        )

        product_code = (
            policy.get("product_code")
            or "無代碼"
        )

        return (
            f"{group_name}｜"
            f"{product_code}｜"
            f'{policy["product_name"]}'
        )

    with st.expander(
        "新增重點權益",
        expanded=False,
    ):
        selected_policy_id = st.selectbox(
            "所屬主約或附約",
            options=policy_ids,
            format_func=format_policy,
            key="new_benefit_policy_id",
        )

        selected_policy = policy_by_id[
            selected_policy_id
        ]

        selected_currency = selected_policy.get(
            "currency",
            "TWD",
        )

        if (
            selected_currency
            not in INSURANCE_CURRENCY_OPTIONS
        ):
            selected_currency = "TWD"

        with st.form(
            f"add_insurance_benefit_form_"
            f"{selected_policy_id}",
            clear_on_submit=True,
        ):
            basic_col1, basic_col2 = st.columns(2)

            with basic_col1:
                benefit_type = st.selectbox(
                    "權益分類",
                    options=BENEFIT_TYPE_OPTIONS,
                    format_func=lambda value: (
                        BENEFIT_TYPE_LABELS[value]
                    ),
                )

                benefit_name = st.text_input(
                    "權益名稱",
                    placeholder=(
                        "例如：身故保險金、住院日額"
                    ),
                )

            with basic_col2:
                verification_status = st.selectbox(
                    "資料確認狀態",
                    options=VERIFICATION_STATUS_OPTIONS,
                    index=2,
                    format_func=lambda value: (
                        VERIFICATION_STATUS_LABELS[value]
                    ),
                )

                benefit_currency = st.selectbox(
                    "幣別",
                    options=INSURANCE_CURRENCY_OPTIONS,
                    index=(
                        INSURANCE_CURRENCY_OPTIONS.index(
                            selected_currency
                        )
                    ),
                )

            benefit_summary = st.text_area(
                "權益摘要",
                placeholder=(
                    "以簡短自然語言說明什麼情況下，"
                    "可以獲得什麼保障或權益。"
                ),
            )

            amount_col1, amount_col2 = st.columns(2)

            with amount_col1:
                benefit_amount_text = st.text_input(
                    "固定金額或計算基準（選填）",
                    placeholder=(
                        "沒有固定金額時保持空白"
                    ),
                )

                benefit_unit = st.text_input(
                    "金額單位或性質（選填）",
                    placeholder=(
                        "例如：每日、每次、基本保額"
                    ),
                )

            with amount_col2:
                calculation_formula = st.text_input(
                    "計算方式（選填）",
                    placeholder=(
                        "例如：基本保額 × 手術倍數"
                    ),
                )

                waiting_period = st.text_input(
                    "等待期（選填）",
                    placeholder=(
                        "例如：生效後第31日起"
                    ),
                )

            eligibility_conditions = st.text_area(
                "主要給付條件（選填）",
                placeholder=(
                    "例如：被保險人於契約有效期間內"
                    "符合條款所列條件。"
                ),
            )

            benefit_limits = st.text_area(
                "重要限制（選填）",
                placeholder=(
                    "例如：同一次住院最高給付180日。"
                ),
            )

            source_col1, source_col2 = st.columns(2)

            with source_col1:
                source_document = st.text_input(
                    "來源文件（選填）",
                    placeholder="例如：AWL8.pdf",
                )

            with source_col2:
                source_clause = st.text_input(
                    "來源條款（選填）",
                    placeholder="例如：第13條",
                )

            benefit_notes = st.text_area(
                "備註（選填）",
            )

            submitted = st.form_submit_button(
                "新增重點權益",
                use_container_width=True,
            )

        if submitted:
            cleaned_name = benefit_name.strip()
            cleaned_summary = benefit_summary.strip()

            if not cleaned_name:
                st.warning("請輸入權益名稱。")
                return

            if not cleaned_summary:
                st.warning("請輸入權益摘要。")
                return

            try:
                benefit_amount = (
                    _parse_optional_amount(
                        benefit_amount_text
                    )
                )

                (
                    supabase.table(
                        "insurance_benefits"
                    )
                    .insert(
                        {
                            "policy_id": (
                                selected_policy_id
                            ),
                            "benefit_type": benefit_type,
                            "benefit_name": cleaned_name,
                            "benefit_amount": (
                                benefit_amount
                            ),
                            "currency": (
                                benefit_currency
                            ),
                            "benefit_unit": (
                                benefit_unit.strip()
                                or None
                            ),
                            "calculation_formula": (
                                calculation_formula.strip()
                                or None
                            ),
                            "benefit_summary": (
                                cleaned_summary
                            ),
                            "eligibility_conditions": (
                                eligibility_conditions.strip()
                                or None
                            ),
                            "benefit_limits": (
                                benefit_limits.strip()
                                or None
                            ),
                            "waiting_period": (
                                waiting_period.strip()
                                or None
                            ),
                            "source_document": (
                                source_document.strip()
                                or None
                            ),
                            "source_clause": (
                                source_clause.strip()
                                or None
                            ),
                            "verification_status": (
                                verification_status
                            ),
                            "sort_order": 0,
                            "notes": (
                                benefit_notes.strip()
                                or None
                            ),
                        }
                    )
                    .execute()
                )

                st.session_state[
                    "insurance_success_message"
                ] = "重點權益新增成功。"

                st.rerun()

            except ValueError as error:
                st.warning(str(error))

            except Exception as error:
                st.error(
                    f"新增重點權益失敗：{error}"
                )

    if not benefits:
        st.info(
            "目前尚未建立重點權益摘要。"
        )
        return

    benefit_policy_ids = {
        benefit["policy_id"]
        for benefit in benefits
        if benefit.get("policy_id")
    }

    benefit_group_ids = {
        policy["policy_group_id"]
        for policy in policies
        if (
            policy["id"] in benefit_policy_ids
            and policy.get("policy_group_id")
        )
    }

    group_filter_options = [
        "all"
    ] + [
        group["id"]
        for group in groups
        if group["id"] in benefit_group_ids
    ]

    group_column, policy_column = st.columns(2)

    with group_column:
        filter_group_id = st.selectbox(
            "查看權益的保單組合",
            options=group_filter_options,
            format_func=lambda value: (
                "全部"
                if value == "all"
                else group_by_id[value].get(
                    "group_name",
                    "未命名保單組合",
                )
            ),
            key="benefit_group_filter",
        )

    available_policy_ids = [
        policy["id"]
        for policy in policies
        if (
            policy["id"] in benefit_policy_ids
            and (
                filter_group_id == "all"
                or policy["policy_group_id"]
                == filter_group_id
            )
        )
    ]

    with policy_column:
        filter_policy_id = st.selectbox(
            "查看權益的主約或附約",
            options=["all"] + available_policy_ids,
            format_func=lambda value: (
                "全部主約與附約"
                if value == "all"
                else format_policy(value)
            ),
            key=(
                "benefit_policy_filter_"
                f"{filter_group_id}"
            ),
        )

    filtered_benefits = []

    for benefit in benefits:
        policy = policy_by_id.get(
            benefit["policy_id"]
        )

        if policy is None:
            continue

        matches_group = (
            filter_group_id == "all"
            or policy["policy_group_id"]
            == filter_group_id
        )

        matches_policy = (
            filter_policy_id == "all"
            or benefit["policy_id"]
            == filter_policy_id
        )

        if matches_group and matches_policy:
            filtered_benefits.append(
                benefit
            )

    display_rows = []

    for benefit in filtered_benefits:
        policy = policy_by_id.get(
            benefit["policy_id"]
        )

        if policy is None:
            continue

        group = group_by_id.get(
            policy["policy_group_id"],
            {},
        )

        amount = benefit.get("benefit_amount")

        if amount is None:
            amount_display = ""
        else:
            amount_display = (
                f'{float(amount):,.2f} '
                f'{benefit.get("currency", "")}'
            )

        source_parts = [
            part
            for part in [
                benefit.get("source_document"),
                benefit.get("source_clause"),
            ]
            if part
        ]

        source_display = "｜".join(source_parts)

        display_rows.append(
            {
                "保單組合": group.get(
                    "group_name",
                    "",
                ),
                "險種": (
                    policy.get("product_code")
                    or policy["product_name"]
                ),
                "權益分類": (
                    BENEFIT_TYPE_LABELS.get(
                        benefit["benefit_type"],
                        benefit["benefit_type"],
                    )
                ),
                "權益名稱": benefit["benefit_name"],
                "摘要": benefit["benefit_summary"],
                "金額／基準": amount_display,
                "單位": (
                    benefit.get("benefit_unit")
                    or ""
                ),
                "計算方式": (
                    benefit.get(
                        "calculation_formula"
                    )
                    or ""
                ),
                "重要限制": (
                    benefit.get("benefit_limits")
                    or ""
                ),
                "來源": source_display,
                "確認狀態": (
                    VERIFICATION_STATUS_LABELS.get(
                        benefit[
                            "verification_status"
                        ],
                        benefit[
                            "verification_status"
                        ],
                    )
                ),
            }
        )

    if not display_rows:
        st.info(
            "目前篩選條件下沒有重點權益。"
        )
    else:
        display_dataframe = pd.DataFrame(
            display_rows
        )

        st.dataframe(
            display_dataframe,
            width="stretch",
            hide_index=True,
        )

        with st.expander(
            "查看權益分類視覺化",
            expanded=False,
        ):
            st.caption(
                "以下統計的是重點權益項目數，"
                "不代表保障額度或保障是否充足。"
            )

            st.markdown("#### 權益分類分布")

            category_counts = (
                display_dataframe[
                    "權益分類"
                ]
                .value_counts()
                .rename_axis(
                    "權益分類"
                )
                .to_frame(
                    "權益項目數"
                )
            )

            st.bar_chart(
                category_counts,
                width="stretch",
            )

            st.markdown(
                "#### 保單組合與權益分類矩陣"
            )

            coverage_matrix = pd.crosstab(
                display_dataframe[
                    "保單組合"
                ],
                display_dataframe[
                    "權益分類"
                ],
            )

            coverage_matrix.index.name = (
                "保單組合"
            )

            coverage_matrix["合計"] = (
                coverage_matrix.sum(axis=1)
            )

            coverage_matrix.loc["合計"] = (
                coverage_matrix.sum(axis=0)
            )

            st.dataframe(
                coverage_matrix,
                width="stretch",
            )

def _show_edit_benefit(
    supabase,
    groups,
    policies,
    benefits,
):
    with st.expander(
        "編輯重點權益",
        expanded=False,
    ):
        if not benefits:
            st.info("目前沒有可以編輯的重點權益。")
            return

        group_by_id = {
            group["id"]: group
            for group in groups
        }

        policy_by_id = {
            policy["id"]: policy
            for policy in policies
        }

        benefit_by_id = {
            benefit["id"]: benefit
            for benefit in benefits
        }

        benefit_ids = list(benefit_by_id.keys())

        def format_benefit(benefit_id):
            benefit = benefit_by_id[benefit_id]

            policy = policy_by_id.get(
                benefit["policy_id"],
                {},
            )

            group = group_by_id.get(
                policy.get("policy_group_id"),
                {},
            )

            group_name = group.get(
                "group_name",
                "未知保單組合",
            )

            product_code = (
                policy.get("product_code")
                or "無代碼"
            )

            return (
                f"{group_name}｜"
                f"{product_code}｜"
                f'{benefit["benefit_name"]}'
            )

        selected_benefit_id = st.selectbox(
            "選擇重點權益",
            options=benefit_ids,
            format_func=format_benefit,
            key="edit_insurance_benefit_id",
        )

        selected_benefit = benefit_by_id[
            selected_benefit_id
        ]

        selected_policy = policy_by_id.get(
            selected_benefit["policy_id"],
            {},
        )

        selected_group = group_by_id.get(
            selected_policy.get("policy_group_id"),
            {},
        )

        current_type = selected_benefit.get(
            "benefit_type",
            "other",
        )

        if current_type not in BENEFIT_TYPE_OPTIONS:
            current_type = "other"

        current_currency = selected_benefit.get(
            "currency",
            "TWD",
        )

        if (
            current_currency
            not in INSURANCE_CURRENCY_OPTIONS
        ):
            current_currency = "TWD"

        current_verification = selected_benefit.get(
            "verification_status",
            "pending",
        )

        if (
            current_verification
            not in VERIFICATION_STATUS_OPTIONS
        ):
            current_verification = "pending"

        existing_amount = selected_benefit.get(
            "benefit_amount"
        )

        amount_default = (
            ""
            if existing_amount is None
            else str(existing_amount)
        )

        group_name = selected_group.get(
            "group_name",
            "未知保單組合",
        )

        product_code = (
            selected_policy.get("product_code")
            or "無代碼"
        )

        product_name = selected_policy.get(
            "product_name",
            "未知險種",
        )

        st.caption(
            f"所屬保單組合：{group_name}｜"
            f"所屬險種：{product_code} {product_name}"
        )

        policies_by_group = {}

        for policy in policies:
            policy_group_id = policy.get(
                "policy_group_id"
            )

            policies_by_group.setdefault(
                policy_group_id,
                [],
            ).append(policy["id"])

        editable_group_ids = [
            group["id"]
            for group in groups
            if policies_by_group.get(
                group["id"]
            )
        ]

        if not editable_group_ids:
            st.warning(
                "目前沒有可以重新指定的"
                "保單組合與險種。"
            )
            return

        current_group_id = (
            selected_policy.get(
                "policy_group_id"
            )
        )

        if (
            current_group_id
            not in editable_group_ids
        ):
            current_group_id = (
                editable_group_ids[0]
            )

        edited_group_id = st.selectbox(
            "重新指定所屬保單組合",
            options=editable_group_ids,
            index=editable_group_ids.index(
                current_group_id
            ),
            format_func=lambda group_id: (
                group_by_id[group_id].get(
                    "group_name",
                    "未知保單組合",
                )
            ),
            key=(
                "edit_benefit_group_"
                f"{selected_benefit_id}"
            ),
            help=(
                "若原本歸屬正確，維持目前選項即可。"
            ),
        )

        edited_policy_options = (
            policies_by_group.get(
                edited_group_id,
                [],
            )
        )

        current_policy_id = (
            selected_benefit["policy_id"]
        )

        if (
            current_policy_id
            not in edited_policy_options
        ):
            current_policy_id = (
                edited_policy_options[0]
            )

        def format_edited_policy(policy_id):
            policy = policy_by_id[
                policy_id
            ]

            product_code = (
                policy.get("product_code")
                or "無代碼"
            )

            product_name = (
                policy.get("product_name")
                or "未知險種"
            )

            return (
                f"{product_code}｜"
                f"{product_name}"
            )

        edited_policy_id = st.selectbox(
            "重新指定所屬主約或附約",
            options=edited_policy_options,
            index=edited_policy_options.index(
                current_policy_id
            ),
            format_func=format_edited_policy,
            key=(
                "edit_benefit_policy_"
                f"{selected_benefit_id}_"
                f"{edited_group_id}"
            ),
        )

        with st.form(
            f"edit_insurance_benefit_form_"
            f"{selected_benefit_id}"
        ):
            basic_col1, basic_col2 = st.columns(2)

            with basic_col1:
                edited_benefit_type = st.selectbox(
                    "權益分類",
                    options=BENEFIT_TYPE_OPTIONS,
                    index=(
                        BENEFIT_TYPE_OPTIONS.index(
                            current_type
                        )
                    ),
                    format_func=lambda value: (
                        BENEFIT_TYPE_LABELS[value]
                    ),
                )

                edited_benefit_name = st.text_input(
                    "權益名稱",
                    value=selected_benefit[
                        "benefit_name"
                    ],
                )

            with basic_col2:
                edited_verification = st.selectbox(
                    "資料確認狀態",
                    options=VERIFICATION_STATUS_OPTIONS,
                    index=(
                        VERIFICATION_STATUS_OPTIONS.index(
                            current_verification
                        )
                    ),
                    format_func=lambda value: (
                        VERIFICATION_STATUS_LABELS[value]
                    ),
                )

                edited_currency = st.selectbox(
                    "幣別",
                    options=INSURANCE_CURRENCY_OPTIONS,
                    index=(
                        INSURANCE_CURRENCY_OPTIONS.index(
                            current_currency
                        )
                    ),
                )

            edited_summary = st.text_area(
                "權益摘要",
                value=(
                    selected_benefit.get(
                        "benefit_summary"
                    )
                    or ""
                ),
            )

            amount_col1, amount_col2 = st.columns(2)

            with amount_col1:
                edited_amount_text = st.text_input(
                    "固定金額或計算基準（選填）",
                    value=amount_default,
                )

                edited_unit = st.text_input(
                    "金額單位或性質（選填）",
                    value=(
                        selected_benefit.get(
                            "benefit_unit"
                        )
                        or ""
                    ),
                )

            with amount_col2:
                edited_formula = st.text_input(
                    "計算方式（選填）",
                    value=(
                        selected_benefit.get(
                            "calculation_formula"
                        )
                        or ""
                    ),
                )

                edited_waiting_period = st.text_input(
                    "等待期（選填）",
                    value=(
                        selected_benefit.get(
                            "waiting_period"
                        )
                        or ""
                    ),
                )

            edited_conditions = st.text_area(
                "主要給付條件（選填）",
                value=(
                    selected_benefit.get(
                        "eligibility_conditions"
                    )
                    or ""
                ),
            )

            edited_limits = st.text_area(
                "重要限制（選填）",
                value=(
                    selected_benefit.get(
                        "benefit_limits"
                    )
                    or ""
                ),
            )

            source_col1, source_col2 = st.columns(2)

            with source_col1:
                edited_source_document = st.text_input(
                    "來源文件（選填）",
                    value=(
                        selected_benefit.get(
                            "source_document"
                        )
                        or ""
                    ),
                )

            with source_col2:
                edited_source_clause = st.text_input(
                    "來源條款（選填）",
                    value=(
                        selected_benefit.get(
                            "source_clause"
                        )
                        or ""
                    ),
                )

            edited_notes = st.text_area(
                "備註（選填）",
                value=(
                    selected_benefit.get("notes")
                    or ""
                ),
            )

            submitted = st.form_submit_button(
                "儲存重點權益修改",
                use_container_width=True,
            )

        if not submitted:
            return

        cleaned_name = edited_benefit_name.strip()
        cleaned_summary = edited_summary.strip()

        if not cleaned_name:
            st.warning("請輸入權益名稱。")
            return

        if not cleaned_summary:
            st.warning("請輸入權益摘要。")
            return

        try:
            edited_amount = _parse_optional_amount(
                edited_amount_text
            )

            (
                supabase.table("insurance_benefits")
                .update(
                    {
                        "policy_id": (
                            edited_policy_id
                        ),
                        "benefit_type": (
                            edited_benefit_type
                        ),
                        "benefit_name": cleaned_name,
                        "benefit_amount": edited_amount,
                        "currency": edited_currency,
                        "benefit_unit": (
                            edited_unit.strip()
                            or None
                        ),
                        "calculation_formula": (
                            edited_formula.strip()
                            or None
                        ),
                        "benefit_summary": (
                            cleaned_summary
                        ),
                        "eligibility_conditions": (
                            edited_conditions.strip()
                            or None
                        ),
                        "benefit_limits": (
                            edited_limits.strip()
                            or None
                        ),
                        "waiting_period": (
                            edited_waiting_period.strip()
                            or None
                        ),
                        "source_document": (
                            edited_source_document.strip()
                            or None
                        ),
                        "source_clause": (
                            edited_source_clause.strip()
                            or None
                        ),
                        "verification_status": (
                            edited_verification
                        ),
                        "notes": (
                            edited_notes.strip()
                            or None
                        ),
                    }
                )
                .eq("id", selected_benefit_id)
                .execute()
            )

            st.session_state[
                "insurance_success_message"
            ] = "重點權益修改成功。"

            st.rerun()

        except ValueError as error:
            st.warning(str(error))

        except Exception as error:
            st.error(
                f"修改重點權益失敗：{error}"
            )

def _show_delete_benefit(
    supabase,
    groups,
    policies,
    benefits,
):
    with st.expander(
        "刪除重點權益",
        expanded=False,
    ):
        if not benefits:
            st.info(
                "目前沒有可以刪除的重點權益。"
            )
            return

        group_by_id = {
            group["id"]: group
            for group in groups
        }

        policy_by_id = {
            policy["id"]: policy
            for policy in policies
        }

        benefit_by_id = {
            benefit["id"]: benefit
            for benefit in benefits
        }

        group_ids_with_benefits = []

        for group in groups:
            group_id = group["id"]

            has_benefit = any(
                (
                    policy_by_id.get(
                        benefit["policy_id"],
                        {},
                    ).get(
                        "policy_group_id"
                    )
                    == group_id
                )
                for benefit in benefits
            )

            if has_benefit:
                group_ids_with_benefits.append(
                    group_id
                )

        if not group_ids_with_benefits:
            st.info(
                "目前找不到可刪除權益的"
                "保單組合。"
            )
            return

        selected_group_id = st.selectbox(
            "選擇保單組合",
            options=group_ids_with_benefits,
            format_func=lambda group_id: (
                group_by_id[group_id].get(
                    "group_name",
                    "未知保單組合",
                )
            ),
            key=(
                "delete_benefit_group_id"
            ),
        )

        policy_ids_with_benefits = [
            policy["id"]
            for policy in policies
            if (
                policy.get(
                    "policy_group_id"
                )
                == selected_group_id
                and any(
                    benefit["policy_id"]
                    == policy["id"]
                    for benefit in benefits
                )
            )
        ]

        def format_delete_policy(
            policy_id
        ):
            policy = policy_by_id[
                policy_id
            ]

            product_code = (
                policy.get("product_code")
                or "無代碼"
            )

            product_name = (
                policy.get("product_name")
                or "未知險種"
            )

            return (
                f"{product_code}｜"
                f"{product_name}"
            )

        selected_policy_id = st.selectbox(
            "選擇主約或附約",
            options=policy_ids_with_benefits,
            format_func=format_delete_policy,
            key=(
                "delete_benefit_policy_"
                f"{selected_group_id}"
            ),
        )

        benefit_ids_for_policy = [
            benefit["id"]
            for benefit in benefits
            if (
                benefit["policy_id"]
                == selected_policy_id
            )
        ]

        def format_delete_benefit(
            benefit_id
        ):
            benefit = benefit_by_id[
                benefit_id
            ]

            benefit_type = (
                BENEFIT_TYPE_LABELS.get(
                    benefit["benefit_type"],
                    benefit["benefit_type"],
                )
            )

            return (
                f"{benefit_type}｜"
                f'{benefit["benefit_name"]}'
            )

        selected_benefit_id = (
            st.selectbox(
                "選擇要刪除的重點權益",
                options=(
                    benefit_ids_for_policy
                ),
                format_func=(
                    format_delete_benefit
                ),
                key=(
                    "delete_benefit_id_"
                    f"{selected_policy_id}"
                ),
            )
        )

        selected_benefit = benefit_by_id[
            selected_benefit_id
        ]

        st.warning(
            "刪除後無法由系統直接復原。"
            "此操作只會刪除所選的重點權益，"
            "不會刪除保單組合或主附約。"
        )

        st.markdown(
            f"""
**權益名稱：** {selected_benefit["benefit_name"]}

**權益摘要：** {selected_benefit.get("benefit_summary") or "未填寫"}
            """
        )

        confirm_delete = st.checkbox(
            "我確認要永久刪除此筆重點權益。",
            key=(
                "confirm_delete_benefit_"
                f"{selected_benefit_id}"
            ),
        )

        if st.button(
            "永久刪除重點權益",
            type="primary",
            use_container_width=True,
            key=(
                "delete_benefit_button_"
                f"{selected_benefit_id}"
            ),
        ):
            if not confirm_delete:
                st.warning(
                    "請先勾選刪除確認。"
                )
                return

            try:
                (
                    supabase
                    .table(
                        "insurance_benefits"
                    )
                    .delete()
                    .eq(
                        "id",
                        selected_benefit_id,
                    )
                    .execute()
                )

                st.session_state[
                    "insurance_success_message"
                ] = (
                    "重點權益已刪除。"
                )

                st.rerun()

            except Exception as error:
                st.error(
                    "刪除重點權益失敗："
                    f"{error}"
                )

def _show_policy_group_table(groups, policies):
    st.divider()
    st.subheader("保單組合總覽")

    if not groups:
        st.info(
            "目前尚未建立保單組合。"
            "請先使用上方的新增功能。"
        )
        return

    insurer_options = sorted(
        {
            group["insurer"]
            for group in groups
            if group.get("insurer")
        }
    )

    filter_col1, filter_col2 = st.columns(2)

    with filter_col1:
        selected_insurer = st.selectbox(
            "保險公司",
            options=["全部"] + insurer_options,
            key="insurance_insurer_filter",
        )

    with filter_col2:
        selected_status = st.selectbox(
            "保單狀態",
            options=["all"]
            + INSURANCE_GROUP_STATUS_OPTIONS,
            format_func=lambda value: (
                "全部"
                if value == "all"
                else INSURANCE_GROUP_STATUS_LABELS[value]
            ),
            key="insurance_status_filter",
        )

    filtered_groups = []

    for group in groups:
        if (
            selected_insurer != "全部"
            and group["insurer"] != selected_insurer
        ):
            continue

        if (
            selected_status != "all"
            and group["status"] != selected_status
        ):
            continue

        filtered_groups.append(group)

    if not filtered_groups:
        st.info("目前沒有符合篩選條件的保單組合。")
        return

    policy_count_by_group = {}

    for policy in policies:
        group_id = policy["policy_group_id"]

        policy_count_by_group[group_id] = (
            policy_count_by_group.get(group_id, 0) + 1
        )

    display_rows = []

    for group in filtered_groups:
        display_rows.append(
            {
                "保單組合": group["group_name"],
                "保險公司": group["insurer"],
                "保單識別": (
                    group["policy_number_hint"] or ""
                ),
                "狀態": INSURANCE_GROUP_STATUS_LABELS.get(
                    group["status"],
                    group["status"],
                ),
                "主約與附約": policy_count_by_group.get(
                    group["id"],
                    0,
                ),
                "生效日": _display_date(
                    group["effective_date"]
                ),
                "繳費終日": _display_date(
                    group["premium_end_date"]
                ),
                "保障終日": _display_date(
                    group["coverage_end_date"]
                ),
                "幣別": group["currency"],
            }
        )

    st.dataframe(
        pd.DataFrame(display_rows),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("保單組合明細")

    for group in filtered_groups:
        status_label = INSURANCE_GROUP_STATUS_LABELS.get(
            group["status"],
            group["status"],
        )

        payment_frequency_label = (
            PAYMENT_FREQUENCY_LABELS.get(
                group["payment_frequency"],
                "待確認",
            )
        )

        policy_number_display = (
            group["policy_number_hint"] or "未記錄"
        )

        policyholder_display = (
            group["policyholder_role"] or "未記錄"
        )

        insured_display = (
            group["primary_insured_role"] or "未記錄"
        )

        effective_date_display = _display_date(
            group["effective_date"]
        )

        premium_end_date_display = _display_date(
            group["premium_end_date"]
        )

        coverage_end_date_display = _display_date(
            group["coverage_end_date"]
        )

        annual_premium_display = _display_amount(
            group["annual_premium"],
            group["currency"],
        )

        policy_count = policy_count_by_group.get(
            group["id"],
            0,
        )

        expander_title = (
            f'{group["insurer"]}｜'
            f'{group["group_name"]}｜'
            f"{status_label}"
        )

        with st.expander(
            expander_title,
            expanded=False,
        ):
            detail_col1, detail_col2, detail_col3 = (
                st.columns(3)
            )

            with detail_col1:
                st.write(
                    f"**保單識別：** {policy_number_display}"
                )

                st.write(
                    f"**要保人角色：** {policyholder_display}"
                )

                st.write(
                    f"**主要被保險人：** {insured_display}"
                )

            with detail_col2:
                st.write(
                    f"**契約生效日：** "
                    f"{effective_date_display}"
                )

                st.write(
                    f"**繳費終日：** "
                    f"{premium_end_date_display}"
                )

                st.write(
                    f"**保障終日：** "
                    f"{coverage_end_date_display}"
                )

            with detail_col3:
                st.write(
                    f"**繳費頻率：** "
                    f"{payment_frequency_label}"
                )

                st.write(
                    f"**年繳保費：** "
                    f"{annual_premium_display}"
                )

                st.write(
                    f"**主約與附約數量：** "
                    f"{policy_count}"
                )

            if group.get("notes"):
                st.info(group["notes"])

def _show_policy_value_manager(
    supabase,
    groups,
    policies,
):
    st.subheader("保單價值管理")

    st.caption(
        "記錄保單價值準備金、解約金、帳戶價值及"
        "其他可取回價值。每次查詢建立一筆新紀錄，"
        "以保留歷史變化。"
    )

    st.info(
        "保單價值準備金不一定等於實際解約金；"
        "若保險公司只顯示價值準備金，請選擇"
        "「保單價值準備金」。"
    )

    success_message = st.session_state.pop(
        "insurance_value_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    if not groups:
        st.info("請先建立保單組合。")
        return

    try:
        response = (
            supabase.table("insurance_policy_values")
            .select(
                "id, policy_group_id, policy_id, "
                "valuation_date, value_type, amount, "
                "currency, source, verification_status, "
                "notes, created_at, updated_at"
            )
            .order("valuation_date", desc=True)
            .order("created_at", desc=True)
            .execute()
        )

        value_records = response.data or []

    except Exception as error:
        st.error(f"讀取保單價值失敗：{error}")
        return

    group_map = {
        group["id"]: group
        for group in groups
    }

    policy_map = {
        policy["id"]: policy
        for policy in policies
    }

    def format_group(group_id):
        group = group_map[group_id]

        company = (
            group.get("insurance_company")
            or group.get("insurer_name")
            or group.get("company_name")
            or ""
        )

        group_name = (
            group.get("group_name")
            or group.get("name")
            or "未命名保單組合"
        )

        return (
            f"{company}｜{group_name}"
            if company
            else group_name
        )

    def format_policy(policy_id):
        if policy_id is None:
            return "整個保單組合（不指定單一險種）"

        policy = policy_map[policy_id]

        product_code = (
            policy.get("product_code")
            or "未設定代碼"
        )

        product_name = (
            policy.get("product_name")
            or "未設定名稱"
        )

        return f"{product_code}｜{product_name}"

    with st.expander(
        "新增保單價值紀錄",
        expanded=False,
    ):
        selected_group_id = st.selectbox(
            "保單組合",
            options=list(group_map.keys()),
            format_func=format_group,
            key="insurance_value_group",
        )

        selected_group = group_map[selected_group_id]

        group_policies = [
            policy
            for policy in policies
            if policy.get("policy_group_id")
            == selected_group_id
        ]

        policy_options = [
            None,
            *[
                policy["id"]
                for policy in group_policies
            ],
        ]

        default_currency = (
            selected_group.get("currency")
            or "TWD"
        )

        currency_options = list(
            dict.fromkeys(
                [
                    default_currency,
                    "TWD",
                    "USD",
                    "JPY",
                    "CNY",
                    "HKD",
                    "EUR",
                    "GBP",
                ]
            )
        )

        with st.form(
            f"add_insurance_value_{selected_group_id}",
            clear_on_submit=True,
        ):
            selected_policy_id = st.selectbox(
                "對應主約或附約",
                options=policy_options,
                format_func=format_policy,
            )

            value_type = st.selectbox(
                "價值類型",
                options=INSURANCE_VALUE_TYPE_OPTIONS,
                format_func=lambda value: (
                    INSURANCE_VALUE_TYPE_LABELS[value]
                ),
            )

            valuation_date = st.date_input(
                "價值查詢日期",
                value="today",
            )

            amount = st.number_input(
                "金額",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
            )

            currency = st.selectbox(
                "幣別",
                options=currency_options,
            )

            source = st.text_input(
                "資料來源",
                placeholder=(
                    "例如：保險公司會員網站、"
                    "年度通知書、客服查詢"
                ),
            )

            verification_status = st.selectbox(
                "資料狀態",
                options=INSURANCE_VALUE_STATUS_OPTIONS,
                format_func=lambda value: (
                    INSURANCE_VALUE_STATUS_LABELS[value]
                ),
                index=INSURANCE_VALUE_STATUS_OPTIONS.index(
                    "pending"
                ),
            )

            notes = st.text_area(
                "備註",
                placeholder=(
                    "例如：畫面顯示為保單價值準備金，"
                    "不代表實際解約可領金額。"
                ),
            )

            submitted = st.form_submit_button(
                "新增價值紀錄",
                use_container_width=True,
            )

        if submitted:
            if amount <= 0:
                st.warning("請輸入大於零的金額。")

            else:
                try:
                    (
                        supabase.table(
                            "insurance_policy_values"
                        )
                        .insert(
                            {
                                "policy_group_id": (
                                    selected_group_id
                                ),
                                "policy_id": (
                                    selected_policy_id
                                ),
                                "valuation_date": (
                                    valuation_date.isoformat()
                                ),
                                "value_type": value_type,
                                "amount": float(amount),
                                "currency": currency,
                                "source": (
                                    source.strip() or None
                                ),
                                "verification_status": (
                                    verification_status
                                ),
                                "notes": (
                                    notes.strip() or None
                                ),
                            }
                        )
                        .execute()
                    )

                    st.session_state[
                        "insurance_value_success_message"
                    ] = "保單價值紀錄新增成功。"

                    st.rerun()

                except Exception as error:
                    st.error(
                        f"新增保單價值失敗：{error}"
                    )

    if value_records:
        with st.expander(
            "編輯保單價值紀錄",
            expanded=False,
        ):
            value_record_map = {
                record["id"]: record
                for record in value_records
            }

            def format_value_record(record_id):
                record = value_record_map[record_id]

                group_label = format_group(
                    record["policy_group_id"]
                )

                value_label = (
                    INSURANCE_VALUE_TYPE_LABELS.get(
                        record["value_type"],
                        record["value_type"],
                    )
                )

                amount_text = (
                    f'{float(record["amount"]):,.2f} '
                    f'{record["currency"]}'
                )

                return (
                    f'{record["valuation_date"]}｜'
                    f"{group_label}｜"
                    f"{value_label}｜"
                    f"{amount_text}"
                )

            selected_value_id = st.selectbox(
                "選擇要編輯的價值紀錄",
                options=list(value_record_map.keys()),
                format_func=format_value_record,
                key="edit_insurance_value_record",
            )

            selected_value_record = value_record_map[
                selected_value_id
            ]

            selected_group_id = (
                selected_value_record[
                    "policy_group_id"
                ]
            )

            selected_policy_id = (
                selected_value_record.get("policy_id")
            )

            st.caption(
                "保單組合："
                f"{format_group(selected_group_id)}"
            )

            st.caption(
                "對應險種："
                f"{format_policy(selected_policy_id)}"
            )

            current_currency = (
                selected_value_record.get("currency")
                or "TWD"
            )

            edit_currency_options = list(
                dict.fromkeys(
                    [
                        current_currency,
                        "TWD",
                        "USD",
                        "JPY",
                        "CNY",
                        "HKD",
                        "EUR",
                        "GBP",
                    ]
                )
            )

            current_value_type = (
                selected_value_record["value_type"]
            )

            current_status = (
                selected_value_record[
                    "verification_status"
                ]
            )

            with st.form(
                f"edit_insurance_value_"
                f"{selected_value_id}"
            ):
                edited_value_type = st.selectbox(
                    "價值類型",
                    options=(
                        INSURANCE_VALUE_TYPE_OPTIONS
                    ),
                    format_func=lambda value: (
                        INSURANCE_VALUE_TYPE_LABELS[
                            value
                        ]
                    ),
                    index=(
                        INSURANCE_VALUE_TYPE_OPTIONS.index(
                            current_value_type
                        )
                    ),
                )

                edited_valuation_date = st.date_input(
                    "價值查詢日期",
                    value=pd.to_datetime(
                        selected_value_record[
                            "valuation_date"
                        ]
                    ).date(),
                )

                edited_amount = st.number_input(
                    "金額",
                    min_value=0.0,
                    value=float(
                        selected_value_record["amount"]
                    ),
                    step=100.0,
                    format="%.2f",
                )

                edited_currency = st.selectbox(
                    "幣別",
                    options=edit_currency_options,
                    index=edit_currency_options.index(
                        current_currency
                    ),
                )

                edited_source = st.text_input(
                    "資料來源",
                    value=(
                        selected_value_record.get(
                            "source"
                        )
                        or ""
                    ),
                )

                edited_status = st.selectbox(
                    "資料狀態",
                    options=(
                        INSURANCE_VALUE_STATUS_OPTIONS
                    ),
                    format_func=lambda value: (
                        INSURANCE_VALUE_STATUS_LABELS[
                            value
                        ]
                    ),
                    index=(
                        INSURANCE_VALUE_STATUS_OPTIONS.index(
                            current_status
                        )
                    ),
                )

                edited_notes = st.text_area(
                    "備註",
                    value=(
                        selected_value_record.get(
                            "notes"
                        )
                        or ""
                    ),
                )

                edit_submitted = (
                    st.form_submit_button(
                        "儲存價值紀錄修改",
                        use_container_width=True,
                    )
                )

            if edit_submitted:
                if edited_amount <= 0:
                    st.warning(
                        "請輸入大於零的金額。"
                    )

                else:
                    try:
                        (
                            supabase.table(
                                "insurance_policy_values"
                            )
                            .update(
                                {
                                    "value_type": (
                                        edited_value_type
                                    ),
                                    "valuation_date": (
                                        edited_valuation_date
                                        .isoformat()
                                    ),
                                    "amount": float(
                                        edited_amount
                                    ),
                                    "currency": (
                                        edited_currency
                                    ),
                                    "source": (
                                        edited_source.strip()
                                        or None
                                    ),
                                    "verification_status": (
                                        edited_status
                                    ),
                                    "notes": (
                                        edited_notes.strip()
                                        or None
                                    ),
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
                                selected_value_id,
                            )
                            .execute()
                        )

                        st.session_state[
                            "insurance_value_"
                            "success_message"
                        ] = (
                            "保單價值紀錄修改成功。"
                        )

                        st.rerun()

                    except Exception as error:
                        st.error(
                            "修改保單價值失敗："
                            f"{error}"
                        )

        with st.expander(
            "刪除錯誤的價值紀錄",
            expanded=False,
        ):
            st.warning(
                "刪除後，該筆歷史紀錄將無法從頁面恢復。"
                "只有在資料確實建立錯誤時才應刪除。"
            )

            delete_value_id = st.selectbox(
                "選擇要刪除的價值紀錄",
                options=list(value_record_map.keys()),
                format_func=format_value_record,
                key="delete_insurance_value_record",
            )

            delete_record = value_record_map[
                delete_value_id
            ]

            delete_type_label = (
                INSURANCE_VALUE_TYPE_LABELS.get(
                    delete_record["value_type"],
                    delete_record["value_type"],
                )
            )

            st.write(
                "**即將刪除：** "
                f'{delete_record["valuation_date"]}｜'
                f"{delete_type_label}｜"
                f'{float(delete_record["amount"]):,.2f} '
                f'{delete_record["currency"]}'
            )

            delete_confirmation = st.text_input(
                "請輸入「刪除」以確認",
                key=(
                    "delete_insurance_value_"
                    "confirmation"
                ),
            )

            delete_submitted = st.button(
                "永久刪除此筆價值紀錄",
                type="primary",
                use_container_width=True,
                disabled=(
                    delete_confirmation.strip()
                    != "刪除"
                ),
                key="delete_insurance_value_button",
            )

            if delete_submitted:
                try:
                    (
                        supabase.table(
                            "insurance_policy_values"
                        )
                        .delete()
                        .eq(
                            "id",
                            delete_value_id,
                        )
                        .execute()
                    )

                    st.session_state[
                        "insurance_value_success_message"
                    ] = "錯誤的保單價值紀錄已刪除。"

                    st.rerun()

                except Exception as error:
                    st.error(
                        "刪除保單價值紀錄失敗："
                        f"{error}"
                    )

    st.divider()
    st.subheader("目前最新保單價值")

    if not value_records:
        st.info("目前尚未建立保單價值紀錄。")
        return

    latest_records = {}

    for record in value_records:
        record_key = (
            record["policy_group_id"],
            record.get("policy_id"),
            record["value_type"],
        )

        if record_key not in latest_records:
            latest_records[record_key] = record

    latest_rows = []

    for record in latest_records.values():
        group_id = record["policy_group_id"]
        policy_id = record.get("policy_id")

        latest_rows.append(
            {
                "保單組合": format_group(group_id),
                "對應險種": format_policy(policy_id),
                "價值類型": (
                    INSURANCE_VALUE_TYPE_LABELS.get(
                        record["value_type"],
                        record["value_type"],
                    )
                ),
                "金額": float(record["amount"]),
                "幣別": record["currency"],
                "查詢日期": record["valuation_date"],
                "資料狀態": (
                    INSURANCE_VALUE_STATUS_LABELS.get(
                        record["verification_status"],
                        record["verification_status"],
                    )
                ),
                "資料來源": record.get("source") or "",
            }
        )

    latest_dataframe = pd.DataFrame(latest_rows)

    st.dataframe(
        latest_dataframe,
        use_container_width=True,
        hide_index=True,
        column_config={
            "金額": st.column_config.NumberColumn(
                "金額",
                format="%.2f",
            ),
        },
    )

    with st.expander(
        "查看保單價值歷史",
        expanded=False,
    ):
        history_rows = []

        for record in value_records:
            history_rows.append(
                {
                    "保單組合": format_group(
                        record["policy_group_id"]
                    ),
                    "對應險種": format_policy(
                        record.get("policy_id")
                    ),
                    "價值類型": (
                        INSURANCE_VALUE_TYPE_LABELS.get(
                            record["value_type"],
                            record["value_type"],
                        )
                    ),
                    "金額": float(record["amount"]),
                    "幣別": record["currency"],
                    "查詢日期": record["valuation_date"],
                    "資料狀態": (
                        INSURANCE_VALUE_STATUS_LABELS.get(
                            record[
                                "verification_status"
                            ],
                            record[
                                "verification_status"
                            ],
                        )
                    ),
                    "資料來源": (
                        record.get("source") or ""
                    ),
                    "備註": record.get("notes") or "",
                }
            )

        history_dataframe = pd.DataFrame(history_rows)

        st.dataframe(
            history_dataframe,
            use_container_width=True,
            hide_index=True,
            column_config={
                "金額": st.column_config.NumberColumn(
                    "金額",
                    format="%.2f",
                ),
            },
        )

def _show_insurance_coverage_summary(
    groups,
    policies,
    benefits,
):
    st.subheader("保障分類摘要")

    st.caption(
        "依已建立的重點權益整理保障分類。"
        "此處只代表系統中已有相關紀錄，"
        "不代表保障額度一定充足。"
    )

    group_map = {
        group["id"]: group
        for group in groups
    }

    policy_map = {
        policy["id"]: policy
        for policy in policies
    }

    verification_labels = {
        "confirmed": "已確認",
        "partially_confirmed": "部分確認",
        "pending": "待確認",
    }

    def get_group_name(group_id):
        group = group_map.get(group_id, {})

        company = (
            group.get("insurance_company")
            or group.get("insurer_name")
            or group.get("company_name")
            or ""
        )

        group_name = (
            group.get("group_name")
            or group.get("name")
            or "未命名保單組合"
        )

        return (
            f"{company}｜{group_name}"
            if company
            else group_name
        )

    def get_policy_name(policy_id):
        policy = policy_map.get(policy_id, {})

        product_code = (
            policy.get("product_code")
            or "未設定代碼"
        )

        product_name = (
            policy.get("product_name")
            or "未設定名稱"
        )

        return f"{product_code}｜{product_name}"

    if not benefits:
        st.info(
            "目前尚未建立重點保障權益，"
            "因此無法產生保障分類摘要。"
        )

    else:
        coverage_summary = {}

        for benefit in benefits:
            benefit_type = (
                benefit.get("benefit_type")
                or "other"
            )

            if benefit_type not in coverage_summary:
                coverage_summary[benefit_type] = {
                    "benefit_count": 0,
                    "policy_ids": set(),
                    "group_ids": set(),
                    "confirmed_count": 0,
                    "partial_count": 0,
                    "pending_count": 0,
                }

            summary = coverage_summary[benefit_type]

            summary["benefit_count"] += 1

            policy_id = benefit.get("policy_id")

            if policy_id:
                summary["policy_ids"].add(policy_id)

                policy = policy_map.get(
                    policy_id,
                    {},
                )

                policy_group_id = policy.get(
                    "policy_group_id"
                )

                if policy_group_id:
                    summary["group_ids"].add(
                        policy_group_id
                    )

            verification_status = (
                benefit.get("verification_status")
                or "pending"
            )

            if verification_status == "confirmed":
                summary["confirmed_count"] += 1

            elif (
                verification_status
                == "partially_confirmed"
            ):
                summary["partial_count"] += 1

            else:
                summary["pending_count"] += 1

        coverage_rows = []

        for benefit_type, summary in (
            coverage_summary.items()
        ):
            benefit_type_label = (
                BENEFIT_TYPE_LABELS.get(
                    benefit_type,
                    benefit_type,
                )
            )

            related_policy_names = sorted(
                {
                    get_policy_name(policy_id)
                    for policy_id
                    in summary["policy_ids"]
                }
            )

            coverage_rows.append(
                {
                    "保障分類": benefit_type_label,
                    "權益項目": (
                        summary["benefit_count"]
                    ),
                    "相關險種": len(
                        summary["policy_ids"]
                    ),
                    "保單組合": len(
                        summary["group_ids"]
                    ),
                    "已確認": (
                        summary["confirmed_count"]
                    ),
                    "部分確認": (
                        summary["partial_count"]
                    ),
                    "待確認": (
                        summary["pending_count"]
                    ),
                    "保障來源": "、".join(
                        related_policy_names
                    ),
                }
            )

        coverage_dataframe = pd.DataFrame(
            coverage_rows
        ).sort_values(
            by=[
                "待確認",
                "部分確認",
                "保障分類",
            ],
            ascending=[
                False,
                False,
                True,
            ],
        )

        summary_col1, summary_col2, summary_col3 = (
            st.columns(3)
        )

        confirmed_benefits = sum(
            1
            for benefit in benefits
            if benefit.get("verification_status")
            == "confirmed"
        )

        incomplete_benefits = (
            len(benefits) - confirmed_benefits
        )

        with summary_col1:
            st.metric(
                "已記錄保障分類",
                len(coverage_summary),
            )

        with summary_col2:
            st.metric(
                "已確認權益",
                confirmed_benefits,
            )

        with summary_col3:
            st.metric(
                "尚未完全確認",
                incomplete_benefits,
            )

        st.dataframe(
            coverage_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader("待確認事項")

    st.caption(
        "集中列出尚未完全確認、缺少重要日期，"
        "或缺少條款來源的資料。"
    )

    pending_items = []

    # 檢查保單組合的重要日期
    for group in groups:
        group_id = group["id"]
        group_name = get_group_name(group_id)

        missing_group_fields = []

        if not group.get("effective_date"):
            missing_group_fields.append("契約生效日")

        if not group.get("premium_end_date"):
            missing_group_fields.append("繳費終日")

        if not group.get("coverage_end_date"):
            missing_group_fields.append("保障終日")

        if missing_group_fields:
            pending_items.append(
                {
                    "資料層級": "保單組合",
                    "保單組合": group_name,
                    "險種／權益": "",
                    "待確認事項": (
                        "缺少："
                        + "、".join(
                            missing_group_fields
                        )
                    ),
                }
            )

    # 檢查主約與附約
    for policy in policies:
        policy_id = policy["id"]
        policy_name = get_policy_name(policy_id)

        group_name = get_group_name(
            policy.get("policy_group_id")
        )

        policy_issues = []

        verification_status = (
            policy.get("verification_status")
            or "pending"
        )

        if verification_status != "confirmed":
            policy_issues.append(
                "資料狀態："
                + verification_labels.get(
                    verification_status,
                    verification_status,
                )
            )

        if not policy.get("coverage_end_date"):
            policy_issues.append("缺少保障終日")

        if policy_issues:
            pending_items.append(
                {
                    "資料層級": "主約／附約",
                    "保單組合": group_name,
                    "險種／權益": policy_name,
                    "待確認事項": "；".join(
                        policy_issues
                    ),
                }
            )

    # 檢查保障權益
    for benefit in benefits:
        policy_id = benefit.get("policy_id")
        policy = policy_map.get(policy_id, {})

        policy_name = get_policy_name(policy_id)

        group_name = get_group_name(
            policy.get("policy_group_id")
        )

        benefit_name = (
            benefit.get("benefit_name")
            or "未命名權益"
        )

        benefit_issues = []

        verification_status = (
            benefit.get("verification_status")
            or "pending"
        )

        if verification_status != "confirmed":
            benefit_issues.append(
                "資料狀態："
                + verification_labels.get(
                    verification_status,
                    verification_status,
                )
            )

        benefit_summary = (
            benefit.get("summary")
            or benefit.get("benefit_summary")
            or benefit.get("description")
            or ""
        )

        if not str(benefit_summary).strip():
            benefit_issues.append("缺少權益摘要")

        if not benefit.get("source_document"):
            benefit_issues.append("缺少來源文件")

        if not benefit.get("source_clause"):
            benefit_issues.append("缺少來源條款")

        if benefit_issues:
            pending_items.append(
                {
                    "資料層級": "保障權益",
                    "保單組合": group_name,
                    "險種／權益": (
                        f"{policy_name}｜"
                        f"{benefit_name}"
                    ),
                    "待確認事項": "；".join(
                        benefit_issues
                    ),
                }
            )

    if not pending_items:
        st.success(
            "目前沒有系統可辨識的待確認事項。"
        )

    else:
        pending_dataframe = pd.DataFrame(
            pending_items
        )

        pending_col1, pending_col2 = st.columns(2)

        with pending_col1:
            st.metric(
                "待確認項目",
                len(pending_dataframe),
            )

        with pending_col2:
            affected_groups = (
                pending_dataframe[
                    "保單組合"
                ].nunique()
            )

            st.metric(
                "涉及保單組合",
                affected_groups,
            )

        level_filter_options = [
            "全部",
            *sorted(
                pending_dataframe[
                    "資料層級"
                ].unique().tolist()
            ),
        ]

        selected_pending_level = st.selectbox(
            "篩選待確認資料",
            options=level_filter_options,
            key="insurance_pending_level",
        )

        if selected_pending_level == "全部":
            display_pending_dataframe = (
                pending_dataframe
            )

        else:
            display_pending_dataframe = (
                pending_dataframe[
                    pending_dataframe[
                        "資料層級"
                    ]
                    == selected_pending_level
                ]
            )

        st.dataframe(
            display_pending_dataframe,
            use_container_width=True,
            hide_index=True,
        )

def show_insurance_manager(supabase):
    st.subheader("保險管理")

    st.caption(
        "集中整理保單組合、主約、附約、保障權益及"
        "可取回價值。保險資料獨立管理，不會自動"
        "納入總資產或投資報酬率。"
    )

    st.warning(
        "請勿輸入完整保單號碼、身分證字號、"
        "受益人姓名或詳細醫療資料。"
    )

    success_message = st.session_state.pop(
        "insurance_success_message",
        None,
    )

    if success_message:
        st.success(success_message)

    try:
        (
            groups,
            policies,
            benefits,
            policy_values,
        ) = _load_insurance_data(supabase)

    except Exception as error:
        st.error(f"讀取保險資料失敗：{error}")
        return

    _show_insurance_summary(
        groups,
        policies,
        benefits,
        policy_values,
    )

    st.divider()

    with st.expander(
        "保障分類摘要與待確認事項",
        expanded=False,
    ):
        _show_insurance_coverage_summary(
            groups,
            policies,
            benefits,
        )

    _show_add_policy_group(supabase)

    _show_edit_policy_group(
        supabase,
        groups,
    )

    _show_policy_manager(
        supabase,
        groups,
        policies,
    )

    _show_edit_policy(
        supabase,
        groups,
        policies,
    )

    _show_benefit_manager(
        supabase,
        groups,
        policies,
        benefits,
    )

    _show_edit_benefit(
        supabase,
        groups,
        policies,
        benefits,
    )

    _show_delete_benefit(
        supabase,
        groups,
        policies,
        benefits,
    )    

    _show_policy_group_table(
        groups,
        policies,
    )

    st.divider()

    _show_policy_value_manager(
        supabase,
        groups,
        policies,
    )