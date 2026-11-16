import hashlib
import io
import json

import pandas as pd


REQUIRED_COLUMNS = {
    "交易日期",
    "買/賣/股利",
    "代號",
    "股票",
    "交易類別",
    "買入股數",
    "買入價格",
    "賣出股數",
    "賣出價格",
    "折讓後手續費",
    "交易稅",
    "成交價金",
    "交易成本",
    "支出",
    "收入",
    "決策原因",
}

IMPORT_TYPES = {
    "buy",
    "sell",
    "cash_dividend",
    "stock_dividend",
}


def _source_bytes(source):
    if isinstance(source, bytes):
        return source

    if isinstance(source, bytearray):
        return bytes(source)

    if hasattr(source, "getvalue"):
        value = source.getvalue()
        return (
            value.encode("utf-8")
            if isinstance(value, str)
            else bytes(value)
        )

    if hasattr(source, "read"):
        position = None

        if hasattr(source, "tell"):
            try:
                position = source.tell()
            except Exception:
                position = None

        value = source.read()

        if position is not None and hasattr(source, "seek"):
            try:
                source.seek(position)
            except Exception:
                pass

        return (
            value.encode("utf-8")
            if isinstance(value, str)
            else bytes(value)
        )

    raise TypeError("無法讀取上傳的 CSV 檔案。")


def _find_header_row(raw_bytes):
    preview = pd.read_csv(
        io.BytesIO(raw_bytes),
        header=None,
        dtype="string",
        keep_default_na=False,
        nrows=10,
    )

    for index, row in preview.iterrows():
        values = {
            str(value).strip()
            for value in row.tolist()
        }

        if REQUIRED_COLUMNS.issubset(values):
            return int(index)

    raise ValueError(
        "找不到標準欄位列。"
        "請確認檔案包含交易日期、買/賣/股利、"
        "代號、股票及金額欄位。"
    )


def _number(value):
    if pd.isna(value):
        return 0.0

    text = str(value).strip().replace(",", "")

    if not text:
        return 0.0

    try:
        return float(text)
    except ValueError as error:
        raise ValueError(
            f"無法將 {value!r} 解析為數字。"
        ) from error


def _clean_symbol(value):
    symbol = _clean_text(value).upper()

    return symbol


def _clean_text(value):
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()

    if text.upper() in {"<NA>", "NAN", "NONE", "NULL"}:
        return ""

    return text


def _asset_type(value):
    normalized = _clean_text(value).upper()

    if normalized == "ETF":
        return "etf"

    return "stock"


def _record_digest(record):
    source = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()[:24]


def prepare_standard_csv_import(
    source,
    *,
    currency,
):
    cleaned_currency = str(currency or "").strip().upper()

    if not cleaned_currency:
        raise ValueError("匯入幣別不能留白。")

    raw_bytes = _source_bytes(source)

    if not raw_bytes:
        raise ValueError("CSV 檔案沒有內容。")

    header_row = _find_header_row(raw_bytes)
    dataframe = pd.read_csv(
        io.BytesIO(raw_bytes),
        header=header_row,
        dtype={"代號": "string"},
    )

    dataframe.columns = [
        str(column).strip()
        for column in dataframe.columns
    ]

    missing_columns = sorted(
        REQUIRED_COLUMNS - set(dataframe.columns)
    )

    if missing_columns:
        raise ValueError(
            "CSV 缺少必要欄位："
            + "、".join(missing_columns)
        )

    dataframe["買/賣/股利"] = (
        dataframe["買/賣/股利"]
        .astype("string")
        .str.strip()
    )
    dataframe["代號"] = (
        dataframe["代號"]
        .astype("string")
        .map(_clean_symbol)
    )
    dataframe["解析日期"] = pd.to_datetime(
        dataframe["交易日期"],
        errors="coerce",
    )

    valid_mask = (
        dataframe["買/賣/股利"].isin(
            ["買", "賣", "股利"]
        )
        & dataframe["代號"].ne("")
        & dataframe["解析日期"].notna()
    )
    valid_dataframe = dataframe.loc[
        valid_mask
    ].copy()

    records = []

    for source_index, row in valid_dataframe.iterrows():
        csv_row = int(source_index) + header_row + 2
        action = str(row["買/賣/股利"])
        symbol = _clean_symbol(row["代號"])
        asset_name = str(row["股票"]).strip()
        asset_type_source = str(
            row["交易類別"]
        ).strip()
        reason = (
            ""
            if pd.isna(row["決策原因"])
            else str(row["決策原因"]).strip()
        )
        transaction_date = (
            row["解析日期"].date().isoformat()
        )

        buy_quantity = _number(row["買入股數"])
        buy_price = _number(row["買入價格"])
        sell_quantity = _number(row["賣出股數"])
        sell_price = _number(row["賣出價格"])
        discounted_fee = _number(
            row["折讓後手續費"]
        )
        tax_amount = _number(row["交易稅"])
        gross_amount = _number(row["成交價金"])
        transaction_cost = _number(
            row["交易成本"]
        )
        expense = _number(row["支出"])
        income = _number(row["收入"])

        is_stock_dividend = (
            action in ("買", "股利")
            and buy_quantity > 0
            and buy_price == 0
            and "股票股利" in reason
        )

        if is_stock_dividend:
            import_type = "stock_dividend"
            quantity_delta = buy_quantity
            unit_price = None
            fee_amount = 0.0
            tax_amount = 0.0
            gross_value = None
            cash_delta = 0.0

        elif action == "買":
            if buy_quantity <= 0 or buy_price <= 0:
                raise ValueError(
                    f"CSV 第 {csv_row} 列買入數量或價格不正確。"
                )

            import_type = "buy"
            quantity_delta = buy_quantity
            unit_price = buy_price
            gross_value = (
                gross_amount
                or buy_quantity * buy_price
            )
            fee_amount = (
                discounted_fee
                or max(transaction_cost - tax_amount, 0)
            )
            cash_delta = -(
                expense
                or gross_value + fee_amount + tax_amount
            )

        elif action == "賣":
            if sell_quantity <= 0 or sell_price <= 0:
                raise ValueError(
                    f"CSV 第 {csv_row} 列賣出數量或價格不正確。"
                )

            import_type = "sell"
            quantity_delta = -sell_quantity
            unit_price = sell_price
            gross_value = (
                gross_amount
                or sell_quantity * sell_price
            )
            fee_amount = (
                discounted_fee
                or max(transaction_cost - tax_amount, 0)
            )
            cash_delta = (
                income
                or gross_value - fee_amount - tax_amount
            )

        else:
            if income <= 0:
                raise ValueError(
                    f"CSV 第 {csv_row} 列現金股利收入必須大於 0。"
                )

            import_type = "cash_dividend"
            quantity_delta = 0.0
            unit_price = None
            gross_value = gross_amount or income
            fee_amount = max(
                gross_value - income - tax_amount,
                0.0,
            )
            cash_delta = income

        reference_source = {
            "date": transaction_date,
            "type": import_type,
            "symbol": symbol,
            "currency": cleaned_currency,
            "quantity": quantity_delta,
            "unit_price": unit_price,
            "gross_amount": gross_value,
            "fee_amount": fee_amount,
            "tax_amount": tax_amount,
            "cash_delta": cash_delta,
            "memo": reason,
            "source_row": csv_row,
        }

        records.append(
            {
                "source_row": csv_row,
                "transaction_date": transaction_date,
                "import_type": import_type,
                "symbol": symbol,
                "asset_name": asset_name,
                "asset_type_source": asset_type_source,
                "currency": cleaned_currency,
                "quantity_delta": quantity_delta,
                "unit_price": unit_price,
                "gross_amount": gross_value,
                "fee_amount": fee_amount,
                "tax_amount": tax_amount,
                "cash_delta": cash_delta,
                "memo": reason or None,
                "record_digest": _record_digest(
                    reference_source
                ),
            }
        )

    records_dataframe = pd.DataFrame(records)

    if records_dataframe.empty:
        raise ValueError(
            "CSV 中找不到可以匯入的交易。"
        )

    records_dataframe = (
        records_dataframe.sort_values(
            by=["transaction_date", "source_row"],
            kind="stable",
        ).reset_index(drop=True)
    )

    if records_dataframe["record_digest"].duplicated().any():
        raise ValueError(
            "CSV 內出現完全相同的交易紀錄，"
            "請先確認是否重複。"
        )

    type_counts = (
        records_dataframe["import_type"]
        .value_counts()
        .to_dict()
    )
    summary = {
        "source_row_count": len(dataframe),
        "valid_transaction_count": len(
            records_dataframe
        ),
        "buy_count": int(type_counts.get("buy", 0)),
        "sell_count": int(type_counts.get("sell", 0)),
        "cash_dividend_count": int(
            type_counts.get("cash_dividend", 0)
        ),
        "stock_dividend_count": int(
            type_counts.get("stock_dividend", 0)
        ),
        "asset_count": int(
            records_dataframe["symbol"].nunique()
        ),
        "start_date": records_dataframe[
            "transaction_date"
        ].min(),
        "end_date": records_dataframe[
            "transaction_date"
        ].max(),
        "buy_outflow": float(
            -records_dataframe.loc[
                records_dataframe["import_type"] == "buy",
                "cash_delta",
            ].sum()
        ),
        "sell_inflow": float(
            records_dataframe.loc[
                records_dataframe["import_type"] == "sell",
                "cash_delta",
            ].sum()
        ),
        "dividend_inflow": float(
            records_dataframe.loc[
                records_dataframe["import_type"]
                == "cash_dividend",
                "cash_delta",
            ].sum()
        ),
        "net_cash_delta": float(
            records_dataframe["cash_delta"].sum()
        ),
    }

    asset_rows = (
        records_dataframe[
            [
                "symbol",
                "asset_name",
                "asset_type_source",
                "currency",
            ]
        ]
        .drop_duplicates(subset=["symbol", "currency"])
        .sort_values(["currency", "symbol"])
        .reset_index(drop=True)
    )
    asset_rows["name"] = asset_rows["asset_name"]
    asset_rows["asset_type"] = asset_rows[
        "asset_type_source"
    ].map(_asset_type)
    asset_rows["market"] = ""
    asset_rows["external_symbol"] = ""
    asset_rows["price_source"] = "manual"
    asset_rows["resolution_status"] = "pending"
    asset_rows["resolution_note"] = ""

    return {
        "records": records_dataframe,
        "assets": asset_rows,
        "summary": summary,
        "currency": cleaned_currency,
        "file_fingerprint": hashlib.sha256(
            raw_bytes
        ).hexdigest()[:24],
    }


def _existing_asset_map(existing_assets):
    result = {}

    for asset in existing_assets:
        key = (
            _clean_symbol(asset.get("symbol")),
            _clean_text(asset.get("currency")).upper(),
        )

        if not key[0] or not key[1]:
            continue

        current = result.get(key)

        if current is None or (
            not current.get("is_active")
            and asset.get("is_active")
        ):
            result[key] = asset

    return result


def _quote_available(quote_fetcher, external_symbol):
    try:
        result = quote_fetcher(external_symbol)
        price = float(result.get("price") or 0)
        return price > 0
    except Exception:
        return False


def resolve_asset_metadata(
    asset_rows,
    existing_assets,
    quote_fetcher,
):
    resolved = asset_rows.copy()
    existing_map = _existing_asset_map(existing_assets)

    for index, row in resolved.iterrows():
        symbol = _clean_symbol(row["symbol"])
        currency = _clean_text(row["currency"]).upper()
        existing = existing_map.get((symbol, currency))

        if existing is not None:
            existing_market = _clean_text(
                existing.get("market")
            ).upper()
            existing_external_symbol = _clean_text(
                existing.get("external_symbol")
            )
            existing_price_source = _clean_text(
                existing.get("price_source")
            ).lower()
            resolved.at[index, "name"] = (
                existing.get("name") or row["name"]
            )
            resolved.at[index, "asset_type"] = (
                existing.get("asset_type")
                or row["asset_type"]
            )
            resolved.at[index, "market"] = existing_market
            resolved.at[index, "external_symbol"] = (
                existing_external_symbol
            )
            resolved.at[index, "price_source"] = (
                existing_price_source or "manual"
            )

            existing_ready = (
                bool(existing_market)
                and existing_price_source in {
                    "manual",
                    "yfinance",
                }
                and (
                    existing_price_source != "yfinance"
                    or bool(existing_external_symbol)
                )
            )

            if existing_ready:
                resolved.at[index, "resolution_status"] = (
                    "existing"
                )
                resolved.at[index, "resolution_note"] = (
                    "使用系統既有資產設定"
                )
                continue

            resolved.at[index, "resolution_note"] = (
                "既有資產設定不完整，已重新辨識"
            )

        if currency == "TWD":
            candidates = [
                ("TWSE", f"{symbol}.TW"),
                ("TPEX", f"{symbol}.TWO"),
            ]
            matches = [
                candidate
                for candidate in candidates
                if _quote_available(
                    quote_fetcher,
                    candidate[1],
                )
            ]

            if len(matches) == 1:
                market, external_symbol = matches[0]
                resolved.at[index, "market"] = market
                resolved.at[
                    index, "external_symbol"
                ] = external_symbol
                resolved.at[index, "price_source"] = (
                    "yfinance"
                )
                resolved.at[index, "resolution_status"] = (
                    "existing_updated"
                    if existing is not None
                    else "auto"
                )
                resolved.at[index, "resolution_note"] = (
                    "既有資產將同步為自動報價"
                    if existing is not None
                    else "自動報價檢查通過"
                )
            elif len(matches) > 1:
                resolved.at[index, "resolution_status"] = (
                    "ambiguous"
                )
                resolved.at[index, "resolution_note"] = (
                    "TWSE 與 TPEX 皆有報價，請手動確認"
                )
            else:
                resolved.at[index, "resolution_status"] = (
                    "unresolved"
                )
                resolved.at[index, "resolution_note"] = (
                    "找不到 .TW 或 .TWO 報價"
                )

        elif currency == "USD":
            direct = symbol
            alternate = symbol.replace(".", "-")
            candidates = list(dict.fromkeys([direct, alternate]))
            match = next(
                (
                    candidate
                    for candidate in candidates
                    if _quote_available(
                        quote_fetcher,
                        candidate,
                    )
                ),
                None,
            )

            if match:
                resolved.at[index, "market"] = "US"
                resolved.at[
                    index, "external_symbol"
                ] = match
                resolved.at[index, "price_source"] = (
                    "yfinance"
                )
                resolved.at[index, "resolution_status"] = (
                    "existing_updated"
                    if existing is not None
                    else "auto"
                )
                resolved.at[index, "resolution_note"] = (
                    "既有資產將同步為美股自動報價"
                    if existing is not None
                    else "美股報價檢查通過"
                )
            else:
                resolved.at[index, "resolution_status"] = (
                    "unresolved"
                )
                resolved.at[index, "resolution_note"] = (
                    "找不到美股 Yahoo 報價"
                )

        else:
            resolved.at[index, "resolution_status"] = (
                "unresolved"
            )
            resolved.at[index, "resolution_note"] = (
                "此幣別需手動設定市場與報價代號"
            )

    return resolved


def validate_asset_metadata(asset_rows):
    cleaned = asset_rows.copy()
    errors = []

    for index, row in cleaned.iterrows():
        symbol = _clean_symbol(row.get("symbol"))
        name = _clean_text(row.get("name"))
        asset_type = _clean_text(
            row.get("asset_type")
        ).lower()
        currency = _clean_text(
            row.get("currency")
        ).upper()
        market = _clean_text(row.get("market")).upper()
        external_symbol = _clean_text(
            row.get("external_symbol")
        )
        price_source = _clean_text(
            row.get("price_source")
        ).lower()

        cleaned.at[index, "symbol"] = symbol
        cleaned.at[index, "name"] = name
        cleaned.at[index, "asset_type"] = asset_type
        cleaned.at[index, "currency"] = currency
        cleaned.at[index, "market"] = market
        cleaned.at[index, "external_symbol"] = (
            external_symbol
        )
        cleaned.at[index, "price_source"] = (
            price_source or "manual"
        )

        if not symbol:
            errors.append("有一筆資產缺少代號")

        if not name:
            errors.append(f"{symbol or '未知資產'}：缺少資產名稱")

        if asset_type not in {"stock", "etf"}:
            errors.append(f"{symbol}：資產類型不正確")

        if not currency:
            errors.append(f"{symbol}：缺少幣別")

        if not market:
            errors.append(f"{symbol}：尚未設定市場")

        if cleaned.at[index, "price_source"] not in {
            "manual",
            "yfinance",
        }:
            errors.append(f"{symbol}：價格來源不正確")

        if (
            cleaned.at[index, "price_source"]
            == "yfinance"
            and not external_symbol
        ):
            errors.append(
                f"{symbol}：缺少外部報價代號"
            )

    duplicate_keys = cleaned.duplicated(
        subset=["symbol", "currency"],
        keep=False,
    )

    if duplicate_keys.any():
        errors.append("資產清單中有重複的代號與幣別。")

    return cleaned, errors


def build_standard_import_payload(
    prepared,
    resolved_assets,
    *,
    source_account_id,
):
    assets, errors = validate_asset_metadata(
        resolved_assets
    )

    if errors:
        raise ValueError("；".join(errors))

    batch_source = (
        f'{prepared["file_fingerprint"]}:'
        f"{source_account_id}"
    )
    batch_digest = hashlib.sha256(
        batch_source.encode("utf-8")
    ).hexdigest()[:24]
    batch_reference = (
        f"broker_csv_v1:{batch_digest}"
    )

    records = prepared["records"].copy()
    records["external_reference"] = records[
        "record_digest"
    ].map(
        lambda digest: (
            f"{batch_reference}:{digest}"
        )
    )

    asset_columns = [
        "symbol",
        "name",
        "asset_type",
        "currency",
        "market",
        "external_symbol",
        "price_source",
    ]
    record_columns = [
        "source_row",
        "transaction_date",
        "import_type",
        "symbol",
        "currency",
        "quantity_delta",
        "unit_price",
        "gross_amount",
        "fee_amount",
        "tax_amount",
        "cash_delta",
        "memo",
        "external_reference",
    ]

    assets_json = assets[asset_columns].to_json(
        orient="records",
        force_ascii=False,
    )
    records_json = records[record_columns].to_json(
        orient="records",
        force_ascii=False,
    )

    return {
        "batch_reference": batch_reference,
        "assets": json.loads(assets_json),
        "records": json.loads(records_json),
    }
