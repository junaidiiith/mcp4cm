import { useMemo, useState } from "react";
import { BarChart3, Info, Loader2, Plus } from "lucide-react";
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
  const cards = [
    { label: "Input Files", value: inputFiles, tone: "neutral" },
    { label: "Models Parsed", value: parsedModels, tone: "neutral" },
    { label: "Warnings", value: warnings, tone: warnings ? "warn" : "neutral" },
    { label: "Models with Warnings", value: filesWithWarnings, tone: filesWithWarnings ? "warn" : "neutral" },
    { label: "Errors", value: failed, tone: failed ? "error" : "neutral" },
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
    </div>
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
          Type
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
        <table>
          <thead>
            <tr>
              <th>Model</th>
              <th>File</th>
              <th>Warnings</th>
              <th>Types</th>
              <th>Inspect</th>
            </tr>
          </thead>
          <tbody>
            {filteredModels.map((row) => (
              <tr key={row.modelId}>
                <td>{row.modelId}</td>
                <td className="warningPath">{row.path}</td>
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
                <td colSpan={5}>No parsed models match the current filter.</td>
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
    <>
      <div className="metricGrid">
        <Metric label="Models" value={summary.models} />
        <Metric label="Avg nodes" value={round(summary.nodes.mean)} />
        <Metric label="Avg edges" value={round(summary.edges.mean)} />
        <Metric label="Median names" value={round(summary.names.median)} />
      </div>
      <div className="listGrid">
        <TopList title="Top Types" items={stats.topTypes} />
        <TopList title="Top Names" items={stats.topNames} />
      </div>
    </>
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

function TopList({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; count: number }>;
}) {
  return (
    <div className="topList">
      <h3>{title}</h3>
      {items.map((item) => (
        <div key={item.label}>
          <span>{item.label}</span>
          <b>{item.count}</b>
        </div>
      ))}
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
