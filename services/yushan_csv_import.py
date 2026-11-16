import hashlib
import json

import pandas as pd


TPEX_SYMBOLS = {
    "00679B",
    "00955",
    "3260",
    "3293",
    "6667",
}

ASSET_NAME_OVERRIDES = {
    "6112": "邁達特",
}


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


def _number(value):
    if pd.isna(value):
        return 0.0

    text = str(value).strip().replace(",", "")

    if not text:
        return 0.0

    return float(text)


def _external_reference(record):
    source = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    digest = hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()[:24]

    return f"yushan_csv_v1:{digest}"


def prepare_yushan_csv_import(source):
    dataframe = pd.read_csv(
        source,
        header=1,
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
        .str.strip()
    )

    dataframe["解析日期"] = pd.to_datetime(
        dataframe["交易日期"],
        errors="coerce",
    )

    valid_mask = (
        dataframe["買/賣/股利"].isin(
            ["買", "賣", "股利"]
        )
        & dataframe["代號"].notna()
        & dataframe["解析日期"].notna()
    )

    valid_dataframe = dataframe.loc[
        valid_mask
    ].copy()

    records = []

    for source_index, row in (
        valid_dataframe.iterrows()
    ):
        action = str(row["買/賣/股利"])
        symbol = str(row["代號"])
        asset_name = str(row["股票"]).strip()
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
            action == "買"
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
            gross_amount = None
            cash_delta = 0.0

        elif action == "買":
            import_type = "buy"
            quantity_delta = buy_quantity
            unit_price = buy_price
            fee_amount = discounted_fee
            cash_delta = -expense

        elif action == "賣":
            import_type = "sell"
            quantity_delta = -sell_quantity
            unit_price = sell_price
            fee_amount = discounted_fee
            cash_delta = income

        else:
            import_type = "cash_dividend"
            quantity_delta = 0.0
            unit_price = None

            # 修正原始表格中威剛 2026/10/23
            # 淨股利誤寫為 153 的已知錯誤。
            if (
                symbol == "3260"
                and transaction_date == "2026-10-23"
            ):
                gross_amount = 576.0
                fee_amount = 10.0
                tax_amount = 0.0
                income = 566.0
            else:
                fee_amount = max(
                    gross_amount
                    - income
                    - tax_amount,
                    0.0,
                )

            cash_delta = income

        reference_source = {
            "date": transaction_date,
            "type": import_type,
            "symbol": symbol,
            "quantity": quantity_delta,
            "unit_price": unit_price,
            "gross_amount": gross_amount,
            "fee_amount": fee_amount,
            "tax_amount": tax_amount,
            "cash_delta": cash_delta,
            "reason": reason,
        }

        records.append(
            {
                "source_row": int(source_index) + 3,
                "transaction_date": transaction_date,
                "import_type": import_type,
                "symbol": symbol,
                "asset_name": asset_name,
                "asset_type_source": str(
                    row["交易類別"]
                ).strip(),
                "quantity_delta": quantity_delta,
                "unit_price": unit_price,
                "gross_amount": gross_amount,
                "fee_amount": fee_amount,
                "tax_amount": tax_amount,
                "cash_delta_twd": cash_delta,
                "memo": reason or None,
                "external_reference": (
                    _external_reference(
                        reference_source
                    )
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

    duplicate_references = int(
        records_dataframe[
            "external_reference"
        ].duplicated().sum()
    )

    if duplicate_references:
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
        "buy_outflow_twd": float(
            -records_dataframe.loc[
                records_dataframe["import_type"]
                == "buy",
                "cash_delta_twd",
            ].sum()
        ),
        "sell_inflow_twd": float(
            records_dataframe.loc[
                records_dataframe["import_type"]
                == "sell",
                "cash_delta_twd",
            ].sum()
        ),
        "dividend_inflow_twd": float(
            records_dataframe.loc[
                records_dataframe["import_type"]
                == "cash_dividend",
                "cash_delta_twd",
            ].sum()
        ),
        "net_cash_delta_twd": float(
            records_dataframe[
                "cash_delta_twd"
            ].sum()
        ),
    }

    asset_rows = (
        records_dataframe[
            ["symbol", "asset_name", "asset_type_source"]
        ]
        .drop_duplicates(subset=["symbol"])
        .sort_values("symbol")
        .reset_index(drop=True)
    )

    asset_rows["name"] = asset_rows.apply(
        lambda row: ASSET_NAME_OVERRIDES.get(
            row["symbol"],
            row["asset_name"],
        ),
        axis=1,
    )
    asset_rows["asset_type"] = asset_rows[
        "asset_type_source"
    ].map(
        lambda value: (
            "etf"
            if str(value).upper() == "ETF"
            else "stock"
        )
    )
    asset_rows["currency"] = "TWD"
    asset_rows["market"] = asset_rows["symbol"].map(
        lambda symbol: (
            "TPEX"
            if symbol in TPEX_SYMBOLS
            else "TWSE"
        )
    )
    asset_rows["external_symbol"] = asset_rows.apply(
        lambda row: (
            f'{row["symbol"]}.TWO'
            if row["market"] == "TPEX"
            else f'{row["symbol"]}.TW'
        ),
        axis=1,
    )
    asset_rows["price_source"] = "yfinance"

    return {
        "records": records_dataframe,
        "assets": asset_rows,
        "summary": summary,
    }


def build_yushan_import_payload(prepared):
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
        "quantity_delta",
        "unit_price",
        "gross_amount",
        "fee_amount",
        "tax_amount",
        "cash_delta_twd",
        "memo",
        "external_reference",
    ]

    assets_json = prepared["assets"][
        asset_columns
    ].to_json(
        orient="records",
        force_ascii=False,
    )
    records_json = prepared["records"][
        record_columns
    ].to_json(
        orient="records",
        force_ascii=False,
    )

    return {
        "assets": json.loads(assets_json),
        "records": json.loads(records_json),
    }
