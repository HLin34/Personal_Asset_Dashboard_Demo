import math
from datetime import datetime
from zoneinfo import ZoneInfo


SEATTLE_TIMEZONE = ZoneInfo(
    "America/Los_Angeles"
)


def _required_number(value, field_name):
    number = float(value)

    if not math.isfinite(number):
        raise ValueError(
            f"{field_name} 不是有效數字。"
        )

    return number


def _optional_number(value, field_name):
    if value is None:
        return None

    return _required_number(
        value,
        field_name,
    )


def save_daily_snapshot(
    supabase,
    *,
    total_assets_twd,
    cash_assets_twd,
    investment_assets_twd,
    remaining_cost_twd=None,
    unrealized_pnl_twd=None,
    realized_pnl_twd=None,
    price_pnl_twd=None,
    net_dividend_twd=None,
    total_pnl_twd=None,
    data_complete=True,
):
    user_response = (
        supabase.auth.get_user()
    )

    current_user = user_response.user

    if current_user is None:
        raise RuntimeError(
            "目前沒有登入中的使用者。"
        )

    now = datetime.now(
        SEATTLE_TIMEZONE
    )

    payload = {
        "user_id": current_user.id,
        "snapshot_date": (
            now.date().isoformat()
        ),
        "total_assets_twd": (
            _required_number(
                total_assets_twd,
                "總資產",
            )
        ),
        "cash_assets_twd": (
            _required_number(
                cash_assets_twd,
                "現金資產",
            )
        ),
        "investment_assets_twd": (
            _required_number(
                investment_assets_twd,
                "投資資產",
            )
        ),
        "remaining_cost_twd": (
            _optional_number(
                remaining_cost_twd,
                "剩餘投資成本",
            )
        ),
        "unrealized_pnl_twd": (
            _optional_number(
                unrealized_pnl_twd,
                "未實現損益",
            )
        ),
        "realized_pnl_twd": (
            _optional_number(
                realized_pnl_twd,
                "已實現損益",
            )
        ),
        "price_pnl_twd": (
            _optional_number(
                price_pnl_twd,
                "價格總損益",
            )
        ),
        "net_dividend_twd": (
            _optional_number(
                net_dividend_twd,
                "淨現金股利",
            )
        ),
        "total_pnl_twd": (
            _optional_number(
                total_pnl_twd,
                "含股利總損益",
            )
        ),
        "data_complete": bool(
            data_complete
        ),
        "updated_at": now.isoformat(),
    }

    response = (
        supabase
        .table("portfolio_snapshots")
        .upsert(
            payload,
            on_conflict=(
                "user_id,snapshot_date"
            ),
        )
        .execute()
    )

    return response.data or []

def save_account_snapshot_rows(
    supabase,
    *,
    snapshot_id,
    account_rows,
):
    """
    儲存指定總快照下的帳戶層級估值。

    同一個 snapshot_id 重新儲存時，
    會先移除舊明細再寫入最新結果，
    避免帳戶取消納入 TWR 後留下舊資料。
    """
    user_response = (
        supabase.auth.get_user()
    )

    current_user = user_response.user

    if current_user is None:
        raise RuntimeError(
            "目前沒有登入中的使用者。"
        )

    if not snapshot_id:
        raise ValueError(
            "缺少資產快照 ID。"
        )

    normalized_rows = []

    for row in account_rows:
        account_id = row.get("account_id")

        if not account_id:
            raise ValueError(
                "帳戶快照缺少 account_id。"
            )

        missing_price_count = int(
            row.get(
                "missing_price_count",
                0,
            )
            or 0
        )

        missing_fx_count = int(
            row.get(
                "missing_fx_count",
                0,
            )
            or 0
        )

        if missing_price_count < 0:
            raise ValueError(
                "缺少價格數量不能小於零。"
            )

        if missing_fx_count < 0:
            raise ValueError(
                "缺少匯率數量不能小於零。"
            )

        normalized_rows.append(
            {
                "user_id": current_user.id,
                "snapshot_id": snapshot_id,
                "account_id": account_id,
                "total_assets_twd": (
                    _required_number(
                        row.get(
                            "total_assets_twd",
                            0,
                        ),
                        "帳戶總資產",
                    )
                ),
                "cash_assets_twd": (
                    _required_number(
                        row.get(
                            "cash_assets_twd",
                            0,
                        ),
                        "帳戶現金資產",
                    )
                ),
                "investment_assets_twd": (
                    _required_number(
                        row.get(
                            "investment_assets_twd",
                            0,
                        ),
                        "帳戶投資資產",
                    )
                ),
                "data_complete": bool(
                    row.get(
                        "data_complete",
                        True,
                    )
                ),
                "missing_price_count": (
                    missing_price_count
                ),
                "missing_fx_count": (
                    missing_fx_count
                ),
            }
        )

    # 重新儲存同一天快照時，
    # 先清除該快照原有的帳戶明細。
    (
        supabase
        .table(
            "portfolio_snapshot_accounts"
        )
        .delete()
        .eq(
            "snapshot_id",
            snapshot_id,
        )
        .eq(
            "user_id",
            current_user.id,
        )
        .execute()
    )

    if not normalized_rows:
        return []

    response = (
        supabase
        .table(
            "portfolio_snapshot_accounts"
        )
        .insert(normalized_rows)
        .execute()
    )

    return response.data or []

def load_portfolio_snapshots(
    supabase,
    limit=3650,
):
    response = (
        supabase
        .table("portfolio_snapshots")
        .select(
            "id, snapshot_date, "
            "total_assets_twd, "
            "cash_assets_twd, "
            "investment_assets_twd, "
            "remaining_cost_twd, "
            "unrealized_pnl_twd, "
            "realized_pnl_twd, "
            "price_pnl_twd, "
            "net_dividend_twd, "
            "total_pnl_twd, "
            "data_complete, "
            "created_at, updated_at"
        )
        .order(
            "snapshot_date",
            desc=False,
        )
        .limit(limit)
        .execute()
    )

    return response.data or []