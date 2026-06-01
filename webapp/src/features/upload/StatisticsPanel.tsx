import { useMemo, useState } from "react";
import { AlertTriangle, BarChart3, FileWarning, Info, Loader2, Plus } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type {
  ParsedModelSummary,
  StatisticsPayload,
  UploadParseJob,
  UploadSummary,
  WarningEntry,
} from "../../types";
import { round } from "../../utils";

export function StatisticsPanel({
  uploadSummary,
  parsedModels,
  warningsList,
  stats,
  statsLoading,
  uploadParseJob,
  onInspect,
}: {
  uploadSummary: UploadSummary | null;
  parsedModels: ParsedModelSummary[];
  warningsList: WarningEntry[];
  stats: StatisticsPayload | null;
  statsLoading: boolean;
  uploadParseJob: UploadParseJob | null;
  onInspect: (row: ParsedModelSummary) => void;
}) {
  return (
    <Card className="panel" id="stats">
      <CardHeader className="panelHeader">
        <h2>
          <BarChart3 size={20} />
          Descriptive Statistics
        </h2>
      </CardHeader>
      <CardContent>
        {uploadSummary && <UploadSummaryPanel summary={uploadSummary} />}
        {(uploadSummary?.records || 0) > 0 ? (
          <ParsedModelsTable models={parsedModels} warnings={warningsList} onInspect={onInspect} />
        ) : null}
        {stats ? (
          <Statistics stats={stats} />
        ) : statsLoading ? (
          <StatisticsLoading job={uploadParseJob} />
        ) : (
          <EmptyState text="Upload a dataset to see descriptive statistics." />
        )}
      </CardContent>
    </Card>
  );
}

function UploadSummaryPanel({ summary }: { summary: UploadSummary }) {
  const parsedModels = Number(summary.records || 0);
  const inputFiles = Number(summary.files || 0);
  const warnings = Number(summary.warnings || 0);
  const filesWithWarnings = Number(summary.warningFiles?.length || 0);
  const failed = Number(summary.errors || 0);
  const parserSource = summary.language && summary.format ? `${summary.language} / ${summary.format}` : "-";
  const cards = [
    { label: "Input Files", value: inputFiles, tone: "neutral" },
    { label: "Models Parsed", value: parsedModels, tone: "neutral" },
    { label: "Warnings", value: warnings, tone: warnings ? "warn" : "neutral" },
    { label: "Models with Warnings", value: filesWithWarnings, tone: filesWithWarnings ? "warn" : "neutral" },
    { label: "Errors", value: failed, tone: failed ? "error" : "neutral" },
    { label: "Parser Source", value: parserSource, tone: "neutral" },
  ];
  return (
    <div className="summaryCards">
      {cards.map((card) => (
        <div className={`summaryCard ${card.tone}`} key={card.label}>
          <span>{card.label}</span>
          <strong>{card.value}</strong>
        </div>
      ))}
      {failed ? (
        <p className="summaryHint">Some inputs failed while parsing.</p>
      ) : (
        <p className="summaryHint neutral">Parsing completed without parse errors.</p>
      )}
      <DatasetQuality summary={summary} />
    </div>
  );
}

function DatasetQuality({ summary }: { summary: UploadSummary }) {
  const emptyFiles = summary.emptyFiles || [];
  const invalidFiles = summary.invalidFiles || [];
  const ignoredFiles = summary.ignoredFiles || [];
  if (!emptyFiles.length && !invalidFiles.length && !ignoredFiles.length) return null;
  return (
    <div className="datasetQuality">
      <h3>
        <FileWarning size={16} />
        Dataset Quality Findings
      </h3>
      <p>These files were excluded before model parsing.</p>
      <div className="qualityFindingGrid">
        <QualityFinding title="Empty files" files={emptyFiles} />
        <QualityFinding title="Invalid XML files" files={invalidFiles} />
        <QualityFinding title="Ignored metadata files" files={ignoredFiles} />
      </div>
    </div>
  );
}

function QualityFinding({ title, files }: { title: string; files: string[] }) {
  return (
    <details className="qualityFinding" open={files.length > 0}>
      <summary>
        <AlertTriangle size={15} />
        {title} <b>{files.length}</b>
      </summary>
      {files.length ? <ul>{files.map((file) => <li key={file}>{file}</li>)}</ul> : <p>None</p>}
    </details>
  );
}

function StatisticsLoading({ job }: { job: UploadParseJob | null }) {
  const parseProcessed = Number(job?.parseProcessedFiles || 0);
  const parseTotal = Number(job?.parseTotalFiles || 0);
  const parseDone = parseTotal > 0 && parseProcessed >= parseTotal;
  const message = parseDone
    ? "Models parsed. Calculating descriptive statistics..."
    : "Parsing models and collecting descriptive statistics...";
  return (
    <div className="statsLoading">
      <Loader2 className="spin" size={16} />
      <span>{message}</span>
    </div>
  );
}

function ParsedModelsTable({
  models,
  warnings,
  onInspect,
}: {
  models: ParsedModelSummary[];
  warnings: WarningEntry[];
  onInspect: (row: ParsedModelSummary) => void;
}) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sort, setSort] = useState<{ key: "nodeCount" | "edgeCount"; direction: "asc" | "desc" } | null>(null);
  const warningsByModelId = useMemo(() => {
    const map = new Map<string, WarningEntry[]>();
    for (const warning of warnings) {
      const modelId = warning.modelId || "";
      if (!modelId) continue;
      if (!map.has(modelId)) map.set(modelId, []);
      map.get(modelId)!.push(warning);
    }
    return map;
  }, [warnings]);
  const types = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of models) {
      for (const [type, count] of Object.entries(row.types || {})) {
        counts[type] = (counts[type] || 0) + Number(count || 0);
      }
    }
    return Object.entries(counts).sort(([, left], [, right]) => right - left);
  }, [models]);

  const filteredModels = models.filter((row) => {
    if (typeFilter !== "all" && !(row.types || {})[typeFilter]) return false;
    if (!query.trim()) return true;
    const lowered = query.trim().toLowerCase();
    const typeText = Object.entries(row.types || {})
      .map(([type, count]) => `${type} ${count}`)
      .join(" ")
      .toLowerCase();
    if (
      row.path.toLowerCase().includes(lowered) ||
      String(row.modelId || "").toLowerCase().includes(lowered) ||
      String(row.name || "").toLowerCase().includes(lowered) ||
      typeText.includes(lowered)
    ) {
      return true;
    }
    const rowWarnings = warningsByModelId.get(row.modelId) || [];
    return rowWarnings.some((warning) => `${warning.type} ${warning.message}`.toLowerCase().includes(lowered));
  });
  const displayedModels = sort
    ? [...filteredModels].sort((left, right) => {
        const difference = left[sort.key] - right[sort.key];
        return sort.direction === "asc" ? difference : -difference;
      })
    : filteredModels;
  const toggleSort = (key: "nodeCount" | "edgeCount") => {
    setSort((current) => ({
      key,
      direction: current?.key === key && current.direction === "desc" ? "asc" : "desc",
    }));
  };
  const sortIndicator = (key: "nodeCount" | "edgeCount") => sort?.key === key ? (sort.direction === "asc" ? " ▲" : " ▼") : "";

  return (
    <div className="warningTableWrap">
      <div className="warningTableHeader">
        <h3>Parsed Models</h3>
        <span>
          {filteredModels.length} of {models.length} models
        </span>
      </div>
      <div className="warningTypeChips">
        {types.map(([type, count]) => (
          <span key={type} className="warningTypeChip">
            {type} ({count})
          </span>
        ))}
      </div>
      <div className="warningFilters">
        <label>
          Warning category
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="all">All</option>
            {types.map(([type]) => (
              <option value={type} key={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          Search
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by model id, name, file path, warning type, or warning text"
          />
        </label>
      </div>
      <div className="warningScroll">
        <table className="parsedModelsTable">
          <colgroup>
            <col className="modelColumn" />
            <col className="fileColumn" />
            <col className="countColumn" />
            <col className="countColumn" />
            <col className="countColumn" />
            <col className="categoriesColumn" />
            <col className="inspectColumn" />
          </colgroup>
          <thead>
            <tr>
              <th>Model</th>
              <th>File</th>
              <th><button type="button" className="tableSortButton" onClick={() => toggleSort("nodeCount")}>Nodes{sortIndicator("nodeCount")}</button></th>
              <th><button type="button" className="tableSortButton" onClick={() => toggleSort("edgeCount")}>Edges{sortIndicator("edgeCount")}</button></th>
              <th>Warnings</th>
              <th>Warning Categories</th>
              <th>Inspect</th>
            </tr>
          </thead>
          <tbody>
            {displayedModels.map((row) => (
              <tr key={row.modelId}>
                <td>{row.modelId}</td>
                <td className="warningPath">{row.path}</td>
                <td>{row.nodeCount}</td>
                <td>{row.edgeCount}</td>
                <td>{row.warnings}</td>
                <td>
                  {Object.entries(row.types || {}).length
                    ? Object.entries(row.types || {})
                        .map(([key, value]) => `${key} (${value})`)
                        .join(", ")
                    : "-"}
                </td>
                <td>
                  <button type="button" className="tableInfoButton" onClick={() => onInspect(row)}>
                    <Info size={15} />
                    Info
                  </button>
                </td>
              </tr>
            ))}
            {!filteredModels.length && (
              <tr>
                <td colSpan={7}>No parsed models match the current filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Statistics({ stats }: { stats: StatisticsPayload }) {
  const summary = stats.summary;
  return (
    <div className="metricGrid">
      <Metric label="Models" value={summary.models} />
      <DistributionMetric label="Nodes per model" distribution={summary.nodes} />
      <DistributionMetric label="Edges per model" distribution={summary.edges} />
      <DistributionMetric label="Names per model" distribution={summary.names} />
    </div>
  );
}

function DistributionMetric({
  label,
  distribution,
}: {
  label: string;
  distribution: { min: number; max: number; mean: number; median: number };
}) {
  return (
    <div className="metric distributionMetric">
      <span>{label}</span>
      <strong>{round(distribution.mean)}</strong>
      <small>average</small>
      <div>
        <em>min {distribution.min}</em>
        <em>median {round(distribution.median)}</em>
        <em>max {distribution.max}</em>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="empty">
      <Plus size={18} />
      {text}
    </div>
  );
}
