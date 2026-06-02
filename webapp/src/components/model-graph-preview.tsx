import { useEffect, useMemo, useState } from "react";
import Cytoscape from "cytoscape";
import type cytoscape from "cytoscape";
import CytoscapeComponent from "react-cytoscapejs";
import coseBilkent from "cytoscape-cose-bilkent";
import type { ModelInspectPayload } from "@/types";

Cytoscape.use(coseBilkent);

type CoseBilkentLayoutOptions = cytoscape.LayoutOptions & {
  name: "cose-bilkent";
  fit: boolean;
  animate: boolean;
  padding: number;
};

const graphLayout: CoseBilkentLayoutOptions = { name: "cose-bilkent", fit: true, animate: false, padding: 20 };

export default function ModelGraphPreview({ payload }: { payload: ModelInspectPayload }) {
  const [cy, setCy] = useState<cytoscape.Core | null>(null);
  const [selectedElement, setSelectedElement] = useState<
    | { kind: "node"; id: string; node: ModelInspectPayload["nodes"][number] }
    | { kind: "edge"; id: string; edge: ModelInspectPayload["edges"][number] }
    | null
  >(null);

  const elements = useMemo<cytoscape.ElementDefinition[]>(() => {
    const nodes = payload.nodes.map((node) => ({
      data: {
        id: node.id,
        nodeId: node.id,
        label: String((node.attrs?.name as string) || node.id),
        type: String((node.attrs?.type as string) || ""),
      },
    }));
    const edges = payload.edges.map((edge, index) => ({
      data: {
        id: edge.key ? `${edge.source}:${edge.target}:${edge.key}` : `${edge.source}:${edge.target}:${index}`,
        edgeIndex: index,
        source: edge.source,
        target: edge.target,
        type: String((edge.attrs?.type as string) || ""),
      },
    }));
    return [...nodes, ...edges];
  }, [payload.edges, payload.nodes]);

  const stylesheet = useMemo<cytoscape.StylesheetJsonBlock[]>(() => [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "font-size": 10,
        "background-color": "#247f7f",
        color: "#12353a",
        "text-wrap": "wrap",
        "text-max-width": "90px",
      },
    },
    {
      selector: "edge",
      style: {
        width: 1.5,
        "line-color": "#8da1b2",
        "target-arrow-color": "#8da1b2",
        "target-arrow-shape": "triangle",
        "curve-style": "bezier",
      },
    },
    {
      selector: "edge[type != '']",
      style: {
        label: "data(type)",
        "font-size": 8,
        color: "#456",
      },
    },
    {
      selector: ":selected",
      style: {
        "border-width": 2,
        "border-color": "#f19c38",
        "line-color": "#f19c38",
        "target-arrow-color": "#f19c38",
      },
    },
  ], []);

  useEffect(() => {
    if (!cy) return;
    const onElementTap: cytoscape.EventHandler = (event) => {
      const element = event.target as cytoscape.NodeSingular | cytoscape.EdgeSingular;
      if (element.isNode()) {
        const nodeId = String(element.data("nodeId") || element.id());
        const node = payload.nodes.find((entry) => entry.id === nodeId);
        if (node) {
          setSelectedElement({ kind: "node", id: nodeId, node });
        }
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
      if (event.target === cy) {
        setSelectedElement(null);
      }
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
  }, [payload.model.id]);

  const selectedAttributes = selectedElement
    ? (selectedElement.kind === "node" ? selectedElement.node.attrs : selectedElement.edge.attrs) || {}
    : {};
  const selectedAttributeEntries = Object.entries(selectedAttributes);

  function renderAttributeValue(value: unknown) {
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean" || value === null) return String(value);
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }

  return (
    <div className="graphPreview">
      <div className="graphMeta">
        <span><strong>Model:</strong> {payload.model.id}</span>
        <span><strong>Language:</strong> {payload.model.language}</span>
        <span><strong>Nodes:</strong> {payload.model.nodeCount}</span>
        <span><strong>Edges:</strong> {payload.model.edgeCount}</span>
      </div>
      <CytoscapeComponent
        className="graphCanvas"
        elements={elements}
        layout={graphLayout}
        stylesheet={stylesheet}
        wheelSensitivity={0.15}
        minZoom={0.1}
        maxZoom={2.8}
        cy={(instance: cytoscape.Core) => setCy(instance)}
      />
      <div className="graphInspectorPanel">
        <h4>Inspector</h4>
        {!selectedElement ? (
          <p className="graphInspectorEmpty">Click a node or edge in the graph to inspect all attributes.</p>
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
      <div className="graphTables">
        <div>
          <h4>Nodes ({payload.nodes.length})</h4>
          <div className="tableLike">
            {payload.nodes.slice(0, 120).map((node) => (
              <div key={node.id}>
                <b>{node.id}</b>
                <span>{String((node.attrs?.type as string) || "")}</span>
                <small>{String((node.attrs?.name as string) || "")}</small>
              </div>
            ))}
          </div>
          {payload.truncated.nodes && <p className="truncHint">Node list truncated for performance.</p>}
        </div>
        <div>
          <h4>Edges ({payload.edges.length})</h4>
          <div className="tableLike">
            {payload.edges.slice(0, 120).map((edge, index) => (
              <div key={`${edge.source}:${edge.target}:${edge.key || index}`}>
                <b>{edge.source} {"->"} {edge.target}</b>
                <span>{String((edge.attrs?.type as string) || "")}</span>
              </div>
            ))}
          </div>
          {payload.truncated.edges && <p className="truncHint">Edge list truncated for performance.</p>}
        </div>
      </div>
    </div>
  );
}
