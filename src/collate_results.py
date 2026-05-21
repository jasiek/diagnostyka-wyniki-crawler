#!/usr/bin/env python3
"""Collate XML lab results into CSV or JSON.

Reads downloads/xml_results/*.xml and emits one record per parameter. Selected
parameters are converted to a clinically common alternative unit; the original
measurement is always preserved.

Unit conversion factors (conventional ↔ SI):

Lipids — cholesterol (total/HDL/LDL) and triglycerides:
  AHRQ Comparative Effectiveness Review No. 24, Appendix A "Lipid Conversion
  Factors". Rugge B, Balshem H, Sehgal R, et al. Screening and Treatment of
  Subclinical Hypothyroidism or Hyperthyroidism. Rockville (MD): Agency for
  Healthcare Research and Quality (US); 2011 Oct.
  https://www.ncbi.nlm.nih.gov/books/NBK83505/
  Cross-checked against NCEP ATP III final report (AHA Circulation 2002),
  which uses the rounded triglyceride factor 88.6.
  https://www.ahajournals.org/doi/10.1161/circ.106.25.3227

Glucose: derived from molecular weight 180.156 g/mol (C₆H₁₂O₆);
  factor = MW / 10 = 18.0156.

Creatinine: derived from molecular weight 113.12 g/mol (C₄H₇N₃O);
  factor = 10000 / MW ≈ 88.4. Matches the widely-cited clinical value
  (e.g. R `physiology` package `creatinine_mgdl_to_uM`).

Bilirubin: derived from molecular weight 584.67 g/mol (C₃₃H₃₆N₄O₆);
  factor = 10000 / MW ≈ 17.104. Matches LABOKLIN SI calculator
  (https://laboklin.com/en/specialist-information/si-calculator/).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


_DATE_TIME_FORMATS = ("%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S")


def normalize_date_time(raw: str) -> str:
    """Best-effort ISO 8601 normalization; falls back to raw on unknown format."""
    if not raw:
        return raw
    for fmt in _DATE_TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt).isoformat()
        except ValueError:
            continue
    return raw


@dataclass(frozen=True)
class ConversionRule:
    label_pattern: str
    source_unit: str
    target_unit: str
    factor: float


CONVERSIONS: tuple[ConversionRule, ...] = (
    ConversionRule(r"bilirubina", "mg/dl", "µmol/l", 17.104),
    ConversionRule(
        r"cholesterol (całkowity|hdl|ldl|nie-hdl)", "mmol/l", "mg/dl", 38.67
    ),
    ConversionRule(r"kreatynina", "mg/dl", "µmol/l", 88.4),
    ConversionRule(r"glukoza", "mmol/l", "mg/dl", 18.0156),
    ConversionRule(r"triglicerydy", "mmol/l", "mg/dl", 88.57),
)


@dataclass
class UnitMeasurement:
    """A measurement in one specific unit. `*_raw` preserves the XML string."""

    value_raw: str
    value_numeric: Optional[float]
    unit: str
    low_raw: str
    low_numeric: Optional[float]
    high_raw: str
    high_numeric: Optional[float]


@dataclass
class Alternative:
    value: float
    unit: str
    low: Optional[float]
    high: Optional[float]
    converted_from: str
    conversion_factor: float


@dataclass
class Measurement:
    barcode: str
    group: str
    date_time: str
    external_item_id: str
    parameter_label: str
    remark_all: str
    original: UnitMeasurement
    alternatives: list[Alternative] = field(default_factory=list)


def _parse_decimal(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _format_decimal(value: float) -> str:
    """Match historical CSV formatting: 2 decimals, comma separator."""
    return f"{value:.2f}".replace(".", ",")


def find_conversion(label: str, unit: str) -> Optional[ConversionRule]:
    if not unit:
        return None
    unit_lc = unit.lower()
    for rule in CONVERSIONS:
        if rule.source_unit == unit_lc and re.search(
            rule.label_pattern, label, re.IGNORECASE
        ):
            return rule
    return None


def build_measurement(
    *,
    barcode: str,
    group: str,
    date_time: str,
    external_item_id: str,
    parameter_label: str,
    remark_all: str,
    raw_value: str,
    raw_unit: str,
    raw_low: str,
    raw_high: str,
) -> Measurement:
    original = UnitMeasurement(
        value_raw=raw_value,
        value_numeric=_parse_decimal(raw_value),
        unit=raw_unit,
        low_raw=raw_low,
        low_numeric=_parse_decimal(raw_low),
        high_raw=raw_high,
        high_numeric=_parse_decimal(raw_high),
    )

    alternatives: list[Alternative] = []
    rule = find_conversion(parameter_label, raw_unit)
    if rule is not None and original.value_numeric is not None:
        alternatives.append(
            Alternative(
                value=original.value_numeric * rule.factor,
                unit=rule.target_unit,
                low=(
                    original.low_numeric * rule.factor
                    if original.low_numeric is not None
                    else None
                ),
                high=(
                    original.high_numeric * rule.factor
                    if original.high_numeric is not None
                    else None
                ),
                converted_from=raw_unit,
                conversion_factor=rule.factor,
            )
        )

    return Measurement(
        barcode=barcode,
        group=group,
        date_time=date_time,
        external_item_id=external_item_id,
        parameter_label=parameter_label,
        remark_all=remark_all,
        original=original,
        alternatives=alternatives,
    )


def parse_xml_file(xml_path: Path) -> list[Measurement]:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    header = root.find("header")
    if header is None:
        return []
    order = header.find("order")
    if order is None:
        return []

    barcode_elem = order.find("barcode")
    barcode = barcode_elem.text if barcode_elem is not None else ""
    created_elem = order.find("created")
    date_time = created_elem.text if created_elem is not None else ""

    measurements: list[Measurement] = []
    for group in root.findall("group"):
        group_name_elem = group.find("name")
        group_name = group_name_elem.text if group_name_elem is not None else ""

        for test in group.findall("test"):
            external_item_id = ""
            ext_elem = test.find("external_item_id")
            if ext_elem is not None:
                id_elem = ext_elem.find("id")
                external_item_id = id_elem.text if id_elem is not None else ""

            for parameter in test.findall("parameter"):
                def _text(name: str) -> str:
                    elem = parameter.find(name)
                    return elem.text if elem is not None and elem.text is not None else ""

                remark_elem = parameter.find("remark_all")
                remark_all = (
                    remark_elem.text.strip()
                    if remark_elem is not None and remark_elem.text
                    else ""
                )

                measurements.append(
                    build_measurement(
                        barcode=barcode or "",
                        group=group_name or "",
                        date_time=date_time or "",
                        external_item_id=external_item_id or "",
                        parameter_label=_text("label"),
                        remark_all=remark_all,
                        raw_value=_text("value"),
                        raw_unit=_text("unit"),
                        raw_low=_text("low"),
                        raw_high=_text("high"),
                    )
                )

    return measurements


CSV_FIELDNAMES = [
    "barcode",
    "group",
    "date_time",
    "external_item_id",
    "parameter_label",
    "parameter_value",
    "parameter_unit",
    "parameter_low",
    "parameter_high",
    "remark_all",
    "original_value",
    "original_unit",
]


def measurement_to_csv_row(m: Measurement) -> dict:
    """Render to the legacy CSV shape.

    If an alternative exists, its formatted value/unit/range become
    parameter_*, while original_* always carries the raw XML strings. This
    matches the pre-refactor output byte-for-byte.
    """
    if m.alternatives:
        alt = m.alternatives[0]
        parameter_value = _format_decimal(alt.value)
        parameter_unit = alt.unit
        parameter_low = _format_decimal(alt.low) if alt.low is not None else m.original.low_raw
        parameter_high = (
            _format_decimal(alt.high) if alt.high is not None else m.original.high_raw
        )
    else:
        parameter_value = m.original.value_raw
        parameter_unit = m.original.unit
        parameter_low = m.original.low_raw
        parameter_high = m.original.high_raw

    return {
        "barcode": m.barcode,
        "group": m.group,
        "date_time": m.date_time,
        "external_item_id": m.external_item_id,
        "parameter_label": m.parameter_label,
        "parameter_value": parameter_value,
        "parameter_unit": parameter_unit,
        "parameter_low": parameter_low,
        "parameter_high": parameter_high,
        "remark_all": m.remark_all,
        "original_value": m.original.value_raw,
        "original_unit": m.original.unit,
    }


def measurement_to_json_obj(m: Measurement) -> dict:
    return {
        "barcode": m.barcode,
        "group": m.group,
        "date_time": normalize_date_time(m.date_time),
        "external_item_id": m.external_item_id,
        "parameter_label": m.parameter_label,
        "remark_all": m.remark_all,
        "measurement": {
            "original": {
                "value": m.original.value_numeric,
                "unit": m.original.unit,
                "reference_low": m.original.low_numeric,
                "reference_high": m.original.high_numeric,
            },
            "alternatives": [
                {
                    "value": a.value,
                    "unit": a.unit,
                    "reference_low": a.low,
                    "reference_high": a.high,
                    "converted_from": a.converted_from,
                    "conversion_factor": a.conversion_factor,
                }
                for a in m.alternatives
            ],
        },
    }


def write_csv(measurements: list[Measurement], output_path: Path) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(measurement_to_csv_row(m) for m in measurements)


def write_json(measurements: list[Measurement], output_path: Path) -> None:
    payload = [measurement_to_json_obj(m) for m in measurements]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def default_output_path(fmt: str) -> Path:
    return Path("lab_results.json" if fmt == "json" else "lab_results.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--format", choices=("csv", "json"), default="csv", help="Output format"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file (defaults to lab_results.{csv,json})",
    )
    parser.add_argument(
        "--xml-dir",
        type=Path,
        default=Path("downloads/xml_results"),
        help="Directory containing XML files",
    )
    args = parser.parse_args()

    output_path = args.output or default_output_path(args.format)

    if not args.xml_dir.exists():
        print(f"Error: Directory {args.xml_dir} does not exist")
        return

    xml_files = sorted(args.xml_dir.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {args.xml_dir}")
        return

    print(f"Found {len(xml_files)} XML files")

    all_measurements: list[Measurement] = []
    for xml_file in xml_files:
        print(f"Processing: {xml_file.name}")
        try:
            measurements = parse_xml_file(xml_file)
            all_measurements.extend(measurements)
            print(f"  - Extracted {len(measurements)} parameter(s)")
        except Exception as e:
            print(f"  - Error processing {xml_file.name}: {e}")

    if not all_measurements:
        print("No data extracted from XML files")
        return

    if args.format == "csv":
        write_csv(all_measurements, output_path)
    else:
        write_json(all_measurements, output_path)

    print(f"\nSuccessfully created {output_path}")
    print(f"Total records written: {len(all_measurements)}")


if __name__ == "__main__":
    main()
