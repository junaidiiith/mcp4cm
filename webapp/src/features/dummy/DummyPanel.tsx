import {
  ChevronLeft,
  ChevronRight,
  Download,
  Filter,
  Info,
  Loader2,
  Plus,
  RotateCcw,
  Search,
  Sparkles,
  SlidersHorizontal,
} from "lucide-react";
import { useState } from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { filterFormulaPreviews, filterGroups, filterLabels, naturalLanguageOptions } from "../../config";
import type { BusyState, DummyProgressState, DummyResponse, FilterConfig } from "../../types";
import { formatDuration, round } from "../../utils";

export function DummyPanel({
  filters,
  onUpdateFilter,
  onResetFilters,
  onRun,
  canRun,
  busy,
  progress,
  result,
  selectedModelId,
  onSelectModelId,
}: {
  filters: FilterConfig[];
  onUpdateFilter: (index: number, patch: Partial<FilterConfig>) => void;
  onResetFilters: () => void;
  onRun: () => void;
  canRun: boolean;
  busy: BusyState;
  progress: DummyProgressState | null;
  result: DummyResponse | null;
  selectedModelId: string | null;
  onSelectModelId: (modelId: string | null) => void;
}) {
  const [showInfo, setShowInfo] = useState(false);
  const enabledFilters = filters.filter((filter) => filter.enabled).length;
  const isRunning = busy === "dummy";
  const hasActiveProgress = progress && progress.status !== "complete";

  return (
    <>
      <Card className="panel" id="dummy">
        <CardHeader className="panelHeader dummyPanelHeader">
          <div className="dummyPanelTitle">
            <h2>
              <Sparkles size={20} />
              Dummy Model Cleansing
            </h2>
            <div className="dummyPanelMeta">
              <Badge variant={enabledFilters ? "success" : "warning"}>
                {enabledFilters}/{filters.length} filters enabled
              </Badge>
              {result && (
                <span>
                  Current run: {result.runSummary.removedModels.toLocaleString()} removed,{" "}
                  {result.runSummary.remainingModels.toLocaleString()} retained
                </span>
              )}
            </div>
          </div>
          <div className="dummyPanelActions">
            <Button
              type="button"
              variant="secondary"
              size="icon"
              onClick={() => setShowInfo(true)}
              title="Dummy cleansing information"
              aria-label="Dummy cleansing information"
            >
              <Info className="dummyInfoIcon" />
            </Button>
            <Button type="button" onClick={onRun} disabled={!canRun || isRunning}>
              {isRunning ? <Loader2 className="spin" size={18} /> : <Filter size={18} />}
              Run Filters
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {hasActiveProgress && <DummyProgress progress={progress} />}
          {!hasActiveProgress && (
            <DummyResults
              result={result}
              selectedModelId={selectedModelId}
              onSelectModelId={onSelectModelId}
            />
          )}
          <Accordion type="single" collapsible className="dummySettingsAccordion">
            <AccordionItem value="filters">
              <AccordionTrigger>
                <div className="dummySettingsTrigger">
                  <span>
                    <SlidersHorizontal size={16} />
                    Filter settings
                  </span>
                  <small>{enabledFilters} enabled</small>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                <div className="dummySettingsHeader">
                  <p>Filter configuration is applied fresh to the original uploaded dataset on every run.</p>
                  <Button type="button" variant="secondary" size="sm" onClick={onResetFilters}>
                    <RotateCcw size={15} />
                    Reset defaults
                  </Button>
                </div>
                <BuiltInFilterEditor filters={filters} onChange={onUpdateFilter} />
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </CardContent>
      </Card>
      {showInfo && <DummyCleansingInfoModal onClose={() => setShowInfo(false)} />}
    </>
  );
}

function DummyProgress({ progress }: { progress: DummyProgressState }) {
  const overallProgress = Math.max(0, Math.min(100, Number(progress.progress || 0)));
  const processed = progress.processedModels || 0;
  const total = progress.totalModels || 0;
  const stageLabel = dummyStageLabel(progress.stage);
  const message = progress.message || (progress.status === "queued" ? "Queued dummy cleansing." : "Running dummy cleansing.");
  return (
    <div className="progressPanel">
      <div className="progressHeader">
        <div>
          <h3>{message}</h3>
          <p>
            {stageLabel}
            {total ? `, ${processed.toLocaleString()} of ${total.toLocaleString()} models` : ""}
            {", "}
            {formatDuration(progress.elapsedMs || 0)} elapsed
          </p>
        </div>
        <strong>{overallProgress}%</strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill" style={{ width: `${overallProgress}%` }} />
      </div>
    </div>
  );
}

function dummyStageLabel(stage: DummyProgressState["stage"]) {
  if (stage === "loading") return "Loading models";
  if (stage === "filtering") return "Evaluating filters";
  if (stage === "summarizing") return "Building results";
  if (stage === "complete") return "Complete";
  if (stage === "error") return "Error";
  return "Queued";
}

function DummyCleansingInfoModal({ onClose }: { onClose: () => void }) {
  return (
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="infoModal">
        <DialogHeader>
          <DialogTitle>Dummy Cleansing Information</DialogTitle>
          <DialogDescription>How names are classified and how filters evaluate models.</DialogDescription>
        </DialogHeader>
        <div className="inspectorBody">
          <h4>Name Classification</h4>
          <ul>
            <li>
              <strong>`missing`</strong>: raw node name is empty or whitespace after trimming.
            </li>
            <li>
              <strong>`placeholder`</strong>: normalized name matches placeholder patterns, keywords, or the normalized
              node type (for example `Class`, `Class1`, `Business Object`, `dummy`, `my class`, `att1`).
            </li>
            <li>
              <strong>`semantic`</strong>: name is present and is not recognized as a placeholder.
            </li>
          </ul>
          <h4>Important Terms</h4>
          <ul>
            <li>
              <strong>`named nodes`</strong>: all nodes except `missing`.
            </li>
            <li>
              <strong>`eligible names`</strong>: `semantic` names only. Filters like naming-density, median-length,
              and vocabulary use this set.
            </li>
            <li>
              <strong>Normalization</strong>: cleansing-time only (`lowercase`, whitespace compaction,
              tokenization). Raw parsed names stay unchanged.
            </li>
          </ul>
          <h4>Filter Execution</h4>
          <ul>
            <li>Filters run in chain order and are cumulative for the waterfall view.</li>
            <li>`primaryRemovalReason` is the first filter that removes a model.</li>
            <li>`allTriggeredFilters` shows every filter that would remove that model.</li>
            <li>Model details keep per-filter metrics, score, threshold, and evidence nodes for traceability.</li>
          </ul>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function BuiltInFilterEditor({
  filters,
  onChange,
}: {
  filters: FilterConfig[];
  onChange: (index: number, patch: Partial<FilterConfig>) => void;
}) {
  const groups = ["Size", "Naming Density", "Placeholder Detection", "Vocabulary", "Language", "Custom", "General"];
  const groupedFilters = groups
    .map((group) => ({
      group,
      rows: filters
        .map((filter, index) => ({ filter, index }))
        .filter(({ filter }) => (filterGroups[filter.id] || "General") === group),
    }))
    .filter((entry) => entry.rows.length > 0);

  return (
    <Accordion type="multiple" className="dummyAccordion">
      {groupedFilters.map(({ group, rows }) => {
        const activeCount = rows.filter(({ filter }) => filter.enabled).length;
        return (
          <AccordionItem value={group} key={group}>
            <AccordionTrigger>
              <div className="dummyGroupHeader">
                <span>{group}</span>
                <span className="dummyGroupCount">
                  {activeCount}/{rows.length} active
                </span>
              </div>
            </AccordionTrigger>
            <AccordionContent>
              <div className="filterEditorGrid">
                {rows.map(({ filter, index }) => {
                  const [title, detail] = filterLabels[filter.id] || [filter.id, ""];
                  const formula = filterFormulaPreviews[filter.id] || "";
                  return (
                    <div className={`filterConfigCard ${filter.enabled ? "" : "disabled"}`} key={filter.id}>
                      <label className="checkLine">
                        <input
                          type="checkbox"
                          checked={filter.enabled}
                          onChange={(event) => onChange(index, { enabled: event.target.checked })}
                        />
                        <span>{title}</span>
                      </label>
                      <p>{detail}</p>
                      <div className="filterConfigFields">
                        {"minNodes" in filter && (
                          <Label>
                            Min nodes
                            <Input
                              type="number"
                              min="0"
                              step="1"
                              value={filter.minNodes}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { minNodes: Number(event.target.value) })}
                            />
                          </Label>
                        )}
                        {"minEdges" in filter && (
                          <Label>
                            Min edges
                            <Input
                              type="number"
                              min="0"
                              step="1"
                              value={filter.minEdges}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { minEdges: Number(event.target.value) })}
                            />
                          </Label>
                        )}
                        {"threshold" in filter && (
                          <Label>
                            Threshold
                            <Input
                              type="number"
                              min="0"
                              max="1"
                              step="0.01"
                              value={filter.threshold}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { threshold: Number(event.target.value) })}
                            />
                          </Label>
                        )}
                        {"minNames" in filter && (
                          <Label>
                            Min names
                            <Input
                              type="number"
                              min="0"
                              step="1"
                              value={filter.minNames}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { minNames: Number(event.target.value) })}
                            />
                          </Label>
                        )}
                        {"minUniqueWords" in filter && (
                          <Label>
                            Min words
                            <Input
                              type="number"
                              min="0"
                              step="1"
                              value={filter.minUniqueWords}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { minUniqueWords: Number(event.target.value) })}
                            />
                          </Label>
                        )}
                        {"minMedianLength" in filter && (
                          <Label>
                            Min median length
                            <Input
                              type="number"
                              min="0"
                              step="1"
                              value={filter.minMedianLength}
                              disabled={!filter.enabled}
                              onChange={(event) =>
                                onChange(index, { minMedianLength: Number(event.target.value) })
                              }
                            />
                          </Label>
                        )}
                        {"pattern" in filter && (
                          <Label className="wideField">
                            Pattern
                            <Input
                              placeholder="e.g. ^(test|dummy|sample)$"
                              value={filter.pattern}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { pattern: event.target.value })}
                            />
                          </Label>
                        )}
                        {"targetField" in filter && (
                          <Label>
                            Target field
                            <select
                              value={filter.targetField}
                              disabled={!filter.enabled}
                              onChange={(event) =>
                                onChange(index, {
                                  targetField: event.target.value as "name" | "name+type" | "type",
                                })
                              }
                            >
                              <option value="name">name</option>
                              <option value="name+type">name+type</option>
                              <option value="type">type</option>
                            </select>
                          </Label>
                        )}
                        {"scope" in filter && (
                          <Label>
                            Scope
                            <select
                              value={filter.scope}
                              disabled={!filter.enabled}
                              onChange={(event) =>
                                onChange(index, {
                                  scope: event.target.value as "eligible_only" | "all_named_nodes",
                                })
                              }
                            >
                              <option value="eligible_only">eligible_only</option>
                              <option value="all_named_nodes">all_named_nodes</option>
                            </select>
                          </Label>
                        )}
                        {"minMatches" in filter && (
                          <Label>
                            Min matches
                            <Input
                              type="number"
                              min="1"
                              step="1"
                              value={filter.minMatches}
                              disabled={!filter.enabled}
                              onChange={(event) => onChange(index, { minMatches: Number(event.target.value) })}
                            />
                          </Label>
                        )}
                        {"languages" in filter && (
                          <LanguageMultiSelect
                            value={filter.languages}
                            disabled={!filter.enabled}
                            onChange={(languages) => onChange(index, { languages })}
                          />
                        )}
                      </div>
                      {formula && (
                        <details className="formulaDetail">
                          <summary>Formula</summary>
                          <code>{formula}</code>
                        </details>
                      )}
                    </div>
                  );
                })}
              </div>
            </AccordionContent>
          </AccordionItem>
        );
      })}
    </Accordion>
  );
}

function LanguageMultiSelect({
  value,
  disabled,
  onChange,
}: {
  value: string[];
  disabled: boolean;
  onChange: (languages: string[]) => void;
}) {
  const selected = new Set(value);
  return (
    <div className="wideField languageMultiSelect">
      <span>Languages</span>
      <div>
        {naturalLanguageOptions.map((option) => (
          <label className="checkLine" key={option.value}>
            <input
              type="checkbox"
              checked={selected.has(option.value)}
              disabled={disabled}
              onChange={(event) => {
                const next = event.target.checked
                  ? [...value, option.value]
                  : value.filter((language) => language !== option.value);
                onChange([...new Set(next)]);
              }}
            />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function DummyResults({
  result,
  selectedModelId,
  onSelectModelId,
}: {
  result: DummyResponse | null;
  selectedModelId: string | null;
  onSelectModelId: (modelId: string | null) => void;
}) {
  const [traceabilityQuery, setTraceabilityQuery] = useState("");
  const [traceabilityPage, setTraceabilityPage] = useState(1);

  if (!result) return <EmptyState text="Run filters to preview the cleansing outcome for the original dataset." />;
  const summary = result.runSummary;
  const distribution = new Map<string, number>();
  for (const outcome of result.modelOutcomes) {
    if (!outcome.primaryRemovalReason) continue;
    distribution.set(outcome.primaryRemovalReason, (distribution.get(outcome.primaryRemovalReason) || 0) + 1);
  }
  const traceabilityPageSize = 25;
  const normalizedQuery = traceabilityQuery.trim().toLowerCase();
  const filteredOutcomes = normalizedQuery
    ? result.modelOutcomes.filter((outcome) => outcome.modelId.toLowerCase().includes(normalizedQuery))
    : result.modelOutcomes;
  const traceabilityPageCount = Math.max(1, Math.ceil(filteredOutcomes.length / traceabilityPageSize));
  const currentTraceabilityPage = Math.min(traceabilityPage, traceabilityPageCount);
  const firstTraceabilityIndex = (currentTraceabilityPage - 1) * traceabilityPageSize;
  const pagedOutcomes = filteredOutcomes.slice(
    firstTraceabilityIndex,
    firstTraceabilityIndex + traceabilityPageSize,
  );
  const selectedFindings = selectedModelId
    ? result.findings.filter((finding) => finding.modelId === selectedModelId)
    : [];

  return (
    <div className="results">
      <div className="dummyOutcome">
        <div className="metricGrid dummyMetricGrid">
          <Metric label="Total models" value={summary.totalModels.toLocaleString()} />
          <Metric label="Removed" value={summary.removedModels.toLocaleString()} />
          <Metric label="Retained" value={summary.remainingModels.toLocaleString()} />
          <Metric label="Removal rate" value={`${Math.round(summary.removalRate * 100)}%`} />
        </div>
        <RemovalDistribution distribution={distribution} totalModels={summary.totalModels} />
      </div>

      <Accordion type="single" collapsible className="dummyDetailsAccordion">
        <AccordionItem value="details">
          <AccordionTrigger>
            <div className="dummySettingsTrigger">
              <span>Detailed results</span>
              <small>{result.modelOutcomes.length.toLocaleString()} models</small>
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <Tabs defaultValue="waterfall">
              <div className="resultsHeader">
                <TabsList>
                  <TabsTrigger value="waterfall">Waterfall</TabsTrigger>
                  <TabsTrigger value="traceability">Traceability</TabsTrigger>
                </TabsList>
                <div className="dummyExportActions">
                  <Button type="button" variant="secondary" size="sm" onClick={() => exportDummyJson(result)}>
                    <Download size={15} />
                    JSON
                  </Button>
                  <Button type="button" variant="secondary" size="sm" onClick={() => exportDummyCsv(result)}>
                    <Download size={15} />
                    Traceability CSV
                  </Button>
                </div>
              </div>
              <Separator />
        <TabsContent value="waterfall">
          <h3>Filter Waterfall</h3>
          <table>
            <thead>
              <tr>
                <th>Filter</th>
                <th>Filtered</th>
                <th>Remaining</th>
              </tr>
            </thead>
            <tbody>
              {result.filterSummaries.map((row) => (
                <tr key={row.filterId}>
                  <td>{filterTitle(row.filterId)}</td>
                  <td>{row.filteredCount}</td>
                  <td>{row.remainingCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>

        <TabsContent value="traceability">
          <div className="traceabilityToolbar">
            <h3>Model Traceability</h3>
            <label className="traceabilitySearch">
              <Search size={16} />
              <Input
                type="search"
                value={traceabilityQuery}
                placeholder="Search model ID"
                onChange={(event) => {
                  setTraceabilityQuery(event.target.value);
                  setTraceabilityPage(1);
                }}
              />
            </label>
          </div>
          <div className="dummyTraceabilityTable">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Decision</th>
                  <th>Primary reason</th>
                  <th>All triggered filters</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {pagedOutcomes.map((outcome) => (
                  <tr key={outcome.modelId}>
                    <td>{outcome.modelId}</td>
                    <td>{outcome.removed ? "Removed" : "Kept"}</td>
                    <td>{outcome.primaryRemovalReason ? filterTitle(outcome.primaryRemovalReason) : "-"}</td>
                    <td>{outcome.allTriggeredFilters.map(filterTitle).join(", ") || "-"}</td>
                    <td>
                      <Button type="button" size="sm" variant="secondary" onClick={() => onSelectModelId(outcome.modelId)}>
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!pagedOutcomes.length && <EmptyState text="No matching model IDs." />}
          </div>
          <div className="traceabilityPagination">
            <span>
              {filteredOutcomes.length
                ? `${(firstTraceabilityIndex + 1).toLocaleString()}-${Math.min(
                    firstTraceabilityIndex + traceabilityPageSize,
                    filteredOutcomes.length,
                  ).toLocaleString()} of ${filteredOutcomes.length.toLocaleString()}`
                : "0 of 0"}
            </span>
            <div>
              <Button
                type="button"
                variant="secondary"
                size="icon"
                onClick={() => setTraceabilityPage(Math.max(1, currentTraceabilityPage - 1))}
                disabled={currentTraceabilityPage <= 1}
                aria-label="Previous traceability page"
                title="Previous page"
              >
                <ChevronLeft size={16} />
              </Button>
              <strong>
                Page {currentTraceabilityPage.toLocaleString()} of {traceabilityPageCount.toLocaleString()}
              </strong>
              <Button
                type="button"
                variant="secondary"
                size="icon"
                onClick={() => setTraceabilityPage(Math.min(traceabilityPageCount, currentTraceabilityPage + 1))}
                disabled={currentTraceabilityPage >= traceabilityPageCount}
                aria-label="Next traceability page"
                title="Next page"
              >
                <ChevronRight size={16} />
              </Button>
            </div>
          </div>
        </TabsContent>
            </Tabs>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
      {selectedModelId && (
        <DummyModelDetailModal
          modelId={selectedModelId}
          findings={selectedFindings}
          onClose={() => onSelectModelId(null)}
        />
      )}
    </div>
  );
}

function RemovalDistribution({
  distribution,
  totalModels,
}: {
  distribution: Map<string, number>;
  totalModels: number;
}) {
  const rows = [...distribution.entries()].sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(1, ...rows.map(([, count]) => count));

  return (
    <section className="dummyDistribution" aria-label="Removal reasons">
      <div className="dummyDistributionHeader">
        <h3>Removal Reasons</h3>
        <span>{rows.length ? `${rows.length} filters removed models` : "No removals"}</span>
      </div>
      {rows.length ? (
        <div className="dummyDistributionList">
          {rows.slice(0, 6).map(([filterId, count]) => (
            <div className="dummyDistributionRow" key={filterId}>
              <div>
                <strong>{filterTitle(filterId)}</strong>
                <span>{Math.round((count / Math.max(1, totalModels)) * 100)}% of dataset</span>
              </div>
              <i aria-hidden="true">
                <b style={{ width: `${Math.max(4, (count / maxCount) * 100)}%` }} />
              </i>
              <em>{count.toLocaleString()}</em>
            </div>
          ))}
        </div>
      ) : (
        <EmptyState text="No models were removed by the current filter configuration." />
      )}
    </section>
  );
}

function DummyModelDetailModal({
  modelId,
  findings,
  onClose,
}: {
  modelId: string;
  findings: DummyResponse["findings"];
  onClose: () => void;
}) {
  return (
    <Dialog
      open
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="infoModal">
        <DialogHeader>
          <DialogTitle>Model Detail</DialogTitle>
          <DialogDescription>{modelId}</DialogDescription>
        </DialogHeader>
        {!findings.length ? (
          <p>No findings available for this model.</p>
        ) : (
          <div className="dummyFindingsList">
            {findings.map((finding, index) => (
              <details className="dummyFindingCard" key={`${finding.modelId}:${finding.filterId}:${index}`}>
                <summary>
                  <span>{filterTitle(finding.filterId)}</span>
                  <span>{finding.decision}</span>
                  <span>Score: {round(finding.score)}</span>
                  <span>Threshold: {round(finding.threshold)}</span>
                </summary>
                <div className="dummyFindingBody">
                  <p>
                    <strong>Reason:</strong> {finding.reason}
                  </p>
                  <p>
                    <strong>Evidence:</strong> {finding.evidence.length ? finding.evidence.join(", ") : "-"}
                  </p>
                  <p>
                    <strong>Evidence Nodes:</strong> {finding.evidenceNodes.length ? finding.evidenceNodes.join(", ") : "-"}
                  </p>
                  <pre>{JSON.stringify(finding.metrics || {}, null, 2)}</pre>
                </div>
              </details>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function filterTitle(filterId: string) {
  return filterLabels[filterId]?.[0] || filterId;
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

function exportDummyJson(result: DummyResponse) {
  downloadText("dummy-results.json", JSON.stringify(result, null, 2), "application/json");
}

function exportDummyCsv(result: DummyResponse) {
  const lines = [
    "modelId,decision,primaryRemovalReason,allTriggeredFilters",
    ...result.modelOutcomes.map((outcome) =>
      [
        csvCell(outcome.modelId),
        csvCell(outcome.removed ? "Removed" : "Kept"),
        csvCell(outcome.primaryRemovalReason ? filterTitle(outcome.primaryRemovalReason) : ""),
        csvCell(outcome.allTriggeredFilters.map(filterTitle).join(" | ")),
      ].join(","),
    ),
  ];
  downloadText("dummy-traceability.csv", lines.join("\n"), "text/csv");
}

function downloadText(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: string) {
  const escaped = String(value || "").replace(/\"/g, '""');
  return `\"${escaped}\"`;
}
