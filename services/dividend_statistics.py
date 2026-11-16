from datetime import datetime


def _number(value):
    return float(value or 0)


def _get_reversed_transaction_ids(transactions):
    """
    找出已被取消或更正的原始交易 ID。

    例如：
    dividend_reversal:原始交易ID
    trade_reversal:原始交易ID
    trade_edit_reversal:原始交易ID
    """
    reversed_transaction_ids = set()

    for transaction in transactions:
        external_reference = str(
            transaction.get("external_reference") or ""
        )

        if "reversal:" not in external_reference:
            continue

        original_transaction_id = (
            external_reference.rsplit(":", 1)[-1].strip()
        )

        if original_transaction_id:
            reversed_transaction_ids.add(
                original_transaction_id
            )

    return reversed_transaction_ids


def _get_transaction_year(transaction_date):
    if not transaction_date:
        return None

    try:
        normalized_date = str(transaction_date).replace(
            "Z",
            "+00:00",
        )

        return datetime.fromisoformat(
            normalized_date
        ).year

    except (TypeError, ValueError):
        return None


def calculate_annual_dividend_summary(transactions):
    """
    依照年度、幣別、帳戶與資產彙總現金股利。

    回傳欄位：
    - year
    - currency
    - account_id
    - asset_id
    - gross_dividend
    - withholding_tax
    - dividend_fee
    - net_dividend
    - dividend_count
    """
    reversed_transaction_ids = (
        _get_reversed_transaction_ids(
            transactions
        )
    )

    summary_map = {}

    for transaction in transactions:
        transaction_id = transaction.get("id")

        if transaction_id in reversed_transaction_ids:
            continue

        external_reference = str(
            transaction.get("external_reference") or ""
        )

        # 取消紀錄本身也不列入統計。
        if "reversal:" in external_reference:
            continue

        if transaction.get("transaction_type") != "dividend":
            continue

        if transaction.get("dividend_type") != "cash":
            continue

        account_id = transaction.get(
            "related_account_id"
        )

        asset_id = transaction.get(
            "related_asset_id"
        )

        if not account_id or not asset_id:
            continue

        year = _get_transaction_year(
            transaction.get("transaction_date")
        )

        if year is None:
            continue

        currency = (
            transaction.get("trade_currency")
            or "未指定"
        )

        gross_dividend = _number(
            transaction.get("gross_amount")
        )

        withholding_tax = _number(
            transaction.get("tax_amount")
        )

        dividend_fee = _number(
            transaction.get("fee_amount")
        )

        net_dividend = (
            gross_dividend
            - withholding_tax
            - dividend_fee
        )

        summary_key = (
            year,
            currency,
            account_id,
            asset_id,
        )

        if summary_key not in summary_map:
            summary_map[summary_key] = {
                "year": year,
                "currency": currency,
                "account_id": account_id,
                "asset_id": asset_id,
                "gross_dividend": 0.0,
                "withholding_tax": 0.0,
                "dividend_fee": 0.0,
                "net_dividend": 0.0,
                "dividend_count": 0,
            }

        summary = summary_map[summary_key]

        summary["gross_dividend"] += gross_dividend
        summary["withholding_tax"] += withholding_tax
        summary["dividend_fee"] += dividend_fee
        summary["net_dividend"] += net_dividend
        summary["dividend_count"] += 1

    summary_rows = list(summary_map.values())

    summary_rows.sort(
        key=lambda row: (
            -row["year"],
            row["currency"],
            row["account_id"],
            row["asset_id"],
        )
    )

    return summary_rows