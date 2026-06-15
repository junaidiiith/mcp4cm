import { useMemo } from "react";
import ModelGraphPreview, { type GraphCompareAnnotations } from "@/components/model-graph-preview";
import type { ModelInspectPayload } from "@/types";

type NodeKey = string;

function textAttr(attrs: Record<string, unknown> | undefined, key: "name" | "type") {
  const value = attrs?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

function nodeKey(node: ModelInspectPayload["nodes"][number]): NodeKey | null {
  const name = textAttr(node.attrs, "name");
  const type = textAttr(node.attrs, "type");
  if (!name || !type) return null;
  return `${normalize(name)}\u0000${normalize(type)}`;
}

function edgeId(edge: ModelInspectPayload["edges"][number], index: number) {
  return edge.key ? `${edge.source}:${edge.target}:${edge.key}` : `${edge.source}:${edge.target}:${index}`;
}

function edgeKey(
  edge: ModelInspectPayload["edges"][number],
  nodeKeysById: Map<string, NodeKey>,
) {
  const sourceKey = nodeKeysById.get(edge.source);
  const targetKey = nodeKeysById.get(edge.target);
  const type = textAttr(edge.attrs, "type");
  if (!sourceKey || !targetKey || !type) return null;
  return `${sourceKey}\u0001${normalize(type)}\u0001${targetKey}`;
}

function buildNodeKeyMap(payload: ModelInspectPayload) {
  const keys = new Map<string, NodeKey>();
  payload.nodes.forEach((node) => {
    const key = nodeKey(node);
    if (key) keys.set(node.id, key);
  });
  return keys;
}

function buildAnnotations(
  current: ModelInspectPayload,
  other: ModelInspectPayload,
  uniqueState: "left-only" | "right-only",
): GraphCompareAnnotations {
  const currentNodeKeys = buildNodeKeyMap(current);
  const otherNodeKeys = buildNodeKeyMap(other);
  const otherNodeKeySet = new Set(otherNodeKeys.values());

  const nodeStates: NonNullable<GraphCompareAnnotations["nodeStates"]> = {};
  current.nodes.forEach((node) => {
    const key = currentNodeKeys.get(node.id);
    nodeStates[node.id] = key && otherNodeKeySet.has(key) ? "shared" : uniqueState;
  });

  const otherEdgeKeys = new Set(
    other.edges
      .map((edge) => edgeKey(edge, otherNodeKeys))
      .filter((key): key is string => Boolean(key)),
  );
  const edgeStates: NonNullable<GraphCompareAnnotations["edgeStates"]> = {};
  current.edges.forEach((edge, index) => {
    const key = edgeKey(edge, currentNodeKeys);
    edgeStates[edgeId(edge, index)] = key && otherEdgeKeys.has(key) ? "shared" : uniqueState;
  });

  return { nodeStates, edgeStates };
}

function countStates(states: Record<string, string> | undefined) {
  const values = Object.values(states || {});
  return {
    shared: values.filter((value) => value === "shared").length,
    unique: values.filter((value) => value !== "shared").length,
  };
}

export default function PairGraphCompareView({
  left,
  right,
}: {
  left: ModelInspectPayload;
  right: ModelInspectPayload;
}) {
  const leftAnnotations = useMemo(() => buildAnnotations(left, right, "left-only"), [left, right]);
  const rightAnnotations = useMemo(() => buildAnnotations(right, left, "right-only"), [left, right]);
  const leftNodes = countStates(leftAnnotations.nodeStates);
  const rightNodes = countStates(rightAnnotations.nodeStates);
  const leftEdges = countStates(leftAnnotations.edgeStates);
  const rightEdges = countStates(rightAnnotations.edgeStates);

  return (
    <div className="pairGraphCompare">
      <div className="pairGraphSummary">
        <div>
          <strong>Exact matches</strong>
          <span>{Math.min(leftNodes.shared, rightNodes.shared)} shared node key(s), {Math.min(leftEdges.shared, rightEdges.shared)} shared edge key(s)</span>
        </div>
        <div>
          <strong>Unique</strong>
          <span>{leftNodes.unique} left node(s), {rightNodes.unique} right node(s)</span>
        </div>
      </div>
      <div className="pairCompareGrid">
        <div className="pairComparePane">
          <div className="pairComparePaneHeader">
            <h4>Left</h4>
            <p>{left.model.id}</p>
          </div>
          <ModelGraphPreview payload={left} mode="compare" />
        </div>
        <div className="pairComparePane">
          <div className="pairComparePaneHeader">
            <h4>Right</h4>
            <p>{right.model.id}</p>
          </div>
          <ModelGraphPreview payload={right} mode="compare" />
        </div>
      </div>
    </div>
  );
}
