import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Crosshair, Maximize2 } from "lucide-react";
import Cytoscape from "cytoscape";
import type cytoscape from "cytoscape";
import CytoscapeComponent from "react-cytoscapejs";
import coseBilkent from "cytoscape-cose-bilkent";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { ModelInspectPayload } from "@/types";

Cytoscape.use(coseBilkent);

type GraphLayoutName = "cose" | "cose-bilkent" | "grid";
type CompareState = "shared" | "left-only" | "right-only";

const LARGE_GRAPH_NODE_THRESHOLD = 1000;

export interface GraphCompareAnnotations {
  nodeStates?: Record<string, CompareState>;
  edgeStates?: Record<string, CompareState>;
}

type SelectedElement =
  | { kind: "node"; id: string; node: ModelInspectPayload["nodes"][number] }
  | { kind: "edge"; id: string; edge: ModelInspectPayload["edges"][number] }
  | null;

interface EnrichedNode {
  id: string;
  name: string;
  type: string;
  missingName: boolean;
  missingType: boolean;
  degree: number;
  size: number;
  color: string;
  compareState?: CompareState;
  raw: ModelInspectPayload["nodes"][number];
}

interface EnrichedEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  missingType: boolean;
  compareState?: CompareState;
  raw: ModelInspectPayload["edges"][number];
}

const typePalette = [
  "#0f766e",
  "#2563eb",
  "#9333ea",
  "#c2410c",
  "#b42318",
  "#2f6f4e",
  "#7c3aed",
  "#0e7490",
  "#a16207",
  "#be185d",
  "#475569",
  "#15803d",
];

const neutralTypeColor = "#8a98a8";

function textAttr(attrs: Record<string, unknown> | undefined, key: "name" | "type") {
  const value = attrs?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

function colorForType(type: string) {
  if (!type) return neutralTypeColor;
  let hash = 0;
  for (let index = 0; index < type.length; index += 1) {
    hash = (hash * 31 + type.charCodeAt(index)) >>> 0;
  }
  return typePalette[hash % typePalette.length];
}

function sizeForDegree(degree: number) {
  return Math.max(18, Math.min(42, 18 + Math.log2(degree + 1) * 4));
}

function renderAttributeValue(value: unknown) {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean" || value === null) return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function lowerIncludes(value: string, query: string) {
  return value.toLowerCase().includes(query);
}

export default function ModelGraphPreview({
  payload,
  mode = "single",
  compareAnnotations,
}: {
  payload: ModelInspectPayload;
  mode?: "single" | "compare";
  compareAnnotations?: GraphCompareAnnotations;
}) {
  const [cy, setCy] = useState<cytoscape.Core | null>(null);
  const [selectedElement, setSelectedElement] = useState<SelectedElement>(null);
  const [layoutName, setLayoutName] = useState<GraphLayoutName>("cose");
  const [showLabels, setShowLabels] = useState(false);
  const [nodeQuery, setNodeQuery] = useState("");
  const [edgeQuery, setEdgeQuery] = useState("");
  const isLargeGraph = payload.model.nodeCount >= LARGE_GRAPH_NODE_THRESHOLD;
  const effectiveLayoutName: GraphLayoutName = isLargeGraph ? "grid" : layoutName;

  const degreeByNode = useMemo(() => {
    const degrees = new Map<string, number>();
    payload.nodes.forEach((node) => degrees.set(node.id, 0));
    payload.edges.forEach((edge) => {
      degrees.set(edge.source, (degrees.get(edge.source) || 0) + 1);
      degrees.set(edge.target, (degrees.get(edge.target) || 0) + 1);
    });
    return degrees;
  }, [payload.edges, payload.nodes]);

  const nodes = useMemo<EnrichedNode[]>(
    () =>
      payload.nodes.map((node) => {
        const name = textAttr(node.attrs, "name");
        const type = textAttr(node.attrs, "type");
        const degree = degreeByNode.get(node.id) || 0;
        return {
          id: node.id,
          name,
          type,
          missingName: !name,
          missingType: !type,
          degree,
          size: sizeForDegree(degree),
          color: colorForType(type),
          compareState: compareAnnotations?.nodeStates?.[node.id],
          raw: node,
        };
      }),
    [compareAnnotations?.nodeStates, degreeByNode, payload.nodes],
  );

  const edgeIds = useMemo(
    () =>
      payload.edges.map((edge, index) =>
        edge.key ? `${edge.source}:${edge.target}:${edge.key}` : `${edge.source}:${edge.target}:${index}`,
      ),
    [payload.edges],
  );

  const edges = useMemo<EnrichedEdge[]>(
    () =>
      payload.edges.map((edge, index) => {
        const id = edgeIds[index];
        const type = textAttr(edge.attrs, "type");
        return {
          id,
          source: edge.source,
          target: edge.target,
          type,
          missingType: !type,
          compareState: compareAnnotations?.edgeStates?.[id],
          raw: edge,
        };
      }),
    [compareAnnotations?.edgeStates, edgeIds, payload.edges],
  );

  const warnings = useMemo(() => {
    const missingNodeNames = nodes.filter((node) => node.missingName).length;
    const missingNodeTypes = nodes.filter((node) => node.missingType).length;
    const missingEdgeTypes = edges.filter((edge) => edge.missingType).length;
    return { missingNodeNames, missingNodeTypes, missingEdgeTypes };
  }, [edges, nodes]);

  const elements = useMemo<cytoscape.ElementDefinition[]>(() => {
    const graphNodes = nodes.map((node) => ({
      data: {
        id: node.id,
        nodeId: node.id,
        label: node.name || "Unknown",
        type: node.type || "Unknown",
        color: node.color,
        size: node.size,
        compareState: node.compareState || "",
      },
    }));
    const graphEdges = edges.map((edge, index) => ({
      data: {
        id: edge.id,
        edgeIndex: index,
        source: edge.source,
        target: edge.target,
        type: edge.type || "Unknown",
        color: colorForType(edge.type),
        compareState: edge.compareState || "",
      },
    }));
    return [...graphNodes, ...graphEdges];
  }, [edges, nodes]);

  const layout = useMemo<cytoscape.LayoutOptions>(
    () => ({
      name: effectiveLayoutName,
      fit: true,
      animate: false,
      padding: mode === "compare" ? 16 : 24,
    }),
    [effectiveLayoutName, mode],
  );

  const stylesheet = useMemo<cytoscape.StylesheetJsonBlock[]>(
    () => [
      {
        selector: "node",
        style: {
          label: showLabels ? "data(label)" : "",
          width: "data(size)",
          height: "data(size)",
          "font-size": 10,
          "background-color": "data(color)",
          "border-width": 1,
          "border-color": "#ffffff",
          color: "#1f2d38",
          "text-wrap": "wrap",
          "text-max-width": "110px",
          "text-valign": "bottom",
          "text-margin-y": 5,
        },
      },
      {
        selector: "edge",
        style: {
          width: 1.3,
          "line-color": "data(color)",
          "target-arrow-color": "data(color)",
          "target-arrow-shape": "triangle",
          "curve-style": "bezier",
          opacity: 0.72,
        },
      },
      {
        selector: "[compareState = 'shared']",
        style: {
          "border-width": 3,
          "border-color": "#16a34a",
          "line-color": "#16a34a",
          "target-arrow-color": "#16a34a",
        },
      },
      {
        selector: "[compareState = 'left-only']",
        style: {
          "border-width": 3,
          "border-color": "#2563eb",
          "line-color": "#2563eb",
          "target-arrow-color": "#2563eb",
        },
      },
      {
        selector: "[compareState = 'right-only']",
        style: {
          "border-width": 3,
          "border-color": "#f97316",
          "line-color": "#f97316",
          "target-arrow-color": "#f97316",
        },
      },
      {
        selector: ":selected",
        style: {
          "border-width": 4,
          "border-color": "#f19c38",
          "line-color": "#f19c38",
          "target-arrow-color": "#f19c38",
          "z-index": 20,
        },
      },
    ],
    [showLabels],
  );

  useEffect(() => {
    if (!cy) return;
    const onElementTap: cytoscape.EventHandler = (event) => {
      const element = event.target as cytoscape.NodeSingular | cytoscape.EdgeSingular;
      if (element.isNode()) {
        const nodeId = String(element.data("nodeId") || element.id());
        const node = payload.nodes.find((entry) => entry.id === nodeId);
        if (node) setSelectedElement({ kind: "node", id: nodeId, node });
        return;
      }
      if (element.isEdge()) {
        const edgeIndex = Number(element.data("edgeIndex"));
        if (Number.isInteger(edgeIndex) && payload.edges[edgeIndex]) {
          setSelectedElement({ kind: "edge", id: String(element.id()), edge: payload.edges[edgeIndex] });
        }
      }
    };
    const onBackgroundTap: cytoscape.EventHandler = (event) => {
      if (event.target === cy) setSelectedElement(null);
    };
    cy.on("tap", "node, edge", onElementTap);
    cy.on("tap", onBackgroundTap);
    return () => {
      cy.off("tap", "node, edge", onElementTap);
      cy.off("tap", onBackgroundTap);
    };
  }, [cy, payload.edges, payload.nodes]);

  useEffect(() => {
    setSelectedElement(null);
    setLayoutName("cose");
    setNodeQuery("");
    setEdgeQuery("");
  }, [payload.model.id]);

  useEffect(() => {
    if (!cy) return;
    cy.$(":selected").unselect();
    if (!selectedElement) return;
    const selected = cy.getElementById(selectedElement.id);
    if (selected.length) selected.select();
  }, [cy, selectedElement]);

  useEffect(() => {
    if (!cy) return;
    cy.layout(layout).run();
  }, [cy, layout]);

  const selectedAttributes = selectedElement
    ? (selectedElement.kind === "node" ? selectedElement.node.attrs : selectedElement.edge.attrs) || {}
    : {};
  const selectedAttributeEntries = Object.entries(selectedAttributes);

  const filteredNodes = useMemo(() => {
    const query = nodeQuery.trim().toLowerCase();
    if (!query) return nodes;
    return nodes.filter((node) =>
      [node.name || "Unknown", node.type || "Unknown", node.id, String(node.degree)].some((value) =>
        lowerIncludes(value, query),
      ),
    );
  }, [nodeQuery, nodes]);

  const filteredEdges = useMemo(() => {
    const query = edgeQuery.trim().toLowerCase();
    if (!query) return edges;
    return edges.filter((edge) =>
      [edge.source, edge.target, edge.type || "Unknown", edge.id].some((value) => lowerIncludes(value, query)),
    );
  }, [edgeQuery, edges]);

  function fitGraph() {
    cy?.fit(undefined, 24);
  }

  function rerunLayout() {
    if (!cy) return;
    cy.layout(layout).run();
  }

  function selectNode(node: EnrichedNode) {
    setSelectedElement({ kind: "node", id: node.id, node: node.raw });
    const element = cy?.getElementById(node.id);
    if (cy && element?.length) cy.center(element);
  }

  function selectEdge(edge: EnrichedEdge) {
    setSelectedElement({ kind: "edge", id: edge.id, edge: edge.raw });
    const element = cy?.getElementById(edge.id);
    if (cy && element?.length) cy.center(element);
  }

  return (
    <div className={`graphPreview ${mode === "compare" ? "compact" : ""}`}>
      <div className="graphMeta">
        <span><strong>Model:</strong> {payload.model.id}</span>
        <span><strong>Language:</strong> {payload.model.language}</span>
        <span><strong>Nodes:</strong> {payload.model.nodeCount}</span>
        <span><strong>Edges:</strong> {payload.model.edgeCount}</span>
      </div>

      {(warnings.missingNodeNames > 0 || warnings.missingNodeTypes > 0 || warnings.missingEdgeTypes > 0) && (
        <div className="graphWarnings">
          <AlertTriangle size={14} />
          {warnings.missingNodeNames > 0 && <span>{warnings.missingNodeNames} nodes missing name</span>}
          {warnings.missingNodeTypes > 0 && <span>{warnings.missingNodeTypes} nodes missing type</span>}
          {warnings.missingEdgeTypes > 0 && <span>{warnings.missingEdgeTypes} edges missing type</span>}
        </div>
      )}

      <div className="graphToolbar">
        <label>
          Layout
          <select
            value={effectiveLayoutName}
            disabled={isLargeGraph}
            onChange={(event) => setLayoutName(event.target.value as GraphLayoutName)}
          >
            <option value="cose">cose</option>
            <option value="cose-bilkent">cose-bilkent</option>
            <option value="grid">grid</option>
          </select>
        </label>
        {isLargeGraph && (
          <span className="graphToolbarHint">
            Grid layout is used automatically for graphs with {LARGE_GRAPH_NODE_THRESHOLD}+ nodes.
          </span>
        )}
        <label>
          Labels
          <select value={showLabels ? "all" : "off"} onChange={(event) => setShowLabels(event.target.value === "all")}>
            <option value="off">Off</option>
            <option value="all">All</option>
          </select>
        </label>
        <Button type="button" variant="secondary" size="sm" onClick={fitGraph}>
          <Maximize2 size={15} />
          Fit
        </Button>
        <Button type="button" variant="secondary" size="sm" onClick={rerunLayout}>
          <Crosshair size={15} />
          Reset
        </Button>
      </div>

      <CytoscapeComponent
        className="graphCanvas"
        elements={elements}
        layout={layout}
        stylesheet={stylesheet}
        wheelSensitivity={0.15}
        minZoom={0.08}
        maxZoom={3}
        cy={(instance: cytoscape.Core) => setCy(instance)}
      />

      <Tabs defaultValue="inspector" className="graphDetailTabs">
        <TabsList className="graphTabsList">
          <TabsTrigger value="inspector">Inspector</TabsTrigger>
          <TabsTrigger value="nodes">Nodes</TabsTrigger>
          <TabsTrigger value="edges">Edges</TabsTrigger>
        </TabsList>
        <TabsContent value="inspector">
          <div className="graphInspectorPanel">
            {!selectedElement ? (
              <p className="graphInspectorEmpty">Click a node or edge in the graph or table to inspect attributes.</p>
            ) : (
              <div className="graphInspectorContent">
                <div className="graphInspectorMeta">
                  <span><strong>Type:</strong> {selectedElement.kind}</span>
                  <span><strong>ID:</strong> {selectedElement.id}</span>
                  {selectedElement.kind === "edge" && (
                    <span><strong>Path:</strong> {selectedElement.edge.source} {"->"} {selectedElement.edge.target}</span>
                  )}
                </div>
                <div className="graphInspectorAttrs">
                  {selectedAttributeEntries.length ? selectedAttributeEntries.map(([key, value]) => (
                    <div key={key}>
                      <b>{key}</b>
                      <pre>{renderAttributeValue(value)}</pre>
                    </div>
                  )) : (
                    <p className="graphInspectorEmpty">No attributes found for this {selectedElement.kind}.</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </TabsContent>
        <TabsContent value="nodes">
          <div className="graphElementBrowser">
            <input
              value={nodeQuery}
              placeholder="Search nodes"
              onChange={(event) => setNodeQuery(event.target.value)}
            />
            <div className="graphTable">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Degree</th>
                    <th>ID</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredNodes.map((node) => (
                    <tr
                      key={node.id}
                      className={selectedElement?.kind === "node" && selectedElement.id === node.id ? "active" : ""}
                      onClick={() => selectNode(node)}
                    >
                      <td><strong>{node.name || "Unknown"}</strong></td>
                      <td><span className="typeSwatch" style={{ background: node.color }} />{node.type || "Unknown"}</td>
                      <td>{node.degree}</td>
                      <td><code>{node.id}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="edges">
          <div className="graphElementBrowser">
            <input
              value={edgeQuery}
              placeholder="Search edges"
              onChange={(event) => setEdgeQuery(event.target.value)}
            />
            <div className="graphTable">
              <table>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Type</th>
                    <th>Target</th>
                    <th>ID</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEdges.map((edge) => (
                    <tr
                      key={edge.id}
                      className={selectedElement?.kind === "edge" && selectedElement.id === edge.id ? "active" : ""}
                      onClick={() => selectEdge(edge)}
                    >
                      <td><code>{edge.source}</code></td>
                      <td><span className="typeSwatch" style={{ background: colorForType(edge.type) }} />{edge.type || "Unknown"}</td>
                      <td><code>{edge.target}</code></td>
                      <td><code>{edge.id}</code></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
