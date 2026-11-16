import unittest

import pandas as pd

from services.standard_csv_import import (
    build_standard_import_payload,
    prepare_standard_csv_import,
    resolve_asset_metadata,
    validate_asset_metadata,
)


HEADERS = (
    "交易日期,買/賣/股利,代號,股票,交易類別,"
    "買入股數,買入價格,賣出股數,賣出價格,現價,"
    "手續費,折讓後手續費,交易稅,成交價金,交易成本,"
    "支出,收入,決策原因,手續費折數"
)


class StandardCsvImportTest(unittest.TestCase):
    def test_taiwan_market_resolution_and_dividend(self):
        source = (
            "標題,,,,,,,,,,,,,,,,,,\n"
            + HEADERS
            + "\n2026/01/02,買,2330,台積電,一般,"
            "1,1000,,,,1,1,0,1000,1,1001,0,測試,1"
            "\n2026/02/02,股利,2330,台積電,一般,"
            ",,,,,0,0,0,10,0,0,10,10 現金股利,1\n"
        ).encode("utf-8")
        prepared = prepare_standard_csv_import(
            source,
            currency="TWD",
        )

        def quote_fetcher(symbol):
            if symbol == "2330.TW":
                return {"price": 1000}

            raise ValueError(symbol)

        assets = resolve_asset_metadata(
            prepared["assets"],
            [],
            quote_fetcher,
        )
        payload = build_standard_import_payload(
            prepared,
            assets,
            source_account_id="account-1",
        )

        self.assertEqual(
            prepared["summary"]["valid_transaction_count"],
            2,
        )
        self.assertEqual(
            prepared["summary"]["dividend_inflow"],
            10,
        )
        self.assertEqual(assets.iloc[0]["market"], "TWSE")
        self.assertEqual(
            assets.iloc[0]["external_symbol"],
            "2330.TW",
        )
        self.assertEqual(len(payload["records"]), 2)

    def test_us_dot_symbol_falls_back_to_dash(self):
        source = (
            "標題,,,,,,,,,,,,,,,,,,\n"
            + HEADERS
            + "\n2026/01/02,買,BRK.B,Berkshire,一般,"
            "1,500,,,,0,0,0,500,0,500,0,測試,1\n"
        ).encode("utf-8")
        prepared = prepare_standard_csv_import(
            source,
            currency="USD",
        )

        def quote_fetcher(symbol):
            if symbol == "BRK-B":
                return {"price": 500}

            raise ValueError(symbol)

        assets = resolve_asset_metadata(
            prepared["assets"],
            [],
            quote_fetcher,
        )

        self.assertEqual(assets.iloc[0]["market"], "US")
        self.assertEqual(
            assets.iloc[0]["external_symbol"],
            "BRK-B",
        )

    def test_nan_market_is_rejected_as_blank(self):
        assets = pd.DataFrame(
            [
                {
                    "symbol": "NET",
                    "name": "Cloudflare",
                    "asset_type": "stock",
                    "currency": "USD",
                    "market": pd.NA,
                    "external_symbol": pd.NA,
                    "price_source": "manual",
                }
            ]
        )

        cleaned, errors = validate_asset_metadata(assets)

        self.assertEqual(cleaned.iloc[0]["market"], "")
        self.assertEqual(
            cleaned.iloc[0]["external_symbol"],
            "",
        )
        self.assertIn("NET：尚未設定市場", errors)

    def test_incomplete_existing_us_asset_is_upgraded(self):
        assets = pd.DataFrame(
            [
                {
                    "symbol": "NET",
                    "name": "Cloudflare",
                    "asset_type": "stock",
                    "currency": "USD",
                }
            ]
        )
        existing_assets = [
            {
                "symbol": "NET",
                "name": "Cloudflare",
                "asset_type": "stock",
                "currency": "USD",
                "market": "",
                "external_symbol": "",
                "price_source": "manual",
                "is_active": True,
            }
        ]

        resolved = resolve_asset_metadata(
            assets,
            existing_assets,
            lambda symbol: {"price": 300},
        )

        self.assertEqual(resolved.iloc[0]["market"], "US")
        self.assertEqual(
            resolved.iloc[0]["external_symbol"],
            "NET",
        )
        self.assertEqual(
            resolved.iloc[0]["price_source"],
            "yfinance",
        )
        self.assertEqual(
            resolved.iloc[0]["resolution_status"],
            "existing_updated",
        )


if __name__ == "__main__":
    unittest.main()
