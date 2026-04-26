import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BarChart3,
  Check,
  Database,
  FileUp,
  Filter,
  GitCompare,
  Loader2,
  Plus,
  Regex,
  SlidersHorizontal,
} from "lucide-react";
import "./styles.css";

const API_URL = import.meta.env.VITE_MCP4CM_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:8765" : "");

const techniques = [
  { id: "hash", label: "Hash", detail: "Exact match on sorted node names" },
  { id: "tfidf", label: "TF-IDF", detail: "Near duplicate text similarity on model tokens" },
  { id: "graph_similarity", label: "Graph metrics", detail: "Jaccard, degree, size, and density similarity" },
  { id: "graph_embedding", label: "Graph embeddings", detail: "Node2Vec graph embedding cosine similarity" },
  { id: "bert_semantic", label: "BERT semantic", detail: "bert-base-uncased semantic similarity on model names and types" },
  { id: "graph_isomorphism", label: "Isomorphism", detail: "Exact structural graph match" },
];

const filterLabels = {
  empty_model: ["Empty graph", "Remove records with no graph nodes."],
  uml_empty_class_name: ["UML empty class name", "Find UML class elements whose extracted name is empty name."],
  uml_empty_name: ["UML empty name", "Find any extracted UML name equal to empty name."],
  too_few_names: ["Too few named elements", "Minimum number of non-empty names required."],
  uml_median_name_length: ["UML short median name", "Median extracted name length must meet the configured minimum."],
  uml_short_name_or_control_flow: ["UML short/control-flow names", "Notebook rule for many short names or short names with control flow."],
  uml_dummy_class: ["UML dummy classes", "Ratio of UML class names such as class a or class 1."],
  uml_generic_class_name: ["UML my class pattern", "Find repeated class names such as my class or my class1."],
  uml_dummy_name: ["UML att dummy names", "Find names such as att, att1, att A, or att 1."],
  uml_two_character_dummy_name: ["UML two-character names", "Ratio of names such as a1 or a b."],
  uml_dummy_keyword: ["UML dummy keywords", "Ratio of UML placeholder keywords."],
  uml_sequential: ["UML sequential names", "Ratio of names ending in a sequence number."],
  uml_vocabulary: ["UML low vocabulary", "Minimum number of unique words across names."],
  generic_sequential: ["Generic sequential names", "Ratio of generic names such as class1 or node2."],
  ecore_type_name: ["Ecore type names", "Ratio of names that exactly match Ecore element types."],
  ecore_numbered: ["Ecore numbered placeholders", "Ratio of names such as entity 1 or class 2."],
  ecore_dummy_keyword: ["Ecore dummy keywords", "Ratio of placeholder/demo terms."],
  ecore_vocabulary: ["Ecore low vocabulary", "Minimum number of unique words across names."],
  archimate_new_model: ["ArchiMate new model", "Detect default model names such as (new model)."],
  archimate_type_name: ["ArchiMate type names", "Ratio of names equal to their ArchiMate element type."],
  archimate_numbered: ["ArchiMate numbered placeholders", "Ratio of names such as entity 1 or aggregate 2."],
  archimate_dummy_keyword: ["ArchiMate dummy keywords", "Ratio of placeholder/demo terms."],
  archimate_crud_code: ["ArchiMate CRUD/code names", "Ratio of code-like names such as read(id) or return true."],
  archimate_vocabulary: ["ArchiMate low vocabulary", "Minimum number of unique words across names."],
  short_names: ["Short names", "Ratio of names at or below the configured length."],
};

const dummyFilterPresets = {
  uml: [
    { id: "empty_model", enabled: true },
    { id: "uml_empty_class_name", enabled: true },
    { id: "uml_empty_name", enabled: true },
    { id: "too_few_names", enabled: true, minNames: 5 },
    { id: "uml_median_name_length", enabled: true, minMedianLength: 4 },
    { id: "uml_short_name_or_control_flow", enabled: true, maxLength: 2, threshold: 0.3, lowThreshold: 0.25, controlFlowThreshold: 0.4 },
    { id: "uml_dummy_class", enabled: true, threshold: 0.13 },
    { id: "uml_generic_class_name", enabled: true, thresholdCount: 2 },
    { id: "uml_dummy_name", enabled: true, threshold: 0 },
    { id: "uml_two_character_dummy_name", enabled: true, threshold: 0.3 },
    { id: "uml_dummy_keyword", enabled: true, threshold: 0.82 },
    { id: "uml_sequential", enabled: true, threshold: 0.75 },
    { id: "uml_vocabulary", enabled: true, minUniqueWords: 3 },
  ],
  ecore: [
    { id: "empty_model", enabled: true },
    { id: "too_few_names", enabled: true, minNames: 5 },
    { id: "ecore_type_name", enabled: true, threshold: 0.6 },
    { id: "ecore_numbered", enabled: true, threshold: 0.3 },
    { id: "ecore_dummy_keyword", enabled: true, threshold: 0.5 },
    { id: "ecore_vocabulary", enabled: true, minUniqueWords: 3 },
    { id: "short_names", enabled: true, maxLength: 2, threshold: 0.4 },
  ],
  archimate: [
    { id: "empty_model", enabled: true },
    { id: "too_few_names", enabled: true, minNames: 5 },
    { id: "archimate_new_model", enabled: true },
    { id: "archimate_type_name", enabled: true, threshold: 0.6 },
    { id: "archimate_numbered", enabled: true, threshold: 0.25 },
    { id: "archimate_dummy_keyword", enabled: true, threshold: 0.7 },
    { id: "archimate_crud_code", enabled: true, threshold: 0.25 },
    { id: "archimate_vocabulary", enabled: true, minUniqueWords: 3 },
    { id: "short_names", enabled: true, maxLength: 2, threshold: 0.35 },
  ],
};

function clonePreset(language) {
  return dummyFilterPresets[language].map((filter) => ({ ...filter }));
}

function App() {
  const [language, setLanguage] = useState("uml");
  const [files, setFiles] = useState([]);
  const [datasetId, setDatasetId] = useState("");
  const [stats, setStats] = useState(null);
  const [uploadSummary, setUploadSummary] = useState(null);
  const [preprocessId, setPreprocessId] = useState("");
  const [modelLimit, setModelLimit] = useState(null);
  const [dummyRows, setDummyRows] = useState([]);
  const [duplicateResult, setDuplicateResult] = useState(null);
  const [duplicateProgress, setDuplicateProgress] = useState(null);
  const [selected, setSelected] = useState(["hash", "tfidf"]);
  const [mandatory, setMandatory] = useState(["hash"]);
  const [minVotes, setMinVotes] = useState(2);
  const [thresholds, setThresholds] = useState({
    hashIncludeTypes: false,
    tfidfIncludeTypes: false,
    tfidfNames: 0.9,
    tfidfNamesTypes: 0.9,
    tfidfMaxFeatures: 50000,
    graphSimilarity: 0.85,
    graphWeights: {
      nodeNameJaccard: 0.25,
      nodeTypeJaccard: 0.2,
      edgeTypeJaccard: 0.15,
      degreeHistogram: 0.15,
      sizeSimilarity: 0.15,
      densitySimilarity: 0.1,
    },
    graphEmbedding: 0.9,
    graphEmbeddingDimensions: 64,
    graphEmbeddingWalkLength: 10,
    graphEmbeddingNumWalks: 20,
    graphEmbeddingWorkers: 1,
    graphEmbeddingSeed: 42,
    bertSemantic: 0.9,
    bertModelName: "bert-base-uncased",
    bertBatchSize: 8,
    bertMaxLength: 256,
    isomorphismMode: "names",
    matchEdgeTypes: true,
  });
  const [regexFilter, setRegexFilter] = useState({ pattern: "", threshold: 0.5, target: "names" });
  const [dummyFilterConfigs, setDummyFilterConfigs] = useState(() => clonePreset("uml"));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const canRun = Boolean(datasetId);
  const selectedTechniques = useMemo(() => new Set(selected), [selected]);

  async function preprocessDataset(nextFiles = files) {
    setError("");
    if (!nextFiles.length) {
      setError("Choose at least one JSON or JSONL file.");
      return;
    }
    setBusy("preprocess");
    try {
      const formData = new FormData();
      formData.append("language", language);
      [...nextFiles].forEach((file) => formData.append("files", file, file.name));
      const response = await postForm("/api/datasets/preprocess", formData);
      setPreprocessId(response.preprocessId);
      setUploadSummary(response.uploadSummary || null);
      if (response.uploadSummary?.totalRecords) {
        setModelLimit(response.uploadSummary.totalRecords);
      }
      setDatasetId("");
      setStats(null);
      setDummyRows([]);
      setDuplicateResult(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function uploadDataset() {
    setError("");
    if (!preprocessId) {
      setError("Preprocess the upload before processing the dataset.");
      return;
    }
    setBusy("upload");
    try {
      const formData = new FormData();
      formData.append("language", language);
      formData.append("preprocessId", preprocessId);
      formData.append("modelLimit", String(modelLimit || uploadSummary?.totalRecords || ""));
      const response = await postForm("/api/datasets", formData);
      setDatasetId(response.datasetId);
      setStats(response.statistics);
      setUploadSummary(response.uploadSummary || null);
      if (response.uploadSummary?.totalRecords) {
        setModelLimit(response.uploadSummary.modelLimit || response.uploadSummary.totalRecords);
      }
      setDummyRows([]);
      setDuplicateResult(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function runDummyFilters() {
    setError("");
    setBusy("dummy");
    try {
      const customRegex = regexFilter.pattern.trim() ? regexFilter : null;
      const response = await postJson("/api/dummy", { datasetId, filterConfigs: dummyFilterConfigs, customRegex });
      setDummyRows(response.rows);
    } catch (err) {
      setError(err.message);
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
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  function toggleSelection(id) {
    setSelected((current) => {
      const isSelected = current.includes(id);
      if (isSelected) {
        setMandatory((mandatoryCurrent) => mandatoryCurrent.filter((item) => item !== id));
        return current.filter((item) => item !== id);
      }
      return [...current, id];
    });
  }

  function toggleMandatory(id) {
    if (!selectedTechniques.has(id)) return;
    setMandatory((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function changeLanguage(nextLanguage) {
    setLanguage(nextLanguage);
    setDummyFilterConfigs(clonePreset(nextLanguage));
    setDummyRows([]);
    setDatasetId("");
    setStats(null);
    setUploadSummary(null);
    setPreprocessId("");
    setModelLimit(null);
  }

  function updateDummyFilter(index, patch) {
    setDummyFilterConfigs((current) => current.map((filter, i) => (i === index ? { ...filter, ...patch } : filter)));
  }

  function resetDummyFilters() {
    setDummyFilterConfigs(clonePreset(language));
    setDummyRows([]);
  }

  return (
    <main>
      <aside className="sidebar">
        <div className="brand">
          <img className="brandMark" src="/mcp4cm-icon.svg" alt="" />
          <div>
            <strong>MCP4CM</strong>
            <span>Model Cleansing Workbench</span>
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
              <select value={language} onChange={(event) => changeLanguage(event.target.value)}>
                <option value="uml">UML</option>
                <option value="ecore">Ecore</option>
                <option value="archimate">ArchiMate</option>
              </select>
            </label>
            <label className="fileDrop">
              <FileUp size={24} />
              <span>{files.length ? `${files.length} file(s) selected` : "Choose JSON / JSONL files"}</span>
              <input
                type="file"
                multiple
                onChange={(event) => {
                  const nextFiles = Array.from(event.target.files || []);
                  setFiles(nextFiles);
                  setUploadSummary(null);
                  setPreprocessId("");
                  setModelLimit(null);
                  setDatasetId("");
                  setStats(null);
                  if (nextFiles.length) preprocessDataset(nextFiles);
                }}
              />
            </label>
            {uploadSummary?.totalRecords > 0 && (
              <ModelLimitSlider
                  total={uploadSummary.totalRecords}
                  value={modelLimit || uploadSummary.totalRecords}
                  onChange={setModelLimit}
                />
            )}
            <button className="primary" onClick={uploadDataset} disabled={!preprocessId || busy === "upload" || busy === "preprocess"}>
              {busy === "upload" || busy === "preprocess" ? <Loader2 className="spin" size={18} /> : <FileUp size={18} />}
              {busy === "preprocess" ? "Preprocessing" : "Process Selected Models"}
            </button>
          </div>
        </section>

        <section className="panel" id="stats">
          <SectionTitle icon={<BarChart3 size={20} />} title="Descriptive Statistics" />
          {uploadSummary && <UploadSummary summary={uploadSummary} />}
          {stats ? <Statistics stats={stats} /> : <EmptyState text="Upload a dataset to see descriptive statistics." />}
        </section>

        <section className="panel" id="dummy">
          <SectionTitle icon={<Filter size={20} />} title="Dummy Model Cleansing" />
          <div className="subsectionHeader">
            <div>
              <h3>Built-in Filters</h3>
              <p>Enable filters and tune thresholds before running the cleansing pass.</p>
            </div>
            <button type="button" onClick={resetDummyFilters}>Reset defaults</button>
          </div>
          <BuiltInFilterEditor filters={dummyFilterConfigs} onChange={updateDummyFilter} />

          <div className="subsectionHeader customHeader">
            <div>
              <h3>Additional Regex Filter</h3>
              <p>Add one temporary regex filter for this run.</p>
            </div>
          </div>
          <div className="controlsRow dummyControls">
            <label>
              Regex target
              <select value={regexFilter.target} onChange={(event) => setRegexFilter({ ...regexFilter, target: event.target.value })}>
                <option value="names">Names</option>
                <option value="names_types">Names + types</option>
              </select>
            </label>
            <label className="grow">
              Custom regex
              <input
                placeholder="e.g. ^(test|dummy|sample)"
                value={regexFilter.pattern}
                onChange={(event) => setRegexFilter({ ...regexFilter, pattern: event.target.value })}
              />
            </label>
            <label>
              Threshold
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={regexFilter.threshold}
                onChange={(event) => setRegexFilter({ ...regexFilter, threshold: Number(event.target.value) })}
              />
            </label>
          </div>
          <div className="actionBar">
            <button onClick={runDummyFilters} disabled={!canRun || busy === "dummy"}>
              {busy === "dummy" ? <Loader2 className="spin" size={18} /> : <Regex size={18} />}
              Run Filters
            </button>
          </div>
          <FilterTable rows={dummyRows} />
        </section>

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
    </main>
  );
}

function SectionTitle({ icon, title }) {
  return <h2>{icon}{title}</h2>;
}

function BuiltInFilterEditor({ filters, onChange }) {
  return (
    <div className="filterEditorGrid">
      {filters.map((filter, index) => {
        const [title, detail] = filterLabels[filter.id] || [filter.id, ""];
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
              {"thresholdCount" in filter && (
                <label>
                  Count threshold
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={filter.thresholdCount}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { thresholdCount: Number(event.target.value) })}
                  />
                </label>
              )}
              {"maxLength" in filter && (
                <label>
                  Max length
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={filter.maxLength}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { maxLength: Number(event.target.value) })}
                  />
                </label>
              )}
              {"lowThreshold" in filter && (
                <label>
                  Low threshold
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={filter.lowThreshold}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { lowThreshold: Number(event.target.value) })}
                  />
                </label>
              )}
              {"controlFlowThreshold" in filter && (
                <label>
                  Control flow threshold
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    value={filter.controlFlowThreshold}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { controlFlowThreshold: Number(event.target.value) })}
                  />
                </label>
              )}
              {"pattern" in filter && (
                <label className="wideField">
                  Pattern
                  <input
                    value={filter.pattern}
                    disabled={!filter.enabled}
                    onChange={(event) => onChange(index, { pattern: event.target.value })}
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
  const label = busy === "upload" ? "Uploading and analyzing" : datasetId ? "Dataset loaded" : "Ready";
  return <div className="status">{busy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}{label}</div>;
}

function UploadSummary({ summary }) {
  return (
    <div className="uploadSummary">
      <span>{summary.usedRecords || summary.records} records used</span>
      <span>{summary.totalRecords || summary.records} records parsed</span>
      <span>{summary.payloads} payloads read</span>
      <span>{summary.skipped} skipped</span>
      <span>{summary.errors} errors</span>
    </div>
  );
}

function ModelLimitSlider({ total, value, onChange }) {
  const min = Math.min(10, total);
  return (
    <label className="modelLimit">
      Models to consider
      <div>
        <input
          type="range"
          min={min}
          max={total}
          step="1"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        <input
          type="number"
          min={min}
          max={total}
          step="1"
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
      <span>{min} to {total} models. Processing will use the selected count.</span>
    </label>
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
        <TopList title="Top Words" items={stats.topWords} />
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

function FilterTable({ rows }) {
  if (!rows.length) return <EmptyState text="Run dummy filters to see filter-by-filter counts." />;
  return <table><thead><tr><th>Filter</th><th>Filtered</th><th>Remaining</th><th>Example evidence</th></tr></thead><tbody>{rows.map((row) => <tr key={row.filterName}><td>{row.filterName}</td><td>{row.filteredCount}</td><td>{row.remainingCount}</td><td>{row.examples?.[0]?.evidence?.slice(0, 3).join(", ") || ""}</td></tr>)}</tbody></table>;
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

function techniqueLabel(id) {
  const labels = {
    hash_names: "Hash: names",
    hash_names_types: "Hash: names + types",
    tfidf_names: "TF-IDF: names",
    tfidf_names_types: "TF-IDF: names + types",
  };
  return techniques.find((technique) => technique.id === id)?.label || labels[id] || id;
}

function backendTechniquesFor(id, thresholds) {
  if (id === "hash") return [thresholds.hashIncludeTypes ? "hash_names_types" : "hash_names"];
  if (id === "tfidf") return [thresholds.tfidfIncludeTypes ? "tfidf_names_types" : "tfidf_names"];
  return [id];
}

function EmptyState({ text }) {
  return <div className="empty"><Plus size={18} />{text}</div>;
}

function round(value) {
  return Number.isInteger(value) ? value : Number(value || 0).toFixed(1);
}

function formatDuration(ms = 0) {
  if (!ms) return "0 ms";
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

async function postJson(path, payload) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await readJsonResponse(response);
  return data;
}

async function postForm(path, formData) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    body: formData,
  });
  const data = await readJsonResponse(response);
  return data;
}

async function getJson(path) {
  const response = await fetch(`${API_URL}${path}`);
  return readJsonResponse(response);
}

async function pollDuplicateJob(jobId) {
  for (;;) {
    await delay(700);
    const job = await getJson(`/api/duplicates/jobs/${jobId}`);
    if (job.status === "complete") return job;
    if (job.status === "error") throw new Error(job.error || job.message || "Duplicate detection failed");
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function readJsonResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  const body = await response.text();
  let data = {};
  if (body && contentType.includes("application/json")) {
    data = JSON.parse(body);
  }
  if (!response.ok) {
    throw new Error(data.error || body || `Request failed with HTTP ${response.status}`);
  }
  if (!body) {
    throw new Error("The backend returned an empty response. Make sure Flask is running on 127.0.0.1:8765.");
  }
  if (!contentType.includes("application/json")) {
    throw new Error("The backend returned a non-JSON response. Make sure the Flask API is running and reachable.");
  }
  return data;
}

createRoot(document.getElementById("root")).render(<App />);
