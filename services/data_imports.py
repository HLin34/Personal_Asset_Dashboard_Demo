from io import BytesIO
import hashlib
import json
from pathlib import PurePosixPath
import stat
import zipfile
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from uuid import UUID

import pandas as pd


BACKUP_FORMAT = "personal_asset_dashboard_backup"
SUPPORTED_BACKUP_VERSIONS = {1, 2, 3}

MAX_ZIP_SIZE_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE_BYTES = 200 * 1024 * 1024
MAX_FILE_COUNT = 100
MAX_PREVIEW_ROWS = 100

COMPARISON_IGNORED_COLUMNS = {
    "user_id",
}

BOOLEAN_COLUMNS = {
    "is_active",
    "cash_linked",
    "data_complete",
}

NUMERIC_COLUMNS = {
    "quantity_delta",
    "unit_price",
    "fee_amount",
    "tax_amount",
    "gross_amount",
    "price",
    "rate",
    "commission_rate",
    "discount_rate",
    "minimum_commission",
    "sell_stock_tax_rate",
    "sell_etf_tax_rate",
    "total_assets_twd",
    "cash_assets_twd",
    "investment_assets_twd",
    "remaining_cost_twd",
    "unrealized_pnl_twd",
    "realized_pnl_twd",
    "price_pnl_twd",
    "net_dividend_twd",
    "total_pnl_twd",
}

RESTORE_TABLE_ORDER = (
    "accounts",
    "assets",
    "transactions",
    "transaction_entries",
    "asset_prices",
    "fx_rates",
    "broker_fee_settings",
    "portfolio_snapshots",
)

RESTORE_BATCH_SIZE = 100


def _new_result():
    return {
        "is_valid": False,
        "manifest": None,
        "tables": {},
        "summary_rows": [],
        "errors": [],
        "warnings": [],
        "zip_size_bytes": 0,
        "uncompressed_size_bytes": 0,
        "restore_capable": False,
    }


def _is_safe_member_name(filename):
    """拒絕絕對路徑、父目錄及 Windows 路徑。"""
    if not isinstance(filename, str) or not filename:
        return False

    normalized_name = filename.replace("\\", "/")
    path = PurePosixPath(normalized_name)

    return (
        not path.is_absolute()
        and ".." not in path.parts
        and ":" not in path.parts[0]
    )


def _is_symbolic_link(zip_info):
    unix_mode = zip_info.external_attr >> 16
    return stat.S_ISLNK(unix_mode)


def _read_zip_bytes(zip_source):
    if isinstance(zip_source, bytes):
        return zip_source

    if isinstance(zip_source, bytearray):
        return bytes(zip_source)

    if hasattr(zip_source, "getvalue"):
        return zip_source.getvalue()

    if hasattr(zip_source, "read"):
        current_position = None

        if hasattr(zip_source, "tell"):
            current_position = zip_source.tell()

        file_bytes = zip_source.read()

        if (
            current_position is not None
            and hasattr(zip_source, "seek")
        ):
            zip_source.seek(current_position)

        return file_bytes

    raise TypeError("無法讀取上傳的 ZIP 檔案。")


def _validate_manifest(manifest, result):
    if not isinstance(manifest, dict):
        result["errors"].append(
            "manifest.json 最外層必須是 JSON 物件。"
        )
        return []

    if manifest.get("format") != BACKUP_FORMAT:
        result["errors"].append(
            "這不是 Personal Asset Dashboard 的備份格式。"
        )

    version = manifest.get("version")

    if version not in SUPPORTED_BACKUP_VERSIONS:
        result["errors"].append(
            f"不支援備份版本：{version!r}。"
        )

    manifest_files = manifest.get("files")

    if not isinstance(manifest_files, list):
        result["errors"].append(
            "manifest.json 缺少有效的 files 清單。"
        )
        return []

    if not manifest_files:
        result["warnings"].append(
            "備份中沒有任何資料表。"
        )

    return manifest_files


def validate_backup_zip(zip_source):
    """
    驗證並預覽 Dashboard ZIP 備份。

    此函數只在記憶體內讀取資料，不會解壓縮到磁碟，
    也不會寫入 Supabase。
    """
    result = _new_result()

    try:
        zip_bytes = _read_zip_bytes(zip_source)
    except Exception as error:
        result["errors"].append(str(error))
        return result

    result["zip_size_bytes"] = len(zip_bytes)

    if not zip_bytes:
        result["errors"].append("上傳的檔案是空的。")
        return result

    if len(zip_bytes) > MAX_ZIP_SIZE_BYTES:
        result["errors"].append(
            "ZIP 超過目前允許的 50 MB。"
        )
        return result

    if not zipfile.is_zipfile(BytesIO(zip_bytes)):
        result["errors"].append("檔案不是有效的 ZIP。")
        return result

    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_file:
            zip_infos = zip_file.infolist()

            if len(zip_infos) > MAX_FILE_COUNT:
                result["errors"].append(
                    "ZIP 內檔案數量超過目前允許的 100 個。"
                )
                return result

            member_names = [
                zip_info.filename
                for zip_info in zip_infos
            ]

            if len(member_names) != len(set(member_names)):
                result["errors"].append(
                    "ZIP 內含有重複檔名。"
                )

            for zip_info in zip_infos:
                if not _is_safe_member_name(zip_info.filename):
                    result["errors"].append(
                        "ZIP 內含有不安全的路徑："
                        f"{zip_info.filename}"
                    )

                if zip_info.flag_bits & 0x1:
                    result["errors"].append(
                        "不支援加密檔案："
                        f"{zip_info.filename}"
                    )

                if _is_symbolic_link(zip_info):
                    result["errors"].append(
                        "ZIP 內不得包含符號連結："
                        f"{zip_info.filename}"
                    )

            total_uncompressed_size = sum(
                zip_info.file_size
                for zip_info in zip_infos
            )

            result["uncompressed_size_bytes"] = (
                total_uncompressed_size
            )

            if (
                total_uncompressed_size
                > MAX_UNCOMPRESSED_SIZE_BYTES
            ):
                result["errors"].append(
                    "ZIP 解壓縮後超過目前允許的 200 MB。"
                )

            if result["errors"]:
                return result

            if "manifest.json" not in member_names:
                result["errors"].append(
                    "ZIP 缺少 manifest.json。"
                )
                return result

            try:
                manifest = json.loads(
                    zip_file.read("manifest.json").decode("utf-8")
                )
            except Exception as error:
                result["errors"].append(
                    "manifest.json 無法讀取："
                    f"{error}"
                )
                return result

            result["manifest"] = manifest

            manifest_files = _validate_manifest(
                manifest,
                result,
            )

            if result["errors"]:
                return result

            declared_filenames = []

            for file_record in manifest_files:
                if not isinstance(file_record, dict):
                    result["errors"].append(
                        "manifest 的 files 項目格式錯誤。"
                    )
                    continue

                filename = file_record.get("filename")
                row_count = file_record.get("row_count")
                columns = file_record.get("columns")

                if (
                    not isinstance(filename, str)
                    or not filename.endswith(".csv")
                    or not _is_safe_member_name(filename)
                ):
                    result["errors"].append(
                        f"manifest 內含無效檔名：{filename!r}。"
                    )
                    continue

                declared_filenames.append(filename)

                if filename not in member_names:
                    result["errors"].append(
                        f"ZIP 缺少 manifest 所列檔案：{filename}。"
                    )
                    continue

                if (
                    not isinstance(row_count, int)
                    or isinstance(row_count, bool)
                    or row_count < 0
                ):
                    result["errors"].append(
                        f"{filename} 的 row_count 無效。"
                    )
                    continue

                if (
                    not isinstance(columns, list)
                    or not all(
                        isinstance(column, str)
                        for column in columns
                    )
                ):
                    result["errors"].append(
                        f"{filename} 的 columns 無效。"
                    )
                    continue

                try:
                    dataframe = pd.read_csv(
                        BytesIO(zip_file.read(filename)),
                        encoding="utf-8-sig",
                        dtype=str,
                        keep_default_na=False,
                    )
                except Exception as error:
                    result["errors"].append(
                        f"{filename} 無法讀取：{error}"
                    )
                    continue

                actual_columns = [
                    str(column)
                    for column in dataframe.columns
                ]
                actual_row_count = int(len(dataframe))

                table_errors = []

                if actual_columns != columns:
                    table_errors.append(
                        "欄位名稱或順序與 manifest 不一致"
                    )

                if actual_row_count != row_count:
                    table_errors.append(
                        "資料筆數與 manifest 不一致"
                    )

                expected_hash = file_record.get("sha256")

                if expected_hash:
                    actual_hash = hashlib.sha256(
                        zip_file.read(filename)
                    ).hexdigest()

                    if actual_hash != expected_hash:
                        table_errors.append(
                            "SHA-256 雜湊值不一致"
                        )

                restore_dataframe = dataframe
                data_filename = None

                if manifest.get("version", 0) >= 3:
                    data_filename = file_record.get(
                        "data_filename"
                    )

                    if (
                        not isinstance(data_filename, str)
                        or not data_filename.endswith(".json")
                        or not _is_safe_member_name(
                            data_filename
                        )
                    ):
                        table_errors.append(
                            "缺少有效的還原 JSON 檔名"
                        )

                    elif data_filename not in member_names:
                        table_errors.append(
                            "缺少還原 JSON 檔案"
                        )

                    else:
                        declared_filenames.append(
                            data_filename
                        )

                        json_bytes = zip_file.read(
                            data_filename
                        )

                        expected_data_hash = (
                            file_record.get(
                                "data_sha256"
                            )
                        )

                        actual_data_hash = (
                            hashlib.sha256(
                                json_bytes
                            ).hexdigest()
                        )

                        if (
                            not expected_data_hash
                            or actual_data_hash
                            != expected_data_hash
                        ):
                            table_errors.append(
                                "還原 JSON 的 SHA-256 "
                                "雜湊值不一致"
                            )

                        try:
                            json_records = json.loads(
                                json_bytes.decode(
                                    "utf-8"
                                )
                            )

                            if not isinstance(
                                json_records,
                                list,
                            ):
                                raise ValueError(
                                    "JSON 最外層必須是陣列"
                                )

                            if not all(
                                isinstance(record, dict)
                                for record in json_records
                            ):
                                raise ValueError(
                                    "JSON 每筆資料必須是物件"
                                )

                            if len(json_records) != row_count:
                                table_errors.append(
                                    "還原 JSON 筆數與 "
                                    "manifest 不一致"
                                )

                            invalid_json_columns = any(
                                set(record.keys())
                                != set(columns)
                                for record in json_records
                            )

                            if invalid_json_columns:
                                table_errors.append(
                                    "還原 JSON 欄位與 "
                                    "manifest 不一致"
                                )

                            restore_dataframe = (
                                pd.DataFrame(
                                    json_records,
                                    columns=columns,
                                )
                            )

                        except Exception as error:
                            table_errors.append(
                                "還原 JSON 無法讀取："
                                f"{error}"
                            )

                table_name = filename[:-4]

                result["tables"][table_name] = {
                    "filename": filename,
                    "data_filename": data_filename,
                    "dataframe": restore_dataframe,
                    "preview": restore_dataframe.head(
                        MAX_PREVIEW_ROWS
                    ),
                    "row_count": actual_row_count,
                    "column_count": len(actual_columns),
                    "columns": actual_columns,
                    "errors": table_errors,
                }

                result["summary_rows"].append(
                    {
                        "資料表": table_name,
                        "檔案": filename,
                        "資料筆數": actual_row_count,
                        "欄位數量": len(actual_columns),
                        "檢查結果": (
                            "正常"
                            if not table_errors
                            else "；".join(table_errors)
                        ),
                    }
                )

                for table_error in table_errors:
                    result["errors"].append(
                        f"{filename}：{table_error}。"
                    )

            if len(declared_filenames) != len(
                set(declared_filenames)
            ):
                result["errors"].append(
                    "manifest 內含有重複檔名。"
                )

            undeclared_files = sorted(
                set(member_names)
                - set(declared_filenames)
                - {"manifest.json"}
            )

            if undeclared_files:
                result["warnings"].append(
                    "ZIP 內含未列於 manifest 的檔案："
                    + "、".join(undeclared_files)
                )

            if manifest.get("version") == 1:
                result["warnings"].append(
                    "這是第 1 版備份：已檢查格式、欄位與筆數，"
                    "但此版本尚未包含 SHA-256 完整性雜湊值。"
                )

            if manifest.get("version") in {1, 2}:
                result["warnings"].append(
                    "此備份可供檢查與衝突分析，但 CSV 無法精確"
                    "區分 NULL 與空字串，因此不開放正式還原。"
                )

    except Exception as error:
        result["errors"].append(
            f"讀取 ZIP 時發生錯誤：{error}"
        )
        return result

    result["is_valid"] = not result["errors"]
    result["restore_capable"] = (
        result["is_valid"]
        and (result["manifest"] or {}).get(
            "version"
        ) >= 3
    )

    return result


def _is_blank_value(value):
    if value is None:
        return True

    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass

    return value == ""


def _normalize_boolean(value):
    if isinstance(value, bool):
        return value

    normalized_text = str(value).strip().lower()

    if normalized_text in {"true", "t", "1", "yes"}:
        return True

    if normalized_text in {"false", "f", "0", "no"}:
        return False

    return normalized_text


def _normalize_number(value):
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return str(value)

    if number == 0:
        return "0"

    return format(number.normalize(), "f")


def _normalize_date_or_timestamp(value, column_name):
    text_value = str(value).strip()

    if (
        column_name.endswith("_date")
        and "T" not in text_value
        and " " not in text_value
    ):
        try:
            return pd.Timestamp(text_value).date().isoformat()
        except (TypeError, ValueError):
            return text_value

    try:
        timestamp = pd.to_datetime(
            text_value,
            utc=True,
        )

        return timestamp.isoformat()

    except (TypeError, ValueError):
        return text_value


def _normalize_comparison_value(value, column_name):
    if _is_blank_value(value):
        return None

    if column_name in BOOLEAN_COLUMNS:
        return _normalize_boolean(value)

    if column_name in NUMERIC_COLUMNS:
        return _normalize_number(value)

    if (
        column_name.endswith("_at")
        or column_name.endswith("_date")
    ):
        return _normalize_date_or_timestamp(
            value,
            column_name,
        )

    return str(value)


def _dataframe_records(dataframe):
    if dataframe is None or dataframe.empty:
        return []

    normalized_dataframe = (
        dataframe.astype(object)
        .where(pd.notna(dataframe), None)
    )

    return normalized_dataframe.to_dict(
        orient="records"
    )


def _row_differences(
    backup_row,
    current_row,
    comparison_columns,
):
    differences = []

    for column_name in comparison_columns:
        backup_value = _normalize_comparison_value(
            backup_row.get(column_name),
            column_name,
        )
        current_value = _normalize_comparison_value(
            current_row.get(column_name),
            column_name,
        )

        if backup_value != current_value:
            differences.append(
                {
                    "欄位": column_name,
                    "備份值": backup_row.get(column_name),
                    "目前值": current_row.get(column_name),
                }
            )

    return differences


def analyze_restore_conflicts(
    backup_tables,
    current_tables,
):
    """
    比較已驗證的備份與目前資料庫資料。

    只進行記憶體內分析，不會寫入、更新或刪除資料。
    `user_id` 不參與內容差異比較；資料仍以每列 `id`
    作為唯一識別。
    """
    analysis = {
        "is_valid": True,
        "summary_rows": [],
        "detail_rows": [],
        "conflicts": [],
        "errors": [],
        "warnings": [],
        "totals": {
            "backup": 0,
            "new": 0,
            "existing": 0,
            "conflict": 0,
            "current_only": 0,
        },
    }

    for table_name, backup_table in (
        (backup_tables or {}).items()
    ):
        backup_dataframe = backup_table.get(
            "dataframe",
            pd.DataFrame(),
        )

        if table_name not in (current_tables or {}):
            analysis["errors"].append(
                f"目前無法讀取資料表 {table_name}，"
                "因此不能進行安全比較。"
            )
            continue

        current_source = current_tables[table_name]

        if isinstance(current_source, pd.DataFrame):
            current_dataframe = current_source.copy()
        else:
            current_dataframe = pd.DataFrame(
                current_source or []
            )

        if "id" not in backup_dataframe.columns:
            analysis["errors"].append(
                f"備份資料表 {table_name} 缺少 id 欄位。"
            )
            continue

        if (
            not current_dataframe.empty
            and "id" not in current_dataframe.columns
        ):
            analysis["errors"].append(
                f"目前資料表 {table_name} 缺少 id 欄位。"
            )
            continue

        backup_records = _dataframe_records(
            backup_dataframe
        )
        current_records = _dataframe_records(
            current_dataframe
        )

        backup_ids = [
            str(row.get("id"))
            for row in backup_records
        ]
        current_ids = [
            str(row.get("id"))
            for row in current_records
        ]

        if len(backup_ids) != len(set(backup_ids)):
            analysis["errors"].append(
                f"備份資料表 {table_name} 含有重複 id。"
            )
            continue

        if len(current_ids) != len(set(current_ids)):
            analysis["errors"].append(
                f"目前資料表 {table_name} 含有重複 id。"
            )
            continue

        current_by_id = {
            str(row.get("id")): row
            for row in current_records
        }

        backup_columns = [
            str(column)
            for column in backup_dataframe.columns
        ]
        current_columns = [
            str(column)
            for column in current_dataframe.columns
        ]

        comparison_columns = [
            column
            for column in backup_columns
            if (
                column != "id"
                and column not in COMPARISON_IGNORED_COLUMNS
                and (
                    current_dataframe.empty
                    or column in current_columns
                )
            )
        ]

        backup_only_columns = sorted(
            set(backup_columns)
            - set(current_columns)
        ) if not current_dataframe.empty else []

        current_only_columns = sorted(
            set(current_columns)
            - set(backup_columns)
        )

        if backup_only_columns or current_only_columns:
            analysis["warnings"].append(
                f"{table_name} 的備份與目前資料庫欄位不同；"
                "正式還原前必須先處理資料庫結構差異。"
            )

        table_counts = {
            "new": 0,
            "existing": 0,
            "conflict": 0,
        }

        for backup_row in backup_records:
            row_id = str(backup_row.get("id"))
            current_row = current_by_id.get(row_id)

            if current_row is None:
                status = "可新增"
                table_counts["new"] += 1
                changed_fields = ""

            else:
                differences = _row_differences(
                    backup_row,
                    current_row,
                    comparison_columns,
                )

                if differences:
                    status = "內容衝突"
                    table_counts["conflict"] += 1
                    changed_fields = "、".join(
                        difference["欄位"]
                        for difference in differences
                    )

                    analysis["conflicts"].append(
                        {
                            "table_name": table_name,
                            "id": row_id,
                            "differences": differences,
                        }
                    )

                else:
                    status = "已存在且相同"
                    table_counts["existing"] += 1
                    changed_fields = ""

            analysis["detail_rows"].append(
                {
                    "資料表": table_name,
                    "ID": row_id,
                    "分類": status,
                    "差異欄位": changed_fields,
                }
            )

        current_only_count = len(
            set(current_ids) - set(backup_ids)
        )

        schema_difference = ""

        if backup_only_columns:
            schema_difference += (
                "僅備份："
                + "、".join(backup_only_columns)
            )

        if current_only_columns:
            if schema_difference:
                schema_difference += "；"

            schema_difference += (
                "僅目前："
                + "、".join(current_only_columns)
            )

        analysis["summary_rows"].append(
            {
                "資料表": table_name,
                "備份筆數": len(backup_records),
                "可新增": table_counts["new"],
                "已存在且相同": table_counts["existing"],
                "內容衝突": table_counts["conflict"],
                "僅存在目前資料庫": current_only_count,
                "欄位差異": schema_difference,
            }
        )

        analysis["totals"]["backup"] += len(
            backup_records
        )
        analysis["totals"]["new"] += table_counts[
            "new"
        ]
        analysis["totals"]["existing"] += table_counts[
            "existing"
        ]
        analysis["totals"]["conflict"] += table_counts[
            "conflict"
        ]
        analysis["totals"][
            "current_only"
        ] += current_only_count

    analysis["is_valid"] = not analysis["errors"]

    return analysis


def _restore_value(value):
    """保留空字串，只將真正的缺值轉成 None。"""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(
        value,
        (datetime, date, time, pd.Timestamp),
    ):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
        return str(value)

    if hasattr(value, "item"):
        return value.item()

    return value


def _prepare_restore_row(row):
    """
    移除備份中的 user_id，讓資料庫使用目前登入者的
    auth.uid() 預設值。
    """
    return {
        column_name: _restore_value(value)
        for column_name, value in row.items()
        if column_name != "user_id"
    }


def build_add_only_restore_plan(
    backup_tables,
    restore_analysis,
):
    """建立只含「可新增」資料的安全還原計畫。"""
    plan = {
        "is_valid": True,
        "rows_by_table": {},
        "summary_rows": [],
        "total_rows": 0,
        "errors": [],
    }

    if not restore_analysis.get("is_valid"):
        plan["errors"].append(
            "衝突分析未通過，不能建立還原計畫。"
        )

    if restore_analysis.get("warnings"):
        plan["errors"].append(
            "備份與目前資料庫存在欄位結構差異。"
        )

    if restore_analysis.get("totals", {}).get(
        "conflict",
        0,
    ):
        plan["errors"].append(
            "仍有內容衝突，僅新增還原已停止。"
        )

    new_ids_by_table = {}

    for detail_row in restore_analysis.get(
        "detail_rows",
        [],
    ):
        if detail_row.get("分類") != "可新增":
            continue

        table_name = detail_row.get("資料表")
        row_id = str(detail_row.get("ID"))

        new_ids_by_table.setdefault(
            table_name,
            set(),
        ).add(row_id)

    unknown_tables = sorted(
        set(new_ids_by_table)
        - set(RESTORE_TABLE_ORDER)
    )

    if unknown_tables:
        plan["errors"].append(
            "備份含有尚未定義還原順序的資料表："
            + "、".join(unknown_tables)
        )

    if plan["errors"]:
        plan["is_valid"] = False
        return plan

    for table_name in RESTORE_TABLE_ORDER:
        new_ids = new_ids_by_table.get(
            table_name,
            set(),
        )

        table_record = (backup_tables or {}).get(
            table_name
        )

        if table_record is None:
            rows_to_restore = []
        else:
            backup_rows = _dataframe_records(
                table_record.get("dataframe")
            )

            rows_to_restore = [
                _prepare_restore_row(row)
                for row in backup_rows
                if str(row.get("id")) in new_ids
            ]

        plan["rows_by_table"][table_name] = (
            rows_to_restore
        )

        plan["summary_rows"].append(
            {
                "資料表": table_name,
                "預計新增筆數": len(
                    rows_to_restore
                ),
            }
        )

        plan["total_rows"] += len(
            rows_to_restore
        )

    return plan


def execute_add_only_restore(
    supabase,
    restore_plan,
    batch_size=RESTORE_BATCH_SIZE,
):
    """
    依外鍵順序新增缺少資料。

    不執行 update、upsert 或 delete。若中途失敗，重新執行
    衝突分析後即可從尚未新增的資料繼續。
    """
    result = {
        "success": False,
        "inserted_rows": 0,
        "table_results": [],
        "errors": [],
    }

    if not restore_plan.get("is_valid"):
        result["errors"].append(
            "還原計畫無效，未寫入任何資料。"
        )
        return result

    if batch_size < 1:
        result["errors"].append(
            "批次大小必須大於零。"
        )
        return result

    for table_name in RESTORE_TABLE_ORDER:
        table_rows = restore_plan.get(
            "rows_by_table",
            {},
        ).get(table_name, [])

        inserted_for_table = 0

        try:
            for start_index in range(
                0,
                len(table_rows),
                batch_size,
            ):
                batch_rows = table_rows[
                    start_index:
                    start_index + batch_size
                ]

                if not batch_rows:
                    continue

                (
                    supabase.table(table_name)
                    .insert(batch_rows)
                    .execute()
                )

                inserted_for_table += len(
                    batch_rows
                )
                result["inserted_rows"] += len(
                    batch_rows
                )

            result["table_results"].append(
                {
                    "資料表": table_name,
                    "新增筆數": inserted_for_table,
                    "結果": "完成",
                }
            )

        except Exception as error:
            result["table_results"].append(
                {
                    "資料表": table_name,
                    "新增筆數": inserted_for_table,
                    "結果": "失敗",
                }
            )

            result["errors"].append(
                f"{table_name} 還原失敗：{error}"
            )

            return result

    result["success"] = True

    return result
