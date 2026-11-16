from config import ASSET_TYPE_LABELS


PRICE_SOURCE_LABELS = {
    "manual": "手動輸入",
    "yahoo": "Yahoo Finance",
    "yfinance": "Yahoo Finance（yfinance）",
    "yuanta_fund": "元大投信官方淨值",
    "franklin_fund": "Franklin Templeton 官方淨值",
    "schroders_fund": "施羅德官方淨值",
}

FX_SOURCE_LABELS = {
    "manual": "手動輸入",
    "frankfurter": "Frankfurter",
}


def _number(value):
    return float(value or 0)


def _record_sort_key(
    record,
    date_field,
):
    return (
        str(record.get(date_field) or ""),
        str(
            record.get("updated_at")
            or record.get("created_at")
            or ""
        ),
    )


def calculate_portfolio_valuation(
    accounts,
    assets,
    entries,
    prices,
    fx_rates,
):
    """
    計算目前資產估值與各帳戶 TWD 摘要。

    回傳：
    - valuation_rows：各帳戶、各資產估值明細
    - account_summary_rows：各帳戶彙總
    - overview_rows：全體資產摘要
    - total_assets_twd
    - cash_assets_twd
    - non_cash_assets_twd
    - missing_price_assets
    - missing_fx_currencies
    """
    account_map = {
        account["id"]: account
        for account in accounts
    }

    asset_map = {
        asset["id"]: asset
        for asset in assets
    }

    sorted_prices = sorted(
        prices,
        key=lambda record: _record_sort_key(
            record,
            "price_date",
        ),
        reverse=True,
    )

    latest_prices = {}

    for price_record in sorted_prices:
        asset_id = price_record.get(
            "asset_id"
        )

        if (
            asset_id
            and asset_id not in latest_prices
        ):
            latest_prices[asset_id] = (
                price_record
            )

    relevant_fx_rates = [
        rate_record
        for rate_record in fx_rates
        if rate_record.get("to_currency")
        == "TWD"
    ]

    sorted_fx_rates = sorted(
        relevant_fx_rates,
        key=lambda record: _record_sort_key(
            record,
            "rate_date",
        ),
        reverse=True,
    )

    latest_fx_rates = {}

    for rate_record in sorted_fx_rates:
        currency = rate_record.get(
            "from_currency"
        )

        if (
            currency
            and currency
            not in latest_fx_rates
        ):
            latest_fx_rates[currency] = (
                rate_record
            )

    balances = {}

    for entry in entries:
        account_id = entry.get(
            "account_id"
        )

        asset_id = entry.get(
            "asset_id"
        )

        if not account_id or not asset_id:
            continue

        balance_key = (
            account_id,
            asset_id,
        )

        balances[balance_key] = (
            balances.get(
                balance_key,
                0.0,
            )
            + _number(
                entry.get("quantity_delta")
            )
        )

    account_summary_map = {}

    for account in accounts:
        account_id = account["id"]

        account_summary_map[account_id] = {
            "帳戶": account.get(
                "name",
                "",
            ),
            "金融機構": account.get(
                "institution",
                "",
            ) or "",
            "帳戶狀態": (
                "使用中"
                if account.get(
                    "is_active",
                    True,
                )
                else "已封存"
            ),
            "現金資產 TWD": 0.0,
            "非現金資產 TWD": 0.0,
            "合計 TWD": 0.0,
            "資產項目數": 0,
            "未估值項目數": 0,
        }

    valuation_rows = []

    missing_price_assets = set()
    missing_fx_currencies = set()

    cash_assets_twd = 0.0
    non_cash_assets_twd = 0.0

    for (
        account_id,
        asset_id,
    ), quantity in balances.items():
        if abs(quantity) < 0.000000000001:
            continue

        account = account_map.get(
            account_id
        )

        asset = asset_map.get(
            asset_id
        )

        if account is None or asset is None:
            continue

        asset_type = asset.get(
            "asset_type",
            "",
        )

        currency = asset.get(
            "currency",
            "TWD",
        )

        unit_price = None
        price_date = ""
        price_source = ""
        original_market_value = None

        if asset_type == "cash":
            original_market_value = quantity
            price_source = "現金餘額"

        else:
            price_record = latest_prices.get(
                asset_id
            )

            if price_record is None:
                missing_price_assets.add(
                    f'{asset.get("symbol", "")}'
                    f'（{asset.get("name", "")}）'
                )

            else:
                unit_price = _number(
                    price_record.get("price")
                )

                original_market_value = (
                    quantity
                    * unit_price
                )

                price_date = (
                    price_record.get(
                        "price_date",
                        "",
                    )
                )

                raw_price_source = (
                    price_record.get(
                        "source",
                        "",
                    )
                )

                price_source = (
                    PRICE_SOURCE_LABELS.get(
                        raw_price_source,
                        raw_price_source,
                    )
                )

        if currency == "TWD":
            fx_rate = 1.0
            fx_date = ""
            fx_source = "基準幣別"

        else:
            fx_record = latest_fx_rates.get(
                currency
            )

            if fx_record is None:
                fx_rate = None
                fx_date = ""
                fx_source = ""

                missing_fx_currencies.add(
                    currency
                )

            else:
                fx_rate = _number(
                    fx_record.get("rate")
                )

                fx_date = fx_record.get(
                    "rate_date",
                    "",
                )

                raw_fx_source = (
                    fx_record.get(
                        "source",
                        "",
                    )
                )

                fx_source = (
                    FX_SOURCE_LABELS.get(
                        raw_fx_source,
                        raw_fx_source,
                    )
                )

        if (
            original_market_value is not None
            and fx_rate is not None
        ):
            market_value_twd = (
                original_market_value
                * fx_rate
            )

            valuation_status = "已估值"

            if asset_type == "cash":
                cash_assets_twd += (
                    market_value_twd
                )
            else:
                non_cash_assets_twd += (
                    market_value_twd
                )

        elif original_market_value is None:
            market_value_twd = None
            valuation_status = "缺少價格"

        else:
            market_value_twd = None
            valuation_status = "缺少匯率"

        item_status = (
            "使用中"
            if (
                account.get(
                    "is_active",
                    True,
                )
                and asset.get(
                    "is_active",
                    True,
                )
            )
            else "已封存"
        )

        valuation_rows.append(
            {
                "帳戶": account.get(
                    "name",
                    "",
                ),
                "金融機構": account.get(
                    "institution",
                    "",
                ) or "",
                "資產類型": (
                    ASSET_TYPE_LABELS.get(
                        asset_type,
                        asset_type,
                    )
                ),
                "資產代號": asset.get(
                    "symbol",
                    "",
                ),
                "資產名稱": asset.get(
                    "name",
                    "",
                ),
                "數量／餘額": quantity,
                "幣別": currency,
                "單位價格": unit_price,
                "原幣市值": (
                    original_market_value
                ),
                "匯率": fx_rate,
                "TWD 市值": market_value_twd,
                "價格日期": price_date,
                "價格來源": price_source,
                "匯率日期": fx_date,
                "匯率來源": fx_source,
                "估值狀態": valuation_status,
                "資料狀態": item_status,
            }
        )

        account_summary = (
            account_summary_map.get(
                account_id
            )
        )

        if account_summary is None:
            continue

        account_summary[
            "資產項目數"
        ] += 1

        if market_value_twd is None:
            account_summary[
                "未估值項目數"
            ] += 1

        elif asset_type == "cash":
            account_summary[
                "現金資產 TWD"
            ] += market_value_twd

        else:
            account_summary[
                "非現金資產 TWD"
            ] += market_value_twd

    account_summary_rows = list(
        account_summary_map.values()
    )

    for account_summary in (
        account_summary_rows
    ):
        account_summary["合計 TWD"] = (
            account_summary[
                "現金資產 TWD"
            ]
            + account_summary[
                "非現金資產 TWD"
            ]
        )

    account_summary_rows.sort(
        key=lambda row: row["合計 TWD"],
        reverse=True,
    )

    valuation_rows.sort(
        key=lambda row: (
            row["TWD 市值"]
            if row["TWD 市值"]
            is not None
            else float("-inf")
        ),
        reverse=True,
    )

    total_assets_twd = (
        cash_assets_twd
        + non_cash_assets_twd
    )

    valuation_complete = not (
        missing_price_assets
        or missing_fx_currencies
    )

    overview_rows = [
        {
            "基準幣別": "TWD",
            "總資產": total_assets_twd,
            "現金資產": cash_assets_twd,
            "非現金資產": (
                non_cash_assets_twd
            ),
            "估值是否完整": (
                "是"
                if valuation_complete
                else "否"
            ),
            "缺少價格資產數": len(
                missing_price_assets
            ),
            "缺少匯率幣別數": len(
                missing_fx_currencies
            ),
        }
    ]

    return {
        "valuation_rows": valuation_rows,
        "account_summary_rows": (
            account_summary_rows
        ),
        "overview_rows": overview_rows,
        "total_assets_twd": (
            total_assets_twd
        ),
        "cash_assets_twd": (
            cash_assets_twd
        ),
        "non_cash_assets_twd": (
            non_cash_assets_twd
        ),
        "valuation_complete": (
            valuation_complete
        ),
        "missing_price_assets": sorted(
            missing_price_assets
        ),
        "missing_fx_currencies": sorted(
            missing_fx_currencies
        ),
    }
