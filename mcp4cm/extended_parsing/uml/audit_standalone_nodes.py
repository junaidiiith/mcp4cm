"""Audit UML XMI datasets for potentially unintended standalone nodes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from mcp4cm.extended_parsing.uml.uml_parser import UMLXMIParser
from mcp4cm.extended_parsing.uml.xmi_utils import localname, xmi_id, xsi_type

SUSPECT_CONTEXT_TAGS: frozenset[str] = frozenset(
    {"guard", "weight", "lowerValue", "upperValue", "defaultValue", "specification"}
)
VALUE_SPEC_NODE_TYPES: frozenset[str] = frozenset(
    {
        "LiteralBoolean",
        "LiteralInteger",
        "LiteralReal",
        "LiteralString",
        "LiteralUnlimitedNatural",
        "Expression",
        "InstanceValue",
    }
)


@dataclass(slots=True)
class IsolateFinding:
    file: str
    node_id: str
    node_type: str
    element_tag: str
    element_xsi_type: str
    parent_tag: str
    parent_xsi_type: str
    suspicious: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "nodeId": self.node_id,
            "nodeType": self.node_type,
            "elementTag": self.element_tag,
            "elementXsiType": self.element_xsi_type,
            "parentTag": self.parent_tag,
            "parentXsiType": self.parent_xsi_type,
            "suspicious": self.suspicious,
        }


def audit_dataset(dataset_root: Path) -> dict[str, Any]:
    parser = UMLXMIParser()
    files = sorted(dataset_root.rglob("*.xmi"))

    stats = {
        "filesTotal": len(files),
        "filesParsed": 0,
        "filesFailed": 0,
        "irNodes": 0,
        "irEdges": 0,
        "isolatedNodes": 0,
        "suspiciousIsolatedNodes": 0,
    }

    isolate_type_counter: Counter[str] = Counter()
    isolate_pattern_counter: Counter[tuple[str, str, str, str, str]] = Counter()
    suspicious_models: Counter[str] = Counter()
    failures: list[dict[str, str]] = []
    findings: list[IsolateFinding] = []

    for path in files:
        try:
            ir, _stats = parser.parse(str(path))
        except Exception as exc:  # noqa: BLE001
            stats["filesFailed"] += 1
            failures.append({"file": str(path), "errorClass": type(exc).__name__, "message": str(exc)})
            continue

        stats["filesParsed"] += 1
        stats["irNodes"] += len(ir.nodes)
        stats["irEdges"] += len(ir.edges)

        degree = {node.id: 0 for node in ir.nodes}
        for edge in ir.edges:
            if edge.sourceId in degree:
                degree[edge.sourceId] += 1
            if edge.targetId in degree:
                degree[edge.targetId] += 1

        root = ET.parse(path).getroot()
        id_index: dict[str, ET.Element] = {}
        parent_map: dict[ET.Element, ET.Element] = {}
        for parent in root.iter():
            for child in list(parent):
                parent_map[child] = parent
        for elem in root.iter():
            elem_id = xmi_id(elem)
            if elem_id and elem_id not in id_index:
                id_index[elem_id] = elem

        node_by_id = {node.id: node for node in ir.nodes}
        for node_id, node_degree in degree.items():
            if node_degree != 0:
                continue

            node = node_by_id[node_id]
            stats["isolatedNodes"] += 1
            isolate_type_counter[node.type] += 1

            elem = id_index.get(node_id)
            if elem is None:
                finding = IsolateFinding(
                    file=path.name,
                    node_id=node_id,
                    node_type=node.type,
                    element_tag="NO_XML",
                    element_xsi_type="",
                    parent_tag="",
                    parent_xsi_type="",
                    suspicious=False,
                )
                findings.append(finding)
                isolate_pattern_counter[(node.type, "NO_XML", "", "", "")] += 1
                continue

            parent = parent_map.get(elem)
            element_tag = localname(elem.tag)
            element_xsi_type = xsi_type(elem) or ""
            parent_tag = localname(parent.tag) if parent is not None else ""
            parent_xsi_type = xsi_type(parent) or "" if parent is not None else ""

            suspicious = bool(
                node.type in VALUE_SPEC_NODE_TYPES
                and (
                    element_tag in SUSPECT_CONTEXT_TAGS
                    or parent_tag in SUSPECT_CONTEXT_TAGS
                    or parent_tag in {"edge", "ownedEnd", "ownedAttribute", "transition"}
                )
            )
            if suspicious:
                stats["suspiciousIsolatedNodes"] += 1
                suspicious_models[path.name] += 1

            findings.append(
                IsolateFinding(
                    file=path.name,
                    node_id=node_id,
                    node_type=node.type,
                    element_tag=element_tag,
                    element_xsi_type=element_xsi_type,
                    parent_tag=parent_tag,
                    parent_xsi_type=parent_xsi_type,
                    suspicious=suspicious,
                )
            )
            isolate_pattern_counter[(node.type, element_tag, element_xsi_type, parent_tag, parent_xsi_type)] += 1

    return {
        "summary": stats,
        "topIsolatedNodeTypes": dict(isolate_type_counter.most_common(25)),
        "topIsolationPatterns": [
            {
                "count": count,
                "nodeType": key[0],
                "elementTag": key[1],
                "elementXsiType": key[2],
                "parentTag": key[3],
                "parentXsiType": key[4],
            }
            for key, count in isolate_pattern_counter.most_common(50)
        ],
        "topSuspiciousModels": [{"file": name, "count": count} for name, count in suspicious_models.most_common(50)],
        "failures": failures,
        "findings": [f.to_dict() for f in findings],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit UML XMI files for isolated standalone nodes.")
    parser.add_argument("dataset", type=Path, help="Path to a UML dataset directory (scans recursively for *.xmi).")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output JSON file. If omitted, prints a compact summary only.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    dataset_root = args.dataset.expanduser().resolve()
    if not dataset_root.exists():
        raise SystemExit(f"Dataset path does not exist: {dataset_root}")

    report = audit_dataset(dataset_root)
    summary = report["summary"]
    print("AUDIT SUMMARY")
    for key in (
        "filesTotal",
        "filesParsed",
        "filesFailed",
        "irNodes",
        "irEdges",
        "isolatedNodes",
        "suspiciousIsolatedNodes",
    ):
        print(f"{key}: {summary[key]}")

    print("\nTOP ISOLATED NODE TYPES")
    for node_type, count in report["topIsolatedNodeTypes"].items():
        print(f"{node_type}: {count}")

    print("\nTOP SUSPICIOUS MODELS")
    for item in report["topSuspiciousModels"][:20]:
        print(f"{item['count']:4d} | {item['file']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote detailed report: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
