import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Check,
  Database,
  FileUp,
  Filter,
  GitCompare,
  Info,
  Loader2,
  Plus,
  SlidersHorizontal,
  X,
} from "lucide-react";
import Cytoscape from "cytoscape";
import CytoscapeComponent from "react-cytoscapejs";
import coseBilkent from "cytoscape-cose-bilkent";
import "./styles.css";
import {
  clonePreset,
  defaultFormatForLanguage,
  defaultThresholds,
  filterFormulaPreviews,
  filterGroups,
  filterLabels,
  formatOptionsByLanguage,
  techniques,
} from "./config";
import { getModelInspect, pollDuplicateJob, pollUploadParseJob, postForm, postJson } from "./api";
import { backendTechniquesFor, formatDuration, round, techniqueLabel } from "./utils";
import type {
  DummyResponse,
  FilterConfig,
  Language,
  ModelInspectPayload,
  ParsedModelSummary,
  RepresentationProfile,
  StatisticsPayload,
  Thresholds,
  UploadParseJob,
  UploadFormat,
  UploadSummary,
  WarningEntry,
} from "./types";

Cytoscape.use(coseBilkent);

export default function App() {
  const uploadChunkSize = 200;
  const [language, setLanguage] = useState<Language>("uml");
  const [format, setFormat] = useState<UploadFormat>(defaultFormatForLanguage("uml"));
  const [files, setFiles] = useState<File[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [stats, setStats] = useState<StatisticsPayload | null>(null);
  const [uploadSummary, setUploadSummary] = useState<UploadSummary | null>(null);
  const [uploadParseJob, setUploadParseJob] = useState<UploadParseJob | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState(0);
  const [dummyResponse, setDummyResponse] = useState<DummyResponse | null>(null);
  const [selectedOutcomeModelId, setSelectedOutcomeModelId] = useState<string | null>(null);
  const [duplicateResult, setDuplicateResult] = useState<any>(null);
  const [duplicateProgress, setDuplicateProgress] = useState<any>(null);
  const [selected, setSelected] = useState<string[]>(["hash", "tfidf"]);
  const [mandatory, setMandatory] = useState<string[]>(["hash"]);
  const [minVotes, setMinVotes] = useState(2);
  const [thresholds, setThresholds] = useState<Thresholds>(defaultThresholds);
  const [representation, setRepresentation] = useState<RepresentationProfile>({
    includeAttributes: true,
    includeOperations: true,
    includeParameters: true,
    includeModelRootNode: false,
  });
  const [dummyFilterConfigs, setDummyFilterConfigs] = useState(() => clonePreset("uml"));
  const [showDummyInfo, setShowDummyInfo] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [selectedModel, setSelectedModel] = useState<ParsedModelSummary | null>(null);
  const [inspectorTab, setInspectorTab] = useState<"warnings" | "model">("warnings");
  const [inspectModel, setInspectModel] = useState<ModelInspectPayload | null>(null);
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectError, setInspectError] = useState("");

  const canRun = Boolean(datasetId);
  const selectedTechniques = useMemo(() => new Set(selected), [selected]);
  const formatOptions = formatOptionsByLanguage[language];
  const selectedFormat = formatOptions.find((option) => option.value === format) || formatOptions[0];
  const directoryMode = selectedFormat.directoryPreferred;
  const representationEnabled = language === "uml" && format === "xmi";
  const warningsList = uploadSummary?.warningsList || [];
  const parsedModels = uploadSummary?.parsedModels || [];
  const statsLoading = !stats && (
    busy === "parse" ||
    uploadParseJob?.status === "queued" ||
    uploadParseJob?.status === "running"
  );
  const fileDropText = directoryMode
    ? (files.length ? `${files.length} file(s) selected from directory` : "Choose model directory")
    : (files.length ? `${files.length} file(s) selected` : "Choose JSON / JSONL files");

  function uploadSessionPayload() {
    const payload: Record<string, any> = { language, format };
    if (representationEnabled) {
      payload.includeAttributes = representation.includeAttributes;
      payload.includeOperations = representation.includeOperations;
      payload.includeParameters = representation.includeParameters;
      payload.includeModelRootNode = representation.includeModelRootNode;
    }
    return payload;
  }

  async function parseDataset(nextFiles = files) {
    setError("");
    if (!nextFiles.length) {
      setError(directoryMode ? "Choose at least one model file or directory." : "Choose at least one JSON or JSONL file.");
      return;
    }
    setBusy("parse");
    setDatasetId("");
    setStats(null);
    setUploadSummary(null);
    setUploadParseJob(null);
    setUploadedFiles(0);
    setDummyResponse(null);
    setSelectedOutcomeModelId(null);
    setDuplicateResult(null);
    setDuplicateProgress(null);
    closeModelInspector();
    try {
      const session = await postJson("/api/uploads/start", uploadSessionPayload());
      const uploadId = String(session.uploadId);
      const total = nextFiles.length;
      for (let start = 0; start < total; start += uploadChunkSize) {
        const chunk = nextFiles.slice(start, start + uploadChunkSize);
        const formData = new FormData();
        chunk.forEach((file) => formData.append("files", file, file.webkitRelativePath || file.name));
        await postForm(`/api/uploads/${uploadId}/chunks`, formData);
        setUploadedFiles(Math.min(start + chunk.length, total));
      }
      const startedJob = await postJson(`/api/uploads/${uploadId}/parse`, {});
      setUploadParseJob(startedJob);
      const finishedJob = await pollUploadParseJob(uploadId, startedJob.jobId, (job) => {
        setUploadParseJob(job);
        if (job.datasetId) setDatasetId(String(job.datasetId));
        if (job.uploadSummary) setUploadSummary(job.uploadSummary);
        if (job.statistics) setStats(job.statistics);
      });
      setUploadParseJob(finishedJob);
      setUploadSummary(finishedJob.uploadSummary || null);
      if (finishedJob.datasetId) setDatasetId(String(finishedJob.datasetId));
      if (finishedJob.statistics) setStats(finishedJob.statistics);
    } catch (err: any) {
      setError(err?.message || "Parsing failed.");
    } finally {
      setBusy("");
    }
  }

  async function runDummyFilters() {
    setError("");
    setBusy("dummy");
    try {
      const response = await postJson("/api/dummy", { datasetId, filterConfigs: dummyFilterConfigs });
      setDummyResponse(response as DummyResponse);
      setSelectedOutcomeModelId(null);
    } catch (err: any) {
      setError(err?.message || "Dummy filter execution failed.");
    } finally {
      setBusy("");
    }
  }

  async function runDuplicateDetection() {
    setError("");
    setBusy("duplicates");
    setDuplicateResult(null);
    setDuplicateProgress(null);
    try {
      if (!selected.length) {
        throw new Error("Select at least one duplicate technique.");
      }
      const selectedBackendTechniques = selected.flatMap((item) => backendTechniquesFor(item, thresholds));
      const selectedBackendSet = new Set(selectedBackendTechniques);
      const activeMandatory = mandatory
        .filter((item) => selected.includes(item))
        .flatMap((item) => backendTechniquesFor(item, thresholds))
        .filter((item) => selectedBackendSet.has(item));
      const payload = {
        datasetId,
        techniques: selectedBackendTechniques,
        selectedTechniques: selectedBackendTechniques,
        mandatoryTechniques: activeMandatory,
        minVotes,
        thresholds,
      };
      const job = await postJson("/api/duplicates/jobs", payload);
      setDuplicateProgress(job);
      const result = await pollDuplicateJob(job.jobId);
      setDuplicateProgress(result);
      setDuplicateResult(result.result);
    } catch (err: any) {
      setError(err?.message || "Duplicate detection failed.");
    } finally {
      setBusy("");
    }
  }

  function openModelInspector(row: ParsedModelSummary) {
    setSelectedModel(row);
    setInspectorTab("warnings");
  }

  function closeModelInspector() {
    setSelectedModel(null);
    setInspectModel(null);
    setInspectError("");
    setInspectLoading(false);
  }

  useEffect(() => {
    let cancelled = false;
    async function loadInspectModel() {
      if (!selectedModel) {
        setInspectModel(null);
        setInspectError("");
        setInspectLoading(false);
        return;
      }
      if (!datasetId || !selectedModel.modelId) {
        setInspectModel(null);
        setInspectError(!datasetId ? "Process selected models to inspect parsed graph details." : "No model id linked for this model.");
        setInspectLoading(false);
        return;
      }
      setInspectLoading(true);
      setInspectError("");
      try {
        const response = await getModelInspect(datasetId, selectedModel.modelId, { nodeLimit: 400, edgeLimit: 800, includeAttrs: true });
        if (!cancelled) {
          setInspectModel(response);
        }
      } catch (err: any) {
        if (!cancelled) {
          setInspectModel(null);
          setInspectError(err?.message || "Failed to load parsed model details.");
        }
      } finally {
        if (!cancelled) {
          setInspectLoading(false);
        }
      }
    }
    loadInspectModel();
    return () => {
      cancelled = true;
    };
  }, [datasetId, selectedModel?.modelId, selectedModel?.path]);

  function toggleSelection(id: string) {
    setSelected((current) => {
      const isSelected = current.includes(id);
      if (isSelected) {
        setMandatory((mandatoryCurrent) => mandatoryCurrent.filter((item) => item !== id));
        return current.filter((item) => item !== id);
      }
      return [...current, id];
    });
  }

  function toggleMandatory(id: string) {
    if (!selectedTechniques.has(id)) return;
    setMandatory((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function changeLanguage(nextLanguage: Language) {
    setLanguage(nextLanguage);
    setFormat(defaultFormatForLanguage(nextLanguage));
    setDummyFilterConfigs(clonePreset(nextLanguage));
    setFiles([]);
    setDummyResponse(null);
    setSelectedOutcomeModelId(null);
    setDatasetId("");
    setStats(null);
    setUploadSummary(null);
    setUploadParseJob(null);
    setUploadedFiles(0);
    closeModelInspector();
    if (nextLanguage !== "uml") {
      setRepresentation({
        includeAttributes: true,
        includeOperations: true,
        includeParameters: true,
        includeModelRootNode: false,
      });
    }
  }

  function changeFormat(nextFormat: UploadFormat) {
    setFormat(nextFormat);
    setFiles([]);
    setUploadSummary(null);
    setUploadParseJob(null);
    setUploadedFiles(0);
    setDatasetId("");
    setStats(null);
    setDummyResponse(null);
    setSelectedOutcomeModelId(null);
    closeModelInspector();
    if (!(language === "uml" && nextFormat === "xmi")) {
      setRepresentation({
        includeAttributes: true,
        includeOperations: true,
        includeParameters: true,
        includeModelRootNode: false,
      });
    }
  }

  function updateDummyFilter(index: number, patch: FilterConfig) {
    setDummyFilterConfigs((current) => current.map((filter, i) => (i === index ? { ...filter, ...patch } : filter)));
  }

  function resetDummyFilters() {
    setDummyFilterConfigs(clonePreset(language));
    setDummyResponse(null);
    setSelectedOutcomeModelId(null);
  }

  return (
    <main>
      <aside className="sidebar">
        <div className="brand">
          <img className="brandMark" src="/mcp4cm-icon.svg" alt="" />
          <div>
            <strong>MCP4CM</strong>
            <span>Model Cleansing Pipeline</span>
          </div>
        </div>
        <nav>
          <a href="#upload"><FileUp size={18} />Upload</a>
          <a href="#stats"><BarChart3 size={18} />Statistics</a>
          <a href="#dummy"><Filter size={18} />Dummy Filters</a>
          <a href="#duplicates"><GitCompare size={18} />Duplicates</a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <h1>Model Dataset Cleansing</h1>
            <p>Upload UML, Ecore, or ArchiMate model datasets, inspect quality, and decide duplicates with transparent evidence.</p>
          </div>
          <Status datasetId={datasetId} busy={busy} />
        </header>

        {error && <div className="error">{error}</div>}

        <section className="panel" id="upload">
          <SectionTitle icon={<Database size={20} />} title="Dataset Upload" />
          <div className="uploadGrid">
            <label>
              Modeling language
              <select value={language} onChange={(event) => changeLanguage(event.target.value as Language)}>
                <option value="uml">UML</option>
                <option value="ecore">Ecore</option>
                <option value="archimate">ArchiMate</option>
                <option value="bpmn">BPMN</option>
              </select>
            </label>
            <label>
              Parser format
              <select value={format} onChange={(event) => changeFormat(event.target.value as UploadFormat)}>
                {formatOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="fileDrop">
              <FileUp size={24} />
              <span>{fileDropText}</span>
              <input
                type="file"
                multiple
                accept={selectedFormat.accept}
                {...(directoryMode ? ({ webkitdirectory: "", directory: "" } as any) : {})}
                onChange={(event) => {
                  const nextFiles = Array.from(event.target.files || []);
                  setFiles(nextFiles);
                  setUploadParseJob(null);
                  setUploadedFiles(0);
                }}
              />
            </label>
            {representationEnabled && (
              <div className="representationPanel">
                <p>Enable to materialize feature nodes and parent-link edges in the parsed graph.</p>
                <div className="representationChecks">
                  <label className="inlineCheck">
                    <input
                      type="checkbox"
                      checked={representation.includeAttributes}
                      onChange={(event) =>
                        setRepresentation((current) => ({ ...current, includeAttributes: event.target.checked }))
                      }
                    />
                    Attributes as Nodes
                  </label>
                  <label className="inlineCheck">
                    <input
                      type="checkbox"
                      checked={representation.includeOperations}
                      onChange={(event) =>
                        setRepresentation((current) => ({ ...current, includeOperations: event.target.checked }))
                      }
                    />
                    Operations as Nodes
                  </label>
                  <label className="inlineCheck">
                    <input
                      type="checkbox"
                      checked={representation.includeParameters}
                      onChange={(event) =>
                        setRepresentation((current) => ({ ...current, includeParameters: event.target.checked }))
                      }
                    />
                    Parameters as Nodes
                  </label>
                  <label className="inlineCheck">
                    <input
                      type="checkbox"
                      checked={representation.includeModelRootNode}
                      onChange={(event) =>
                        setRepresentation((current) => ({ ...current, includeModelRootNode: event.target.checked }))
                      }
                    />
                    Create model root node
                  </label>
                </div>
              </div>
            )}
            <div className="actionBar">
              <button
                type="button"
                className="primary"
                disabled={!files.length || busy === "parse"}
                onClick={() => parseDataset()}
              >
                {busy === "parse" ? <Loader2 className="spin" size={18} /> : <FileUp size={18} />}
                {datasetId ? "Reparse Dataset" : "Parse Dataset"}
              </button>
            </div>
          <p className="uploadHint">Select files, tune parser parameters, then parse. You can reparse with new parameters at any time.</p>
          </div>
          {(busy === "parse" || uploadParseJob) && (
            <UploadParseProgress
              totalFiles={files.length}
              uploadedFiles={uploadedFiles}
              job={uploadParseJob}
            />
          )}
        </section>

        <section className="panel" id="stats">
          <SectionTitle icon={<BarChart3 size={20} />} title="Descriptive Statistics" />
          {uploadSummary && <UploadSummaryPanel summary={uploadSummary} />}
          {(uploadSummary?.records || 0) > 0 ? (
            <ParsedModelsTable
              models={parsedModels}
              warnings={warningsList}
              onInspect={openModelInspector}
            />
          ) : null}
          {stats ? (
            <Statistics stats={stats} />
          ) : statsLoading ? (
            <StatisticsLoading job={uploadParseJob} />
          ) : (
            <EmptyState text="Upload a dataset to see descriptive statistics." />
          )}
        </section>

        <section className="panel" id="dummy">
          <SectionTitle icon={<Filter size={20} />} title="Dummy Model Cleansing" />
          <div className="subsectionHeader">
            <div>
              <h3>Built-in Filters</h3>
              <p>Enable canonical V2 filters and tune formulas before running the cleansing pass.</p>
            </div>
            <div className="subsectionActions">
              <button type="button" className="tableInfoButton" onClick={() => setShowDummyInfo(true)}>
                <Info size={15} />
                Info
              </button>
              <button type="button" onClick={resetDummyFilters}>Reset defaults</button>
            </div>
          </div>
          <BuiltInFilterEditor filters={dummyFilterConfigs} onChange={updateDummyFilter} />
          <div className="actionBar">
            <button onClick={runDummyFilters} disabled={!canRun || busy === "dummy"}>
              {busy === "dummy" ? <Loader2 className="spin" size={18} /> : <Filter size={18} />}
              Run Filters
            </button>
          </div>
          <DummyResults
            result={dummyResponse}
            selectedModelId={selectedOutcomeModelId}
            onSelectModelId={setSelectedOutcomeModelId}
          />
        </section>
        {showDummyInfo && <DummyCleansingInfoModal onClose={() => setShowDummyInfo(false)} />}

        <section className="panel" id="duplicates">
          <SectionTitle icon={<GitCompare size={20} />} title="Duplicate Detection" />
          <div className="techGrid">
            {techniques.map((technique) => (
              <div className="techCard" key={technique.id}>
                <label className="checkLine">
                  <input
                    type="checkbox"
                    checked={selected.includes(technique.id)}
                    onChange={() => toggleSelection(technique.id)}
                  />
                  <span>{technique.label}</span>
                </label>
                <p>{technique.detail}</p>
                <label className="mandatory">
                  <input
                    type="checkbox"
                    checked={mandatory.includes(technique.id)}
                    disabled={!selected.includes(technique.id)}
                    onChange={() => toggleMandatory(technique.id)}
                  />
                  Mandatory
                </label>
                <details className="techConfig">
                  <summary><SlidersHorizontal size={15} /> Configure</summary>
                  <TechniqueConfig technique={technique.id} thresholds={thresholds} onChange={setThresholds} />
                </details>
              </div>
            ))}
          </div>

          <div className="runConfig">
            <label>Min votes<input type="number" min="1" value={minVotes} onChange={(e) => setMinVotes(Number(e.target.value))} /></label>
          </div>

          <div className="actionBar">
            <button className="primary" onClick={runDuplicateDetection} disabled={!canRun || busy === "duplicates"}>
              {busy === "duplicates" ? <Loader2 className="spin" size={18} /> : <GitCompare size={18} />}
              Run Duplicate Detection
            </button>
          </div>
          {duplicateProgress && <DuplicateProgress progress={duplicateProgress} />}
          <DuplicateResults result={duplicateResult} />
        </section>
      </section>
      {selectedModel && (
        <WarningInspectorDrawer
          model={selectedModel}
          warnings={warningsList.filter((entry) => (entry.modelId || "") === selectedModel.modelId)}
          tab={inspectorTab}
          onTabChange={setInspectorTab}
          onClose={closeModelInspector}
          inspectLoading={inspectLoading}
          inspectError={inspectError}
          inspectModel={inspectModel}
        />
      )}
    </main>
  );
}

function SectionTitle({ icon, title }) {
  return <h2>{icon}{title}</h2>;
}

function DummyCleansingInfoModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="infoOverlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="infoModal" onClick={(event) => event.stopPropagation()}>
        <div className="inspectorHeader">
          <div>
            <h3>Dummy Cleansing Information</h3>
            <p>How names are classified and how filters evaluate models.</p>
          </div>
          <button type="button" className="closeButton" onClick={onClose} aria-label="Close information">
            <X size={18} />
          </button>
        </div>
        <div className="inspectorBody">
          <h4>Name Classification</h4>
          <ul>
            <li><strong>`missing`</strong>: raw node name is empty or whitespace after trimming.</li>
            <li><strong>`type_like`</strong>: normalized name matches normalized node type (for example `Class`, `Class1`, `Business Object`).</li>
            <li><strong>`placeholder`</strong>: normalized name matches placeholder patterns or keywords (for example `dummy`, `my class`, `att1`).</li>
            <li><strong>`semantic`</strong>: name is present and is neither `type_like` nor `placeholder`.</li>
          </ul>
          <h4>Important Terms</h4>
          <ul>
            <li><strong>`named nodes`</strong>: all nodes except `missing`.</li>
            <li><strong>`eligible names`</strong>: `semantic` names only. Filters like naming-density, median-length, and vocabulary use this set.</li>
            <li><strong>Normalization</strong>: cleansing-time only (`lowercase`, whitespace compaction, tokenization). Raw parsed names stay unchanged.</li>
          </ul>
          <h4>Filter Execution</h4>
          <ul>
            <li>Filters run in chain order and are cumulative for the waterfall view.</li>
            <li>`primaryRemovalReason` is the first filter that removes a model.</li>
            <li>`allTriggeredFilters` shows every filter that would remove that model.</li>
            <li>`findings` keep per-filter metrics, score, threshold, and evidence nodes for traceability.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function UploadParseProgress({
  totalFiles,
  uploadedFiles,
  job,
}: {
  totalFiles: number;
  uploadedFiles: number;
  job: UploadParseJob | null;
}) {
  const uploadPercent = totalFiles ? Math.round((uploadedFiles / totalFiles) * 100) : 0;
  const parseTotal = job?.parseTotalFiles || job?.totalFiles || totalFiles;
  const parseProcessed = job?.parseProcessedFiles || 0;
  const parsePercent = parseTotal ? Math.round((parseProcessed / parseTotal) * 100) : 0;
  return (
    <div className="uploadProgress">
      <h3>Processing Progress</h3>
      <div className="uploadProgressRow">
        <span>Files uploaded</span>
        <strong>{uploadedFiles} / {totalFiles}</strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill" style={{ width: `${uploadPercent}%` }} />
      </div>
      <div className="uploadProgressRow">
        <span>Parse</span>
        <strong>{parseProcessed} / {parseTotal || "-"}</strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill secondary" style={{ width: `${parsePercent}%` }} />
      </div>
      <p>{job?.message || "Preparing upload..."}</p>
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
    const typeText = Object.entries(row.types || {}).map(([type, count]) => `${type} ${count}`).join(" ").toLowerCase();
    if (
      row.path.toLowerCase().includes(lowered) ||
      String(row.modelId || "").toLowerCase().includes(lowered) ||
      String(row.name || "").toLowerCase().includes(lowered) ||
      typeText.includes(lowered)
    ) return true;
    const rowWarnings = warningsByModelId.get(row.modelId) || [];
    return rowWarnings.some((warning) => `${warning.type} ${warning.message}`.toLowerCase().includes(lowered));
  });

  return (
    <div className="warningTableWrap">
      <div className="warningTableHeader">
        <h3>Parsed Models</h3>
        <span>{filteredModels.length} of {models.length} models</span>
      </div>
      <div className="warningTypeChips">
        {types.map(([type, count]) => (
          <span key={type} className="warningTypeChip">{type} ({count})</span>
        ))}
      </div>
      <div className="warningFilters">
        <label>
          Type
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="all">All</option>
            {types.map(([type]) => <option value={type} key={type}>{type}</option>)}
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
                <td>{Object.entries(row.types || {}).length ? Object.entries(row.types || {}).map(([key, value]) => `${key} (${value})`).join(", ") : "-"}</td>
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

function BuiltInFilterEditor({ filters, onChange }) {
  return (
    <div className="filterEditorGrid">
      {filters.map((filter, index) => {
        const [title, detail] = filterLabels[filter.id] || [filter.id, ""];
        const group = filterGroups[filter.id] || "General";
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
            <p><strong>Group:</strong> {group}</p>
            {formula && <p><strong>Formula:</strong> <code>{formula}</code></p>}
            <div className="filterConfigFields">
              {"minNodes" in filter && (
                <label>
                  Min nodes
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={filter.minNodes}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { minNodes: Number(event.target.value) })}
                  />
                </label>
              )}
              {"minEdges" in filter && (
                <label>
                  Min edges
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={filter.minEdges}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { minEdges: Number(event.target.value) })}
                  />
                </label>
              )}
              {"threshold" in filter && (
                <label>
                  Threshold
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={filter.threshold}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { threshold: Number(event.target.value) })}
                  />
                </label>
              )}
              {"minNames" in filter && (
                <label>
                  Min names
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={filter.minNames}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { minNames: Number(event.target.value) })}
                  />
                </label>
              )}
              {"minUniqueWords" in filter && (
                <label>
                  Min words
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={filter.minUniqueWords}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { minUniqueWords: Number(event.target.value) })}
                  />
                </label>
              )}
              {"minMedianLength" in filter && (
                <label>
                  Min median length
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={filter.minMedianLength}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { minMedianLength: Number(event.target.value) })}
                  />
                </label>
              )}
              {"pattern" in filter && (
                <label className="wideField">
                  Pattern
                  <input
                    placeholder="e.g. ^(test|dummy|sample)$"
                    value={filter.pattern}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { pattern: event.target.value })}
                  />
                </label>
              )}
              {"targetField" in filter && (
                <label>
                  Target field
                  <select
                    value={filter.targetField}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { targetField: event.target.value })}
                  >
                    <option value="name">name</option>
                    <option value="name+type">name+type</option>
                    <option value="type">type</option>
                  </select>
                </label>
              )}
              {"scope" in filter && (
                <label>
                  Scope
                  <select
                    value={filter.scope}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { scope: event.target.value })}
                  >
                    <option value="eligible_only">eligible_only</option>
                    <option value="all_named_nodes">all_named_nodes</option>
                  </select>
                </label>
              )}
              {"minMatches" in filter && (
                <label>
                  Min matches
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={filter.minMatches}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { minMatches: Number(event.target.value) })}
                  />
                </label>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function TechniqueConfig({ technique, thresholds, onChange }) {
  const patch = (updates) => onChange({ ...thresholds, ...updates });
  const patchWeights = (updates) => onChange({ ...thresholds, graphWeights: { ...thresholds.graphWeights, ...updates } });

  if (technique === "hash") {
    return (
      <div className="configGrid compact">
        <label className="inlineCheck">
          <input type="checkbox" checked={thresholds.hashIncludeTypes} onChange={(event) => patch({ hashIncludeTypes: event.target.checked })} />
          Types
        </label>
      </div>
    );
  }

  if (technique === "tfidf") {
    const thresholdKey = thresholds.tfidfIncludeTypes ? "tfidfNamesTypes" : "tfidfNames";
    return (
      <div className="configGrid">
        <label className="inlineCheck">
          <input type="checkbox" checked={thresholds.tfidfIncludeTypes} onChange={(event) => patch({ tfidfIncludeTypes: event.target.checked })} />
          Types
        </label>
        <label>Threshold<input type="number" min="0" max="1" step="0.01" value={thresholds[thresholdKey]} onChange={(event) => patch({ [thresholdKey]: Number(event.target.value) })} /></label>
        <label>Max features<input type="number" min="1000" step="1000" value={thresholds.tfidfMaxFeatures} onChange={(event) => patch({ tfidfMaxFeatures: Number(event.target.value) })} /></label>
      </div>
    );
  }

  if (technique === "graph_similarity") {
    const weights = thresholds.graphWeights;
    return (
      <div className="configGrid">
        <label>Threshold<input type="number" min="0" max="1" step="0.01" value={thresholds.graphSimilarity} onChange={(event) => patch({ graphSimilarity: Number(event.target.value) })} /></label>
        <label>Node names<input type="number" min="0" step="0.01" value={weights.nodeNameJaccard} onChange={(event) => patchWeights({ nodeNameJaccard: Number(event.target.value) })} /></label>
        <label>Node types<input type="number" min="0" step="0.01" value={weights.nodeTypeJaccard} onChange={(event) => patchWeights({ nodeTypeJaccard: Number(event.target.value) })} /></label>
        <label>Edge types<input type="number" min="0" step="0.01" value={weights.edgeTypeJaccard} onChange={(event) => patchWeights({ edgeTypeJaccard: Number(event.target.value) })} /></label>
        <label>Degree histogram<input type="number" min="0" step="0.01" value={weights.degreeHistogram} onChange={(event) => patchWeights({ degreeHistogram: Number(event.target.value) })} /></label>
        <label>Size<input type="number" min="0" step="0.01" value={weights.sizeSimilarity} onChange={(event) => patchWeights({ sizeSimilarity: Number(event.target.value) })} /></label>
        <label>Density<input type="number" min="0" step="0.01" value={weights.densitySimilarity} onChange={(event) => patchWeights({ densitySimilarity: Number(event.target.value) })} /></label>
      </div>
    );
  }

  if (technique === "graph_embedding") {
    return (
      <div className="configGrid">
        <label>Threshold<input type="number" min="0" max="1" step="0.01" value={thresholds.graphEmbedding} onChange={(event) => patch({ graphEmbedding: Number(event.target.value) })} /></label>
        <label>Dimensions<input type="number" min="8" step="8" value={thresholds.graphEmbeddingDimensions} onChange={(event) => patch({ graphEmbeddingDimensions: Number(event.target.value) })} /></label>
        <label>Walk length<input type="number" min="1" step="1" value={thresholds.graphEmbeddingWalkLength} onChange={(event) => patch({ graphEmbeddingWalkLength: Number(event.target.value) })} /></label>
        <label>Walks<input type="number" min="1" step="1" value={thresholds.graphEmbeddingNumWalks} onChange={(event) => patch({ graphEmbeddingNumWalks: Number(event.target.value) })} /></label>
        <label>Workers<input type="number" min="1" step="1" value={thresholds.graphEmbeddingWorkers} onChange={(event) => patch({ graphEmbeddingWorkers: Number(event.target.value) })} /></label>
        <label>Seed<input type="number" step="1" value={thresholds.graphEmbeddingSeed} onChange={(event) => patch({ graphEmbeddingSeed: Number(event.target.value) })} /></label>
      </div>
    );
  }

  if (technique === "bert_semantic") {
    return (
      <div className="configGrid">
        <label>Threshold<input type="number" min="0" max="1" step="0.01" value={thresholds.bertSemantic} onChange={(event) => patch({ bertSemantic: Number(event.target.value) })} /></label>
        <label className="wideField">Model<input value={thresholds.bertModelName} onChange={(event) => patch({ bertModelName: event.target.value })} /></label>
        <label>Batch size<input type="number" min="1" step="1" value={thresholds.bertBatchSize} onChange={(event) => patch({ bertBatchSize: Number(event.target.value) })} /></label>
        <label>Max length<input type="number" min="16" max="512" step="16" value={thresholds.bertMaxLength} onChange={(event) => patch({ bertMaxLength: Number(event.target.value) })} /></label>
      </div>
    );
  }

  if (technique === "graph_isomorphism") {
    return (
      <div className="configGrid">
        <label>Mode<select value={thresholds.isomorphismMode} onChange={(event) => patch({ isomorphismMode: event.target.value })}><option value="structure">Structure</option><option value="names">Names</option><option value="names_types">Names + types</option></select></label>
        <label className="inlineCheck">
          <input type="checkbox" checked={thresholds.matchEdgeTypes} onChange={(event) => patch({ matchEdgeTypes: event.target.checked })} />
          Match edge types
        </label>
      </div>
    );
  }

  return null;
}

function Status({ datasetId, busy }) {
  const label = busy === "parse"
    ? "Parsing models"
    : busy === "upload"
    ? "Parsing models"
    : datasetId
    ? "Models parsed"
    : "Ready";
  return <div className="status">{busy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}{label}</div>;
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
      {failed
        ? <p className="summaryHint">Some inputs failed while parsing.</p>
        : <p className="summaryHint neutral">Parsing completed without parse errors.</p>}
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

function WarningInspectorDrawer({
  model,
  warnings,
  tab,
  onTabChange,
  onClose,
  inspectLoading,
  inspectError,
  inspectModel,
}: {
  model: ParsedModelSummary;
  warnings: WarningEntry[];
  tab: "warnings" | "model";
  onTabChange: (tab: "warnings" | "model") => void;
  onClose: () => void;
  inspectLoading: boolean;
  inspectError: string;
  inspectModel: ModelInspectPayload | null;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="inspectorOverlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="inspectorDrawer" onClick={(event) => event.stopPropagation()}>
        <div className="inspectorHeader">
          <div>
            <h3>Model Details</h3>
            <p>{model.modelId}</p>
            <p>{model.path}</p>
          </div>
          <button type="button" className="closeButton" onClick={onClose} aria-label="Close model inspector">
            <X size={18} />
          </button>
        </div>
        <div className="inspectorTabs">
          <button type="button" className={tab === "warnings" ? "active" : ""} onClick={() => onTabChange("warnings")}>Warnings</button>
          <button type="button" className={tab === "model" ? "active" : ""} onClick={() => onTabChange("model")}>Parsed Model</button>
        </div>
        {tab === "warnings" ? (
          <div className="inspectorBody">
            <div className="warningTypeChips">
              {Object.entries(model.types || {}).map(([type, count]) => (
                <span key={type} className="warningTypeChip">{type} ({count})</span>
              ))}
            </div>
            <div className="warningList inspector">
              {warnings.length ? warnings.map((warning, index) => (
                <div className="warningListRow" key={`${warning.type}:${index}`}>
                  <span>{warning.type}</span>
                  <p>{warning.message}</p>
                </div>
              )) : (
                <div className="warningListRow hint">
                  <p>No detailed warning entries were emitted for this file.</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="inspectorBody">
            {inspectLoading ? (
              <div className="inspectState"><Loader2 className="spin" size={16} />Loading parsed model...</div>
            ) : inspectError ? (
              <div className="inspectState error"><AlertTriangle size={16} />{inspectError}</div>
            ) : inspectModel ? (
              <ModelGraphPreview payload={inspectModel} />
            ) : (
              <div className="inspectState">No parsed model data available.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ModelGraphPreview({ payload }: { payload: ModelInspectPayload }) {
  const [cy, setCy] = useState<any>(null);
  const [selectedElement, setSelectedElement] = useState<
    | { kind: "node"; id: string; node: ModelInspectPayload["nodes"][number] }
    | { kind: "edge"; id: string; edge: ModelInspectPayload["edges"][number] }
    | null
  >(null);

  const elements = useMemo(() => {
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

  const stylesheet = useMemo(() => [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "font-size": 10,
        "background-color": "#247f7f",
        color: "#12353a",
        "text-wrap": "wrap",
        "text-max-width": 90,
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
    const onElementTap = (event: any) => {
      const element = event.target;
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
    const onBackgroundTap = (event: any) => {
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
        layout={{ name: "cose-bilkent", fit: true, animate: false, padding: 20 }}
        stylesheet={stylesheet as any}
        wheelSensitivity={0.15}
        minZoom={0.1}
        maxZoom={2.8}
        cy={(instance) => setCy(instance)}
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

function Statistics({ stats }) {
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

function Metric({ label, value }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function TopList({ title, items }) {
  return <div className="topList"><h3>{title}</h3>{items.map((item) => <div key={item.label}><span>{item.label}</span><b>{item.count}</b></div>)}</div>;
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
      <div className="metricGrid small">
        <Metric label="Total models" value={summary.totalModels} />
        <Metric label="Removed" value={summary.removedModels} />
        <Metric label="Remaining" value={summary.remainingModels} />
        <Metric label="Removal rate" value={`${Math.round(summary.removalRate * 100)}%`} />
      </div>
      <div className="actionBar">
        <button type="button" onClick={() => exportDummyJson(result)}>Export JSON</button>
        <button type="button" onClick={() => exportDummyCsv(result)}>Export CSV</button>
      </div>
      <h3>Filter Waterfall</h3>
      <table>
        <thead><tr><th>Filter</th><th>Filtered</th><th>Remaining</th></tr></thead>
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
      <h3>Primary Removal Distribution</h3>
      <table>
        <thead><tr><th>Filter</th><th>Models</th></tr></thead>
        <tbody>
          {[...distribution.entries()].sort((a, b) => b[1] - a[1]).map(([filterId, count]) => (
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
      <h3>Model Traceability</h3>
      <div className="dummyTraceabilityTable">
        <table>
          <thead><tr><th>Model</th><th>Decision</th><th>Primary reason</th><th>All triggered filters</th><th>Details</th></tr></thead>
          <tbody>
            {result.modelOutcomes.map((outcome) => (
              <tr key={outcome.modelId}>
                <td>{outcome.modelId}</td>
                <td>{outcome.removed ? "Removed" : "Kept"}</td>
                <td>{outcome.primaryRemovalReason || "-"}</td>
                <td>{outcome.allTriggeredFilters.join(", ") || "-"}</td>
                <td>
                  <button type="button" onClick={() => onSelectModelId(outcome.modelId)}>Open</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="infoOverlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="infoModal" onClick={(event) => event.stopPropagation()}>
        <div className="inspectorHeader">
          <div>
            <h3>Model Detail</h3>
            <p>{modelId}</p>
          </div>
          <button type="button" className="closeButton" onClick={onClose} aria-label="Close model detail dialog">
            <X size={18} />
          </button>
        </div>
        <div className="inspectorBody">
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
                    <p><strong>Reason:</strong> {finding.reason}</p>
                    <p><strong>Evidence:</strong> {finding.evidence.length ? finding.evidence.join(", ") : "-"}</p>
                    <p><strong>Evidence Nodes:</strong> {finding.evidenceNodes.length ? finding.evidenceNodes.join(", ") : "-"}</p>
                    <pre>{JSON.stringify(finding.metrics || {}, null, 2)}</pre>
                  </div>
                </details>
              ))}
            </div>
          )}
        </div>
      </div>
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
  const escaped = String(value || "").replace(/\"/g, "\"\"");
  return `\"${escaped}\"`;
}

function DuplicateProgress({ progress }) {
  const completed = new Set(progress.completedTechniques || []);
  return (
    <div className="progressPanel">
      <div className="progressHeader">
        <div>
          <h3>{progress.currentTechnique ? `Running ${techniqueLabel(progress.currentTechnique)}` : progress.message}</h3>
          <p>{progress.totalModels} models, {completed.size} of {progress.totalTechniques} techniques complete, {formatDuration(progress.elapsedMs)} elapsed</p>
          {progress.message && progress.currentTechnique && <p>{progress.message}</p>}
          {progress.totalItems > 0 && (
            <p>{progress.processedItems} of {progress.totalItems} items processed in this algorithm</p>
          )}
        </div>
        <strong>{progress.progress}%</strong>
      </div>
      <div className="progressTrack">
        <div className="progressFill" style={{ width: `${progress.progress}%` }} />
      </div>
      {progress.currentTechnique && (
        <div className="subProgress">
          <span>{techniqueLabel(progress.currentTechnique)} progress</span>
          <strong>{progress.techniqueProgress || 0}%</strong>
          <div className="progressTrack">
            <div className="progressFill secondary" style={{ width: `${progress.techniqueProgress || 0}%` }} />
          </div>
        </div>
      )}
      <div className="techniqueProgressGrid">
        {(progress.selectedTechniques || []).map((technique) => (
          <div className={`techniqueProgress ${completed.has(technique) ? "done" : progress.currentTechnique === technique ? "active" : ""}`} key={technique}>
            {completed.has(technique) ? <Check size={15} /> : progress.currentTechnique === technique ? <Loader2 className="spin" size={15} /> : <span />}
            {techniqueLabel(technique)}
          </div>
        ))}
      </div>
    </div>
  );
}

function DuplicateResults({ result }) {
  if (!result) return <EmptyState text="Run duplicate detection to see technique votes and candidate pairs." />;
  return (
    <div className="results">
      <div className="metricGrid small">
        <Metric label="Duplicate pairs" value={result.duplicatePairs} />
        {"votedDuplicatePairs" in result && <Metric label="Vote-approved pairs" value={result.votedDuplicatePairs} />}
        <Metric label="Runtime" value={formatDuration(result.elapsedMs)} />
        {Object.entries(result.techniqueCounts).map(([key, value]) => <Metric key={key} label={key} value={value} />)}
      </div>
      <DuplicateModelCharts modelCounts={result.modelCounts || {}} />
      <table>
        <thead><tr><th>Left</th><th>Right</th><th>Duplicate</th><th>Votes</th><th>Techniques</th></tr></thead>
        <tbody>{result.decisions.map((row) => <tr key={`${row.leftId}-${row.rightId}`}><td>{row.leftId}</td><td>{row.rightId}</td><td>{row.isDuplicate ? "Yes" : "No"}</td><td>{row.voteCount}</td><td>{row.techniques.join(", ")}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function DuplicateModelCharts({ modelCounts }) {
  const entries = Object.entries(modelCounts);
  if (!entries.length) return null;
  return (
    <div className="duplicateCharts">
      {entries.map(([technique, counts]) => (
        <div className="duplicateChartCard" key={technique}>
          <h3>{techniqueLabel(technique)}</h3>
          <div className="piePair">
            <PieStat label="Duplicate models" value={counts.duplicateModels} total={counts.totalModels} tone="duplicate" />
            <PieStat label="Unique models" value={counts.uniqueModels} total={counts.totalModels} tone="unique" />
          </div>
          <p>{counts.pairCount} duplicate pair(s) found in {formatDuration(counts.elapsedMs)}</p>
        </div>
      ))}
    </div>
  );
}

function PieStat({ label, value, total, tone }) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="pieStat">
      <div className={`pie ${tone}`} style={{ "--percent": `${percent}%` }} aria-label={`${label}: ${value} of ${total}`} />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{percent}% of {total}</small>
      </div>
    </div>
  );
}

function EmptyState({ text }) {
  return <div className="empty"><Plus size={18} />{text}</div>;
}
