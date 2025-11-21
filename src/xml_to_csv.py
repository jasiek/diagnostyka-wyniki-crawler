#!/usr/bin/env python3
"""
Script to collate XML lab results into a CSV file.

This script parses XML files from downloads/xml_results/*.xml and creates a CSV
with columns: barcode, group, date_time, external_item_id, parameter_label,
parameter_value, parameter_unit, parameter_low, parameter_high, remark_all
"""

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict


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

                row = {
                    "barcode": barcode,
                    "group": group_name,
                    "date_time": date_time,
                    "external_item_id": external_item_id,
                    "parameter_label": (
                        label_elem.text if label_elem is not None else ""
                    ),
                    "parameter_value": (
                        value_elem.text if value_elem is not None else ""
                    ),
                    "parameter_unit": unit_elem.text if unit_elem is not None else "",
                    "parameter_low": low_elem.text if low_elem is not None else "",
                    "parameter_high": high_elem.text if high_elem is not None else "",
                    "remark_all": (
                        remark_all_elem.text.strip()
                        if remark_all_elem is not None and remark_all_elem.text
                        else ""
                    ),
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
