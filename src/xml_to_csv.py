#!/usr/bin/env python3
"""
Script to collate XML lab results into a CSV file.

This script parses XML files from downloads/xml_results/*.xml and creates a CSV
with columns: barcode, group, date_time, external_item_id, parameter_label,
parameter_value, parameter_unit, parameter_low, parameter_high, remark_all
"""

import csv
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Tuple, Optional


# Unit conversion factors (conventional ↔ SI).
#
# Lipids — cholesterol (total/HDL/LDL) and triglycerides:
#   AHRQ Comparative Effectiveness Review No. 24, Appendix A "Lipid Conversion
#   Factors". Rugge B, Balshem H, Sehgal R, et al. Screening and Treatment of
#   Subclinical Hypothyroidism or Hyperthyroidism. Rockville (MD): Agency for
#   Healthcare Research and Quality (US); 2011 Oct.
#   https://www.ncbi.nlm.nih.gov/books/NBK83505/
#   Cross-checked against NCEP ATP III final report (AHA Circulation 2002),
#   which uses the rounded triglyceride factor 88.6.
#   https://www.ahajournals.org/doi/10.1161/circ.106.25.3227
#
# Glucose: derived from molecular weight 180.156 g/mol (C₆H₁₂O₆);
#   factor = MW / 10 = 18.0156.
#
# Creatinine: derived from molecular weight 113.12 g/mol (C₄H₇N₃O);
#   factor = 10000 / MW ≈ 88.4. Matches the widely-cited clinical value
#   (e.g. R `physiology` package `creatinine_mgdl_to_uM`).
#
# Bilirubin: derived from molecular weight 584.67 g/mol (C₃₃H₃₆N₄O₆);
#   factor = 10000 / MW ≈ 17.104. Matches LABOKLIN SI calculator
#   (https://laboklin.com/en/specialist-information/si-calculator/).
BILIRUBIN_MGDL_TO_UMOLL = 17.104
CHOLESTEROL_MMOLL_TO_MGDL = 38.67
CREATININE_MGDL_TO_UMOLL = 88.4
GLUCOSE_MMOLL_TO_MGDL = 18.0156
TRIGLYCERIDES_MMOLL_TO_MGDL = 88.57


def convert_units(value: str, unit: str, label: str) -> Tuple[str, str, str, str]:
    """
    Convert parameter values to standardized units if needed.
    - Bilirubin: mg/dl → µmol/l (× BILIRUBIN_MGDL_TO_UMOLL)
    - Cholesterol: mmol/l → mg/dl (× CHOLESTEROL_MMOLL_TO_MGDL)
    - Creatinine: mg/dl → µmol/l (× CREATININE_MGDL_TO_UMOLL)
    - Glucose: mmol/l → mg/dl (× GLUCOSE_MMOLL_TO_MGDL)
    - Triglycerides: mmol/l → mg/dl (× TRIGLYCERIDES_MMOLL_TO_MGDL)

    Args:
        value: The parameter value
        unit: The parameter unit
        label: The parameter label

    Returns:
        Tuple of (converted_value, converted_unit, original_value, original_unit)
        If no conversion needed, returns (value, unit, value, unit)
    """
    # Check if this is a bilirubin parameter
    if re.search(r"bilirubina", label, re.IGNORECASE):
        # Check if unit is mg/dl and needs conversion
        if unit and unit.lower() == "mg/dl":
            try:
                # Replace comma with dot for float conversion
                numeric_value = float(value.replace(",", "."))
                # Convert mg/dl to µmol/l
                converted_value = numeric_value * BILIRUBIN_MGDL_TO_UMOLL
                # Format with 2 decimal places and use comma as decimal separator
                converted_value_str = f"{converted_value:.2f}".replace(".", ",")
                return converted_value_str, "µmol/l", value, unit
            except (ValueError, AttributeError):
                # If conversion fails, return original values
                return value, unit, value, unit

    # Check if this is a cholesterol parameter (total, HDL, LDL, or non-HDL)
    if re.search(r"cholesterol (całkowity|hdl|ldl|nie-hdl)", label, re.IGNORECASE):
        # Check if unit is mmol/l and needs conversion
        if unit and unit.lower() == "mmol/l":
            try:
                # Replace comma with dot for float conversion
                numeric_value = float(value.replace(",", "."))
                # Convert mmol/l to mg/dl
                converted_value = numeric_value * CHOLESTEROL_MMOLL_TO_MGDL
                # Format with 2 decimal places and use comma as decimal separator
                converted_value_str = f"{converted_value:.2f}".replace(".", ",")
                return converted_value_str, "mg/dl", value, unit
            except (ValueError, AttributeError):
                # If conversion fails, return original values
                return value, unit, value, unit

    # Check if this is a creatinine parameter
    if re.search(r"kreatynina", label, re.IGNORECASE):
        # Check if unit is mg/dl and needs conversion
        if unit and unit.lower() == "mg/dl":
            try:
                # Replace comma with dot for float conversion
                numeric_value = float(value.replace(",", "."))
                # Convert mg/dl to µmol/l
                converted_value = numeric_value * CREATININE_MGDL_TO_UMOLL
                # Format with 2 decimal places and use comma as decimal separator
                converted_value_str = f"{converted_value:.2f}".replace(".", ",")
                return converted_value_str, "µmol/l", value, unit
            except (ValueError, AttributeError):
                # If conversion fails, return original values
                return value, unit, value, unit

    # Check if this is a glucose parameter
    if re.search(r"glukoza", label, re.IGNORECASE):
        # Check if unit is mmol/l and needs conversion
        if unit and unit.lower() == "mmol/l":
            try:
                # Replace comma with dot for float conversion
                numeric_value = float(value.replace(",", "."))
                # Convert mmol/l to mg/dl
                converted_value = numeric_value * GLUCOSE_MMOLL_TO_MGDL
                # Format with 2 decimal places and use comma as decimal separator
                converted_value_str = f"{converted_value:.2f}".replace(".", ",")
                return converted_value_str, "mg/dl", value, unit
            except (ValueError, AttributeError):
                # If conversion fails, return original values
                return value, unit, value, unit

    # Check if this is a triglycerides parameter
    if re.search(r"triglicerydy", label, re.IGNORECASE):
        # Check if unit is mmol/l and needs conversion
        if unit and unit.lower() == "mmol/l":
            try:
                # Replace comma with dot for float conversion
                numeric_value = float(value.replace(",", "."))
                # Convert mmol/l to mg/dl
                converted_value = numeric_value * TRIGLYCERIDES_MMOLL_TO_MGDL
                # Format with 2 decimal places and use comma as decimal separator
                converted_value_str = f"{converted_value:.2f}".replace(".", ",")
                return converted_value_str, "mg/dl", value, unit
            except (ValueError, AttributeError):
                # If conversion fails, return original values
                return value, unit, value, unit

    # No conversion needed
    return value, unit, value, unit


def parse_xml_file(xml_path: Path) -> List[Dict]:
    """
    Parse a single XML file and extract lab result data.

    Args:
        xml_path: Path to the XML file

    Returns:
        List of dictionaries, each containing data for one row in the CSV
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Extract header information
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

    # Process all groups and their tests
    rows = []
    for group in root.findall("group"):
        group_name_elem = group.find("name")
        group_name = group_name_elem.text if group_name_elem is not None else ""

        # Process all tests in the group
        for test in group.findall("test"):
            # Get external_item_id
            external_item_id_elem = test.find("external_item_id")
            external_item_id = ""
            if external_item_id_elem is not None:
                id_elem = external_item_id_elem.find("id")
                external_item_id = id_elem.text if id_elem is not None else ""

            # Process all parameters in the test
            for parameter in test.findall("parameter"):
                label_elem = parameter.find("label")
                value_elem = parameter.find("value")
                unit_elem = parameter.find("unit")
                low_elem = parameter.find("low")
                high_elem = parameter.find("high")
                remark_all_elem = parameter.find("remark_all")

                # Extract raw values
                param_label = label_elem.text if label_elem is not None else ""
                param_value = value_elem.text if value_elem is not None else ""
                param_unit = unit_elem.text if unit_elem is not None else ""
                param_low = low_elem.text if low_elem is not None else ""
                param_high = high_elem.text if high_elem is not None else ""

                # Convert values if needed (bilirubin, cholesterol, etc.)
                (
                    converted_value,
                    converted_unit,
                    original_value,
                    original_unit,
                ) = convert_units(param_value, param_unit, param_label)

                # Also convert reference ranges if unit was converted
                if converted_unit != original_unit:
                    # Determine conversion factor (see module-level constants for citations)
                    conversion_factor = BILIRUBIN_MGDL_TO_UMOLL
                    if re.search(
                        r"cholesterol (całkowity|hdl|ldl|nie-hdl)",
                        param_label,
                        re.IGNORECASE,
                    ):
                        conversion_factor = CHOLESTEROL_MMOLL_TO_MGDL
                    elif re.search(r"kreatynina", param_label, re.IGNORECASE):
                        conversion_factor = CREATININE_MGDL_TO_UMOLL
                    elif re.search(r"glukoza", param_label, re.IGNORECASE):
                        conversion_factor = GLUCOSE_MMOLL_TO_MGDL
                    elif re.search(r"triglicerydy", param_label, re.IGNORECASE):
                        conversion_factor = TRIGLYCERIDES_MMOLL_TO_MGDL

                    # Convert low range
                    if param_low:
                        try:
                            low_numeric = float(param_low.replace(",", "."))
                            converted_low = low_numeric * conversion_factor
                            param_low = f"{converted_low:.2f}".replace(".", ",")
                        except (ValueError, AttributeError):
                            pass

                    # Convert high range
                    if param_high:
                        try:
                            high_numeric = float(param_high.replace(",", "."))
                            converted_high = high_numeric * conversion_factor
                            param_high = f"{converted_high:.2f}".replace(".", ",")
                        except (ValueError, AttributeError):
                            pass

                row = {
                    "barcode": barcode,
                    "group": group_name,
                    "date_time": date_time,
                    "external_item_id": external_item_id,
                    "parameter_label": param_label,
                    "parameter_value": converted_value,
                    "parameter_unit": converted_unit,
                    "parameter_low": param_low,
                    "parameter_high": param_high,
                    "remark_all": (
                        remark_all_elem.text.strip()
                        if remark_all_elem is not None and remark_all_elem.text
                        else ""
                    ),
                    "original_value": original_value,
                    "original_unit": original_unit,
                }
                rows.append(row)

    return rows


def main():
    """Main function to process all XML files and create CSV output."""
    # Define paths
    xml_dir = Path("downloads/xml_results")
    output_csv = Path("lab_results.csv")

    # Check if directory exists
    if not xml_dir.exists():
        print(f"Error: Directory {xml_dir} does not exist")
        return

    # Get all XML files
    xml_files = sorted(xml_dir.glob("*.xml"))

    if not xml_files:
        print(f"No XML files found in {xml_dir}")
        return

    print(f"Found {len(xml_files)} XML files")

    # Collect all rows from all XML files
    all_rows = []
    for xml_file in xml_files:
        print(f"Processing: {xml_file.name}")
        try:
            rows = parse_xml_file(xml_file)
            all_rows.extend(rows)
            print(f"  - Extracted {len(rows)} parameter(s)")
        except Exception as e:
            print(f"  - Error processing {xml_file.name}: {e}")

    # Write to CSV
    if all_rows:
        fieldnames = [
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

        with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_rows)

        print(f"\nSuccessfully created {output_csv}")
        print(f"Total rows written: {len(all_rows)}")
    else:
        print("No data extracted from XML files")


if __name__ == "__main__":
    main()
