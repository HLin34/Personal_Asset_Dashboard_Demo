from decimal import Decimal

import re
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

FX_API_URL = (
    "https://api.frankfurter.dev/v2/rates"
)

YUANTA_FUND_URLS = {
    # 元大台灣高股息優質龍頭基金A不配息
    "TW000T05B5A9": (
        "https://www.yuantafunds.com/"
        "myfund/information/1202"
    ),

    # 元大日本龍頭企業基金A不配息（台幣）
    "TW000T05C1A7": (
        "https://www.yuantafunds.com/"
        "myfund/information/1234"
    ),

    # 元大全球優質龍頭平衡基金A不配息（台幣）
    "TW000T05B6A7": (
        "https://www.yuantafunds.com/"
        "myfund/information/1209"
    ),
}

FRANKLIN_API_URL = (
        "https://www.franklintempleton.lu/"
        "api/pds/price-and-performance"
    )

FRANKLIN_FUND_CONFIGS = {
    # Franklin Technology Fund F (acc) JPY-H1
    "LU2999658995": {
        "fund_id": "4916",
        "share_class_code": "G14",
        "currency": "JPY",
    },
}

SCHRODERS_FUND_SEARCH_URL = (
    "https://fev2-vite.schdr.eu-central-1.isgdigital.com/"
    "zh-tw/tw/individual/gfc/fund/search/filter/"
)

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def fetch_yahoo_asset_price(
    external_symbol,
):
    cleaned_symbol = external_symbol.strip()

    if not cleaned_symbol:
        raise ValueError(
            "尚未設定外部報價代號。"
        )

    ticker = yf.Ticker(cleaned_symbol)

    history = ticker.history(
        period="10d",
        interval="1d",
        auto_adjust=False,
        actions=False,
    )

    if (
        history.empty
        or "Close" not in history.columns
    ):
        raise ValueError(
            f"找不到 {cleaned_symbol} 的價格資料。"
        )

    closing_prices = pd.to_numeric(
        history["Close"],
        errors="coerce",
    ).dropna()

    if closing_prices.empty:
        raise ValueError(
            f"{cleaned_symbol} 沒有可使用的收盤價。"
        )

    latest_price = float(
        closing_prices.iloc[-1]
    )

    latest_date = pd.Timestamp(
        closing_prices.index[-1]
    ).date().isoformat()

    if latest_price <= 0:
        raise ValueError(
            f"{cleaned_symbol} 回傳的價格不正確。"
        )

    return {
        "price": latest_price,
        "price_date": latest_date,
        "external_symbol": cleaned_symbol,
        "source": "yfinance",
    }

@st.cache_data(
    ttl=21600,
    show_spinner=False,
)
def fetch_yahoo_adjusted_history(
    external_symbol,
    start_date,
    end_date,
):
    """
    取得 Yahoo Finance 含股利與分割調整後的歷史價格。

    start_date 與 end_date 可傳入 date 或 YYYY-MM-DD 字串。
    回傳資料會包含起始日前最多 10 天，以便非交易日使用
    最近一個交易日的價格。
    """
    cleaned_symbol = (
        external_symbol.strip()
    )

    if not cleaned_symbol:
        raise ValueError(
            "尚未設定基準外部報價代號。"
        )

    start_timestamp = pd.Timestamp(
        start_date
    ).normalize()

    end_timestamp = pd.Timestamp(
        end_date
    ).normalize()

    if end_timestamp < start_timestamp:
        raise ValueError(
            "基準資料結束日期不能早於開始日期。"
        )

    request_start = (
        start_timestamp
        - pd.Timedelta(days=10)
    ).date().isoformat()

    # Yahoo Finance 的 end 不包含當日，
    # 因此向後多抓兩天。
    request_end = (
        end_timestamp
        + pd.Timedelta(days=2)
    ).date().isoformat()

    ticker = yf.Ticker(
        cleaned_symbol
    )

    history = ticker.history(
        start=request_start,
        end=request_end,
        interval="1d",
        auto_adjust=True,
        actions=False,
    )

    if (
        history.empty
        or "Close" not in history.columns
    ):
        raise ValueError(
            f"找不到 {cleaned_symbol} "
            "的調整後歷史價格。"
        )

    adjusted_prices = pd.to_numeric(
        history["Close"],
        errors="coerce",
    ).dropna()

    if adjusted_prices.empty:
        raise ValueError(
            f"{cleaned_symbol} 沒有可使用的"
            "調整後歷史價格。"
        )

    result_rows = []

    for index, price in (
        adjusted_prices.items()
    ):
        adjusted_price = float(price)

        if adjusted_price <= 0:
            continue

        price_date = pd.Timestamp(
            index
        ).date().isoformat()

        result_rows.append(
            {
                "price_date": price_date,
                "adjusted_close": (
                    adjusted_price
                ),
                "external_symbol": (
                    cleaned_symbol
                ),
                "source": (
                    "yfinance_adjusted"
                ),
            }
        )

    if not result_rows:
        raise ValueError(
            f"{cleaned_symbol} 沒有有效的"
            "調整後歷史價格。"
        )

    result_rows.sort(
        key=lambda row: row["price_date"]
    )

    return result_rows

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def fetch_yuanta_fund_price(
    external_symbol,
):
    cleaned_symbol = external_symbol.strip().upper()

    if not cleaned_symbol:
        raise ValueError(
            "尚未設定基金 ISIN。"
        )

    fund_url = YUANTA_FUND_URLS.get(
        cleaned_symbol
    )

    if fund_url is None:
        raise ValueError(
            f"尚未設定 {cleaned_symbol} 的元大基金頁面。"
        )

    response = requests.get(
        fund_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            ),
        },
        timeout=20,
    )

    response.raise_for_status()
    response.encoding = "utf-8"

    nav_match = re.search(
        r"最新淨值</p>"
        r".*?"
        r"<p[^>]*>\s*"
        r"([\d,]+(?:\.\d+)?)"
        r".*?"
        r"\((\d{4}/\d{2}/\d{2})\)",
        response.text,
        flags=re.DOTALL,
    )

    if nav_match is None:
        raise ValueError(
            "無法從元大投信官網解析最新淨值。"
        )

    latest_price = float(
        nav_match.group(1).replace(",", "")
    )

    latest_date = (
        nav_match.group(2)
        .replace("/", "-")
    )

    if latest_price <= 0:
        raise ValueError(
            "元大投信官網回傳的淨值不正確。"
        )

    return {
        "price": latest_price,
        "price_date": latest_date,
        "external_symbol": cleaned_symbol,
        "source": "yuanta_fund",
    }

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)

def fetch_franklin_fund_price(
    external_symbol,
):
    cleaned_symbol = (
        external_symbol.strip().upper()
    )

    if not cleaned_symbol:
        raise ValueError(
            "尚未設定基金 ISIN。"
        )

    fund_config = FRANKLIN_FUND_CONFIGS.get(
        cleaned_symbol
    )

    if fund_config is None:
        raise ValueError(
            f"尚未設定 {cleaned_symbol} "
            "的 Franklin 基金資料。"
        )

    query = """
    query Pricing(
      $fundid: String!
      $shareclasscode: String!
      $countrycode: String!
      $languagecode: String!
    ) {
      Overview(
        fundid: $fundid
        shareclasscode: $shareclasscode
        countrycode: $countrycode
        languagecode: $languagecode
      ) {
        fundid
        fundname
        shareclass {
          shclname
          nav {
            currcode
            navdate
            navvalue
          }
        }
      }
    }
    """

    response = requests.post(
        FRANKLIN_API_URL,
        params={
            "op": "Pricing",
            "id": "0",
        },
        json={
            "operationName": "Pricing",
            "variables": {
                "fundid": fund_config["fund_id"],
                "shareclasscode": (
                    fund_config[
                        "share_class_code"
                    ]
                ),
                "countrycode": "LU",
                "languagecode": "en_GB",
            },
            "query": query,
        },
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            ),
            "Accept": "application/json",
            "Referer": (
                "https://www.franklintempleton.lu/"
            ),
        },
        timeout=20,
    )

    response.raise_for_status()
    response_data = response.json()

    if response_data.get("errors"):
        raise ValueError(
            "Franklin 官方資料介面回傳錯誤："
            f'{response_data["errors"]}'
        )

    overview = (
        response_data
        .get("data", {})
        .get("Overview")
    )

    if not overview:
        raise ValueError(
            "Franklin 官方資料沒有回傳基金資訊。"
        )

    share_classes = (
        overview.get("shareclass") or []
    )

    if not share_classes:
        raise ValueError(
            "Franklin 官方資料沒有回傳基金級別。"
        )

    nav_record = (
        share_classes[0].get("nav") or {}
    )

    returned_currency = (
        nav_record.get("currcode") or ""
    ).upper()

    if (
        returned_currency
        != fund_config["currency"]
    ):
        raise ValueError(
            "Franklin 回傳的計價幣別不正確："
            f"{returned_currency}"
        )

    raw_price = str(
        nav_record.get("navvalue") or ""
    )

    cleaned_price = re.sub(
        r"[^\d.\-]",
        "",
        raw_price,
    )

    if not cleaned_price:
        raise ValueError(
            "Franklin 官方資料沒有可使用的淨值。"
        )

    latest_price = float(cleaned_price)

    raw_date = (
        nav_record.get("navdate") or ""
    )

    try:
        latest_date = (
            pd.to_datetime(
                raw_date,
                format="%d/%m/%Y",
            )
            .date()
            .isoformat()
        )

    except Exception as error:
        raise ValueError(
            "無法解析 Franklin 淨值日期："
            f"{raw_date}"
        ) from error

    if latest_price <= 0:
        raise ValueError(
            "Franklin 回傳的淨值不正確。"
        )

    return {
        "price": latest_price,
        "price_date": latest_date,
        "external_symbol": cleaned_symbol,
        "currency": returned_currency,
        "source": "franklin_fund",
    }

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)
def fetch_schroders_fund_price(
    external_symbol,
):
    cleaned_symbol = (
        external_symbol.strip().upper()
    )

    if not cleaned_symbol:
        raise ValueError(
            "尚未設定基金 ISIN。"
        )

    response = requests.get(
        SCHRODERS_FUND_SEARCH_URL,
        params={
            "channel": "individual",
            "clientId": "schdr",
            "clientVersion": "v1",
            "language": "zh-tw",
            "location": "tw",
            "r": "/fund/search/filter/",
            "pageIndex": "0",
            "pageSize": "10",
            "searchText": cleaned_symbol.lower(),
            "tabIndex": "0",
            "prerender": "true",
            "baseUrl": (
                "https://www.schroders.com/zh-tw/tw/"
                "individual/fund-centre/#"
            ),
        },
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Referer": (
                "https://www.schroders.com/zh-tw/tw/"
                "individual/fund-centre/"
            ),
        },
        timeout=30,
    )

    response.raise_for_status()

    record_pattern = re.compile(
        r'"identifier":"'
        + re.escape(cleaned_symbol)
        + r'".*?'
        r'"baseCurrencyRaw":"([A-Z]{3})".*?'
        r'"priceEndValueRaw":'
        r'([0-9]+(?:\.[0-9]+)?).*?'
        r'"priceEndDateRaw":"([^"]+)"',
        flags=re.DOTALL,
    )

    record_match = record_pattern.search(
        response.text
    )

    if record_match is None:
        raise ValueError(
            "無法從施羅德官網找到這個 ISIN 的最新淨值。"
        )

    returned_currency = record_match.group(1)
    latest_price = float(record_match.group(2))
    raw_date = record_match.group(3)

    try:
        latest_date = (
            pd.to_datetime(
                raw_date,
                format="%m/%d/%Y",
            )
            .date()
            .isoformat()
        )
    except Exception as error:
        raise ValueError(
            "無法解析施羅德淨值日期："
            f"{raw_date}"
        ) from error

    if latest_price <= 0:
        raise ValueError(
            "施羅德官網回傳的淨值不正確。"
        )

    return {
        "price": latest_price,
        "price_date": latest_date,
        "external_symbol": cleaned_symbol,
        "currency": returned_currency,
        "source": "schroders_fund",
    }

def fetch_external_asset_price(asset):
    price_source = (
        asset.get("price_source")
        or "manual"
    )

    external_symbol = (
        asset.get("external_symbol")
        or ""
    ).strip()

    if not external_symbol:
        raise ValueError(
            "尚未設定外部報價代號或基金 ISIN。"
        )

    if price_source in {
        "yahoo",
        "yfinance",
    }:
        return fetch_yahoo_asset_price(
            external_symbol
        )

    if price_source == "yuanta_fund":
        return fetch_yuanta_fund_price(
            external_symbol
        )

    if price_source == "franklin_fund":
        return fetch_franklin_fund_price(
            external_symbol
        )

    if price_source == "schroders_fund":
        return fetch_schroders_fund_price(
            external_symbol
        )

    raise ValueError(
        f"不支援的價格來源：{price_source}"
    )

@st.cache_data(
    ttl=3600,
    show_spinner=False,
)

def fetch_frankfurter_rates(currencies):
    requested_currencies = tuple(
        sorted(
            {
                currency.upper()
                for currency in currencies
                if currency.upper() != "TWD"
            }
        )
    )

    if not requested_currencies:
        return {}

    response = requests.get(
        FX_API_URL,
        params={
            "base": "TWD",
            "quotes": ",".join(requested_currencies),
        },
        timeout=10,
    )

    response.raise_for_status()
    response_rows = response.json()

    converted_rates = {}

    for row in response_rows:
        currency = row["quote"].upper()
        foreign_currency_per_twd = Decimal(
            str(row["rate"])
        )

        if foreign_currency_per_twd <= 0:
            continue

        twd_per_foreign_currency = (
            Decimal("1") / foreign_currency_per_twd
        ).quantize(
            Decimal("0.000001")
        )

        converted_rates[currency] = {
            "rate": str(twd_per_foreign_currency),
            "rate_date": row["date"],
            "source": "frankfurter",
        }

    missing_currencies = (
        set(requested_currencies)
        - set(converted_rates)
    )

    if missing_currencies:
        missing_text = ", ".join(
            sorted(missing_currencies)
        )

        raise ValueError(
            f"外部資料沒有回傳以下幣別：{missing_text}"
        )

    return converted_rates

def refresh_all_market_data(supabase):
    result = {
        "prices_updated": 0,
        "prices_protected": 0,
        "fx_updated": 0,
        "fx_protected": 0,
        "errors": [],
    }

    try:
        assets_response = (
            supabase.table("assets")
            .select(
                "id, symbol, name, asset_type, "
                "currency, external_symbol, "
                "price_source, is_active"
            )
            .eq("is_active", True)
            .execute()
        )

        prices_response = (
            supabase.table("asset_prices")
            .select(
                "id, asset_id, price_date, source"
            )
            .execute()
        )

        fx_response = (
            supabase.table("fx_rates")
            .select(
                "id, from_currency, to_currency, "
                "rate_date, source"
            )
            .eq("to_currency", "TWD")
            .execute()
        )

        assets = assets_response.data or []
        existing_prices = (
            prices_response.data or []
        )
        existing_fx_rates = (
            fx_response.data or []
        )

    except Exception as error:
        raise RuntimeError(
            f"讀取市場資料失敗：{error}"
        ) from error

    investment_asset_types = {
        "stock",
        "etf",
        "fund",
        "crypto",
    }

    supported_price_sources = {
        "yahoo",
        "yfinance",
        "yuanta_fund",
        "franklin_fund",
        "schroders_fund",
    }

    external_assets = [
        asset
        for asset in assets
        if (
            asset["asset_type"]
            in investment_asset_types
            and (
                asset["external_symbol"] or ""
            ).strip()
            and (
                asset.get("price_source")
                in supported_price_sources
            )
        )
    ]

    price_record_map = {
        (
            price_record["asset_id"],
            price_record["price_date"],
        ): price_record
        for price_record in existing_prices
    }

    # 使用者主動按下同步按鈕時，
    # 清除一小時快取並重新向外部服務查詢。
    fetch_yahoo_asset_price.clear()
    fetch_yuanta_fund_price.clear()
    fetch_franklin_fund_price.clear()
    fetch_schroders_fund_price.clear()

    for asset in external_assets:
        try:
            fetched_record = (
                fetch_external_asset_price(asset)
            )

            fetched_date = (
                fetched_record["price_date"]
            )

            fetched_price = float(
                fetched_record["price"]
            )

            fetched_source = (
                fetched_record["source"]
            )

            returned_currency = (
                fetched_record.get("currency")
            )

            if (
                returned_currency
                and returned_currency
                != asset["currency"]
            ):
                raise ValueError(
                    "外部資料計價幣別為 "
                    f"{returned_currency}，"
                    "但資產設定為 "
                    f'{asset["currency"]}。'
                )

            price_key = (
                asset["id"],
                fetched_date,
            )

            existing_record = (
                price_record_map.get(price_key)
            )

            if (
                existing_record is not None
                and existing_record["source"]
                == "manual"
            ):
                result["prices_protected"] += 1
                continue

            if existing_record is None:
                inserted_response = (
                    supabase
                    .table("asset_prices")
                    .insert(
                        {
                            "asset_id": asset["id"],
                            "price": fetched_price,
                            "price_date": fetched_date,
                            "currency": (
                                asset["currency"]
                            ),
                            "source": fetched_source,
                        }
                    )
                    .execute()
                )

                inserted_rows = (
                    inserted_response.data or []
                )

                if inserted_rows:
                    price_record_map[price_key] = (
                        inserted_rows[0]
                    )

            else:
                (
                    supabase
                    .table("asset_prices")
                    .update(
                        {
                            "price": fetched_price,
                            "currency": (
                                asset["currency"]
                            ),
                            "source": fetched_source,
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
                        existing_record["id"],
                    )
                    .execute()
                )

            result["prices_updated"] += 1

        except Exception as error:
            result["errors"].append(
                f'{asset["symbol"]} 價格：{error}'
            )

    foreign_currencies = sorted(
        {
            asset["currency"]
            for asset in assets
            if asset["currency"] != "TWD"
        }
    )

    if foreign_currencies:
        try:
            fetch_frankfurter_rates.clear()

            external_fx_rates = (
                fetch_frankfurter_rates(
                    tuple(foreign_currencies)
                )
            )

            fx_record_map = {
                (
                    record["from_currency"],
                    record["to_currency"],
                    record["rate_date"],
                ): record
                for record in existing_fx_rates
            }

            for (
                currency,
                external_record,
            ) in external_fx_rates.items():
                fx_key = (
                    currency,
                    "TWD",
                    external_record["rate_date"],
                )

                existing_record = (
                    fx_record_map.get(fx_key)
                )

                if (
                    existing_record is not None
                    and existing_record["source"]
                    == "manual"
                ):
                    result["fx_protected"] += 1
                    continue

                external_rate = float(
                    external_record["rate"]
                )

                if existing_record is None:
                    inserted_response = (
                        supabase
                        .table("fx_rates")
                        .insert(
                            {
                                "from_currency": (
                                    currency
                                ),
                                "to_currency": "TWD",
                                "rate": external_rate,
                                "rate_date": (
                                    external_record[
                                        "rate_date"
                                    ]
                                ),
                                "source": (
                                    "frankfurter"
                                ),
                            }
                        )
                        .execute()
                    )

                    inserted_rows = (
                        inserted_response.data or []
                    )

                    if inserted_rows:
                        fx_record_map[fx_key] = (
                            inserted_rows[0]
                        )

                else:
                    (
                        supabase
                        .table("fx_rates")
                        .update(
                            {
                                "rate": external_rate,
                                "source": (
                                    "frankfurter"
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
                            existing_record["id"],
                        )
                        .execute()
                    )

                result["fx_updated"] += 1

        except Exception as error:
            result["errors"].append(
                f"匯率更新：{error}"
            )

    return result
