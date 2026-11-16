import unittest

from services.portfolio_cost import (
    calculate_portfolio_costs,
)


ASSETS = {
    "asset-1": {
        "asset_type": "stock",
    }
}


def make_transaction(
    transaction_id,
    transaction_date,
    transaction_type,
    fee_amount=0,
    tax_amount=0,
    dividend_type=None,
    external_reference=None,
):
    return {
        "id": transaction_id,
        "transaction_date": transaction_date,
        "created_at": transaction_date,
        "transaction_type": transaction_type,
        "fee_amount": fee_amount,
        "tax_amount": tax_amount,
        "dividend_type": dividend_type,
        "external_reference": external_reference,
    }


def make_entry(
    transaction_id,
    quantity_delta,
    unit_price=None,
):
    return {
        "transaction_id": transaction_id,
        "account_id": "account-1",
        "asset_id": "asset-1",
        "quantity_delta": quantity_delta,
        "unit_price": unit_price,
    }


class PortfolioCostTest(unittest.TestCase):
    def test_moving_average_and_realized_pnl(self):
        transactions = [
            make_transaction(
                "opening",
                "2026-01-01T12:00:00+00:00",
                "opening_balance",
            ),
            make_transaction(
                "buy",
                "2026-02-01T12:00:00+00:00",
                "buy",
                fee_amount=10,
            ),
            make_transaction(
                "stock-dividend",
                "2026-03-01T12:00:00+00:00",
                "dividend",
                dividend_type="stock",
            ),
            make_transaction(
                "sell",
                "2026-04-01T12:00:00+00:00",
                "sell",
                fee_amount=5,
                tax_amount=5,
            ),
        ]

        entries = [
            make_entry(
                "opening",
                100,
                10,
            ),
            make_entry(
                "buy",
                100,
                20,
            ),
            make_entry(
                "stock-dividend",
                10,
            ),
            make_entry(
                "sell",
                -50,
                30,
            ),
        ]

        results = calculate_portfolio_costs(
            transactions,
            entries,
            ASSETS,
        )

        result = results[
            ("account-1", "asset-1")
        ]

        self.assertAlmostEqual(
            result["quantity"],
            160,
        )

        self.assertAlmostEqual(
            result["average_cost"],
            14.3333333333,
        )

        self.assertAlmostEqual(
            result["total_cost"],
            2293.3333333333,
        )

        self.assertAlmostEqual(
            result["realized_pnl"],
            773.3333333333,
        )

        self.assertTrue(
            result["cost_complete"]
        )

    def test_manual_adjustment_keeps_average_cost(self):
        transactions = [
            make_transaction(
                "opening",
                "2026-01-01T12:00:00+00:00",
                "opening_balance",
            ),
            make_transaction(
                "adjustment",
                "2026-02-01T12:00:00+00:00",
                "adjustment",
            ),
        ]

        entries = [
            make_entry(
                "opening",
                100,
                10,
            ),
            make_entry(
                "adjustment",
                50,
            ),
        ]

        results = calculate_portfolio_costs(
            transactions,
            entries,
            ASSETS,
        )

        result = results[
            ("account-1", "asset-1")
        ]

        self.assertAlmostEqual(
            result["quantity"],
            150,
        )

        self.assertAlmostEqual(
            result["average_cost"],
            10,
        )

        self.assertAlmostEqual(
            result["total_cost"],
            1500,
        )

        self.assertTrue(
            result["cost_complete"]
        )

    def test_cancelled_trade_is_excluded(self):
        transactions = [
            make_transaction(
                "opening",
                "2026-01-01T12:00:00+00:00",
                "opening_balance",
            ),
            make_transaction(
                "cancelled-buy",
                "2026-02-01T12:00:00+00:00",
                "buy",
            ),
            make_transaction(
                "buy-reversal",
                "2026-02-02T12:00:00+00:00",
                "adjustment",
                external_reference=(
                    "trade_reversal:"
                    "cancelled-buy"
                ),
            ),
        ]

        entries = [
            make_entry(
                "opening",
                5,
                10,
            ),
            make_entry(
                "cancelled-buy",
                10,
                20,
            ),
            make_entry(
                "buy-reversal",
                -10,
                20,
            ),
        ]

        results = calculate_portfolio_costs(
            transactions,
            entries,
            ASSETS,
        )

        result = results[
            ("account-1", "asset-1")
        ]

        self.assertAlmostEqual(
            result["quantity"],
            5,
        )

        self.assertAlmostEqual(
            result["total_cost"],
            50,
        )

        self.assertAlmostEqual(
            result["average_cost"],
            10,
        )


if __name__ == "__main__":
    unittest.main()