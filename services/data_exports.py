import hashlib
import json
import re
import zipfile

from datetime import date, datetime, time, timezone
from decimal import Decimal
from io import BytesIO
from numbers import Number
from uuid import UUID

import pandas as pd

from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


FORMULA_PREFIXES = (
    "=",
    "+",
    "-",
    "@",
)

INVALID_SHEET_CHARACTERS = re.compile(
    r"[\[\]:*?/\\]"
)

INVALID_FILENAME_CHARACTERS = re.compile(
    r'[\\/:*?"<>|]'
)


def _protect_formula_text(value):
    """
    避免使用者輸入的文字在 Excel 中被當成公式執行。
    """
    if not isinstance(value, str):
        return value

    candidate = value.lstrip()

    if candidate.startswith(FORMULA_PREFIXES):
        return "'" + value

    return value


def _excel_cell_value(value):
    """
    將 Python、Pandas 及 Supabase 常見值轉成
    openpyxl 可以安全寫入的格式。
    """
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):
        return _protect_formula_text(value)

    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )

    if isinstance(
        value,
        (datetime, date, time, pd.Timestamp),
    ):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (Number, bool)):
        return value

    return _protect_formula_text(str(value))


def _prepare_excel_dataframe(dataframe):
    """
    建立適合寫入 Excel 的副本，不修改原始 DataFrame。
    """
    prepared_dataframe = dataframe.copy()

    for column in prepared_dataframe.columns:
        prepared_dataframe[column] = (
            prepared_dataframe[column].map(
                _excel_cell_value
            )
        )

    return prepared_dataframe


def _prepare_csv_dataframe(
    dataframe,
    protect_formulas,
):
    """
    建立適合寫入 CSV 的副本。

    一般報表應保護公式；原始備份則保留原值，
    方便未來還原資料。
    """
    prepared_dataframe = dataframe.copy()

    if not protect_formulas:
        return prepared_dataframe

    for column in prepared_dataframe.columns:
        prepared_dataframe[column] = (
            prepared_dataframe[column].map(
                _protect_formula_text
            )
        )

    return prepared_dataframe


def _safe_sheet_name(
    requested_name,
    used_names,
):
    """
    建立符合 Excel 規則且不重複的工作表名稱。
    """
    base_name = INVALID_SHEET_CHARACTERS.sub(
        "_",
        str(requested_name),
    ).strip()

    if not base_name:
        base_name = "資料"

    base_name = base_name[:31]

    sheet_name = base_name
    counter = 2

    while sheet_name in used_names:
        suffix = f"_{counter}"

        sheet_name = (
            base_name[: 31 - len(suffix)]
            + suffix
        )

        counter += 1

    used_names.add(sheet_name)

    return sheet_name


def _safe_csv_filename(
    requested_name,
    used_names,
):
    """
    建立適合放進 ZIP 的安全 CSV 檔名。
    """
    base_name = INVALID_FILENAME_CHARACTERS.sub(
        "_",
        str(requested_name),
    ).strip(" .")

    if not base_name:
        base_name = "data"

    if base_name.lower().endswith(".csv"):
        base_name = base_name[:-4]

    filename = f"{base_name}.csv"
    counter = 2

    while filename.lower() in used_names:
        filename = f"{base_name}_{counter}.csv"
        counter += 1

    used_names.add(filename.lower())

    return filename


def dataframe_to_csv_bytes(
    dataframe,
    protect_formulas=True,
):
    """
    將單一 DataFrame 轉成 UTF-8 BOM CSV bytes。

    UTF-8 BOM 可讓 Windows Excel 正確辨識中文。
    """
    if dataframe is None:
        dataframe = pd.DataFrame()

    prepared_dataframe = (
        _prepare_csv_dataframe(
            dataframe,
            protect_formulas=protect_formulas,
        )
    )

    csv_text = prepared_dataframe.to_csv(
        index=False,
        encoding="utf-8-sig",
    )

    return csv_text.encode("utf-8-sig")


def _backup_json_default(value):
    """將少數 JSON 不支援的資料型別轉成可還原格式。"""
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

    return str(value)


def dataframe_to_backup_json_bytes(dataframe):
    """
    建立供正式還原使用的 JSON。

    與 CSV 不同，JSON 能區分 null、空字串、布林值與數字。
    """
    if dataframe is None:
        dataframe = pd.DataFrame()

    normalized_dataframe = (
        dataframe.astype(object)
        .where(pd.notna(dataframe), None)
    )

    records = normalized_dataframe.to_dict(
        orient="records"
    )

    return json.dumps(
        records,
        ensure_ascii=False,
        indent=2,
        default=_backup_json_default,
        allow_nan=False,
    ).encode("utf-8")


def dataframes_to_excel_bytes(dataframes):
    """
    將多個 DataFrame 寫入同一個 Excel 活頁簿。

    dataframes 格式：
    {
        "資產總覽": overview_dataframe,
        "帳戶餘額": accounts_dataframe,
    }
    """
    output = BytesIO()
    used_sheet_names = set()

    export_dataframes = dataframes or {}

    if not export_dataframes:
        export_dataframes = {
            "說明": pd.DataFrame(
                {
                    "訊息": [
                        "目前沒有可匯出的資料。"
                    ]
                }
            )
        }

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        for requested_name, dataframe in (
            export_dataframes.items()
        ):
            if dataframe is None:
                dataframe = pd.DataFrame()

            sheet_name = _safe_sheet_name(
                requested_name,
                used_sheet_names,
            )

            prepared_dataframe = (
                _prepare_excel_dataframe(
                    dataframe
                )
            )

            prepared_dataframe.to_excel(
                writer,
                sheet_name=sheet_name,
                index=False,
            )

            worksheet = writer.book[sheet_name]

            worksheet.freeze_panes = "A2"

            if worksheet.max_row >= 1:
                worksheet.auto_filter.ref = (
                    worksheet.dimensions
                )

            header_fill = PatternFill(
                fill_type="solid",
                fgColor="1F4E78",
            )

            header_font = Font(
                color="FFFFFF",
                bold=True,
            )

            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font

            for column_index, column_cells in enumerate(
                worksheet.columns,
                start=1,
            ):
                maximum_length = 0

                for cell in column_cells:
                    if cell.value is None:
                        continue

                    cell_length = len(
                        str(cell.value)
                    )

                    maximum_length = max(
                        maximum_length,
                        cell_length,
                    )

                adjusted_width = min(
                    max(maximum_length + 2, 10),
                    40,
                )

                column_letter = get_column_letter(
                    column_index
                )

                worksheet.column_dimensions[
                    column_letter
                ].width = adjusted_width

    output.seek(0)

    return output.getvalue()


def dataframes_to_zip_bytes(dataframes):
    """
    將多個原始 DataFrame 轉成 CSV 與 JSON 並包成 ZIP。

    CSV 方便人工查看；JSON 保留 null、空字串、布林值
    與數字型別，供未來安全還原。
    """
    output = BytesIO()
    used_filenames = set()

    export_time = datetime.now(
        timezone.utc
    ).isoformat()

    manifest = {
        "format": "personal_asset_dashboard_backup",
        "version": 3,
        "created_at_utc": export_time,
        "encoding": "UTF-8 with BOM",
        "restore_data_encoding": "UTF-8 JSON",
        "files": [],
    }

    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as zip_file:
        for requested_name, dataframe in (
            (dataframes or {}).items()
        ):
            if dataframe is None:
                dataframe = pd.DataFrame()

            filename = _safe_csv_filename(
                requested_name,
                used_filenames,
            )

            csv_bytes = dataframe_to_csv_bytes(
                dataframe,
                protect_formulas=False,
            )

            csv_sha256 = hashlib.sha256(
                csv_bytes
            ).hexdigest()

            data_filename = (
                filename[:-4]
                + ".json"
            )

            json_bytes = (
                dataframe_to_backup_json_bytes(
                    dataframe
                )
            )

            json_sha256 = hashlib.sha256(
                json_bytes
            ).hexdigest()

            zip_file.writestr(
                filename,
                csv_bytes,
            )

            zip_file.writestr(
                data_filename,
                json_bytes,
            )

            manifest["files"].append(
                {
                    "filename": filename,
                    "data_filename": data_filename,
                    "row_count": int(
                        len(dataframe)
                    ),
                    "columns": [
                        str(column)
                        for column in dataframe.columns
                    ],
                    "sha256": csv_sha256,
                    "data_sha256": json_sha256,
                }
            )

        zip_file.writestr(
            "manifest.json",
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8"),
        )

    output.seek(0)

    return output.getvalue()
