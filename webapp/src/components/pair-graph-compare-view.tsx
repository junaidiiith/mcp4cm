import { useMemo } from "react";
import ModelGraphPreview, { type GraphCompareAnnotations } from "@/components/model-graph-preview";
import type { ModelInspectPayload } from "@/types";

type NodeKey = string;
type EdgeKey = string;
type CompareState = "shared" | "left-only" | "right-only";

function textAttr(attrs: Record<string, unknown> | undefined, key: "name" | "type" | "label" | "relationship") {
  const value = attrs?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function normalize(value: string) {
  return value.trim().toLowerCase();
}

function normalizeComparableString(value: string) {
  return value.replace(/0x[0-9a-f]+/gi, "0x...");
}

function stableComparableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableComparableValue);
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !["id", "xmi:id", "xmiId"].includes(key))
      .sort(([left], [right]) => left.localeCompare(right));
    return Object.fromEntries(entries.map(([key, entryValue]) => [key, stableComparableValue(entryValue)]));
  }
  if (typeof value === "string") return normalizeComparableString(value);
  return value;
}

function stableComparableJson(value: unknown) {
  return JSON.stringify(stableComparableValue(value));
}

function edgeType(edge: ModelInspectPayload["edges"][number]) {
  return normalize(textAttr(edge.attrs, "type") || textAttr(edge.attrs, "relationship") || textAttr(edge.attrs, "label"));
}

function baseNodeKey(node: ModelInspectPayload["nodes"][number]): NodeKey {
  const name = textAttr(node.attrs, "name");
  const type = textAttr(node.attrs, "type");
  if (name || type) return `named:${normalize(name)}\u0000${normalize(type)}`;
  return `attrs:${stableComparableJson(node.attrs || {})}`;
}

function edgeId(edge: ModelInspectPayload["edges"][number], index: number) {
  return edge.key ? `${edge.source}:${edge.target}:${edge.key}` : `${edge.source}:${edge.target}:${index}`;
}

function attrsWithoutIdentity(attrs: Record<string, unknown> | undefined) {
  if (!attrs) return {};
  const { id: _id, key: _key, ...rest } = attrs;
  return rest;
}

function buildNodeKeyMap(payload: ModelInspectPayload): Map<string, NodeKey> {
  let keys = new Map<string, NodeKey>();
  payload.nodes.forEach((node) => {
    keys.set(node.id, baseNodeKey(node));
  });

  for (let iteration = 0; iteration < 2; iteration += 1) {
    const nextKeys = new Map<string, NodeKey>();
    payload.nodes.forEach((node) => {
      const incidentEdges: string[] = [];
      payload.edges.forEach((edge) => {
        const type = edgeType(edge);
        if (edge.source === node.id) {
          incidentEdges.push(`out:${type}:${keys.get(edge.target) || ""}`);
        }
        if (edge.target === node.id) {
          incidentEdges.push(`in:${type}:${keys.get(edge.source) || ""}`);
        }
      });
      incidentEdges.sort();
      nextKeys.set(node.id, `${baseNodeKey(node)}\u0002${incidentEdges.join("\u0003")}`);
    });
    keys = nextKeys;
  }

  return keys;
}

function edgeKey(edge: ModelInspectPayload["edges"][number], nodeKeysById: Map<string, NodeKey>): EdgeKey {
  return [
    nodeKeysById.get(edge.source) || "",
    edgeType(edge),
    stableComparableJson(attrsWithoutIdentity(edge.attrs)),
    nodeKeysById.get(edge.target) || "",
  ].join("\u0001");
}

function countByValue(values: Iterable<string>) {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return counts;
}

function buildAnnotations(
  current: ModelInspectPayload,
  other: ModelInspectPayload,
  uniqueState: Exclude<CompareState, "shared">,
): GraphCompareAnnotations {
  const currentNodeKeys = buildNodeKeyMap(current);
  const otherNodeKeys = buildNodeKeyMap(other);
  const remainingOtherNodeKeys = countByValue(otherNodeKeys.values());

  const nodeStates: NonNullable<GraphCompareAnnotations["nodeStates"]> = {};
  current.nodes.forEach((node) => {
    const key = currentNodeKeys.get(node.id);
    const remainingMatches = key ? remainingOtherNodeKeys.get(key) || 0 : 0;
    if (key && remainingMatches > 0) {
      nodeStates[node.id] = "shared";
      remainingOtherNodeKeys.set(key, remainingMatches - 1);
    } else {
      nodeStates[node.id] = uniqueState;
    }
  });

  const remainingOtherEdgeKeys = countByValue(other.edges.map((edge) => edgeKey(edge, otherNodeKeys)));
  const edgeStates: NonNullable<GraphCompareAnnotations["edgeStates"]> = {};
  current.edges.forEach((edge, index) => {
    const key = edgeKey(edge, currentNodeKeys);
    const remainingMatches = remainingOtherEdgeKeys.get(key) || 0;
    if (remainingMatches > 0) {
      edgeStates[edgeId(edge, index)] = "shared";
      remainingOtherEdgeKeys.set(key, remainingMatches - 1);
    } else {
      edgeStates[edgeId(edge, index)] = uniqueState;
    }
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
          <span>{Math.min(leftNodes.shared, rightNodes.shared)} shared node(s), {Math.min(leftEdges.shared, rightEdges.shared)} shared edge(s)</span>
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
          <ModelGraphPreview payload={left} mode="compare" compareAnnotations={leftAnnotations} />
        </div>
        <div className="pairComparePane">
          <div className="pairComparePaneHeader">
            <h4>Right</h4>
            <p>{right.model.id}</p>
          </div>
          <ModelGraphPreview payload={right} mode="compare" compareAnnotations={rightAnnotations} />
        </div>
      </div>
    </div>
  );
}
