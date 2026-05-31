import { Filter, Info, Loader2, Plus, Sparkles } from "lucide-react";
import { useState } from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { filterFormulaPreviews, filterGroups, filterLabels } from "../../config";
import type { BusyState, DummyResponse, FilterConfig } from "../../types";
import { round } from "../../utils";

export function DummyPanel({
  filters,
  onUpdateFilter,
  onResetFilters,
  onRun,
  canRun,
  busy,
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
  result: DummyResponse | null;
  selectedModelId: string | null;
  onSelectModelId: (modelId: string | null) => void;
}) {
  const [showInfo, setShowInfo] = useState(false);

  return (
    <>
      <Card className="panel" id="dummy">
        <CardHeader className="panelHeader">
          <h2>
            <Sparkles size={20} />
            Dummy Model Cleansing
          </h2>
        </CardHeader>
        <CardContent>
          <div className="subsectionHeader">
          <h2>Built-in Filters</h2>
            <div className="subsectionActions">
              <Button type="button" variant="secondary" onClick={() => setShowInfo(true)}>
                <Info size={15} />
                Info
              </Button>
              <Button type="button" variant="secondary" onClick={onResetFilters}>
                Reset defaults
              </Button>
            </div>
          </div>
          <BuiltInFilterEditor filters={filters} onChange={onUpdateFilter} />
          <div className="actionBar">
            <Button onClick={onRun} disabled={!canRun || busy === "dummy"}>
              {busy === "dummy" ? <Loader2 className="spin" size={18} /> : <Filter size={18} />}
              Run Filters
            </Button>
          </div>
          <DummyResults
            result={result}
            selectedModelId={selectedModelId}
            onSelectModelId={onSelectModelId}
          />
        </CardContent>
      </Card>
      {showInfo && <DummyCleansingInfoModal onClose={() => setShowInfo(false)} />}
    </>
  );
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
              <strong>`type_like`</strong>: normalized name matches normalized node type (for example `Class`,
              `Class1`, `Business Object`).
            </li>
            <li>
              <strong>`placeholder`</strong>: normalized name matches placeholder patterns or keywords (for example
              `dummy`, `my class`, `att1`).
            </li>
            <li>
              <strong>`semantic`</strong>: name is present and is neither `type_like` nor `placeholder`.
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
            <li>`findings` keep per-filter metrics, score, threshold, and evidence nodes for traceability.</li>
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
  const groups = ["Size", "Naming Density", "Placeholder Detection", "Vocabulary", "Custom", "General"];
  const groupedFilters = groups
    .map((group) => ({
      group,
      rows: filters
        .map((filter, index) => ({ filter, index }))
        .filter(({ filter }) => (filterGroups[filter.id] || "General") === group),
    }))
    .filter((entry) => entry.rows.length > 0);

  return (
    <Accordion type="multiple" defaultValue={groupedFilters.map((entry) => entry.group)} className="dummyAccordion">
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

function DummyResults({
  result,
  selectedModelId,
  onSelectModelId,
}: {
  result: DummyResponse | null;
  selectedModelId: string | null;
  onSelectModelId: (modelId: string | null) => void;
}) {
  if (!result) return <EmptyState text="Run dummy filters to see run summary, waterfall, and model traceability." />;
  const summary = result.runSummary;
  const distribution = new Map<string, number>();
  for (const outcome of result.modelOutcomes) {
    if (!outcome.primaryRemovalReason) continue;
    distribution.set(outcome.primaryRemovalReason, (distribution.get(outcome.primaryRemovalReason) || 0) + 1);
  }
  const selectedFindings = selectedModelId
    ? result.findings.filter((finding) => finding.modelId === selectedModelId)
    : [];

  return (
    <div className="results">
      <Tabs defaultValue="overview">
        <div className="resultsHeader">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="waterfall">Waterfall</TabsTrigger>
            <TabsTrigger value="traceability">Traceability</TabsTrigger>
            <TabsTrigger value="findings">Model Findings</TabsTrigger>
          </TabsList>
          <div className="actionBar">
            <Button type="button" variant="secondary" onClick={() => exportDummyJson(result)}>
              Export JSON
            </Button>
            <Button type="button" variant="secondary" onClick={() => exportDummyCsv(result)}>
              Export CSV
            </Button>
          </div>
        </div>

        <TabsContent value="overview">
          <div className="metricGrid small">
            <Metric label="Total models" value={summary.totalModels} />
            <Metric label="Removed" value={summary.removedModels} />
            <Metric label="Remaining" value={summary.remainingModels} />
            <Metric label="Removal rate" value={`${Math.round(summary.removalRate * 100)}%`} />
          </div>
          <h3>Primary Removal Distribution</h3>
          <table>
            <thead>
              <tr>
                <th>Filter</th>
                <th>Models</th>
              </tr>
            </thead>
            <tbody>
              {[...distribution.entries()]
                .sort((a, b) => b[1] - a[1])
                .map(([filterId, count]) => (
                  <tr key={filterId}>
                    <td>{filterId}</td>
                    <td>{count}</td>
                  </tr>
                ))}
              {!distribution.size && (
                <tr>
                  <td colSpan={2}>No models were removed.</td>
                </tr>
              )}
            </tbody>
          </table>
        </TabsContent>

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
                  <td>{row.filterId}</td>
                  <td>{row.filteredCount}</td>
                  <td>{row.remainingCount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TabsContent>

        <TabsContent value="traceability">
          <h3>Model Traceability</h3>
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
                {result.modelOutcomes.map((outcome) => (
                  <tr key={outcome.modelId}>
                    <td>{outcome.modelId}</td>
                    <td>{outcome.removed ? "Removed" : "Kept"}</td>
                    <td>{outcome.primaryRemovalReason || "-"}</td>
                    <td>{outcome.allTriggeredFilters.join(", ") || "-"}</td>
                    <td>
                      <Button type="button" size="sm" variant="secondary" onClick={() => onSelectModelId(outcome.modelId)}>
                        Open
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </TabsContent>

        <TabsContent value="findings">
          {result.findings.length ? (
            <div className="dummyFindingsList">
              {result.findings.slice(0, 180).map((finding, index) => (
                <details className="dummyFindingCard" key={`${finding.modelId}:${finding.filterId}:${index}`}>
                  <summary>
                    <span>{finding.modelId}</span>
                    <span>{finding.filterId}</span>
                    <span>{finding.decision}</span>
                    <span>Score {round(finding.score)}</span>
                  </summary>
                  <div className="dummyFindingBody">
                    <p>
                      <strong>Reason:</strong> {finding.reason}
                    </p>
                    <p>
                      <strong>Evidence:</strong> {finding.evidence.length ? finding.evidence.join(", ") : "-"}
                    </p>
                    <p>
                      <strong>Nodes:</strong> {finding.evidenceNodes.length ? finding.evidenceNodes.join(", ") : "-"}
                    </p>
                    <pre>{JSON.stringify(finding.metrics || {}, null, 2)}</pre>
                  </div>
                </details>
              ))}
            </div>
          ) : (
            <EmptyState text="No findings emitted in this run." />
          )}
        </TabsContent>
      </Tabs>
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
                  <span>{finding.filterId}</span>
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
    "modelId,filterId,decision,reason,score,threshold,evidence",
    ...result.findings.map((finding) =>
      [
        csvCell(finding.modelId),
        csvCell(finding.filterId),
        csvCell(finding.decision),
        csvCell(finding.reason),
        csvCell(String(finding.score)),
        csvCell(String(finding.threshold)),
        csvCell(finding.evidence.join(" | ")),
      ].join(","),
    ),
  ];
  downloadText("dummy-findings.csv", lines.join("\n"), "text/csv");
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
