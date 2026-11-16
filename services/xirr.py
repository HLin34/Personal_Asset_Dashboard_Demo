from datetime import date, datetime
from math import isfinite


class XirrCalculationError(ValueError):
    pass


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if value is None:
        raise XirrCalculationError(
            "Cash flow date cannot be empty."
        )

    text = str(value).strip()

    if text.endswith("Z"):
        text = (
            text[:-1]
            + "+00:00"
        )

    try:
        return datetime.fromisoformat(
            text
        ).date()

    except ValueError:
        try:
            return date.fromisoformat(
                text[:10]
            )

        except ValueError as error:
            raise XirrCalculationError(
                f"Invalid cash flow date: {value}"
            ) from error


def normalize_cash_flows(cash_flows):
    """
    cash_flows 格式：

    [
        (日期, 金額),
        (日期, 金額),
    ]

    投入資金使用負數；
    賣出、股利及期末市值使用正數。
    """

    combined_flows = {}

    for flow_date, amount in cash_flows:
        normalized_date = _to_date(
            flow_date
        )

        normalized_amount = float(
            amount or 0
        )

        if not isfinite(normalized_amount):
            raise XirrCalculationError(
                "Cash flow amount must be finite."
            )

        if abs(normalized_amount) < 0.000000000001:
            continue

        combined_flows[
            normalized_date
        ] = (
            combined_flows.get(
                normalized_date,
                0.0,
            )
            + normalized_amount
        )

    normalized_flows = sorted(
        (
            flow_date,
            amount,
        )
        for flow_date, amount
        in combined_flows.items()
        if abs(amount) >= 0.000000000001
    )

    if len(normalized_flows) < 2:
        raise XirrCalculationError(
            "At least two non-zero cash flows "
            "are required."
        )

    has_negative = any(
        amount < 0
        for _, amount in normalized_flows
    )

    has_positive = any(
        amount > 0
        for _, amount in normalized_flows
    )

    if not has_negative or not has_positive:
        raise XirrCalculationError(
            "XIRR requires at least one negative "
            "and one positive cash flow."
        )

    return normalized_flows


def calculate_xnpv(
    rate,
    cash_flows,
):
    if rate <= -1:
        raise XirrCalculationError(
            "Rate must be greater than -100%."
        )

    normalized_flows = (
        normalize_cash_flows(
            cash_flows
        )
    )

    base_date = normalized_flows[0][0]

    total_value = 0.0

    for flow_date, amount in normalized_flows:
        days = (
            flow_date
            - base_date
        ).days

        years = days / 365.0

        denominator = (
            1.0 + rate
        ) ** years

        total_value += (
            amount / denominator
        )

    return total_value


def calculate_xirr(
    cash_flows,
    tolerance=0.00000001,
    max_iterations=250,
):
    """
    使用二分法計算年化 XIRR。

    回傳小數：
        0.10 代表 10%
        -0.05 代表 -5%
    """

    normalized_flows = (
        normalize_cash_flows(
            cash_flows
        )
    )

    def xnpv(rate):
        base_date = (
            normalized_flows[0][0]
        )

        total_value = 0.0

        for (
            flow_date,
            amount,
        ) in normalized_flows:
            days = (
                flow_date
                - base_date
            ).days

            years = days / 365.0

            denominator = (
                1.0 + rate
            ) ** years

            total_value += (
                amount / denominator
            )

        return total_value

    lower_rate = -0.999999
    upper_rate = 1.0

    lower_value = xnpv(
        lower_rate
    )

    upper_value = xnpv(
        upper_rate
    )

    expansion_count = 0

    while (
        lower_value * upper_value > 0
        and expansion_count < 100
    ):
        upper_rate = (
            upper_rate * 2.0
            + 1.0
        )

        upper_value = xnpv(
            upper_rate
        )

        expansion_count += 1

    if lower_value * upper_value > 0:
        raise XirrCalculationError(
            "Unable to find an XIRR solution "
            "for these cash flows."
        )

    for _ in range(max_iterations):
        middle_rate = (
            lower_rate
            + upper_rate
        ) / 2.0

        middle_value = xnpv(
            middle_rate
        )

        if (
            abs(middle_value)
            <= tolerance
        ):
            return middle_rate

        if (
            lower_value
            * middle_value
            <= 0
        ):
            upper_rate = middle_rate
            upper_value = middle_value

        else:
            lower_rate = middle_rate
            lower_value = middle_value

        if (
            abs(
                upper_rate
                - lower_rate
            )
            <= tolerance
        ):
            return (
                lower_rate
                + upper_rate
            ) / 2.0

    result = (
        lower_rate
        + upper_rate
    ) / 2.0

    if not isfinite(result):
        raise XirrCalculationError(
            "XIRR result is not finite."
        )

    return result