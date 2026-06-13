import networkx as nx
import pytest

from mcp4cm.core import Dataset, ModelRecord
from mcp4cm.dummy import derive_nodes, evaluate_dummy_filters
from mcp4cm.duplicates import detect_duplicates_by_node_name_hash, hashable_name_tokens, record_tokens
from mcp4cm.name_classification import (
    TokenizerConfig,
    classify_name_slot,
    extract_node_labels,
    normalize_name,
    normalize_type,
    tokenize_label,
)
from mcp4cm.statistics import typed_name_entries


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" Customer ", "customer"),
        ("Customer   Order", "customer order"),
        ("CustomerOrder", "customer order"),
        ("creationDate", "creation date"),
        ("get_data", "get data"),
        ("Real-time data acquisition", "real time data acquisition"),
        ("my.datatype", "my datatype"),
        ("OrderId", "order id"),
        ("userID", "user id"),
        ("PHP 7.x", "php 7 x"),
        ("List<Order>", "list order"),
        ("...", ""),
        ("Gestão de SLA", "gestão de sla"),
        ("退出與取回卡片", "退出與取回卡片"),
        ("Программист", "программист"),
    ],
)
def test_normalize_name_contract(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected", "tokens"),
    [
        ("Class", "class", ("class",)),
        ("DecisionNode", "decision node", ("decision", "node")),
        ("ActivityFinalNode", "activity final node", ("activity", "final", "node")),
        ("BusinessProcess", "business process", ("business", "process")),
        ("Application Component", "application component", ("application", "component")),
        ("EClass", "eclass", ("eclass",)),
        ("EAttribute", "eattribute", ("eattribute",)),
        ("EReference", "ereference", ("ereference",)),
    ],
)
def test_normalize_type_contract(raw, expected, tokens):
    normalized = normalize_type(raw)

    assert normalized == expected
    assert tokenize_label(normalized) == tokens


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", ()),
        ("customer order", ("customer", "order")),
        ("creation date", ("creation", "date")),
        ("order id", ("order", "id")),
        ("php 7 x", ("php", "x")),
        ("list order", ("list", "order")),
        ("gestão de sla", ("gestão", "de", "sla")),
        ("退出與取回卡片", ("退出與取回卡片",)),
        ("customer customer", ("customer", "customer")),
    ],
)
def test_tokenizer_default_contract(value, expected):
    assert tokenize_label(value) == expected


def test_tokenizer_configuration_variants():
    assert tokenize_label("php 7 x", TokenizerConfig(keep_numeric_tokens=True)) == ("php", "7", "x")
    assert tokenize_label("customer customer order", TokenizerConfig(deduplicate=True)) == ("customer", "order")
    assert tokenize_label("a b id", TokenizerConfig(min_token_length=2)) == ("id",)
    assert tokenize_label("gestão de sla", TokenizerConfig(stopwords=("de",))) == ("gestão", "sla")


@pytest.mark.parametrize(
    ("normalized_name", "normalized_type", "name_tokens", "expected"),
    [
        ("", "class", (), "missing"),
        ("class", "class", ("class",), "type_like"),
        ("class 2", "class", ("class",), "type_like"),
        ("entity 1", "business object", ("entity",), "placeholder"),
        ("aggregate 1", "grouping", ("aggregate",), "placeholder"),
        ("class a", "class", ("class", "a"), "placeholder"),
        ("junction copy", "junction", ("junction", "copy"), "placeholder"),
        ("test", "class", ("test",), "placeholder"),
        ("todo", "action", ("todo",), "placeholder"),
        ("customer", "class", ("customer",), "semantic"),
        ("name", "property", ("name",), "semantic"),
        ("id", "property", ("id",), "semantic"),
    ],
)
def test_classifier_contract(normalized_name, normalized_type, name_tokens, expected):
    result = classify_name_slot(
        normalized_name,
        normalized_type,
        normalized_name=normalized_name,
        normalized_type=normalized_type,
        name_tokens=name_tokens,
    )

    assert result.classification == expected


@pytest.mark.parametrize(
    ("case_id", "raw_name", "raw_type", "normalized_name", "normalized_type", "name_tokens", "type_tokens", "classification"),
    [
        ("missing-empty", "", "Class", "", "class", (), ("class",), "missing"),
        ("missing-whitespace", "   ", "Class", "", "class", (), ("class",), "missing"),
        ("missing-punctuation", "...", "BusinessObject", "", "business object", (), ("business", "object"), "missing"),
        ("type-exact", "InitialNode", "InitialNode", "initial node", "initial node", ("initial", "node"), ("initial", "node"), "type_like"),
        ("type-numbered-suffix", "DecisionNode2", "DecisionNode", "decision node2", "decision node", ("decision", "node2"), ("decision", "node"), "type_like"),
        ("type-spaced-vs-camel", "Business Process", "BusinessProcess", "business process", "business process", ("business", "process"), ("business", "process"), "type_like"),
        ("type-model-root", "model", "Model", "model", "model", ("model",), ("model",), "type_like"),
        ("placeholder-numbered-entity", "entity 1", "BusinessObject", "entity 1", "business object", ("entity",), ("business", "object"), "placeholder"),
        ("placeholder-numbered-class", "class 1", "ApplicationComponent", "class 1", "application component", ("class",), ("application", "component"), "placeholder"),
        ("placeholder-operation-template", "privateOperation", "Operation", "private operation", "operation", ("private", "operation"), ("operation",), "placeholder"),
        ("placeholder-attribute-template", "publicAttribute", "Property", "public attribute", "property", ("public", "attribute"), ("property",), "placeholder"),
        ("placeholder-att-letter", "attB", "Property", "att b", "property", ("att", "b"), ("property",), "placeholder"),
        ("placeholder-type-letter-suffix", "ClassA", "Class", "class a", "class", ("class", "a"), ("class",), "placeholder"),
        ("placeholder-copy-type-label", "Junction (copy)", "Junction", "junction copy", "junction", ("junction", "copy"), ("junction",), "placeholder"),
        ("semantic-pascal-domain", "ShoppingCart", "Class", "shopping cart", "class", ("shopping", "cart"), ("class",), "semantic"),
        ("semantic-camel-property", "creationDate", "Property", "creation date", "property", ("creation", "date"), ("property",), "semantic"),
        ("semantic-id-property", "OrderId", "Property", "order id", "property", ("order", "id"), ("property",), "semantic"),
        ("semantic-snake-method", "get_data", "Operation", "get data", "operation", ("get", "data"), ("operation",), "semantic"),
        ("semantic-generic-syntax", "List<Order>", "Parameter", "list order", "parameter", ("list", "order"), ("parameter",), "semantic"),
        ("semantic-version-tech", "PHP 7.x", "TechnologyService", "php 7 x", "technology service", ("php", "x"), ("technology", "service"), "semantic"),
        ("semantic-accented", "Gestão de SLA", "BusinessProcess", "gestão de sla", "business process", ("gestão", "de", "sla"), ("business", "process"), "semantic"),
        ("semantic-cyrillic", "Программист", "BusinessRole", "программист", "business role", ("программист",), ("business", "role"), "semantic"),
        ("semantic-cjk", "退出與取回卡片", "Action", "退出與取回卡片", "action", ("退出與取回卡片",), ("action",), "semantic"),
    ],
)
def test_extracted_label_golden_cases(
    case_id,
    raw_name,
    raw_type,
    normalized_name,
    normalized_type,
    name_tokens,
    type_tokens,
    classification,
):
    graph = nx.DiGraph()
    graph.add_node(case_id, name=raw_name, type=raw_type)
    record = ModelRecord(model_id="model-1", language="uml", graph=graph)

    label = extract_node_labels(record)[0]

    assert label.model_id == "model-1"
    assert label.element_id == case_id
    assert label.element_kind == "node"
    assert label.raw_name == raw_name
    assert label.raw_type == raw_type
    assert label.normalized_name == normalized_name
    assert label.normalized_type == normalized_type
    assert label.name_tokens == name_tokens
    assert label.type_tokens == type_tokens
    assert label.classification == classification


def test_extract_node_labels_uses_eclass_only_as_type_fallback():
    graph = nx.DiGraph()
    graph.add_node("fallback", name="Customer", eClass="EClass")
    graph.add_node("type-wins", name="Customer", type="Class", eClass="EClass")
    record = ModelRecord(model_id="model-1", language="ecore", graph=graph)

    labels = {label.element_id: label for label in extract_node_labels(record)}

    assert labels["fallback"].raw_type == "EClass"
    assert labels["fallback"].normalized_type == "eclass"
    assert labels["type-wins"].raw_type == "Class"
    assert labels["type-wins"].normalized_type == "class"


def test_record_level_domain_fixture_keeps_statistics_dummy_and_duplicates_aligned():
    graph = nx.DiGraph()
    graph.add_node("semantic-class", name="ShoppingCart", type="Class")
    graph.add_node("semantic-property", name="creationDate", type="Property")
    graph.add_node("type-like", name="DecisionNode2", type="DecisionNode")
    graph.add_node("placeholder", name="publicAttribute", type="Property")
    graph.add_node("missing", name="...", type="BusinessObject")
    record = ModelRecord(model_id="domain", language="uml", graph=graph)

    labels = {label.element_id: label for label in extract_node_labels(record)}
    statistics_entries = {
        entry["name"]: (entry["classification"], entry["nameTokens"])
        for entry in typed_name_entries(record)
    }
    dummy_nodes = {
        node.normalized_name: (node.classification, node.tokens)
        for node in derive_nodes(record)
    }

    assert labels["semantic-class"].classification == "semantic"
    assert labels["semantic-class"].name_tokens == ("shopping", "cart")
    assert labels["semantic-property"].classification == "semantic"
    assert labels["type-like"].classification == "type_like"
    assert labels["placeholder"].classification == "placeholder"
    assert labels["missing"].classification == "missing"
    assert statistics_entries == dummy_nodes
    assert record_tokens(record, token_mode="names") == [
        "creation date",
        "decision node2",
        "public attribute",
        "shopping cart",
    ]
    assert hashable_name_tokens(record, include_types=True) == [
        "creation date\tproperty",
        "decision node2\tdecision node",
        "public attribute\tproperty",
        "shopping cart\tclass",
    ]


def test_record_level_placeholder_fixture_drives_dummy_and_duplicate_decisions_from_shared_labels():
    first_graph = nx.DiGraph()
    second_graph = nx.DiGraph()
    for graph in (first_graph, second_graph):
        graph.add_node("class", name="Class1", type="Class")
        graph.add_node("entity", name="entity 1", type="BusinessObject")
        graph.add_node("attribute", name="attB", type="Property")
        graph.add_node("copy", name="Junction (copy)", type="Junction")
        graph.add_node("todo", name="todo", type="Action")
        graph.add_edge("class", "entity", type="Association")
        graph.add_edge("entity", "attribute", type="Association")
        graph.add_edge("attribute", "copy", type="Association")
        graph.add_edge("copy", "todo", type="Association")

    first = ModelRecord(model_id="placeholder-a", language="uml", graph=first_graph)
    second = ModelRecord(model_id="placeholder-b", language="uml", graph=second_graph)
    dataset = Dataset([first, second], "uml")

    labels = {label.element_id: label for label in extract_node_labels(first)}
    assert {label.classification for label in labels.values()} == {"type_like", "placeholder"}
    assert labels["class"].classification == "type_like"
    assert labels["entity"].name_tokens == ("entity",)
    assert labels["attribute"].name_tokens == ("att", "b")
    assert labels["copy"].normalized_name == "junction copy"

    evaluation = evaluate_dummy_filters(
        Dataset([first], "uml"),
        filter_configs=[
            {"id": "placeholder_name_ratio", "enabled": True, "threshold": 0.5},
            {"id": "min_size", "enabled": False},
            {"id": "too_few_named_elements", "enabled": False},
            {"id": "short_median_name_length", "enabled": False},
            {"id": "low_vocabulary", "enabled": False},
            {"id": "type_like_name_ratio", "enabled": False},
            {"id": "name_repetition_ratio", "enabled": False},
            {"id": "regex_rule", "enabled": False},
        ],
    )
    assert evaluation.model_outcomes[0].removed is True
    assert evaluation.model_outcomes[0].primary_removal_reason == "placeholder_name_ratio"

    groups = detect_duplicates_by_node_name_hash(dataset)
    assert len(groups) == 1
    assert groups[0].model_ids == ("placeholder-a", "placeholder-b")
