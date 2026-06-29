from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.models.calibration import CalibrationScenarioProfile, ScadaTemperatureSample
from app.services.calibration_import_service import CalibrationImportService
from app.services.calibration_service import CalibrationService


def _xlsx_bytes(sheets: dict[str, list[list[object]]]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>"
            + "".join(
                f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>'
                for index, name in enumerate(sheets, 1)
            )
            + "</sheets></workbook>",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
                for index in range(1, len(sheets) + 1)
            )
            + "</Relationships>",
        )
        for sheet_index, rows in enumerate(sheets.values(), 1):
            xml_rows = []
            for row_index, row in enumerate(rows, 1):
                cells = []
                for column_index, value in enumerate(row, 1):
                    column = chr(64 + column_index)
                    if isinstance(value, str):
                        cells.append(
                            f'<c r="{column}{row_index}" t="inlineStr"><is><t>{value}</t></is></c>'
                        )
                    else:
                        cells.append(f'<c r="{column}{row_index}"><v>{value}</v></c>')
                xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
            workbook.writestr(
                f"xl/worksheets/sheet{sheet_index}.xml",
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>',
            )
    return output.getvalue()


def _build_archive(path: Path) -> None:
    scada_headers = [
        "Pen Index",
        "Name",
        "Start Time",
        "End Time",
        "Min Time",
        "Min Value",
        "Max Time",
        "Max Value",
        "Avg Value",
        "Quality",
    ]
    good_row = [1, "MHO132 TRINIDAD AVERAGE AMBIENT TEMP", 46200.5, 46200.54, 46200.5, 28, 46200.54, 30, 29, "Good"]
    inactive_row = [1, "MHO132 TRINIDAD AVERAGE AMBIENT TEMP", 46200.54, 46200.58, 46200.54, 0, 46200.58, 0, 0, "Inactive"]
    load_sheets = {}
    for label, base in (
        ("Hot day 20260512", 1100),
        ("Typical day 20260602", 950),
        ("Rainy Day 20260623", 850),
    ):
        load_sheets[label] = [["Hour", "Demand (MW)", "Spin (MW)"]] + [
            [hour, base + hour, 150] for hour in range(1, 25)
        ]

    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "20260512 Sunny day.xlsx",
            _xlsx_bytes({"trending_exportdata": [scada_headers, good_row, inactive_row]}),
        )
        archive.writestr(
            "20260602 typical day.xlsx",
            _xlsx_bytes({"trending_exportdata": [scada_headers, good_row, inactive_row]}),
        )
        archive.writestr(
            "20260623 rain day.xlsx",
            _xlsx_bytes({"20260623 rainy day": [scada_headers, good_row, inactive_row]}),
        )
        archive.writestr("Load forecasting data.xlsx", _xlsx_bytes(load_sheets))


def test_calibration_import_and_weighted_scenario_selection(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    archive = tmp_path / "calibration.zip"
    _build_archive(archive)

    counts = CalibrationImportService(session_factory=session_factory).import_archive(archive)
    with session_factory() as session:
        assert session.scalar(select(func.count(CalibrationScenarioProfile.id))) == 72
        assert session.scalar(select(func.count(ScadaTemperatureSample.id))) == 6

    snapshot = CalibrationService(session_factory=session_factory).get_snapshot(
        {
            "temperature_c": 29,
            "humidity_percent": 95,
            "rainfall_mm_hr": 8,
            "cloud_cover_percent": 100,
            "weather_condition": "Heavy rain",
        }
    )
    hot_snapshot = CalibrationService(session_factory=session_factory).get_snapshot(
        {
            "temperature_c": 34,
            "humidity_percent": 60,
            "rainfall_mm_hr": 0,
            "cloud_cover_percent": 15,
            "weather_condition": "Hot and sunny",
        }
    )
    typical_snapshot = CalibrationService(session_factory=session_factory).get_snapshot(
        {
            "temperature_c": 30,
            "humidity_percent": 72,
            "rainfall_mm_hr": 0.2,
            "cloud_cover_percent": 45,
            "weather_condition": "Partly cloudy",
        }
    )

    assert counts["workbooks"] == 4
    assert snapshot is not None
    assert snapshot.selected_scenario_key == "rainy"
    assert snapshot.selection_confidence is not None
    assert snapshot.scenario_scores["rainy"] > snapshot.scenario_scores["hot"]
    assert hot_snapshot is not None
    assert hot_snapshot.selected_scenario_key == "hot"
    assert typical_snapshot is not None
    assert typical_snapshot.selected_scenario_key == "typical"
    assert all(
        point.temperature_c > 20
        for scenario in snapshot.scenarios
        for point in scenario.scada_temperature_trace
        if point.temperature_c is not None
    )
