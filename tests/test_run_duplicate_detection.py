import json

from scripts.run_duplicate_detection import dataset_choices, dataset_parser, load_prepared_dataset


def bpmn_model(model_id: str, name: str) -> dict:
    return {
        "resourceId": model_id,
        "stencil": {"id": "BPMNDiagram"},
        "properties": {"name": name},
        "childShapes": [
            {
                "resourceId": f"{model_id}-task",
                "stencil": {"id": "Task"},
                "properties": {"name": "Create order"},
                "outgoing": [],
                "childShapes": [],
            }
        ],
    }


def test_sap_sam_bpmn_dataset_uses_signavio_parser(tmp_path):
    data_dir = tmp_path / "data"
    dataset_dir = data_dir / "sap-sam-bpmn"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "first.json").write_text(json.dumps(bpmn_model("first", "First")), encoding="utf-8")
    (dataset_dir / "second.json").write_text(json.dumps(bpmn_model("second", "Second")), encoding="utf-8")

    dataset = load_prepared_dataset(data_dir, "sap-sam-bpmn")

    assert dataset_parser("sap-sam-bpmn") == ("bpmn", "signavio")
    assert dataset.dataset_type == "sap-sam-bpmn"
    assert len(dataset.records) == 2
    assert {record.language for record in dataset.records} == {"bpmn"}


def test_dataset_choices_are_data_dir_folders(tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "eamodelset-json").mkdir(parents=True)
    (data_dir / "sap-sam-bpmn").mkdir()
    (data_dir / ".mcp4cm_embeddings").mkdir()
    (data_dir / "__MACOSX").mkdir()

    assert dataset_choices(data_dir) == ("eamodelset-json", "sap-sam-bpmn")
