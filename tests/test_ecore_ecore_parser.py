import uuid

import pytest

pytest.importorskip("pyecore")

from mcp4cm.parsers.ecore_ecore.parser import EcoreParser
from mcp4cm.parsers.parse import parse_staged_files


def _write_minimal_ecore(path, package_name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<ecore:EPackage xmi:version="2.0"
    xmlns:xmi="http://www.omg.org/XMI"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:ecore="http://www.eclipse.org/emf/2002/Ecore"
    name="{package_name}" nsURI="http://example.test/{package_name}" nsPrefix="{package_name}">
  <eClassifiers xsi:type="ecore:EClass" name="Item"/>
</ecore:EPackage>
""",
        encoding="utf-8",
    )


def test_ecore_parser_materializes_named_references_as_nodes(tmp_path):
    model_path = tmp_path / "school.ecore"
    model_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<ecore:EPackage xmi:version="2.0"
    xmlns:xmi="http://www.omg.org/XMI"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:ecore="http://www.eclipse.org/emf/2002/Ecore"
    name="school" nsURI="http://example.test/school" nsPrefix="school">
  <eClassifiers xsi:type="ecore:EClass" name="Classroom">
    <eStructuralFeatures xsi:type="ecore:EReference" name="students" upperBound="-1"
        eType="#//Student" containment="true"/>
  </eClassifiers>
  <eClassifiers xsi:type="ecore:EClass" name="Student">
    <eTypeParameters name="T"/>
  </eClassifiers>
</ecore:EPackage>
""",
        encoding="utf-8",
    )

    ir, stats = EcoreParser().parse(str(model_path))

    reference_nodes = [node for node in ir.nodes if node.type == "EReference"]
    assert [(node.name, node.data["containment"]) for node in reference_nodes] == [("students", True)]

    reference_id = reference_nodes[0].id
    classroom_id = next(node.id for node in ir.nodes if node.name == "Classroom")
    student_id = next(node.id for node in ir.nodes if node.name == "Student")

    assert any(
        edge.type == "Contains" and edge.sourceId == classroom_id and edge.targetId == reference_id for edge in ir.edges
    )
    assert any(
        edge.type == "ReferenceType" and edge.sourceId == reference_id and edge.targetId == student_id
        for edge in ir.edges
    )
    assert any(node.type == "ETypeParameter" and node.name == "T" for node in ir.nodes)
    assert stats.warning_count == 0


def test_ecore_file_adapter_uses_relative_path_as_model_id_for_duplicate_basenames(tmp_path):
    first = tmp_path / "owner-a" / "repo-a" / "model" / "library.ecore"
    second = tmp_path / "owner-b" / "repo-b" / "model" / "library.ecore"
    _write_minimal_ecore(first, "library")
    _write_minimal_ecore(second, "library")

    result = parse_staged_files(
        language="ecore",
        format="ecore",
        staged_files=[
            {"relativePath": "owner-a/repo-a/model/library.ecore", "storedPath": str(first)},
            {"relativePath": "owner-b/repo-b/model/library.ecore", "storedPath": str(second)},
        ],
        options={"resolveExternalRefs": False},
    )

    assert result.invalid_files == []
    expected_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_URL, "mcp4cm:ecore:owner-a/repo-a/model/library.ecore")),
        str(uuid.uuid5(uuid.NAMESPACE_URL, "mcp4cm:ecore:owner-b/repo-b/model/library.ecore")),
    ]
    assert [record.model_id for record in result.records] == [
        *expected_ids,
    ]
    assert set(result.diagnostics) == set(expected_ids)
    assert all(len(record.model_id) == 36 and record.model_id != "library" for record in result.records)
