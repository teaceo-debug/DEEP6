#!/usr/bin/env python3
"""Workspace XML mutation: backup -> find chart -> inject indicator -> validate.

Fallback chart installation method when UIA-based install_indicator.ps1 fails.
Reads NT8 workspace XML, finds a chart tab by instrument/title, injects an
indicator element matching the discovered schema, validates, and saves.

Schema discovered from actual NT8 workspace files:
  _Workspaces.xml: <NinjaTrader> -> <ActiveWorkspace>Name</ActiveWorkspace>
  {Name}.xml:      <NinjaTrader> -> <NTWindows> -> <Chart-{GUID}> ->
                   <TabControl> -> <Tab-{GUID}> -> <Indicators> ->
                   <Indicator BarsIndex="0" Instrument="..." Name="..." Panel="...">
"""

import sys
import os
import json
import argparse
import shutil
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

script_dir = os.path.dirname(os.path.abspath(__file__))
skill_dir = os.path.dirname(script_dir)
sys.path.insert(0, skill_dir)

# Default NT8 workspaces directory
DEFAULT_WORKSPACES_DIR = os.path.join(
    os.environ.get("USERPROFILE", ""),
    "Documents", "NinjaTrader 8", "workspaces"
)


def find_active_workspace(workspaces_dir: str) -> tuple:
    """Find the active workspace name and its XML file path.

    Reads _Workspaces.xml and extracts the <ActiveWorkspace> element text.
    Returns (workspace_name, workspace_path) or (None, None) on failure.
    """
    meta_path = os.path.join(workspaces_dir, "_Workspaces.xml")
    if not os.path.exists(meta_path):
        return None, None

    tree = ET.parse(meta_path)
    root = tree.getroot()

    # Schema: <NinjaTrader> -> <ActiveWorkspace>Main</ActiveWorkspace>
    active_elem = root.find("ActiveWorkspace")
    if active_elem is not None and active_elem.text:
        active_name = active_elem.text.strip()
    else:
        # Fallback: check OpenWorkspaces
        open_ws = root.find(".//OpenWorkspace")
        if open_ws is not None and open_ws.text:
            active_name = open_ws.text.strip()
        else:
            active_name = "Main"

    workspace_path = os.path.join(workspaces_dir, f"{active_name}.xml")
    return active_name, workspace_path


def backup_workspace(workspace_path: str) -> str:
    """Create timestamped backup (G3 guardrail — mandatory before any write)."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = f"{workspace_path}.backup-{timestamp}"
    shutil.copy2(workspace_path, backup_path)
    return backup_path


def find_chart_tabs(root: ET.Element, chart_title: str) -> list:
    """Find chart tab elements matching the title/instrument.

    Searches the discovered NT8 schema:
      <NTWindows> -> <Chart-{GUID}> -> <TabControl> -> <Tab-{GUID}>
    Matches against <Instrument> and <Label> in <BarsProperties> within <DataSeries>.

    Returns list of (tab_element, instrument_full_name, chart_guid) tuples.
    """
    matches = []
    title_lower = chart_title.lower()

    nt_windows = root.find("NTWindows")
    if nt_windows is None:
        return matches

    for chart_elem in nt_windows:
        tag = chart_elem.tag
        if not tag.startswith("Chart-"):
            continue

        chart_guid = tag.replace("Chart-", "")

        # Check if chart has a valid Class (skip empty/ghost charts)
        class_elem = chart_elem.find("Class")
        if class_elem is None or not class_elem.text:
            continue

        tab_control = chart_elem.find("TabControl")
        if tab_control is None:
            continue

        for tab_elem in tab_control:
            tab_tag = tab_elem.tag
            if not tab_tag.startswith("Tab-"):
                continue

            # Search DataSeries -> BarsProperties for instrument/label match
            instrument_name = _extract_instrument(tab_elem)
            if instrument_name and title_lower in instrument_name.lower():
                matches.append((tab_elem, instrument_name, chart_guid))

    return matches


def _extract_instrument(tab_elem: ET.Element) -> str:
    """Extract instrument name from a chart tab's DataSeries.

    Schema: <DataSeries> -> <BarsProperties> -> <BarsProperties> ->
            <Instrument> and <Label>
    """
    data_series = tab_elem.find("DataSeries")
    if data_series is None:
        return None

    # BarsProperties has nested structure: outer <BarsProperties> -> inner <BarsProperties>
    outer_bp = data_series.find("BarsProperties")
    if outer_bp is None:
        return None

    # The inner BarsProperties contains the Instrument element
    # It's namespaced but ET handles it if we search broadly
    for bp in outer_bp.iter("BarsProperties"):
        instrument = bp.find("Instrument")
        if instrument is not None and instrument.text:
            return instrument.text.strip()
        label = bp.find("Label")
        if label is not None and label.text:
            return label.text.strip()

    return None


def _extract_instrument_full(tab_elem: ET.Element) -> str:
    """Extract the full instrument name with exchange (e.g., 'MNQ 06-26 Globex').

    Looks at existing indicators' Instrument attribute as the source of truth,
    since chart BarsProperties only has the short name.
    """
    indicators = tab_elem.find("Indicators")
    if indicators is not None:
        for ind in indicators.findall("Indicator"):
            inst = ind.get("Instrument")
            if inst:
                return inst

    # Fallback: append common exchange suffixes based on instrument
    short_name = _extract_instrument(tab_elem)
    if short_name:
        # NQ/MNQ/ES/MES futures default to Globex
        for prefix in ("NQ", "MNQ", "ES", "MES", "YM", "RTY"):
            if short_name.upper().startswith(prefix):
                return f"{short_name} Globex"
    return short_name


def _get_next_indicator_id(tab_elem: ET.Element) -> int:
    """Find the max IndicatorId in existing indicators and return next value."""
    max_id = 0
    indicators = tab_elem.find("Indicators")
    if indicators is not None:
        for ind in indicators:
            for child in ind:
                id_elem = child.find("IndicatorId")
                if id_elem is not None and id_elem.text:
                    try:
                        val = int(id_elem.text)
                        if val > max_id:
                            max_id = val
                    except ValueError:
                        pass
    return max_id + 1


def _get_next_zorder(tab_elem: ET.Element) -> int:
    """Find the max ZOrder in existing indicators and return next value."""
    max_z = 10000
    indicators = tab_elem.find("Indicators")
    if indicators is not None:
        for ind in indicators:
            for child in ind:
                z_elem = child.find("ZOrder")
                if z_elem is not None and z_elem.text:
                    try:
                        val = int(z_elem.text)
                        if val > max_z:
                            max_z = val
                    except ValueError:
                        pass
    return max_z + 1


def check_already_installed(tab_elem: ET.Element, full_name: str) -> bool:
    """Check if indicator is already installed on this chart tab."""
    indicators = tab_elem.find("Indicators")
    if indicators is None:
        return False
    for ind in indicators.findall("Indicator"):
        if ind.get("Name") == full_name:
            return True
    return False


def inject_indicator(
    tab_elem: ET.Element,
    class_name: str,
    namespace: str,
    panel: str
) -> ET.Element:
    """Inject an indicator element into the chart tab's <Indicators> section.

    Follows the discovered NT8 workspace XML schema:
      <Indicator BarsIndex="0" Instrument="..." Name="..." Panel="...">
        <{ClassName} xmlns:xsd="..." xmlns:xsi="...">
          ...base properties...
        </{ClassName}>
        <Input><PriceType>Close</PriceType></Input>
      </Indicator>

    Args:
        tab_elem: The chart tab XML element
        class_name: Indicator class name (e.g., "DEEP6Signal")
        namespace: Full namespace (e.g., "NinjaTrader.NinjaScript.Indicators.DEEP6")
        panel: "price" maps to Panel="-1" (overlay), "0" for price panel, or sub-panel number

    Returns:
        The newly created Indicator element
    """
    indicators = tab_elem.find("Indicators")
    if indicators is None:
        indicators = ET.SubElement(tab_elem, "Indicators")

    # Resolve panel value
    if panel == "price":
        panel_value = "-1"
    elif panel == "overlay":
        panel_value = "-1"
    elif panel == "sub":
        panel_value = "1"
    else:
        panel_value = str(panel)

    # Full indicator name (namespace path — NOT assembly-qualified per real schema)
    full_name = f"{namespace}.{class_name}"

    # Get instrument from tab
    instrument_full = _extract_instrument_full(tab_elem)
    instrument_full = instrument_full or ""

    # Create Indicator element with discovered attribute schema
    indicator_elem = ET.SubElement(indicators, "Indicator")
    indicator_elem.set("BarsIndex", "0")
    indicator_elem.set("Instrument", instrument_full)
    indicator_elem.set("Name", full_name)
    indicator_elem.set("Panel", panel_value)

    # Create inner class element with base NinjaScript properties
    ns_attrs = {
        "xmlns:xsd": "http://www.w3.org/2001/XMLSchema",
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
    }
    class_elem = ET.SubElement(indicator_elem, class_name, ns_attrs)

    # Standard NinjaScript indicator properties (from discovered schema)
    _add_text_child(class_elem, "IsVisible", "true")
    _add_text_child(class_elem, "calculate2", "OnEachTick")
    _add_text_child(class_elem, "AreLinesConfigurable", "true")
    _add_text_child(class_elem, "ArePlotsConfigurable", "true")
    _add_text_child(class_elem, "BarsToLoad", "0")
    _add_text_child(class_elem, "Calculate", "OnEachTick")
    _add_text_child(class_elem, "Displacement", "0")
    _add_text_child(class_elem, "DisplayInDataBox", "false")
    _add_text_child(class_elem, "IsAutoScale", "true")

    lines = ET.SubElement(class_elem, "Lines")
    _add_text_child(class_elem, "MaximumBarsLookBack", "TwoHundredFiftySix")
    _add_text_child(class_elem, "Name", "")

    _add_text_child(class_elem, "Panel", panel_value)

    plots = ET.SubElement(class_elem, "Plots")
    _add_text_child(class_elem, "ScaleJustification", "Right")
    _add_text_child(class_elem, "ShowTransparentPlotsInDataBox", "false")
    _add_text_child(class_elem, "IsDataSeriesRequired", "true")
    _add_text_child(class_elem, "IsOverlay", "true" if panel_value == "-1" else "false")
    _add_text_child(class_elem, "SelectedValueSeries", "0")
    _add_text_child(class_elem, "InputPlot", "0")
    _add_text_child(class_elem, "IsTradingHoursBreakLineVisible", "true")
    _add_text_child(class_elem, "PaintPriceMarkers", "false")
    _add_text_child(class_elem, "DrawHorizontalGridLines", "true")
    _add_text_child(class_elem, "DrawVerticalGridLines", "true")
    _add_text_child(class_elem, "DrawOnPricePanel", "true")
    _add_text_child(class_elem, "ChartHashCodeDeserialized", "0")

    next_id = _get_next_indicator_id(tab_elem)
    _add_text_child(class_elem, "IndicatorId", str(next_id))
    _add_text_child(class_elem, "InstrumentDeserialized", instrument_full)
    _add_text_child(class_elem, "MaxSerialized", "0")
    _add_text_child(class_elem, "MinSerialized", "0")

    next_z = _get_next_zorder(tab_elem)
    _add_text_child(class_elem, "ZOrder", str(next_z))

    # Input element (standard for all indicators)
    input_elem = ET.SubElement(indicator_elem, "Input")
    _add_text_child(input_elem, "PriceType", "Close")

    return indicator_elem


def _add_text_child(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """Add a child element with text content."""
    elem = ET.SubElement(parent, tag)
    elem.text = text
    return elem


def validate_xml(path: str) -> bool:
    """Validate XML well-formedness after mutation."""
    try:
        ET.parse(path)
        return True
    except ET.ParseError:
        return False


def indent_xml(elem: ET.Element, level: int = 0) -> None:
    """Add indentation to XML for readability (stdlib-compatible)."""
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


def main():
    parser = argparse.ArgumentParser(
        description="NT8 workspace XML mutation for fallback chart indicator installation"
    )
    parser.add_argument(
        "--workspace",
        help="Workspace XML path (auto-detect from _Workspaces.xml if omitted)"
    )
    parser.add_argument(
        "--workspaces-dir",
        default=DEFAULT_WORKSPACES_DIR,
        help="NT8 workspaces directory"
    )
    parser.add_argument(
        "--class-name",
        required=True,
        help="Indicator class name (e.g., DEEP6Footprint, DEEP6Signal)"
    )
    parser.add_argument(
        "--namespace",
        default="NinjaTrader.NinjaScript.Indicators.DEEP6",
        help="Indicator namespace (default: NinjaTrader.NinjaScript.Indicators.DEEP6)"
    )
    parser.add_argument(
        "--chart-title",
        required=True,
        help="Chart title/instrument to search for (e.g., NQ, MNQ, ES)"
    )
    parser.add_argument(
        "--panel",
        default="price",
        help="Panel: price (overlay, -1), 0 (price axis), sub (1), or numeric"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show plan without modifying workspace XML"
    )
    args = parser.parse_args()

    workspaces_dir = args.workspaces_dir

    # Resolve workspace path
    if args.workspace:
        workspace_path = args.workspace
        workspace_name = Path(workspace_path).stem
    else:
        workspace_name, workspace_path = find_active_workspace(workspaces_dir)

    if not workspace_path or not os.path.exists(workspace_path):
        print(json.dumps({
            "error": "Workspace file not found",
            "path": workspace_path,
            "workspaces_dir": workspaces_dir,
        }))
        sys.exit(1)

    # Parse workspace XML
    tree = ET.parse(workspace_path)
    root = tree.getroot()

    # Find chart tabs matching the title
    matches = find_chart_tabs(root, args.chart_title)
    chart_found = len(matches) > 0

    # Full indicator name for duplicate check
    full_name = f"{args.namespace}.{args.class_name}"

    # Check for duplicates in matched tabs
    already_installed = False
    if chart_found:
        tab_elem, instrument, chart_guid = matches[0]
        already_installed = check_already_installed(tab_elem, full_name)

    if args.dry_run:
        result = {
            "workspace": workspace_path,
            "workspace_name": workspace_name,
            "backup_path": "(dry-run)",
            "chart_found": chart_found,
            "charts_matched": len(matches),
            "chart_details": [
                {
                    "instrument": m[1],
                    "chart_guid": m[2],
                }
                for m in matches
            ],
            "indicator_name": full_name,
            "already_installed": already_installed,
            "injected": False,
            "xml_valid": True,
            "dry_run": True,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    if not chart_found:
        result = {
            "workspace": workspace_path,
            "workspace_name": workspace_name,
            "chart_found": False,
            "injected": False,
            "error": f"Chart '{args.chart_title}' not found in workspace XML",
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    if already_installed:
        result = {
            "workspace": workspace_path,
            "workspace_name": workspace_name,
            "chart_found": True,
            "indicator_name": full_name,
            "already_installed": True,
            "injected": False,
            "note": "Indicator already present on chart — no mutation needed",
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # G3 MANDATORY: Backup before any write
    backup_path = backup_workspace(workspace_path)

    # Inject indicator into the first matching chart tab
    tab_elem, instrument, chart_guid = matches[0]
    inject_indicator(tab_elem, args.class_name, args.namespace, args.panel)

    # Write modified XML (preserve BOM + encoding)
    tree.write(workspace_path, xml_declaration=True, encoding="utf-8")

    # Validate well-formedness
    xml_valid = validate_xml(workspace_path)

    if not xml_valid:
        # Restore from backup immediately
        shutil.copy2(backup_path, workspace_path)
        result = {
            "workspace": workspace_path,
            "backup_path": backup_path,
            "chart_found": True,
            "injected": False,
            "xml_valid": False,
            "error": "XML validation failed after mutation -- restored from backup",
        }
        print(json.dumps(result, indent=2))
        sys.exit(1)

    result = {
        "workspace": workspace_path,
        "workspace_name": workspace_name,
        "backup_path": backup_path,
        "chart_found": True,
        "chart_instrument": instrument,
        "chart_guid": chart_guid,
        "indicator_name": full_name,
        "injected": True,
        "xml_valid": True,
        "reload_needed": True,
        "reload_method": "NEEDS_RESTART",
    }
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
