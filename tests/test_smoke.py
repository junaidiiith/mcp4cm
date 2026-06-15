import pytest

from mcp4cm.core import Dataset
from mcp4cm.dummy import (
    default_filter_configs,
    detect_dummy_models,
    evaluate_dummy_filters,
    summarize_filters_by_language,
)
from mcp4cm.duplicates import (
    detect_duplicates_by_node_name_hash,
    detect_duplicates_by_node_name_type_hash,
    graph_embedding_pairs,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    record_tokens,
    tfidf_duplicate_by_names,
    tfidf_duplicate_by_names_and_types,
    tfidf_duplicate_pairs,
    vote_duplicate_pairs,
)
from mcp4cm.loading import load_eamodelset, load_modelset
from mcp4cm.parsers.archimate_json.parser import ArchimateJsonParser
from mcp4cm.parsers.catalog import ParserOptions, resolve_parser
from mcp4cm.parsers.diagnostics import ParserRunStats, WarningType
from mcp4cm.parsers.graph import drop_ir_edges_with_missing_nodes
from mcp4cm.parsers.ir import IR, Edge, Node
from mcp4cm.parsers.modelset_json.parser import ModelSetJsonParser
from mcp4cm.parsers.parse import parse_file
from mcp4cm.parsers.uml_xmi.parser import ParseOptions, UMLXMIParser
from mcp4cm.xmi_names import EMPTY_NAME_SENTINEL, extract_xmi_names, normalize_identifier


def test_drop_ir_edges_with_missing_nodes_removes_invalid_edges_and_reports_warning():
    ir = IR(
        id="m1",
        language="UML",
        nodes=[Node(id="n1", type="Class", name="A"), Node(id="n2", type="Class", name="B")],
        edges=[
            Edge(id="e-ok", sourceId="n1", targetId="n2", type="Association"),
            Edge(id="e-missing-source", sourceId="x", targetId="n2", type="Association"),
            Edge(id="e-missing-target", sourceId="n1", targetId="y", type="Association"),
        ],
    )
    stats = ParserRunStats()

    dropped = drop_ir_edges_with_missing_nodes(ir, stats)

    assert dropped == 2
    assert [edge.id for edge in ir.edges] == ["e-ok"]
    assert stats.warnings_by_type[WarningType.UNRESOLVED_REFERENCE] == 2
    assert stats.elements_skipped == 2


def test_ecore_parser_descriptor_accepts_external_resolution_option():
    descriptor = resolve_parser("ecore", "ecore")

    enabled = descriptor.normalize_options({"resolveExternalRefs": "true"})
    disabled = descriptor.normalize_options({"resolveExternalRefs": "false"})

    assert enabled.values["resolve_external_refs"] is True
    assert disabled.values["resolve_external_refs"] is False


def test_xmi_name_extraction_is_normalized_and_kept_in_memory(tmp_path):
    model_path = tmp_path / "names.xmi"
    model_path.write_text(
        """<?xml version="1.0"?>
<uml:Model xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <packagedElement xsi:type="uml:Class" name="HTTPServer"/>
  <packagedElement xsi:type="uml:Class" name=""/>
  <ownedComment body="customer_id"/>
</uml:Model>
""",
        encoding="utf-8",
    )

    extracted = extract_xmi_names(model_path)

    assert normalize_identifier("ownedEnd") == "owned end"
    assert extracted.names == ("http server", EMPTY_NAME_SENTINEL, "customer id")
    assert extracted.typed_names == ("class: http server", "class: empty name", "comment: customer id")


def test_archimate_parser_smoke():
    raw = {
        "archimateId": "m1",
        "name": "Example",
        "tags": ["demo"],
        "elements": [
            {"id": "a", "name": "App", "type": "ApplicationComponent", "layer": "application"},
            {"id": "b", "name": "DB", "type": "DataObject", "layer": "application"},
        ],
        "relationships": [{"id": "r1", "sourceId": "a", "targetId": "b", "type": "Access"}],
    }
    record = ArchimateJsonParser().parse(raw)
    assert record.node_count == 2
    assert record.edge_count == 1
    assert "App" in record.names


def test_hash_duplicate_detection_smoke():
    parser = ArchimateJsonParser()
    raw = {
        "elements": [{"id": "a", "name": "Foo", "type": "ApplicationComponent"}],
        "relationships": [],
    }
    first = parser.parse(raw, model_id="one")
    second = parser.parse(raw, model_id="two")
    groups = detect_duplicates_by_node_name_hash(Dataset([first, second], "archimate"))
    assert len(groups) == 1
    assert groups[0].model_ids == ("one", "two")


def test_duplicate_hash_modes_use_names_and_name_types():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Customer", "type": "BusinessActor"},
                {"id": "y", "name": "Order", "type": "DataObject"},
            ],
            "relationships": [],
        },
        model_id="second",
    )

    dataset = Dataset([first, second], "archimate")

    assert len(detect_duplicates_by_node_name_hash(dataset)) == 1
    assert detect_duplicates_by_node_name_type_hash(dataset) == []


def test_duplicate_hash_ignores_raw_extracted_xmi_vocabulary_when_available():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {"elements": [{"id": "a", "name": "Graph A", "type": "Class"}], "relationships": []}, model_id="first"
    )
    second = parser.parse(
        {"elements": [{"id": "b", "name": "Graph B", "type": "Class"}], "relationships": []}, model_id="second"
    )
    reordered = parser.parse(
        {"elements": [{"id": "c", "name": "Graph C", "type": "Class"}], "relationships": []}, model_id="reordered"
    )
    for record in (first, second):
        record.metadata["extracted_names"] = ["http server", "empty name", "customer id"]
        record.metadata["extracted_typed_names"] = ["class: http server", "class: empty name", "comment: customer id"]
    reordered.metadata["extracted_names"] = ["customer id", "empty name", "http server"]
    reordered.metadata["extracted_typed_names"] = ["comment: customer id", "class: empty name", "class: http server"]

    dataset = Dataset([first, second, reordered], "uml")

    assert detect_duplicates_by_node_name_hash(dataset) == []
    assert detect_duplicates_by_node_name_type_hash(dataset) == []


def test_duplicate_hash_reports_progress():
    parser = ArchimateJsonParser()
    records = [
        parser.parse(
            {"elements": [{"id": str(index), "name": "Order", "type": "BusinessObject"}], "relationships": []},
            model_id=str(index),
        )
        for index in range(3)
    ]
    events = []

    detect_duplicates_by_node_name_hash(Dataset(records, "archimate"), progress=events.append)

    assert events
    assert events[-1]["current"] == 3
    assert events[-1]["total"] == 3
    assert events[-1]["percent"] == 100


def test_tfidf_duplicate_modes_and_graph_similarity():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r1", "sourceId": "b", "targetId": "a", "type": "Association"}],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Order", "type": "BusinessObject"},
                {"id": "y", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r2", "sourceId": "y", "targetId": "x", "type": "Association"}],
        },
        model_id="second",
    )
    third = parser.parse(
        {
            "elements": [
                {"id": "m", "name": "Invoice", "type": "DataObject"},
                {"id": "n", "name": "Payment", "type": "BusinessProcess"},
            ],
            "relationships": [],
        },
        model_id="third",
    )

    dataset = Dataset([first, second, third], "archimate")

    assert [(pair.left_id, pair.right_id) for pair in tfidf_duplicate_by_names(dataset, threshold=0.99)] == [
        ("first", "second")
    ]
    assert [(pair.left_id, pair.right_id) for pair in tfidf_duplicate_by_names_and_types(dataset, threshold=0.99)] == [
        ("first", "second")
    ]
    assert [(pair.left_id, pair.right_id) for pair in graph_similarity_pairs(dataset, threshold=0.99)] == [
        ("first", "second")
    ]


def test_tfidf_names_types_bag_includes_edge_types():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r1", "sourceId": "b", "targetId": "a", "type": "Association"}],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Order", "type": "BusinessObject"},
                {"id": "y", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r2", "sourceId": "y", "targetId": "x", "type": "Flow"}],
        },
        model_id="second",
    )
    dataset = Dataset([first, second], "archimate")

    assert [(pair.left_id, pair.right_id) for pair in tfidf_duplicate_by_names(dataset, threshold=0.99)] == [
        ("first", "second")
    ]
    assert tfidf_duplicate_by_names_and_types(dataset, threshold=0.99) == []


def test_graph_embedding_uses_shared_semantic_feature_space(monkeypatch):
    class FakeWordVectors(dict):
        pass

    class FakeNode2Vec:
        def __init__(self, graph, dimensions, **_kwargs):
            self.graph = graph
            self.dimensions = dimensions

        def fit(self, **_kwargs):
            vectors = FakeWordVectors()
            for node in self.graph.nodes():
                vectors[node] = fake_vector(self.graph, node, self.dimensions)
            return type("FakeModel", (), {"wv": vectors})()

    def feature_vector(node: str, dimensions: int):
        values = [0.0] * dimensions
        if node.endswith("::order") or node.endswith("::customer"):
            values[0] = 1.0
        elif node.endswith("::invoice") or node.endswith("::payment"):
            values[0] = -1.0
        elif node.endswith("::business object") or node.endswith("::business actor"):
            values[1] = 1.0
        elif node.endswith("::association"):
            values[2] = 1.0
        return values

    def fake_vector(graph, node: str, dimensions: int):
        if node.startswith("feature::"):
            return feature_vector(node, dimensions)
        values = [0.0] * dimensions
        feature_neighbors = [neighbor for neighbor in graph.neighbors(node) if str(neighbor).startswith("feature::")]
        if not feature_neighbors:
            values[3] = 1.0
            return values
        for neighbor in feature_neighbors:
            for index, value in enumerate(feature_vector(str(neighbor), dimensions)):
                values[index] += value
        return values

    monkeypatch.setattr("mcp4cm.duplicates.require_node2vec", lambda: FakeNode2Vec)
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r1", "sourceId": "a", "targetId": "b", "type": "Association"}],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Order", "type": "BusinessObject"},
                {"id": "y", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r2", "sourceId": "x", "targetId": "y", "type": "Association"}],
        },
        model_id="second",
    )
    third = parser.parse(
        {
            "elements": [
                {"id": "m", "name": "Invoice", "type": "BusinessObject"},
                {"id": "n", "name": "Payment", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r3", "sourceId": "m", "targetId": "n", "type": "Association"}],
        },
        model_id="third",
    )
    dataset = Dataset([first, second, third], "archimate")

    semantic_pairs = graph_embedding_pairs(dataset, threshold=0.9, dimensions=4)
    topology_pairs = graph_embedding_pairs(
        dataset,
        threshold=0.9,
        dimensions=4,
        use_node_names=False,
        use_node_types=False,
        use_edge_types=False,
    )

    assert [(pair.left_id, pair.right_id) for pair in semantic_pairs] == [("first", "second")]
    assert {(pair.left_id, pair.right_id) for pair in topology_pairs} == {
        ("first", "second"),
        ("first", "third"),
        ("second", "third"),
    }


def test_tfidf_typed_name_pairs_keep_type_name_bindings_atomic():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order Item", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Order Item", "type": "BusinessActor"},
                {"id": "y", "name": "Customer", "type": "BusinessObject"},
            ],
            "relationships": [],
        },
        model_id="second",
    )
    dataset = Dataset([first, second], "archimate")

    assert tfidf_duplicate_pairs(dataset, token_mode="names_types_bag", threshold=0.99)
    assert tfidf_duplicate_pairs(dataset, token_mode="typed_name_pairs", threshold=0.99) == []
    assert record_tokens(first, token_mode="typed_name_pairs") == [
        "type_business_actor__name_customer",
        "type_business_object__name_order_item",
    ]


def test_tfidf_typed_name_pair_ngrams_operate_on_atomic_pair_tokens():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order Item", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Order Item", "type": "BusinessObject"},
                {"id": "y", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [],
        },
        model_id="second",
    )
    dataset = Dataset([first, second], "archimate")

    pairs = tfidf_duplicate_pairs(dataset, token_mode="typed_name_pairs", threshold=0.99, ngram_range=(1, 2))

    assert [(pair.left_id, pair.right_id) for pair in pairs] == [("first", "second")]


def test_pairwise_duplicate_algorithms_report_progress():
    parser = ArchimateJsonParser()
    records = [
        parser.parse(
            {
                "elements": [{"id": str(index), "name": f"Order {index}", "type": "BusinessObject"}],
                "relationships": [],
            },
            model_id=str(index),
        )
        for index in range(4)
    ]
    dataset = Dataset(records, "archimate")

    tfidf_events = []
    graph_events = []
    isomorphism_events = []
    tfidf_duplicate_by_names(dataset, threshold=0.1, progress=tfidf_events.append)
    graph_similarity_pairs(dataset, threshold=0.1, progress=graph_events.append)
    graph_isomorphism_pairs(dataset, mode="structure", progress=isomorphism_events.append)

    assert tfidf_events[-1]["percent"] == 100
    assert graph_events[-1]["percent"] == 100
    assert isomorphism_events[-1]["percent"] == 100


def test_graph_isomorphism_modes():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r1", "sourceId": "b", "targetId": "a", "type": "Association"}],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Order", "type": "DataObject"},
                {"id": "y", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r2", "sourceId": "y", "targetId": "x", "type": "Association"}],
        },
        model_id="second",
    )

    dataset = Dataset([first, second], "archimate")

    assert len(graph_isomorphism_pairs(dataset, mode="structure")) == 1
    assert len(graph_isomorphism_pairs(dataset, mode="names")) == 1
    assert graph_isomorphism_pairs(dataset, mode="names_types") == []


def test_duplicate_voting_combines_techniques():
    parser = ArchimateJsonParser()
    first = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Order", "type": "BusinessObject"},
                {"id": "b", "name": "Customer", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r1", "sourceId": "b", "targetId": "a", "type": "Association"}],
        },
        model_id="first",
    )
    second = parser.parse(
        {
            "elements": [
                {"id": "x", "name": "Customer", "type": "BusinessActor"},
                {"id": "y", "name": "Order", "type": "BusinessObject"},
            ],
            "relationships": [{"id": "r2", "sourceId": "x", "targetId": "y", "type": "Association"}],
        },
        model_id="second",
    )

    decisions = vote_duplicate_pairs(Dataset([first, second], "archimate"), min_votes=3)

    assert len(decisions) == 1
    assert decisions[0].is_duplicate
    assert decisions[0].vote_count == 6


def test_dummy_detection_smoke():
    parser = ArchimateJsonParser()
    record = parser.parse(
        {
            "elements": [
                {"id": "a", "name": "Class1", "type": "BusinessObject"},
                {"id": "b", "name": "Class2", "type": "BusinessObject"},
            ],
            "relationships": [],
        },
        model_id="dummy",
    )
    findings = detect_dummy_models(Dataset([record], "archimate"), filter_configs=default_filter_configs())
    assert findings
    assert findings[0].filter_id == "min_size"


def uml_record(names, *, model_id="uml", node_type="Class"):
    return ModelSetJsonParser("uml").parse(
        {
            "ids": model_id,
            "graph": {
                "directed": True,
                "nodes": [{"id": str(index), "name": name, "type": node_type} for index, name in enumerate(names)],
                "edges": [],
            },
        },
        model_id=model_id,
    )


def test_modelset_json_parser_accepts_top_level_graph_payload():
    record = ModelSetJsonParser("uml").parse(
        {
            "directed": True,
            "multigraph": True,
            "nodes": [
                {"id": 1, "name": "User", "eClass": "Actor"},
                {"id": 2, "name": "Login", "eClass": "UseCase"},
            ],
            "links": [{"source": 1, "target": 2, "type": "Association"}],
        },
        model_id="top-level",
    )

    assert record.node_count == 2
    assert record.edge_count == 1
    assert "User" in record.names


def test_dummy_cleansing_v2_filter_chain_and_traceability():
    record = ModelSetJsonParser("uml").parse(
        {
            "ids": "uml-dummy",
            "graph": {
                "directed": True,
                "nodes": [
                    {"id": "1", "name": "Order", "type": "Class"},
                    {"id": "2", "name": "Order", "type": "Class"},
                    {"id": "3", "name": "Order", "type": "Class"},
                    {"id": "4", "name": "Order", "type": "Class"},
                    {"id": "5", "name": "Customer", "type": "Class"},
                    {"id": "6", "name": "Invoice", "type": "Class"},
                ],
                "edges": [
                    {"source": "1", "target": "2", "type": "Association"},
                    {"source": "2", "target": "3", "type": "Association"},
                    {"source": "3", "target": "4", "type": "Association"},
                    {"source": "4", "target": "5", "type": "Association"},
                ],
            },
        },
        model_id="uml-dummy",
    )
    result = evaluate_dummy_filters(Dataset([record], "uml"), filter_configs=default_filter_configs())

    assert result.run_summary.total_models == 1
    assert result.run_summary.removed_models == 1
    assert result.model_outcomes[0].primary_removal_reason == "name_repetition_ratio"
    assert any(finding.decision == "removed" for finding in result.findings)


def test_dummy_cleansing_v2_regex_rule():
    record = uml_record(["Order", "Customer", "TestUser", "Payment", "Invoice"], model_id="regex-model")
    configs = default_filter_configs()
    for config in configs:
        if config["id"] == "regex_rule":
            config["enabled"] = True
            config["pattern"] = "^test"
            config["targetField"] = "name"
            config["scope"] = "all_named_nodes"
            config["minMatches"] = 1
    result = evaluate_dummy_filters(Dataset([record], "uml"), filter_configs=configs)
    regex_findings = [finding for finding in result.findings if finding.filter_id == "regex_rule"]
    assert regex_findings
    assert regex_findings[0].decision == "removed"


def test_dummy_cleansing_v2_filter_summary_groups_mixed_modelset_by_language():
    uml = ModelSetJsonParser("uml").parse(
        {
            "ids": "uml-dummy",
            "model_type": "uml",
            "txt": "",
            "graph": {
                "directed": True,
                "multigraph": False,
                "nodes": [{"id": index, "name": f"Class {index}", "eClass": "Class"} for index in range(1, 6)],
                "links": [],
            },
        }
    )
    ecore = ModelSetJsonParser("ecore").parse(
        {
            "ids": "ecore-dummy",
            "model_type": "ecore",
            "txt": "",
            "graph": {
                "directed": True,
                "multigraph": False,
                "nodes": [{"id": index, "name": f"Entity {index}", "eClass": "EClass"} for index in range(1, 6)],
                "links": [],
            },
        }
    )

    summaries = summarize_filters_by_language(Dataset([uml, ecore], "modelset"))

    assert set(summaries) == {"ecore", "uml"}
    assert any(row.filtered_count == 1 for row in summaries["ecore"])
    assert any(row.filtered_count == 1 for row in summaries["uml"])


def test_eamodelset_loading_filters_by_natural_language(tmp_path):
    for model_id, language in [("english", "en"), ("german", "de")]:
        model_dir = tmp_path / model_id
        model_dir.mkdir()
        (model_dir / "model.json").write_text(
            f'{{"archimateId": "{model_id}", "name": "{model_id}", "language": "{language}", '
            '"elements": [], "relationships": []}',
            encoding="utf-8",
        )

    dataset = load_eamodelset(tmp_path, language="en")

    assert len(dataset) == 1
    assert dataset[0].model_id == "english"


def test_eamodelset_loading_accepts_flat_json_exports(tmp_path):
    (tmp_path / "english.json").write_text(
        '{"archimateId": "english", "name": "English", "language": "en", '
        '"elements": [{"id": "a", "name": "App", "type": "ApplicationComponent"}], "relationships": []}',
        encoding="utf-8",
    )

    dataset = load_eamodelset(tmp_path, language="en")

    assert len(dataset) == 1
    assert dataset[0].model_id == "english"
    assert dataset[0].node_count == 1


def test_modelset_loading_discovers_nested_json_exports(tmp_path):
    model_dir = tmp_path / "repo" / "project.ecore"
    model_dir.mkdir(parents=True)
    (model_dir / "model.json").write_text(
        '{"directed": true, "nodes": [{"id": 1, "name": "Wheel", "eClass": "EClass"}], "links": []}',
        encoding="utf-8",
    )

    dataset = load_modelset(tmp_path, language="ecore", format="json")

    assert len(dataset) == 1
    assert dataset[0].model_id == "model"
    assert dataset[0].node_count == 1


def test_language_filter_accepts_multiple_values(tmp_path):
    for model_id, language in [("english", "en"), ("german", "de"), ("spanish", "es")]:
        model_dir = tmp_path / model_id
        model_dir.mkdir()
        (model_dir / "model.json").write_text(
            f'{{"archimateId": "{model_id}", "name": "{model_id}", "language": "{language}", '
            '"elements": [], "relationships": []}',
            encoding="utf-8",
        )

    dataset = load_eamodelset(tmp_path, language={"en", "es"})

    assert dataset.ids() == ["english", "spanish"]


def test_uml_parser_embeds_multiplicity_without_literal_value_nodes(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Class" xmi:id="A" name="A"/>
    <packagedElement xsi:type="uml:Class" xmi:id="B" name="B"/>
    <packagedElement xsi:type="uml:Association" xmi:id="Assoc1" memberEnd="endA endB">
      <ownedEnd xmi:id="endA" name="a" type="A">
        <lowerValue xsi:type="uml:LiteralInteger" xmi:id="lvA" value="0"/>
        <upperValue xsi:type="uml:LiteralUnlimitedNatural" xmi:id="uvA" value="*"/>
      </ownedEnd>
      <ownedEnd xmi:id="endB" name="b" type="B">
        <lowerValue xsi:type="uml:LiteralInteger" xmi:id="lvB" value="1"/>
        <upperValue xsi:type="uml:LiteralInteger" xmi:id="uvB" value="1"/>
      </ownedEnd>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "model.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser().parse(str(model_path))

    node_types = {node.type for node in ir.nodes}
    assert "LiteralInteger" not in node_types
    assert "LiteralUnlimitedNatural" not in node_types

    assoc_edge = next(edge for edge in ir.edges if edge.id == "Assoc1")
    assert assoc_edge.data["end1"]["lower"] == "0"
    assert assoc_edge.data["end1"]["upper"] == "*"
    assert assoc_edge.data["end2"]["lower"] == "1"
    assert assoc_edge.data["end2"]["upper"] == "1"


def test_uml_xml_pye_parser_smoke(tmp_path):
    pytest.importorskip("pyecore")
    from mcp4cm.parsers.uml_xml_pyecore.parser import UMLXMLPyEcoreParser

    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Class" xmi:id="A" name="A"/>
    <packagedElement xsi:type="uml:Class" xmi:id="B" name="B"/>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "model.uml"
    model_path.write_text(xmi, encoding="utf-8")

    ir, stats = UMLXMLPyEcoreParser().parse(str(model_path))

    assert stats.warning_count == 0
    assert ir.language == "UML-XML-PyEcore"
    assert {node.id for node in ir.nodes} >= {"model1", "A", "B"}
    assert {node.type for node in ir.nodes} >= {"Model", "Class"}
    assert any(edge.type == "packagedElement" for edge in ir.edges)


def test_uml_xml_pye_parser_silently_removes_xmi_extensions(tmp_path):
    pytest.importorskip("pyecore")
    from mcp4cm.parsers.diagnostics import WarningType
    from mcp4cm.parsers.uml_xml_pyecore.parser import UMLXMLPyEcoreParser

    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <xmi:Extension extender="http://www.eclipse.org/emf/2002/Ecore">
      <eAnnotations xmi:id="ann1" source="genmymodel"/>
    </xmi:Extension>
    <packagedElement xsi:type="uml:Class" xmi:id="A" name="A"/>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "model.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    _ir, stats = UMLXMLPyEcoreParser().parse(str(model_path))

    assert stats.warning_count == 0
    assert stats.warnings_by_type.get(WarningType.COMPATIBILITY_ADAPTATION, 0) == 0


def test_uml_xml_pye_parser_stubs_primitive_types_on_nodes(tmp_path):
    pytest.importorskip("pyecore")
    from mcp4cm.parsers.diagnostics import WarningType
    from mcp4cm.parsers.uml_xml_pyecore.parser import UMLXMLPyEcoreParser

    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packageImport xmi:id="pi1" importingNamespace="model1">
      <importedPackage href="http://www.omg.org/spec/UML/20131001/PrimitiveTypes.xmi#/"/>
    </packageImport>
    <packagedElement xsi:type="uml:Class" xmi:id="A" name="A">
      <ownedAttribute xmi:id="p1" name="title">
        <type xsi:type="uml:PrimitiveType" href="http://www.omg.org/spec/UML/20131001/PrimitiveTypes.xmi#//String"/>
      </ownedAttribute>
      <ownedAttribute xmi:id="p2" name="count">
        <type xsi:type="uml:PrimitiveType" href="http://www.omg.org/spec/UML/20131001/PrimitiveTypes.xmi#//Integer"/>
      </ownedAttribute>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "model.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, stats = UMLXMLPyEcoreParser().parse(str(model_path))

    assert stats.warning_count == 0
    assert stats.warnings_by_type.get(WarningType.UNRESOLVED_REFERENCE, 0) == 0

    properties = {node.id: node for node in ir.nodes if node.eClass == "Property"}
    assert properties["p1"].type == "String"
    assert properties["p1"].name == "title"
    assert properties["p1"].eClass == "Property"
    assert "type" not in properties["p1"].data
    assert "name" not in properties["p1"].data
    assert properties["p2"].type == "Integer"
    assert properties["p2"].eClass == "Property"
    assert not any(edge.type == "type" for edge in ir.edges)


def test_uml_xml_pye_parser_stubs_genmymodel_primitive_types(tmp_path):
    pytest.importorskip("pyecore")
    from mcp4cm.parsers.diagnostics import WarningType
    from mcp4cm.parsers.uml_xml_pyecore.parser import UMLXMLPyEcoreParser

    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packageImport xmi:id="pi1" importingNamespace="model1">
      <importedPackage href="pathmap://GENMYMODEL_LIBRARIES/GenMyModelPrimitiveTypes.library.uml#/"/>
    </packageImport>
    <packagedElement xsi:type="uml:Class" xmi:id="A" name="A">
      <ownedAttribute xmi:id="p1" name="created">
        <type xsi:type="uml:PrimitiveType" href="pathmap://GENMYMODEL_LIBRARIES/GenMyModelPrimitiveTypes.library.uml#//Date"/>
      </ownedAttribute>
      <ownedAttribute xmi:id="p2" name="amount">
        <type xsi:type="uml:PrimitiveType" href="pathmap://GENMYMODEL_LIBRARIES/GenMyModelPrimitiveTypes.library.uml#//Long"/>
      </ownedAttribute>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "model.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, stats = UMLXMLPyEcoreParser().parse(str(model_path))

    assert stats.warning_count == 0
    assert stats.warnings_by_type.get(WarningType.UNRESOLVED_REFERENCE, 0) == 0

    properties = {node.id: node for node in ir.nodes if node.eClass == "Property"}
    assert properties["p1"].type == "Date"
    assert properties["p2"].type == "Long"


def test_uml_xml_pye_descriptor_and_adapter(tmp_path):
    pytest.importorskip("pyecore")

    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="model">
    <packagedElement xsi:type="uml:Class" xmi:id="C1" name="Class1"/>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "descriptor.uml"
    model_path.write_text(xmi, encoding="utf-8")

    descriptor = resolve_parser("uml", "xml-pyecore")
    result = parse_file(model_path, language="uml", format="xml-pyecore", model_id="descriptor")

    assert descriptor.parser_id == "uml-xml-pyecore"
    assert descriptor.matches_extension("model.uml")
    assert result.record.model_id == "descriptor"
    assert result.record.language == "uml"
    assert result.record.metadata["format"] == "xml-pyecore"
    assert result.record.metadata["parserLanguage"] == "UML-XML-PyEcore"
    assert result.record.node_count >= 2


def test_uml_parser_embeds_guard_and_weight_without_value_spec_nodes(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Activity" xmi:id="act1" name="Flow">
      <ownedNode xsi:type="uml:InitialNode" xmi:id="n1" name="Start"/>
      <ownedNode xsi:type="uml:ActivityFinalNode" xmi:id="n2" name="End"/>
      <edge xsi:type="uml:ControlFlow" xmi:id="e1" source="n1" target="n2" activity="act1">
        <guard xsi:type="uml:LiteralString" xmi:id="g1" value="ok"/>
        <weight xsi:type="uml:LiteralInteger" xmi:id="w1" value="3"/>
      </edge>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "activity.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser().parse(str(model_path))

    node_types = {node.type for node in ir.nodes}
    assert "LiteralString" not in node_types
    assert "LiteralInteger" not in node_types

    control_flow = next(edge for edge in ir.edges if edge.id == "e1")
    assert control_flow.type == "ControlFlow"
    assert control_flow.data["guard"] == {"id": "g1", "type": "uml:LiteralString", "value": "ok"}
    assert control_flow.data["weight"] == {"id": "w1", "type": "uml:LiteralInteger", "value": "3"}


def test_uml_parser_embeds_transition_owned_rule_specification_without_literal_nodes(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:StateMachine" xmi:id="sm1" name="SM">
      <region xmi:id="r1" stateMachine="sm1">
        <subvertex xsi:type="uml:State" xmi:id="s1" name="S1"/>
        <subvertex xsi:type="uml:State" xmi:id="s2" name="S2"/>
        <transition xmi:id="t1" source="s1" target="s2" container="r1" guard="rule1">
          <ownedRule xmi:id="rule1" context="t1">
            <specification xsi:type="uml:LiteralString" xmi:id="spec1" value="ok"/>
          </ownedRule>
        </transition>
      </region>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "transition.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser().parse(str(model_path))
    node_types = {node.type for node in ir.nodes}
    assert "LiteralString" not in node_types

    transition = next(edge for edge in ir.edges if edge.id == "t1")
    assert transition.type == "Transition"
    assert transition.data["guard"] == "rule1"
    assert transition.data["ownedRuleRefs"] == ["rule1"]
    assert transition.data["ownedRules"] == [
        {"id": "rule1", "context": "t1", "specification": {"id": "spec1", "type": "uml:LiteralString", "value": "ok"}}
    ]
    assert transition.data["guardRule"] == transition.data["ownedRules"][0]


def test_uml_parser_embeds_instance_slot_values_without_value_spec_nodes(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Class" xmi:id="C1" name="Person">
      <ownedAttribute xmi:id="A1" name="name" visibility="public"/>
    </packagedElement>
    <packagedElement xsi:type="uml:InstanceSpecification" xmi:id="I1" name="john" classifier="C1">
      <slot xmi:id="SLOT1" definingFeature="A1" owningInstance="I1">
        <value xsi:type="uml:Expression" xmi:id="V1" symbol="John Doe"/>
      </slot>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "instance.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser().parse(str(model_path))
    node_types = {node.type for node in ir.nodes}
    assert "Expression" not in node_types
    assert "InstanceValue" not in node_types

    instance = next(node for node in ir.nodes if node.id == "I1")
    assert instance.type == "InstanceSpecification"
    assert instance.data["classifierRefs"] == ["C1"]
    assert instance.data["slotRefs"] == ["SLOT1"]
    assert instance.data["slots"] == [
        {
            "id": "SLOT1",
            "definingFeature": "A1",
            "owningInstance": "I1",
            "values": [{"id": "V1", "type": "uml:Expression", "symbol": "John Doe"}],
            "value": {"id": "V1", "type": "uml:Expression", "symbol": "John Doe"},
        }
    ]


def test_uml_parser_embeds_message_arguments_without_literal_nodes(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Interaction" xmi:id="int1" name="I">
      <lifeline xmi:id="l1" name="A"/>
      <lifeline xmi:id="l2" name="B"/>
      <fragment xsi:type="uml:MessageOccurrenceSpecification" xmi:id="send1" covered="l1"/>
      <fragment xsi:type="uml:MessageOccurrenceSpecification" xmi:id="recv1" covered="l2"/>
      <message xmi:id="m1" name="login" interaction="int1" sendEvent="send1" receiveEvent="recv1">
        <argument xsi:type="uml:LiteralString" xmi:id="arg1" value="user"/>
        <argument xsi:type="uml:LiteralString" xmi:id="arg2" value="secret"/>
      </message>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "message.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser().parse(str(model_path))
    node_types = {node.type for node in ir.nodes}
    assert "LiteralString" not in node_types

    message = next(edge for edge in ir.edges if edge.id == "m1")
    assert message.type == "Message"
    assert message.data["arguments"] == [
        {"id": "arg1", "type": "uml:LiteralString", "value": "user"},
        {"id": "arg2", "type": "uml:LiteralString", "value": "secret"},
    ]


def test_uml_parser_adds_model_and_xml_ownership_edges(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Package" xmi:id="pkg1" name="Pkg">
      <packagedElement xsi:type="uml:Class" xmi:id="C1" name="InnerClass"/>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "ownership.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser(options=ParseOptions(include_model_root_node=True)).parse(str(model_path))
    edges = {edge.id: edge for edge in ir.edges}
    nodes = {node.id: node for node in ir.nodes}

    assert "model1" in nodes
    assert nodes["model1"].type == "Model"

    assert "model1__model_contains__pkg1" in edges
    assert edges["model1__model_contains__pkg1"].type == "contains"
    assert edges["model1__model_contains__pkg1"].data["derivedFrom"] == "modelOwnership"

    assert "pkg1__owns__C1" in edges
    assert edges["pkg1__owns__C1"].type == "contains"
    assert edges["pkg1__owns__C1"].data["derivedFrom"] == "xmlOwnership"


def test_uml_parser_without_model_root_node_skips_model_contains_edges(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:Package" xmi:id="pkg1" name="Pkg">
      <packagedElement xsi:type="uml:Class" xmi:id="C1" name="InnerClass"/>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "ownership-no-root.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser(options=ParseOptions(include_model_root_node=False)).parse(str(model_path))
    edge_ids = {edge.id for edge in ir.edges}
    node_ids = {node.id for node in ir.nodes}

    assert "model1" not in node_ids
    assert "model1__model_contains__pkg1" not in edge_ids


def test_uml_parser_materializes_reference_edges_from_node_data(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="M">
    <packagedElement xsi:type="uml:StateMachine" xmi:id="sm1" name="SM">
      <region xmi:id="r1" stateMachine="sm1">
        <subvertex xsi:type="uml:State" xmi:id="s1" name="S1" container="r1"/>
      </region>
    </packagedElement>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "references.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    ir, _stats = UMLXMIParser().parse(str(model_path))
    edges = {edge.id: edge for edge in ir.edges}

    assert "r1__ref__stateMachine__sm1" in edges
    assert edges["r1__ref__stateMachine__sm1"].type == "references"
    assert edges["r1__ref__stateMachine__sm1"].data["referenceKey"] == "stateMachine"


def test_uml_xmi_adapter_keeps_raw_record_name_model_placeholder(tmp_path):
    xmi = """<?xml version="1.0" encoding="UTF-8"?>
<xmi:XMI xmi:version="2.1"
    xmlns:xmi="http://schema.omg.org/spec/XMI/2.1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xmlns:uml="http://www.eclipse.org/uml2/5.0.0/UML">
  <uml:Model xmi:id="model1" name="model">
    <packagedElement xsi:type="uml:Class" xmi:id="C1" name="Class1"/>
  </uml:Model>
</xmi:XMI>
"""
    model_path = tmp_path / "record-name-normalization.xmi"
    model_path.write_text(xmi, encoding="utf-8")

    descriptor = resolve_parser("uml", "xmi")
    record = (
        descriptor.create_adapter()
        .parse_file(
            model_path,
            model_id=model_path.stem,
            options=ParserOptions({"include_model_root_node": False}),
        )
        .record
    )

    assert record.name == "model"
