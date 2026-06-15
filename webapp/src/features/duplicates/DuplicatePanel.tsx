import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { ChevronLeft, ChevronRight, Download, Eye, GitCompare, Layers3, Loader2, Plus, SlidersHorizontal } from "lucide-react";
import { getDuplicateGroupDetail, getDuplicateGroups, getDuplicatePairs } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { techniques } from "../../config";
import type {
  BusyState,
  DuplicateCanonicalSelection,
  DuplicateGroup,
  DuplicateGroupDetail,
  DuplicateGroupsPage,
  DuplicatePairDecision,
  DuplicatePairsPage,
  DuplicateProgressState,
  DuplicateResult,
  Thresholds,
} from "../../types";
import { formatDuration, round, techniqueLabel } from "../../utils";

export function DuplicatePanel({
  canRun,
  busy,
  selected,
  mandatory,
  thresholds,
  minVotes,
  duplicateProgress,
  duplicateResult,
  onToggleSelection,
  onToggleMandatory,
  onThresholdsChange,
  onMinVotesChange,
  onRun,
  onInspectModel,
  onInspectBoth,
}: {
  canRun: boolean;
  busy: BusyState;
  selected: string[];
  mandatory: string[];
  thresholds: Thresholds;
  minVotes: number;
  duplicateProgress: DuplicateProgressState | null;
  duplicateResult: DuplicateResult | null;
  onToggleSelection: (id: string) => void;
  onToggleMandatory: (id: string) => void;
  onThresholdsChange: (next: Thresholds) => void;
  onMinVotesChange: (next: number) => void;
  onRun: () => void;
  onInspectModel: (modelId: string) => void;
  onInspectBoth: (leftId: string, rightId: string) => void;
}) {
  return (
    <Card className="panel" id="duplicates">
      <CardHeader className="panelHeader">
        <h2>
          <Layers3 size={20} />
          Duplicate Detection
        </h2>
      </CardHeader>
      <CardContent>
        <div className="techGrid">
          {techniques.map((technique) => (
            <div className="techCard" key={technique.id}>
              <label className="checkLine">
                <input
                  type="checkbox"
                  checked={selected.includes(technique.id)}
                  onChange={() => onToggleSelection(technique.id)}
                />
                <span>{technique.label}</span>
              </label>
              <p>{technique.detail}</p>
              <label className="mandatory">
                <input
                  type="checkbox"
                  checked={mandatory.includes(technique.id)}
                  disabled={!selected.includes(technique.id)}
                  onChange={() => onToggleMandatory(technique.id)}
                />
                Mandatory
              </label>
              <details className="techConfig">
                <summary>
                  <SlidersHorizontal size={15} /> Configure
                </summary>
                <TechniqueConfig technique={technique.id} thresholds={thresholds} onChange={onThresholdsChange} />
              </details>
            </div>
          ))}
        </div>

        <div className="runConfig">
          <Label>
            Min votes
            <Input
              type="number"
              min="1"
              value={minVotes}
              onChange={(event) => onMinVotesChange(Number(event.target.value))}
            />
          </Label>
        </div>

        <div className="actionBar">
          <Button onClick={onRun} disabled={!canRun || busy === "duplicates"}>
            {busy === "duplicates" ? <Loader2 className="spin" size={18} /> : <GitCompare size={18} />}
            Run Duplicate Detection
          </Button>
        </div>
        {duplicateProgress && <DuplicateProgress progress={duplicateProgress} />}
        <DuplicateResults result={duplicateResult} onInspectModel={onInspectModel} onInspectBoth={onInspectBoth} />
      </CardContent>
    </Card>
  );
}

function TechniqueConfig({
  technique,
  thresholds,
  onChange,
}: {
  technique: string;
  thresholds: Thresholds;
  onChange: (next: Thresholds) => void;
}) {
  const patch = (updates: Partial<Thresholds>) => onChange({ ...thresholds, ...updates });
  const patchWeights = (updates: Partial<Thresholds["graphWeights"]>) =>
    onChange({ ...thresholds, graphWeights: { ...thresholds.graphWeights, ...updates } });

  if (technique === "hash") {
    return (
      <div className="configGrid">
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.hashIncludeTypes}
            onChange={(event) => patch({ hashIncludeTypes: event.target.checked })}
          />
          Types
        </label>
        <label>
          Min named nodes
          <input
            type="number"
            min="0"
            step="1"
            value={thresholds.minNamedNodes}
            onChange={(event) => patch({ minNamedNodes: Number(event.target.value) })}
          />
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.deduplicateNameTokens}
            onChange={(event) => patch({ deduplicateNameTokens: event.target.checked })}
          />
          Deduplicate names
        </label>
      </div>
    );
  }

  if (technique === "tfidf") {
    return (
      <div className="configGrid">
        <label>
          Token mode
          <select
            value={thresholds.tfidfTokenMode}
            onChange={(event) => patch({ tfidfTokenMode: event.target.value as Thresholds["tfidfTokenMode"] })}
          >
            <option value="names">names</option>
            <option value="names_types_bag">names_types_bag</option>
            <option value="typed_name_pairs">typed_name_pairs</option>
          </select>
        </label>
        <label>
          Threshold
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={thresholds.tfidfSimilarityThreshold}
            onChange={(event) => patch({ tfidfSimilarityThreshold: Number(event.target.value) })}
          />
        </label>
        <label>
          Max features
          <input
            type="number"
            min="1000"
            step="1000"
            value={thresholds.tfidfMaxFeatures}
            onChange={(event) => patch({ tfidfMaxFeatures: Number(event.target.value) })}
          />
        </label>
        <label>
          Min DF
          <input
            type="number"
            min="0.1"
            step="0.1"
            value={thresholds.minDf}
            onChange={(event) => patch({ minDf: Number(event.target.value) })}
          />
        </label>
        <label>
          N-gram min
          <input
            type="number"
            min="1"
            step="1"
            value={thresholds.ngramRangeMin}
            onChange={(event) => patch({ ngramRangeMin: Number(event.target.value) })}
          />
        </label>
        <label>
          N-gram max
          <input
            type="number"
            min={thresholds.ngramRangeMin}
            step="1"
            value={thresholds.ngramRangeMax}
            onChange={(event) => patch({ ngramRangeMax: Number(event.target.value) })}
          />
        </label>
        <label>
          Stopwords
          <select
            value={thresholds.stopwordsMode}
            onChange={(event) => patch({ stopwordsMode: event.target.value as Thresholds["stopwordsMode"] })}
          >
            <option value="none">none</option>
            <option value="english">english</option>
          </select>
        </label>
      </div>
    );
  }

  if (technique === "graph_similarity") {
    const weights = thresholds.graphWeights;
    return (
      <div className="configGrid">
        <label>
          Threshold
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={thresholds.graphSimilarity}
            onChange={(event) => patch({ graphSimilarity: Number(event.target.value) })}
          />
        </label>
        <label>
          Node names
          <input
            type="number"
            min="0"
            step="0.01"
            value={weights.nodeNameJaccard}
            onChange={(event) => patchWeights({ nodeNameJaccard: Number(event.target.value) })}
          />
        </label>
        <label>
          Node types
          <input
            type="number"
            min="0"
            step="0.01"
            value={weights.nodeTypeJaccard}
            onChange={(event) => patchWeights({ nodeTypeJaccard: Number(event.target.value) })}
          />
        </label>
        <label>
          Edge types
          <input
            type="number"
            min="0"
            step="0.01"
            value={weights.edgeTypeJaccard}
            onChange={(event) => patchWeights({ edgeTypeJaccard: Number(event.target.value) })}
          />
        </label>
        <label>
          Degree histogram
          <input
            type="number"
            min="0"
            step="0.01"
            value={weights.degreeHistogram}
            onChange={(event) => patchWeights({ degreeHistogram: Number(event.target.value) })}
          />
        </label>
        {thresholds.useDirectedMetrics && (
          <>
            <label>
              In-degree histogram
              <input
                type="number"
                min="0"
                step="0.01"
                value={weights.inDegreeHistogram}
                onChange={(event) => patchWeights({ inDegreeHistogram: Number(event.target.value) })}
              />
            </label>
            <label>
              Out-degree histogram
              <input
                type="number"
                min="0"
                step="0.01"
                value={weights.outDegreeHistogram}
                onChange={(event) => patchWeights({ outDegreeHistogram: Number(event.target.value) })}
              />
            </label>
          </>
        )}
        <label>
          Size
          <input
            type="number"
            min="0"
            step="0.01"
            value={weights.sizeSimilarity}
            onChange={(event) => patchWeights({ sizeSimilarity: Number(event.target.value) })}
          />
        </label>
        <label>
          Density
          <input
            type="number"
            min="0"
            step="0.01"
            value={weights.densitySimilarity}
            onChange={(event) => patchWeights({ densitySimilarity: Number(event.target.value) })}
          />
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.useDirectedMetrics}
            onChange={(event) => patch({ useDirectedMetrics: event.target.checked })}
          />
          Directed metrics
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.normalizeParallelEdges}
            onChange={(event) => patch({ normalizeParallelEdges: event.target.checked })}
          />
          Normalize parallel edges
        </label>
      </div>
    );
  }

  if (technique === "graph_embedding") {
    return (
      <div className="configGrid">
        <label>
          Threshold
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={thresholds.graphEmbeddingThreshold}
            onChange={(event) =>
              patch({
                graphEmbeddingThreshold: Number(event.target.value),
                graphEmbedding: Number(event.target.value),
              })
            }
          />
        </label>
        <label>
          Dimensions
          <input
            type="number"
            min="8"
            step="8"
            value={thresholds.graphEmbeddingDimensions}
            onChange={(event) => patch({ graphEmbeddingDimensions: Number(event.target.value) })}
          />
        </label>
        <label>
          Walk length
          <input
            type="number"
            min="1"
            step="1"
            value={thresholds.graphEmbeddingWalkLength}
            onChange={(event) => patch({ graphEmbeddingWalkLength: Number(event.target.value) })}
          />
        </label>
        <label>
          Walks
          <input
            type="number"
            min="1"
            step="1"
            value={thresholds.graphEmbeddingNumWalks}
            onChange={(event) => patch({ graphEmbeddingNumWalks: Number(event.target.value) })}
          />
        </label>
        <label>
          Workers
          <input
            type="number"
            min="1"
            step="1"
            value={thresholds.graphEmbeddingWorkers}
            onChange={(event) => patch({ graphEmbeddingWorkers: Number(event.target.value) })}
          />
        </label>
        <label>
          Seed
          <input
            type="number"
            step="1"
            value={thresholds.graphEmbeddingSeed}
            onChange={(event) => patch({ graphEmbeddingSeed: Number(event.target.value) })}
          />
        </label>
        <label>
          Pooling
          <select
            value={thresholds.graphEmbeddingPooling}
            onChange={(event) => patch({ graphEmbeddingPooling: event.target.value as Thresholds["graphEmbeddingPooling"] })}
          >
            <option value="mean">mean</option>
            <option value="mean_max">mean_max</option>
          </select>
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.graphEmbeddingUseNodeNames}
            onChange={(event) => patch({ graphEmbeddingUseNodeNames: event.target.checked })}
          />
          Node names
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.graphEmbeddingUseNodeTypes}
            onChange={(event) => patch({ graphEmbeddingUseNodeTypes: event.target.checked })}
          />
          Node types
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.graphEmbeddingUseEdgeTypes}
            onChange={(event) => patch({ graphEmbeddingUseEdgeTypes: event.target.checked })}
          />
          Edge types
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.graphEmbeddingPoolFeatures}
            onChange={(event) => patch({ graphEmbeddingPoolFeatures: event.target.checked })}
          />
          Pool features
        </label>
      </div>
    );
  }

  if (technique === "bert_semantic") {
    return (
      <div className="configGrid">
        <label>
          Threshold
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={thresholds.bertSemantic}
            onChange={(event) => patch({ bertSemantic: Number(event.target.value) })}
          />
        </label>
        <label>
          Text mode
          <select
            value={thresholds.semanticTextMode}
            onChange={(event) => patch({ semanticTextMode: event.target.value as Thresholds["semanticTextMode"] })}
          >
            <option value="names">names</option>
            <option value="names_types_bag">names_types_bag</option>
            <option value="typed_name_pairs">typed_name_pairs</option>
          </select>
        </label>
        <label className="wideField">
          Model
          <input value={thresholds.bertModelName} onChange={(event) => patch({ bertModelName: event.target.value })} />
        </label>
        <label>
          Batch size
          <input
            type="number"
            min="1"
            step="1"
            value={thresholds.bertBatchSize}
            onChange={(event) => patch({ bertBatchSize: Number(event.target.value) })}
          />
        </label>
        <label>
          Max length
          <input
            type="number"
            min="16"
            max="512"
            step="16"
            value={thresholds.bertMaxLength}
            onChange={(event) => patch({ bertMaxLength: Number(event.target.value) })}
          />
        </label>
      </div>
    );
  }

  if (technique === "graph_isomorphism") {
    return (
      <div className="configGrid">
        <label>
          Mode
          <select value={thresholds.isomorphismMode} onChange={(event) => patch({ isomorphismMode: event.target.value })}>
            <option value="structure">Structure</option>
            <option value="names">Names</option>
            <option value="names_types">Names + types</option>
          </select>
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.matchEdgeTypes}
            onChange={(event) => patch({ matchEdgeTypes: event.target.checked })}
          />
          Match edge types
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.ignoreDirection}
            onChange={(event) => patch({ ignoreDirection: event.target.checked })}
          />
          Ignore direction
        </label>
        <label className="inlineCheck">
          <input
            type="checkbox"
            checked={thresholds.matchParallelEdgeMultiplicity}
            onChange={(event) => patch({ matchParallelEdgeMultiplicity: event.target.checked })}
          />
          Match parallel multiplicity
        </label>
      </div>
    );
  }

  return null;
}

function DuplicateProgress({ progress }: { progress: DuplicateProgressState }) {
  const overallProgress = Math.max(0, Math.min(100, Number(progress.progress || 0)));
  const completed = (progress.completedTechniques || []).length;
  const total = progress.totalTechniques || 0;
  const message =
    progress.message ||
    (progress.status === "complete" ? "Duplicate detection complete." : "Running duplicate detection.");
  return (
    <div className="progressPanel">
      <div className="progressHeader">
        <div>
          <h3>{message}</h3>
          <p>
            {progress.totalModels || 0} models, {completed} of {total} techniques complete, {" "}
            {formatDuration(progress.elapsedMs || 0)} elapsed
          </p>
          {progress.currentTechnique && <p>Current technique: {techniqueLabel(progress.currentTechnique)}</p>}
        </div>
        <strong>{overallProgress}%</strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill" style={{ width: `${overallProgress}%` }} />
      </div>
    </div>
  );
}

function DuplicateResults({
  result,
  onInspectModel,
  onInspectBoth,
}: {
  result: DuplicateResult | null;
  onInspectModel: (modelId: string) => void;
  onInspectBoth: (leftId: string, rightId: string) => void;
}) {
  if (!result) return <EmptyState text="Run duplicate detection to see technique votes and candidate pairs." />;
  const candidatePairs = result.candidatePairs ?? result.duplicatePairs;
  const approvedPairs = result.approvedPairs ?? result.votedDuplicatePairs ?? 0;
  const duplicateGroups = result.duplicateGroups ?? result.groupSummary?.totalGroups ?? result.groups?.length ?? 0;
  const affectedModels = result.affectedModels ?? result.groupSummary?.affectedModels ?? 0;
  const largestGroupSize = result.largestGroupSize ?? result.groupSummary?.largestGroupSize ?? 0;

  return (
    <div className="results">
      <div className="metricGrid small">
        <Metric label="Candidate pairs" value={candidatePairs} />
        <Metric label="Vote-approved pairs" value={approvedPairs} />
        <Metric label="Duplicate groups" value={duplicateGroups} />
        <Metric label="Affected models" value={affectedModels} />
        <Metric label="Largest group" value={largestGroupSize} />
        <Metric label="Runtime" value={formatDuration(result.elapsedMs)} />
        {Object.entries(result.techniqueCounts).map(([key, value]) => (
          <Metric key={key} label={techniqueLabel(key)} value={value} />
        ))}
      </div>
      <DuplicateModelCharts modelCounts={result.modelCounts || {}} />
      <DuplicateReviewTabs result={result} onInspectModel={onInspectModel} onInspectBoth={onInspectBoth} />
    </div>
  );
}

function DuplicateReviewTabs({
  result,
  onInspectModel,
  onInspectBoth,
}: {
  result: DuplicateResult;
  onInspectModel: (modelId: string) => void;
  onInspectBoth: (leftId: string, rightId: string) => void;
}) {
  return (
    <Tabs defaultValue="groups" className="duplicateTabs">
      <div className="resultsHeader duplicateResultsHeader">
        <div>
          <span>Review results</span>
          <strong>{result.totalDecisions ?? result.decisions.length} candidate decision(s)</strong>
        </div>
        <TabsList>
          <TabsTrigger value="groups">Groups</TabsTrigger>
          <TabsTrigger value="pairs">Pairs</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="groups">
        <DuplicateGroupsReview result={result} onInspectModel={onInspectModel} onInspectBoth={onInspectBoth} />
      </TabsContent>
      <TabsContent value="pairs">
        <DuplicatePairsReview result={result} onInspectBoth={onInspectBoth} />
      </TabsContent>
    </Tabs>
  );
}

function DuplicateGroupsReview({
  result,
  onInspectModel,
  onInspectBoth,
}: {
  result: DuplicateResult;
  onInspectModel: (modelId: string) => void;
  onInspectBoth: (leftId: string, rightId: string) => void;
}) {
  const jobId = result.jobId || "";
  const initialPage = useMemo<DuplicateGroupsPage>(
    () =>
      result.groupsPage || {
        groups: result.groups || [],
        page: 1,
        pageSize: 25,
        total: result.groups?.length || 0,
        totalPages: 1,
      },
    [result],
  );
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [groupsPage, setGroupsPage] = useState<DuplicateGroupsPage>(initialPage);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupDetail, setGroupDetail] = useState<DuplicateGroupDetail | null>(null);
  const [canonicalOverrides, setCanonicalOverrides] = useState<Record<string, string>>({});

  useEffect(() => {
    setPage(1);
    setQuery("");
    setGroupsPage(initialPage);
    setSelectedGroupId(null);
    setGroupDetail(null);
    setCanonicalOverrides({});
  }, [initialPage]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const next = await getDuplicateGroups(jobId, { page, pageSize: 25, query: query.trim() });
        if (!cancelled) setGroupsPage(next);
      } catch (err) {
        if (!cancelled) setLoadError(errorText(err, "Could not load duplicate groups."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [jobId, page, query]);

  useEffect(() => {
    if (!jobId || !selectedGroupId) return;
    const groupId = selectedGroupId;
    let cancelled = false;
    async function loadDetail() {
      try {
        const detail = await getDuplicateGroupDetail(jobId, groupId);
        if (!cancelled) setGroupDetail(detail);
      } catch (err) {
        if (!cancelled) setLoadError(errorText(err, "Could not load duplicate group detail."));
      }
    }
    loadDetail();
    return () => {
      cancelled = true;
    };
  }, [jobId, selectedGroupId]);

  function canonicalFor(group: DuplicateGroup) {
    return canonicalOverrides[group.groupId] || group.canonicalModelId;
  }

  async function exportCanonicalSelections() {
    const groups = await loadAllGroupsForExport(jobId, result, groupsPage);
    const selections: DuplicateCanonicalSelection[] = groups.map((group) => {
      const canonicalModelId = canonicalOverrides[group.groupId] || group.canonicalModelId;
      return {
        groupId: group.groupId,
        canonicalModelId,
        duplicateModelIds: group.modelIds.filter((modelId) => modelId !== canonicalModelId),
      };
    });
    downloadText("duplicate-canonical-selection.json", JSON.stringify({ selections }, null, 2), "application/json");
  }

  return (
    <div className="duplicateReview">
      <div className="duplicateToolbar">
        <Input
          value={query}
          placeholder="Search groups or model IDs"
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
        <Button type="button" variant="secondary" onClick={exportCanonicalSelections} disabled={!groupsPage.total}>
          <Download size={16} />
          Export canonical JSON
        </Button>
      </div>
      {loadError && <div className="error">{loadError}</div>}
      <div className="duplicateDecisionTable duplicateGroupTable">
        <table>
          <thead>
            <tr>
              <th>Group</th>
              <th>Evidence</th>
              <th>Quality</th>
              <th>Canonical model</th>
              <th>Methods</th>
              <th>Review</th>
            </tr>
          </thead>
          <tbody>
            {groupsPage.groups.map((group) => (
              <tr key={group.groupId}>
                <td>
                  <strong>{group.groupId}</strong>
                  <small>{group.size} models</small>
                </td>
                <td>
                  <strong>
                    {group.approvedInternalPairs} / {group.possibleInternalPairs}
                  </strong>
                  <small>
                    {group.candidateRejectedInternalPairs} not approved, {group.missingInternalPairs} missing
                  </small>
                </td>
                <td>
                  <span className={`qualityPill ${group.confidence}`}>{group.confidence}</span>
                  {group.warnings?.length ? <small>{group.warnings[0]}</small> : <small>All direct evidence looks consistent.</small>}
                </td>
                <td>
                  <select
                    value={canonicalFor(group)}
                    onChange={(event) =>
                      setCanonicalOverrides((current) => ({ ...current, [group.groupId]: event.target.value }))
                    }
                  >
                    {(group.modelSummaries || group.modelIds.map((modelId) => ({ modelId }))).map((model) => (
                      <option key={model.modelId} value={model.modelId}>
                        {model.modelId}
                      </option>
                    ))}
                  </select>
                  <small>{group.canonicalReason || "Suggested canonical model"}</small>
                </td>
                <td>
                  <div className="scoreChips">
                    {group.techniques.map((technique) => (
                      <span key={technique} className="scoreChip">
                        {techniqueLabel(technique)}
                      </span>
                    ))}
                  </div>
                </td>
                <td>
                  <button type="button" className="tableInfoButton" onClick={() => setSelectedGroupId(group.groupId)}>
                    <Eye size={15} />
                    Inspect group
                  </button>
                </td>
              </tr>
            ))}
            {!loading && !groupsPage.groups.length && (
              <tr>
                <td colSpan={6}>No duplicate groups match the current filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination page={groupsPage.page} totalPages={groupsPage.totalPages} loading={loading} onPageChange={setPage} />
      {selectedGroupId && groupDetail && (
        <DuplicateGroupDetailPanel
          detail={groupDetail}
          canonicalModelId={canonicalOverrides[groupDetail.group.groupId] || groupDetail.group.canonicalModelId}
          onCanonicalChange={(modelId) =>
            setCanonicalOverrides((current) => ({ ...current, [groupDetail.group.groupId]: modelId }))
          }
          onInspectModel={onInspectModel}
          onInspectBoth={onInspectBoth}
        />
      )}
    </div>
  );
}

function DuplicateGroupDetailPanel({
  detail,
  canonicalModelId,
  onCanonicalChange,
  onInspectModel,
  onInspectBoth,
}: {
  detail: DuplicateGroupDetail;
  canonicalModelId: string;
  onCanonicalChange: (modelId: string) => void;
  onInspectModel: (modelId: string) => void;
  onInspectBoth: (leftId: string, rightId: string) => void;
}) {
  return (
    <div className="duplicateGroupDetail">
      <div className="duplicateGroupDetailHeader">
        <div>
          <h3>{detail.group.groupId}</h3>
          <p>
            {detail.group.size} models, {detail.group.approvedInternalPairs} approved internal pair(s),{" "}
            {detail.group.candidateRejectedInternalPairs} candidate warning(s)
          </p>
        </div>
        <label>
          Canonical
          <select value={canonicalModelId} onChange={(event) => onCanonicalChange(event.target.value)}>
            {detail.modelSummaries.map((model) => (
              <option key={model.modelId} value={model.modelId}>
                {model.modelId}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="duplicateGroupModels">
        {detail.modelSummaries.map((model) => (
          <button
            key={model.modelId}
            type="button"
            className={model.modelId === canonicalModelId ? "canonicalModelChip active" : "canonicalModelChip"}
            onClick={() => onInspectModel(model.modelId)}
          >
            <strong>{model.modelId}</strong>
            <span>
              {model.nodeCount ?? 0} nodes, {model.edgeCount ?? 0} edges
            </span>
          </button>
        ))}
      </div>
      <div className="duplicateDecisionTable duplicateInternalPairs">
        <table>
          <thead>
            <tr>
              <th>Pair</th>
              <th>Status</th>
              <th>Votes</th>
              <th>Methods</th>
              <th>Scores</th>
              <th>Compare</th>
            </tr>
          </thead>
          <tbody>
            {detail.pairs.map((pair) => (
              <DuplicatePairRow key={`${pair.leftId}-${pair.rightId}`} pair={pair} onInspectBoth={onInspectBoth} />
            ))}
            {!detail.pairs.length && (
              <tr>
                <td colSpan={6}>This group has no internal candidate pair details.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function DuplicatePairsReview({
  result,
  onInspectBoth,
}: {
  result: DuplicateResult;
  onInspectBoth: (leftId: string, rightId: string) => void;
}) {
  const jobId = result.jobId || "";
  const initialPage = useMemo<DuplicatePairsPage>(
    () =>
      result.pairsPage || {
        pairs: result.decisions || [],
        page: 1,
        pageSize: 50,
        total: result.totalDecisions ?? result.decisions.length,
        totalPages: 1,
      },
    [result],
  );
  const [page, setPage] = useState(1);
  const [decision, setDecision] = useState<"all" | "approved" | "rejected">("all");
  const [query, setQuery] = useState("");
  const [pairsPage, setPairsPage] = useState<DuplicatePairsPage>(initialPage);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    setPage(1);
    setPairsPage(initialPage);
  }, [initialPage]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    async function load() {
      setLoading(true);
      setLoadError("");
      try {
        const next = await getDuplicatePairs(jobId, { page, pageSize: 50, decision, query: query.trim() });
        if (!cancelled) setPairsPage(next);
      } catch (err) {
        if (!cancelled) setLoadError(errorText(err, "Could not load duplicate pairs."));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [jobId, page, decision, query]);

  return (
    <div className="duplicateReview">
      <div className="duplicateToolbar">
        <Input
          value={query}
          placeholder="Search model IDs or methods"
          onChange={(event) => {
            setQuery(event.target.value);
            setPage(1);
          }}
        />
        <select
          value={decision}
          onChange={(event) => {
            setDecision(event.target.value as "all" | "approved" | "rejected");
            setPage(1);
          }}
        >
          <option value="all">All decisions</option>
          <option value="approved">Approved only</option>
          <option value="rejected">Not approved</option>
        </select>
      </div>
      {loadError && <div className="error">{loadError}</div>}
      <div className="duplicateDecisionTable">
        <table>
          <thead>
            <tr>
              <th>Pair</th>
              <th>Group</th>
              <th>Status</th>
              <th>Votes</th>
              <th>Methods</th>
              <th>Scores</th>
              <th>Compare</th>
            </tr>
          </thead>
          <tbody>
            {pairsPage.pairs.map((pair) => (
              <DuplicatePairRow key={`${pair.leftId}-${pair.rightId}`} pair={pair} onInspectBoth={onInspectBoth} showGroup />
            ))}
            {!loading && !pairsPage.pairs.length && (
              <tr>
                <td colSpan={7}>No duplicate pairs match the current filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <Pagination page={pairsPage.page} totalPages={pairsPage.totalPages} loading={loading} onPageChange={setPage} />
    </div>
  );
}

function DuplicatePairRow({
  pair,
  onInspectBoth,
  showGroup = false,
}: {
  pair: DuplicatePairDecision;
  onInspectBoth: (leftId: string, rightId: string) => void;
  showGroup?: boolean;
}) {
  return (
    <tr className={pair.isDuplicate ? "" : "notApprovedPair"}>
      <td>
        <div className="pairIds">
          <span>{pair.leftId}</span>
          <span>{pair.rightId}</span>
        </div>
      </td>
      {showGroup && <td>{pair.groupId || "-"}</td>}
      <td>
        <span className={pair.isDuplicate ? "decisionPill approved" : "decisionPill rejected"}>
          {pair.isDuplicate ? "Approved" : "Not approved"}
        </span>
      </td>
      <td>
        {pair.voteCount}
        {pair.requiredVotes ? ` / ${pair.requiredVotes}` : ""}
      </td>
      <td>{pair.techniques.map(techniqueLabel).join(", ") || "-"}</td>
      <td>
        <div className="scoreChips">
          {Object.entries(pair.scores || {}).map(([technique, score]) => (
            <span key={technique} className="scoreChip">
              <b>{techniqueLabel(technique)}</b>: {round(score)}
            </span>
          ))}
          {!Object.keys(pair.scores || {}).length && <span>-</span>}
        </div>
      </td>
      <td>
        <button type="button" className="tableInfoButton" onClick={() => onInspectBoth(pair.leftId, pair.rightId)}>
          <Eye size={15} />
          Inspect Both
        </button>
      </td>
    </tr>
  );
}

function Pagination({
  page,
  totalPages,
  loading,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  loading: boolean;
  onPageChange: (page: number) => void;
}) {
  if (totalPages <= 1) return null;
  return (
    <div className="tablePagination">
      <button type="button" disabled={page <= 1 || loading} onClick={() => onPageChange(Math.max(1, page - 1))}>
        <ChevronLeft size={15} />
        Previous
      </button>
      <span>
        Page {page} of {totalPages}
      </span>
      <button type="button" disabled={page >= totalPages || loading} onClick={() => onPageChange(Math.min(totalPages, page + 1))}>
        Next
        <ChevronRight size={15} />
      </button>
    </div>
  );
}

async function loadAllGroupsForExport(
  jobId: string,
  result: DuplicateResult,
  currentPage: DuplicateGroupsPage,
): Promise<DuplicateGroup[]> {
  if (!jobId) return result.groups || currentPage.groups;
  const first = await getDuplicateGroups(jobId, { page: 1, pageSize: 250 });
  const groups = [...first.groups];
  for (let page = 2; page <= first.totalPages; page += 1) {
    const next = await getDuplicateGroups(jobId, { page, pageSize: 250 });
    groups.push(...next.groups);
  }
  return groups;
}

function downloadText(filename: string, content: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function errorText(err: unknown, fallback: string) {
  return err instanceof Error ? err.message : fallback;
}

function DuplicateModelCharts({ modelCounts }: { modelCounts: DuplicateResult["modelCounts"] }) {
  const entries = Object.entries(modelCounts);
  if (!entries.length) return null;

  return (
    <div className="duplicateCharts">
      {entries.map(([technique, counts]) => (
        <div className="duplicateChartCard" key={technique}>
          <h3>{techniqueLabel(technique)}</h3>
          <div className="piePair">
            <PieStat
              label="Duplicate models"
              value={counts.duplicateModels}
              total={counts.totalModels}
              tone="duplicate"
            />
            <PieStat label="Unique models" value={counts.uniqueModels} total={counts.totalModels} tone="unique" />
          </div>
          <p>
            {counts.pairCount} duplicate pair(s) found in {formatDuration(counts.elapsedMs)}
          </p>
        </div>
      ))}
    </div>
  );
}

function PieStat({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  tone: string;
}) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="pieStat">
      <div
        className={`pie ${tone}`}
        style={{ "--percent": `${percent}%` } as CSSProperties}
        aria-label={`${label}: ${value} of ${total}`}
      />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>
          {percent}% of {total}
        </small>
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
