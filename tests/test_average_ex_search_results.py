import csv
import importlib.util
import sys
from pathlib import Path


def _load_script_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "average_ex_search_results.py"
    spec = importlib.util.spec_from_file_location("average_ex_search_results", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_final_output(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "Montage",
        "Current_Ch1_mA",
        "Current_Ch2_mA",
        "TImax_ROI",
        "TImean_ROI",
        "TImean_GM",
        "Focality",
        "Composite_Index",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_average_sources_strict_common_montages(tmp_path):
    mod = _load_script_module()

    first = tmp_path / "sub-001.csv"
    second = tmp_path / "sub-002.csv"
    shared = "E001_E002 <> E003_E004_I1-5.0mA_I2-5.0mA"
    only_first = "E005_E006 <> E007_E008_I1-5.0mA_I2-5.0mA"

    _write_final_output(
        first,
        [
            {
                "Montage": shared,
                "Current_Ch1_mA": "5",
                "Current_Ch2_mA": "5",
                "TImax_ROI": "1.0",
                "TImean_ROI": "2.0",
                "TImean_GM": "3.0",
                "Focality": "4.0",
                "Composite_Index": "8.0",
            },
            {
                "Montage": only_first,
                "Current_Ch1_mA": "5",
                "Current_Ch2_mA": "5",
                "TImax_ROI": "10.0",
                "TImean_ROI": "20.0",
                "TImean_GM": "30.0",
                "Focality": "40.0",
                "Composite_Index": "800.0",
            },
        ],
    )
    _write_final_output(
        second,
        [
            {
                "Montage": shared,
                "Current_Ch1_mA": "5",
                "Current_Ch2_mA": "5",
                "TImax_ROI": "3.0",
                "TImean_ROI": "4.0",
                "TImean_GM": "5.0",
                "Focality": "6.0",
                "Composite_Index": "24.0",
            }
        ],
    )

    rows, data, common_count, union_count = mod.average_sources(
        [
            mod.SourceCSV("001", first),
            mod.SourceCSV("002", second),
        ]
    )

    assert common_count == 1
    assert union_count == 2
    assert len(data["001"]) == 2
    assert len(rows) == 1
    assert rows[0]["Montage"] == shared
    assert rows[0]["Current_Ch1_mA_mean"] == 5.0
    assert rows[0]["TImean_ROI_mean"] == 3.0
    assert rows[0]["Focality_mean"] == 5.0
    assert rows[0]["Composite_Index_mean"] == 16.0
    assert rows[0]["E1_plus"] == "E001"
    assert rows[0]["E2_minus"] == "E004"

    mean_rows = mod.mean_final_output_rows(rows)
    assert list(mean_rows[0]) == list(mod.FINAL_OUTPUT_COLUMNS)
    assert mean_rows[0]["Current_Ch1_mA"] == 5.0
    assert mean_rows[0]["TImean_ROI"] == 3.0
    assert mean_rows[0]["Focality"] == 5.0

    subject_rows = mod.subject_final_output_rows(rows, data, "002")
    assert [row["Montage"] for row in subject_rows] == [shared]
    assert subject_rows[0]["TImean_ROI"] == 4.0


def test_write_average_workbook_has_mean_and_subject_tabs(tmp_path):
    mod = _load_script_module()

    first = tmp_path / "sub-001.csv"
    second = tmp_path / "sub-002.csv"
    montage = "E001_E002 <> E003_E004_I1-5.0mA_I2-5.0mA"
    _write_final_output(
        first,
        [
            {
                "Montage": montage,
                "Current_Ch1_mA": "5",
                "Current_Ch2_mA": "5",
                "TImax_ROI": "1.0",
                "TImean_ROI": "2.0",
                "TImean_GM": "3.0",
                "Focality": "4.0",
                "Composite_Index": "8.0",
            }
        ],
    )
    _write_final_output(
        second,
        [
            {
                "Montage": montage,
                "Current_Ch1_mA": "5",
                "Current_Ch2_mA": "5",
                "TImax_ROI": "3.0",
                "TImean_ROI": "4.0",
                "TImean_GM": "5.0",
                "Focality": "6.0",
                "Composite_Index": "24.0",
            }
        ],
    )
    sources = [mod.SourceCSV("001", first), mod.SourceCSV("002", second)]
    rows, data, _, _ = mod.average_sources(sources)
    workbook = tmp_path / "average.xlsx"

    mod.write_average_workbook(workbook, sources=sources, averaged=rows, data=data)

    import zipfile

    with zipfile.ZipFile(workbook) as xlsx:
        assert "xl/workbook.xml" in xlsx.namelist()
        workbook_xml = xlsx.read("xl/workbook.xml").decode()
        assert 'name="Mean"' in workbook_xml
        assert 'name="001"' in workbook_xml
        assert 'name="002"' in workbook_xml
        assert 'name="Sources"' in workbook_xml
