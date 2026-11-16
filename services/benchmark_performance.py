from services.market_data import (
    fetch_yahoo_adjusted_history,
)


BENCHMARK_OPTIONS = {
    "VT": {
        "label": "VT｜全球股票",
        "external_symbol": "VT",
        "currency": "USD",
    },
    "SPY": {
        "label": "SPY｜S&P 500",
        "external_symbol": "SPY",
        "currency": "USD",
    },
    "0050": {
        "label": "0050｜台灣大型股",
        "external_symbol": "0050.TW",
        "currency": "TWD",
    },
}


def _date_text(value):
    if value is None:
        return ""

    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]

    return str(value)[:10]


def _find_price_on_or_before(
    price_rows,
    target_date,
):
    target_date = _date_text(
        target_date
    )

    eligible_rows = [
        row
        for row in price_rows
        if _date_text(
            row.get("price_date")
        ) <= target_date
    ]

    if not eligible_rows:
        return None

    eligible_rows.sort(
        key=lambda row: _date_text(
            row.get("price_date")
        ),
        reverse=True,
    )

    return eligible_rows[0]


def _find_fx_rate_on_or_before(
    fx_rates,
    currency,
    target_date,
):
    if currency == "TWD":
        return {
            "rate": 1.0,
            "rate_date": _date_text(
                target_date
            ),
            "direction": "TWD/TWD",
        }

    target_date = _date_text(
        target_date
    )

    candidates = []

    for record in fx_rates:
        rate_date = _date_text(
            record.get("rate_date")
        )

        if (
            not rate_date
            or rate_date > target_date
        ):
            continue

        from_currency = (
            record.get("from_currency")
        )

        to_currency = (
            record.get("to_currency")
        )

        rate = float(
            record.get("rate") or 0
        )

        if rate <= 0:
            continue

        if (
            from_currency == currency
            and to_currency == "TWD"
        ):
            candidates.append(
                {
                    "rate": rate,
                    "rate_date": rate_date,
                    "direction": (
                        f"{currency}/TWD"
                    ),
                }
            )

        elif (
            from_currency == "TWD"
            and to_currency == currency
        ):
            candidates.append(
                {
                    "rate": 1.0 / rate,
                    "rate_date": rate_date,
                    "direction": (
                        f"TWD/{currency} inverted"
                    ),
                }
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda row: row["rate_date"],
        reverse=True,
    )

    return candidates[0]


def _build_portfolio_return_map(
    snapshot_rows,
    period_rows,
):
    if not snapshot_rows:
        return {}

    sorted_snapshots = sorted(
        snapshot_rows,
        key=lambda row: _date_text(
            row.get("snapshot_date")
        ),
    )

    first_date = _date_text(
        sorted_snapshots[0][
            "snapshot_date"
        ]
    )

    return_map = {
        first_date: 0.0,
    }

    cumulative_growth = 1.0
    calculation_valid = True

    sorted_periods = sorted(
        period_rows,
        key=lambda row: _date_text(
            row.get("結束日期")
        ),
    )

    for period in sorted_periods:
        end_date = _date_text(
            period.get("結束日期")
        )

        period_return = period.get(
            "區間報酬率"
        )

        if (
            not end_date
            or period_return is None
            or not calculation_valid
        ):
            if end_date:
                return_map[end_date] = None

            calculation_valid = False
            continue

        cumulative_growth *= (
            1.0 + float(period_return)
        )

        return_map[end_date] = (
            cumulative_growth - 1.0
        )

    return return_map


def build_benchmark_comparison(
    snapshot_rows,
    period_rows,
    fx_rates,
    benchmark_key,
):
    """
    將投資組合累積 TWR 與基準的調整後報酬率，
    以共同日期及 TWD 口徑進行比較。
    """
    if benchmark_key not in BENCHMARK_OPTIONS:
        raise ValueError(
            "不支援所選的大盤基準。"
        )

    if not snapshot_rows:
        return {
            "benchmark": (
                BENCHMARK_OPTIONS[
                    benchmark_key
                ]
            ),
            "comparison_rows": [],
            "warnings": [
                "目前尚無 TWR 快照。"
            ],
        }

    benchmark = BENCHMARK_OPTIONS[
        benchmark_key
    ]

    portfolio_return_map = (
        _build_portfolio_return_map(
            snapshot_rows,
            period_rows,
        )
    )

    target_dates = sorted(
        portfolio_return_map.keys()
    )

    if not target_dates:
        return {
            "benchmark": benchmark,
            "comparison_rows": [],
            "warnings": [
                "目前沒有可比較的 TWR 日期。"
            ],
        }

    benchmark_prices = (
        fetch_yahoo_adjusted_history(
            benchmark[
                "external_symbol"
            ],
            target_dates[0],
            target_dates[-1],
        )
    )

    raw_rows = []
    warnings = []

    for target_date in target_dates:
        price_record = (
            _find_price_on_or_before(
                benchmark_prices,
                target_date,
            )
        )

        if price_record is None:
            warnings.append(
                f"{target_date} 找不到"
                "基準價格。"
            )
            continue

        fx_record = (
            _find_fx_rate_on_or_before(
                fx_rates,
                benchmark["currency"],
                target_date,
            )
        )

        if fx_record is None:
            warnings.append(
                f"{target_date} 找不到 "
                f'{benchmark["currency"]}/TWD '
                "匯率。"
            )
            continue

        adjusted_close = float(
            price_record[
                "adjusted_close"
            ]
        )

        fx_rate = float(
            fx_record["rate"]
        )

        benchmark_value_twd = (
            adjusted_close * fx_rate
        )

        raw_rows.append(
            {
                "日期": target_date,
                "投資組合累積 TWR": (
                    portfolio_return_map[
                        target_date
                    ]
                ),
                "基準調整後價格": (
                    adjusted_close
                ),
                "基準價格日期": (
                    price_record[
                        "price_date"
                    ]
                ),
                "匯率": fx_rate,
                "匯率日期": (
                    fx_record["rate_date"]
                ),
                "基準 TWD 價值": (
                    benchmark_value_twd
                ),
            }
        )

    if not raw_rows:
        return {
            "benchmark": benchmark,
            "comparison_rows": [],
            "warnings": warnings,
        }

    base_benchmark_value = float(
        raw_rows[0][
            "基準 TWD 價值"
        ]
    )

    comparison_rows = []

    for row in raw_rows:
        benchmark_return = (
            float(
                row["基準 TWD 價值"]
            )
            / base_benchmark_value
            - 1.0
        )

        portfolio_return = row[
            "投資組合累積 TWR"
        ]

        excess_return = (
            float(portfolio_return)
            - benchmark_return
            if portfolio_return
            is not None
            else None
        )

        comparison_rows.append(
            {
                **row,
                "基準累積報酬率": (
                    benchmark_return
                ),
                "超額報酬": (
                    excess_return
                ),
                "投資組合指數": (
                    (
                        1.0
                        + float(
                            portfolio_return
                        )
                    )
                    * 100.0
                    if portfolio_return
                    is not None
                    else None
                ),
                "基準指數": (
                    (
                        1.0
                        + benchmark_return
                    )
                    * 100.0
                ),
            }
        )

    return {
        "benchmark": benchmark,
        "comparison_rows": (
            comparison_rows
        ),
        "warnings": warnings,
        "start_date": (
            comparison_rows[0]["日期"]
        ),
        "end_date": (
            comparison_rows[-1]["日期"]
        ),
    }