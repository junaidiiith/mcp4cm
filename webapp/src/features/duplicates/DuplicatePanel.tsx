import { GitCompare, Layers3, Loader2, Plus, SlidersHorizontal } from "lucide-react";
import { EChart } from "@/components/charts/EChart";
import { duplicatePieOption } from "@/components/charts/builders";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { techniques } from "../../config";
import type { BusyState, DuplicateProgressState, DuplicateResult, Thresholds } from "../../types";
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
          <Label>
            Result limit
            <Input
              type="number"
              min="1"
              step="50"
              value={thresholds.resultLimit}
              onChange={(event) => onThresholdsChange({ ...thresholds, resultLimit: Number(event.target.value) })}
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
  const totalDecisions = result.totalDecisions ?? result.decisions.length;
  const returnedDecisions = result.returnedDecisions ?? result.decisions.length;

  return (
    <div className="results">
      <div className="metricGrid small">
        <Metric label="Candidate pairs" value={candidatePairs} />
        <Metric label="Vote-approved pairs" value={approvedPairs} />
        <Metric label="Runtime" value={formatDuration(result.elapsedMs)} />
        {Object.entries(result.techniqueCounts).map(([key, value]) => (
          <Metric key={key} label={key} value={value} />
        ))}
      </div>
      {result.truncated && (
        <div className="error">
          Showing {returnedDecisions} of {totalDecisions} decisions due to result limit ({result.truncationLimit}).
        </div>
      )}
      <DuplicateModelCharts modelCounts={result.modelCounts || {}} />
      <div className="duplicateDecisionTable">
        <table>
          <thead>
            <tr>
              <th>Left</th>
              <th>Right</th>
              <th>Compare</th>
              <th>Approved</th>
              <th>Votes</th>
              <th>Techniques</th>
              <th>Scores</th>
            </tr>
          </thead>
          <tbody>
            {result.decisions.map((row) => (
              <tr key={`${row.leftId}-${row.rightId}`}>
                <td>
                  <div className="decisionCell">
                    <span>{row.leftId}</span>
                    <button type="button" className="tableInfoButton" onClick={() => onInspectModel(row.leftId)}>
                      Inspect Left
                    </button>
                  </div>
                </td>
                <td>
                  <div className="decisionCell">
                    <span>{row.rightId}</span>
                    <button type="button" className="tableInfoButton" onClick={() => onInspectModel(row.rightId)}>
                      Inspect Right
                    </button>
                  </div>
                </td>
                <td>
                  <button
                    type="button"
                    className="tableInfoButton"
                    onClick={() => onInspectBoth(row.leftId, row.rightId)}
                  >
                    Inspect Both
                  </button>
                </td>
                <td>{row.isDuplicate ? "Yes" : "No"}</td>
                <td>
                  {row.voteCount}
                  {row.requiredVotes ? ` / ${row.requiredVotes}` : ""}
                </td>
                <td>{row.techniques.join(", ") || "-"}</td>
                <td>
                  <div className="scoreChips">
                    {Object.entries(row.scores || {}).map(([technique, score]) => (
                      <span key={technique} className="scoreChip">
                        <b>{techniqueLabel(technique)}</b>: {round(score)}
                      </span>
                    ))}
                    {!Object.keys(row.scores || {}).length && <span>-</span>}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
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
  tone: "duplicate" | "unique";
}) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="pieStat">
      <EChart
        ariaLabel={`${label}: ${value} of ${total}`}
        className="pieChart"
        height={86}
        option={duplicatePieOption({ label, value, total, tone })}
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
