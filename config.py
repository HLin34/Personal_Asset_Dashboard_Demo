ACCOUNT_TYPE_LABELS = {
    "bank": "銀行帳戶",
    "brokerage": "證券／券商帳戶",
    "fund_platform": "基金平台",
    "crypto": "加密貨幣平台",
    "cash": "實體現金",
    "other": "其他",
}

ACCOUNT_TYPE_OPTIONS = list(
    ACCOUNT_TYPE_LABELS.keys()
)

ASSET_TYPE_OPTIONS = [
    "cash",
    "stock",
    "etf",
    "fund",
    "bond",
    "crypto",
    "other",
]

ASSET_TYPE_LABELS = {
    "cash": "現金",
    "stock": "股票",
    "etf": "ETF",
    "fund": "基金",
    "bond": "債券",
    "crypto": "加密貨幣",
    "other": "其他",
}

CURRENCY_OPTIONS = [
    "TWD",
    "USD",
    "JPY",
    "EUR",
    "GBP",
    "CAD",
    "AUD",
    "HKD",
    "SGD",
    "CNY",
    "KRW",
]

PRICE_SOURCE_LABELS = {
    "manual": "手動輸入",
    "yfinance": "Yahoo Finance",
    "yuanta_fund": "元大投信官方淨值",
    "franklin_fund": "Franklin Templeton 官方淨值",
    "schroders_fund": "施羅德官方淨值",
}

PRICE_SOURCE_OPTIONS = list(
    PRICE_SOURCE_LABELS.keys()
)

FX_SOURCE_LABELS = {
    "manual": "手動輸入",
    "frankfurter": "Frankfurter 自動匯率",
}
