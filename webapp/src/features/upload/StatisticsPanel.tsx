import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, BarChart3, ChevronLeft, ChevronRight, FileWarning, Info, Loader2, Plus } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { getDatasetModels } from "../../api";
import type {
  ParsedModelSummary,
  StatisticsPayload,
  UploadParseJob,
  UploadSummary,
  WarningEntry,
} from "../../types";
import { round } from "../../utils";

const DEFAULT_PAGE_SIZE = 50;

export function StatisticsPanel({
  datasetId,
  uploadSummary,
  warningsList,
  stats,
  statsLoading,
  uploadParseJob,
  onInspect,
}: {
  datasetId: string;
  uploadSummary: UploadSummary | null;
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
          Statistics
        </h2>
      </CardHeader>
      <CardContent>
        {uploadSummary && <UploadSummaryPanel summary={uploadSummary} />}
        {(uploadSummary?.records || 0) > 0 && datasetId ? (
          <ParsedModelsTable datasetId={datasetId} onInspect={onInspect} />
        ) : null}
        {stats ? (
          <Statistics stats={stats} />
        ) : statsLoading ? (
          <StatisticsLoading job={uploadParseJob} />
        ) : (
          <EmptyState text="Upload a dataset to see statistics." />
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
  const statisticsStage = job?.stage === "statistics";
  const message = statisticsStage || parseDone
    ? "Models parsed. Calculating statistics..."
    : "Parsing models and collecting statistics...";
  return (
    <div className="statsLoading">
      <Loader2 className="spin" size={16} />
      <span>{message}</span>
    </div>
  );
}

function ParsedModelsTable({
  datasetId,
  onInspect,
}: {
  datasetId: string;
  onInspect: (row: ParsedModelSummary) => void;
}) {
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sort, setSort] = useState<{ key: "nodeCount" | "edgeCount"; direction: "asc" | "desc" } | null>(null);
  const [page, setPage] = useState(1);
  const [models, setModels] = useState<ParsedModelSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    setPage(1);
  }, [datasetId, query, typeFilter, sort]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const response = await getDatasetModels(datasetId, {
          page,
          pageSize: DEFAULT_PAGE_SIZE,
          query: query.trim(),
          sort: sort?.key || "modelId",
          order: sort?.direction || "asc",
          warningType: typeFilter,
        });
        if (!cancelled) {
          setModels(response.models);
          setTotal(response.total);
          setTotalPages(response.totalPages);
        }
      } catch (error: unknown) {
        if (!cancelled) {
          setModels([]);
          setTotal(0);
          setTotalPages(0);
          setLoadError(error instanceof Error ? error.message : "Failed to load parsed models.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [datasetId, page, query, typeFilter, sort]);

  const types = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const row of models) {
      for (const [type, count] of Object.entries(row.types || {})) {
        counts[type] = (counts[type] || 0) + Number(count || 0);
      }
    }
    return Object.entries(counts).sort(([, left], [, right]) => right - left);
  }, [models]);

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
          {loading ? "Loading..." : `${total} models`}
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
      {loadError ? <p className="summaryHint error">{loadError}</p> : null}
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
            {models.map((row) => (
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
            {!loading && !models.length && (
              <tr>
                <td colSpan={7}>No parsed models match the current filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {totalPages > 1 ? (
        <div className="tablePagination">
          <button type="button" disabled={page <= 1 || loading} onClick={() => setPage((current) => Math.max(1, current - 1))}>
            <ChevronLeft size={15} />
            Previous
          </button>
          <span>
            Page {page} of {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages || loading}
            onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
          >
            Next
            <ChevronRight size={15} />
          </button>
        </div>
      ) : null}
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
