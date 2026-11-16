from datetime import date
from datetime import datetime
from datetime import time
from zoneinfo import ZoneInfo


SEATTLE_TIMEZONE = ZoneInfo(
    "America/Los_Angeles"
)


def _number(value, field_name):
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} 不是有效數字。"
        ) from error


def _snapshot_datetime(value):
    """
    快照只有日期，因此視為該日結束時的估值。
    """
    if isinstance(value, datetime):
        result = value

    elif isinstance(value, date):
        result = datetime.combine(
            value,
            time.max,
            tzinfo=SEATTLE_TIMEZONE,
        )

    else:
        parsed_date = date.fromisoformat(
            str(value)[:10]
        )

        result = datetime.combine(
            parsed_date,
            time.max,
            tzinfo=SEATTLE_TIMEZONE,
        )

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=SEATTLE_TIMEZONE
        )

    return result.astimezone(
        SEATTLE_TIMEZONE
    )


def _flow_datetime(value):
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).replace(
            "Z",
            "+00:00",
        )
        result = datetime.fromisoformat(text)

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=SEATTLE_TIMEZONE
        )

    return result.astimezone(
        SEATTLE_TIMEZONE
    )


def _signed_flow_amount(flow):
    amount_twd = _number(
        flow.get("amount_twd"),
        "外部資金流金額",
    )

    if amount_twd <= 0:
        raise ValueError(
            "外部資金流金額必須大於零。"
        )

    flow_type = flow.get("flow_type")

    if flow_type == "contribution":
        return amount_twd

    if flow_type == "withdrawal":
        return -amount_twd

    raise ValueError(
        f"不支援的資金流類型：{flow_type}"
    )


def calculate_twr(
    snapshots,
    cash_flows=None,
):
    """
    依相鄰快照計算時間加權報酬率。

    快照區間內若有外部資金流，使用
    Modified Dietz 權重調整區間報酬，
    再將所有有效區間連鎖。

    snapshots 每筆至少包含：
    - snapshot_date
    - total_assets_twd

    cash_flows 每筆至少包含：
    - flow_at
    - flow_type
    - amount_twd
    """
    cash_flows = cash_flows or []

    snapshot_map = {}

    for snapshot in snapshots:
        snapshot_at = _snapshot_datetime(
            snapshot.get("snapshot_date")
        )

        snapshot_value = _number(
            snapshot.get("total_assets_twd"),
            "快照資產價值",
        )

        if snapshot_value < 0:
            raise ValueError(
                "快照資產價值不能小於零。"
            )

        # 同一天若意外有多筆，以最後讀到者為準。
        snapshot_map[
            snapshot_at.date()
        ] = {
            "snapshot_at": snapshot_at,
            "snapshot_value": snapshot_value,
        }

    normalized_snapshots = sorted(
        snapshot_map.values(),
        key=lambda item: item["snapshot_at"],
    )

    normalized_flows = []

    for flow in cash_flows:
        normalized_flows.append(
            {
                "flow_at": _flow_datetime(
                    flow.get("flow_at")
                ),
                "flow_type": flow.get(
                    "flow_type"
                ),
                "amount_twd": abs(
                    _signed_flow_amount(flow)
                ),
                "signed_amount_twd": (
                    _signed_flow_amount(flow)
                ),
            }
        )

    normalized_flows.sort(
        key=lambda item: item["flow_at"]
    )

    warnings = []

    if len(normalized_snapshots) < 2:
        warnings.append(
            "至少需要兩個不同日期的帳戶快照，"
            "目前尚無法計算 TWR。"
        )

        return {
            "twr": None,
            "period_rows": [],
            "valid_period_count": 0,
            "warnings": warnings,
        }

    period_rows = []
    cumulative_growth = 1.0
    valid_period_count = 0

    for index in range(
        1,
        len(normalized_snapshots),
    ):
        start_snapshot = (
            normalized_snapshots[index - 1]
        )
        end_snapshot = (
            normalized_snapshots[index]
        )

        start_at = start_snapshot["snapshot_at"]
        end_at = end_snapshot["snapshot_at"]

        start_value = start_snapshot[
            "snapshot_value"
        ]
        end_value = end_snapshot[
            "snapshot_value"
        ]

        interval_seconds = (
            end_at - start_at
        ).total_seconds()

        if interval_seconds <= 0:
            continue

        interval_flows = [
            flow
            for flow in normalized_flows
            if (
                start_at
                < flow["flow_at"]
                <= end_at
            )
        ]

        contribution_twd = sum(
            flow["amount_twd"]
            for flow in interval_flows
            if flow["flow_type"]
            == "contribution"
        )

        withdrawal_twd = sum(
            flow["amount_twd"]
            for flow in interval_flows
            if flow["flow_type"]
            == "withdrawal"
        )

        net_flow_twd = (
            contribution_twd
            - withdrawal_twd
        )

        weighted_flow_twd = 0.0

        for flow in interval_flows:
            remaining_seconds = (
                end_at - flow["flow_at"]
            ).total_seconds()

            weight = (
                remaining_seconds
                / interval_seconds
            )

            weight = min(
                1.0,
                max(0.0, weight),
            )

            weighted_flow_twd += (
                weight
                * flow["signed_amount_twd"]
            )

        denominator = (
            start_value
            + weighted_flow_twd
        )

        investment_gain_twd = (
            end_value
            - start_value
            - net_flow_twd
        )

        if denominator <= 0:
            period_return = None
            period_status = "無法計算"

            warnings.append(
                f"{start_at.date()} 至 "
                f"{end_at.date()} 的報酬率分母"
                "小於或等於零。"
            )

        else:
            period_return = (
                investment_gain_twd
                / denominator
            )

            cumulative_growth *= (
                1.0 + period_return
            )

            valid_period_count += 1
            period_status = "正常"

        cumulative_return = (
            cumulative_growth - 1.0
            if valid_period_count
            else None
        )

        period_rows.append(
            {
                "開始日期": (
                    start_at.date().isoformat()
                ),
                "結束日期": (
                    end_at.date().isoformat()
                ),
                "期初價值 TWD": start_value,
                "期末價值 TWD": end_value,
                "外部投入 TWD": (
                    contribution_twd
                ),
                "外部取回 TWD": (
                    withdrawal_twd
                ),
                "淨外部資金流 TWD": (
                    net_flow_twd
                ),
                "投資損益 TWD": (
                    investment_gain_twd
                ),
                "區間報酬率": period_return,
                "累積 TWR": cumulative_return,
                "狀態": period_status,
            }
        )

    twr = (
        cumulative_growth - 1.0
        if valid_period_count
        else None
    )

    return {
        "twr": twr,
        "period_rows": period_rows,
        "valid_period_count": (
            valid_period_count
        ),
        "warnings": warnings,
    }