from mcp4cm.core import Dataset
from mcp4cm.dummy import (
    archimate_filters,
    archimate_generic_numbered_filter,
    archimate_new_model_filter,
    detect_dummy_models,
    ecore_filters,
    summarize_filters_by_language,
    summarize_filters,
    uml_filters,
)
from mcp4cm.duplicates import (
    detect_duplicates_by_hash,
    detect_duplicates_by_node_name_hash,
    detect_duplicates_by_node_name_type_hash,
    graph_isomorphism_pairs,
    graph_similarity_pairs,
    tfidf_duplicate_by_names,
    tfidf_duplicate_by_names_and_types,
    vote_duplicate_pairs,
)
from mcp4cm.loading import load_eamodelset
from mcp4cm.parsers.archimate import ArchimateParser
from mcp4cm.parsers.modelset import EcoreParser, UMLParser


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
    record = ArchimateParser().parse(raw)
    assert record.node_count == 2
    assert record.edge_count == 1
    assert "App" in record.names


def test_hash_duplicate_detection_smoke():
    parser = ArchimateParser()
    raw = {
        "elements": [{"id": "a", "name": "Foo", "type": "ApplicationComponent"}],
        "relationships": [],
    }
    first = parser.parse(raw, model_id="one")
    second = parser.parse(raw, model_id="two")
    groups = detect_duplicates_by_hash(Dataset([first, second], "archimate"))
    assert len(groups) == 1
    assert groups[0].model_ids == ("one", "two")


def test_duplicate_hash_modes_use_names_and_name_types():
    parser = ArchimateParser()
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


def test_tfidf_duplicate_modes_and_graph_similarity():
    parser = ArchimateParser()
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


def test_graph_isomorphism_modes():
    parser = ArchimateParser()
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
                {"id": "x", "name": "Invoice", "type": "BusinessObject"},
                {"id": "y", "name": "Supplier", "type": "BusinessActor"},
            ],
            "relationships": [{"id": "r2", "sourceId": "y", "targetId": "x", "type": "Association"}],
        },
        model_id="second",
    )

    dataset = Dataset([first, second], "archimate")

    assert len(graph_isomorphism_pairs(dataset, mode="structure")) == 1
    assert len(graph_isomorphism_pairs(dataset, mode="types")) == 1
    assert graph_isomorphism_pairs(dataset, mode="names_types") == []


def test_duplicate_voting_combines_techniques():
    parser = ArchimateParser()
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
    parser = ArchimateParser()
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
    findings = detect_dummy_models(Dataset([record], "archimate"))
    assert findings


def test_archimate_filters_detect_type_name_templates():
    parser = ArchimateParser()
    record = parser.parse(
        {
            "archimateId": "archimate-template",
            "name": "Template",
            "elements": [
                {"id": "a", "name": "Business Process", "type": "BusinessProcess"},
                {"id": "b", "name": "Application Component", "type": "ApplicationComponent"},
                {"id": "c", "name": "Data Object", "type": "DataObject"},
                {"id": "d", "name": "Business Actor", "type": "BusinessActor"},
                {"id": "e", "name": "Node", "type": "Node"},
            ],
            "relationships": [],
        }
    )

    findings = detect_dummy_models(Dataset([record], "archimate"), filters=archimate_filters())

    assert findings
    assert findings[0].reason == "archimate_type_names"


def test_archimate_filter_summary_counts_cumulatively():
    parser = ArchimateParser()
    new_model = parser.parse(
        {
            "archimateId": "new-model",
            "name": "(new model)",
            "elements": [{"id": str(index), "name": f"Order {index}", "type": "BusinessObject"} for index in range(5)],
            "relationships": [],
        }
    )
    numbered = parser.parse(
        {
            "archimateId": "numbered",
            "name": "Numbered",
            "elements": [{"id": str(index), "name": f"Entity {index}", "type": "BusinessObject"} for index in range(5)],
            "relationships": [],
        }
    )

    summaries = summarize_filters(
        Dataset([new_model, numbered], "archimate"),
        filters=[archimate_new_model_filter(), archimate_generic_numbered_filter()],
    )

    assert [(row.filter_name, row.filtered_count, row.remaining_count) for row in summaries] == [
        ("archimate_new_model_filter", 1, 1),
        ("archimate_generic_numbered_filter", 1, 0),
    ]


def test_uml_dummy_patterns_detect_placeholder_classes():
    raw = {
        "ids": "uml-dummy",
        "model_type": "uml",
        "txt": "class: my class 1\nclass: my class 2",
        "graph": {
            "directed": True,
            "multigraph": False,
            "nodes": [
                {"id": 1, "name": "class a", "eClass": "Class"},
                {"id": 2, "name": "class 1", "eClass": "Class"},
                {"id": 3, "name": "my class", "eClass": "Class"},
                {"id": 4, "name": "Order", "eClass": "Class"},
                {"id": 5, "name": "Customer", "eClass": "Class"},
            ],
            "links": [],
        },
    }
    record = UMLParser().parse(raw)
    findings = detect_dummy_models(Dataset([record], "uml"))
    assert findings[0].reason in {"uml_dummy_classes", "uml_dummy_names"}


def test_uml_filters_can_be_passed_explicitly():
    raw = {
        "ids": "uml-control-flow",
        "model_type": "uml",
        "txt": "",
        "graph": {
            "directed": True,
            "multigraph": False,
            "nodes": [
                {"id": 1, "name": "control flow", "eClass": "ControlFlow"},
                {"id": 2, "name": "control-flow", "eClass": "ControlFlow"},
                {"id": 3, "name": "control flow", "eClass": "ControlFlow"},
                {"id": 4, "name": "control flow", "eClass": "ControlFlow"},
                {"id": 5, "name": "control flow", "eClass": "ControlFlow"},
            ],
            "links": [],
        },
    }
    record = UMLParser().parse(raw)
    findings = detect_dummy_models(Dataset([record], "uml"), filters=uml_filters())
    assert findings
    assert findings[0].reason == "uml_dummy_keywords"


def test_ecore_filters_detect_numbered_placeholders():
    raw = {
        "ids": "ecore-dummy",
        "model_type": "ecore",
        "txt": "",
        "graph": {
            "directed": True,
            "multigraph": False,
            "nodes": [
                {"id": 1, "name": "Entity 1", "eClass": "EClass"},
                {"id": 2, "name": "Entity 2", "eClass": "EClass"},
                {"id": 3, "name": "Entity 3", "eClass": "EClass"},
                {"id": 4, "name": "Entity 4", "eClass": "EClass"},
                {"id": 5, "name": "Order", "eClass": "EClass"},
            ],
            "links": [],
        },
    }
    record = EcoreParser().parse(raw)
    findings = detect_dummy_models(Dataset([record], "ecore"), filters=ecore_filters())
    assert findings
    assert findings[0].reason == "ecore_generic_numbered_names"


def test_filter_summary_groups_mixed_modelset_by_language():
    uml = UMLParser().parse(
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
    ecore = EcoreParser().parse(
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
            (
                '{"archimateId": "%s", "name": "%s", "language": "%s", '
                '"elements": [], "relationships": []}'
            )
            % (model_id, model_id, language),
            encoding="utf-8",
        )

    dataset = load_eamodelset(tmp_path, language="en")

    assert len(dataset) == 1
    assert dataset[0].model_id == "english"


def test_language_filter_accepts_multiple_values(tmp_path):
    for model_id, language in [("english", "en"), ("german", "de"), ("spanish", "es")]:
        model_dir = tmp_path / model_id
        model_dir.mkdir()
        (model_dir / "model.json").write_text(
            (
                '{"archimateId": "%s", "name": "%s", "language": "%s", '
                '"elements": [], "relationships": []}'
            )
            % (model_id, model_id, language),
            encoding="utf-8",
        )

    dataset = load_eamodelset(tmp_path, language={"en", "es"})

    assert dataset.ids() == ["english", "spanish"]
