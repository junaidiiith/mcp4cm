from mcp4cm.core import Dataset
from mcp4cm.gnn import GNNTrainingConfig, gnn_duplicate_pairs, gnn_graph_embeddings
from mcp4cm.parsers.archimate_json.parser import ArchimateJsonParser


def test_gnn_configuration_validates_training_ranges():
    GNNTrainingConfig().validate()

    try:
        GNNTrainingConfig(edge_dropout=1.0).validate()
    except ValueError as exc:
        assert "edge_dropout" in str(exc)
    else:  # pragma: no cover - protects the validation contract
        raise AssertionError("invalid GraphCL augmentation rate was accepted")


def test_gnn_handles_empty_and_single_graph_datasets_without_ml_dependencies():
    assert gnn_graph_embeddings(Dataset([], "archimate")) == {}

    record = ArchimateJsonParser().parse({"elements": [], "relationships": []}, model_id="empty")
    assert gnn_duplicate_pairs(Dataset([record], "archimate")) == []
