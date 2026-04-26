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
  ShieldCheck,
} from "lucide-react";
import "./styles.css";

const API_URL = import.meta.env.VITE_MCP4CM_API_URL || "http://127.0.0.1:8765";

const techniques = [
  { id: "hash_names", label: "Hash: names", detail: "Exact match on sorted node names" },
  { id: "hash_names_types", label: "Hash: names + types", detail: "Exact match on sorted name/type pairs" },
  { id: "tfidf_names", label: "TF-IDF: names", detail: "Near duplicate text similarity on names" },
  { id: "tfidf_names_types", label: "TF-IDF: names + types", detail: "Near duplicate text similarity on names and types" },
  { id: "graph_similarity", label: "Graph metrics", detail: "Jaccard, degree, size, and density similarity" },
  { id: "graph_isomorphism", label: "Isomorphism", detail: "Exact structural graph match" },
];

const filterLabels = {
  empty_model: ["Empty graph", "Remove records with no graph nodes."],
  uml_empty_class_name: ["UML empty class marker", "Regex over raw text for empty class-name placeholders."],
  uml_empty_name: ["UML empty name marker", "Regex over raw text for empty-name placeholders."],
  too_few_names: ["Too few named elements", "Minimum number of non-empty names required."],
  uml_dummy_class: ["UML dummy classes", "Ratio of UML class names such as class a or class 1."],
  uml_dummy_name: ["UML dummy names", "Ratio of short placeholder names such as att1 or a b."],
  uml_dummy_keyword: ["UML dummy keywords", "Ratio of UML placeholder keywords."],
  uml_sequential: ["UML sequential names", "Ratio of names ending in a sequence number."],
  uml_short_name: ["UML short names", "Ratio of names below the short-name length rule."],
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
    { id: "uml_empty_class_name", enabled: true, pattern: "class:\\s*empty name" },
    { id: "uml_empty_name", enabled: true, pattern: "empty name" },
    { id: "too_few_names", enabled: true, minNames: 5 },
    { id: "uml_dummy_class", enabled: true, threshold: 0.5 },
    { id: "uml_dummy_name", enabled: true, threshold: 0.3 },
    { id: "uml_dummy_keyword", enabled: true, threshold: 0.82 },
    { id: "uml_sequential", enabled: true, threshold: 0.75 },
    { id: "uml_short_name", enabled: true, threshold: 0.3 },
    { id: "uml_vocabulary", enabled: true, minUniqueWords: 3 },
    { id: "generic_sequential", enabled: true, threshold: 0.75 },
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
  const [dummyRows, setDummyRows] = useState([]);
  const [duplicateResult, setDuplicateResult] = useState(null);
  const [selected, setSelected] = useState(["hash_names", "hash_names_types", "tfidf_names"]);
  const [mandatory, setMandatory] = useState(["hash_names"]);
  const [minVotes, setMinVotes] = useState(2);
  const [thresholds, setThresholds] = useState({
    tfidfNames: 0.9,
    tfidfNamesTypes: 0.9,
    graphSimilarity: 0.85,
    isomorphismMode: "types",
    matchEdgeTypes: true,
  });
  const [regexFilter, setRegexFilter] = useState({ pattern: "", threshold: 0.5, target: "names" });
  const [dummyFilterConfigs, setDummyFilterConfigs] = useState(() => clonePreset("uml"));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const canRun = Boolean(datasetId);
  const selectedTechniques = useMemo(() => new Set(selected), [selected]);

  async function uploadDataset() {
    setError("");
    if (!files.length) {
      setError("Choose at least one JSON or JSONL file.");
      return;
    }
    setBusy("upload");
    try {
      const payloadFiles = await Promise.all(
        [...files].map(async (file) => ({ name: file.name, content: await file.text() }))
      );
      const response = await postJson("/api/datasets", { language, files: payloadFiles });
      setDatasetId(response.datasetId);
      setStats(response.statistics);
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
    try {
      const response = await postJson("/api/duplicates", {
        datasetId,
        techniques: selected,
        mandatoryTechniques: mandatory,
        minVotes,
        thresholds,
      });
      setDuplicateResult(response);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  function toggleSelection(id) {
    setSelected((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
    setMandatory((current) => current.filter((item) => item !== id || selectedTechniques.has(id)));
  }

  function toggleMandatory(id) {
    if (!selectedTechniques.has(id)) return;
    setMandatory((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function changeLanguage(nextLanguage) {
    setLanguage(nextLanguage);
    setDummyFilterConfigs(clonePreset(nextLanguage));
    setDummyRows([]);
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
          <div className="brandMark"><ShieldCheck size={22} /></div>
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
              <input type="file" multiple onChange={(event) => setFiles(event.target.files || [])} />
            </label>
            <button className="primary" onClick={uploadDataset} disabled={busy === "upload"}>
              {busy === "upload" ? <Loader2 className="spin" size={18} /> : <FileUp size={18} />}
              Upload and Analyze
            </button>
          </div>
        </section>

        <section className="panel" id="stats">
          <SectionTitle icon={<BarChart3 size={20} />} title="Descriptive Statistics" />
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
              </div>
            ))}
          </div>

          <div className="thresholdGrid">
            <label>Min votes<input type="number" min="1" value={minVotes} onChange={(e) => setMinVotes(Number(e.target.value))} /></label>
            <label>TF-IDF names<input type="number" min="0" max="1" step="0.01" value={thresholds.tfidfNames} onChange={(e) => setThresholds({ ...thresholds, tfidfNames: Number(e.target.value) })} /></label>
            <label>TF-IDF names + types<input type="number" min="0" max="1" step="0.01" value={thresholds.tfidfNamesTypes} onChange={(e) => setThresholds({ ...thresholds, tfidfNamesTypes: Number(e.target.value) })} /></label>
            <label>Graph threshold<input type="number" min="0" max="1" step="0.01" value={thresholds.graphSimilarity} onChange={(e) => setThresholds({ ...thresholds, graphSimilarity: Number(e.target.value) })} /></label>
            <label>Isomorphism mode<select value={thresholds.isomorphismMode} onChange={(e) => setThresholds({ ...thresholds, isomorphismMode: e.target.value })}><option value="structure">Structure</option><option value="types">Types</option><option value="names_types">Names + types</option></select></label>
          </div>

          <div className="actionBar">
            <button className="primary" onClick={runDuplicateDetection} disabled={!canRun || busy === "duplicates"}>
              {busy === "duplicates" ? <Loader2 className="spin" size={18} /> : <GitCompare size={18} />}
              Run Duplicate Detection
            </button>
          </div>
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

function Status({ datasetId, busy }) {
  return <div className="status">{busy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}{datasetId ? "Dataset loaded" : "Ready"}</div>;
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

function DuplicateResults({ result }) {
  if (!result) return <EmptyState text="Run duplicate detection to see technique votes and candidate pairs." />;
  return (
    <div className="results">
      <div className="metricGrid small">
        <Metric label="Duplicate pairs" value={result.duplicatePairs} />
        {Object.entries(result.techniqueCounts).map(([key, value]) => <Metric key={key} label={key} value={value} />)}
      </div>
      <table>
        <thead><tr><th>Left</th><th>Right</th><th>Duplicate</th><th>Votes</th><th>Techniques</th></tr></thead>
        <tbody>{result.decisions.map((row) => <tr key={`${row.leftId}-${row.rightId}`}><td>{row.leftId}</td><td>{row.rightId}</td><td>{row.isDuplicate ? "Yes" : "No"}</td><td>{row.voteCount}</td><td>{row.techniques.join(", ")}</td></tr>)}</tbody>
      </table>
    </div>
  );
}

function EmptyState({ text }) {
  return <div className="empty"><Plus size={18} />{text}</div>;
}

function round(value) {
  return Number.isInteger(value) ? value : Number(value || 0).toFixed(1);
}

async function postJson(path, payload) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

createRoot(document.getElementById("root")).render(<App />);
