import { useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, Check, FileUp, Filter, GitCompare, Loader2, Network } from "lucide-react";
import { Toaster, toast } from "sonner";
import {
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
} from "./components/ui/sidebar";
import { clonePreset, defaultFormatForLanguage, defaultThresholds, formatOptionsByLanguage } from "./config";
import {
  delay,
  errorMessage,
  getDatasetAfterDummyStatistics,
  getDatasetStatistics,
  pollDummyJob,
  pollDuplicateJob,
  pollUploadParseJob,
  postForm,
  postJson,
} from "./api";
import { backendTechniquesFor } from "./utils";
import type {
  BusyState,
  DummyProgressState,
  DuplicateProgressState,
  DuplicateResult,
  DummyResponse,
  FilterConfig,
  Language,
  ParsedModelSummary,
  RepresentationProfile,
  StatisticsPayload,
  Thresholds,
  UploadFormat,
  UploadParseJob,
  UploadSummary,
} from "./types";
import { UploadPanel } from "./features/upload/UploadPanel";
import { StatisticsPanel } from "./features/upload/StatisticsPanel";
import { VisualizationPanel } from "./features/upload/VisualizationPanel";
import { DummyPanel } from "./features/dummy/DummyPanel";
import { DuplicatePanel } from "./features/duplicates/DuplicatePanel";
import {
  ModelGraphDrawer,
  PairCompareModal,
  useModelInspect,
  WarningInspectorDrawer,
} from "./features/inspector/Inspector";

type UploadSessionPayload = {
  language: Language;
  format: UploadFormat;
} & Partial<RepresentationProfile>;

interface UploadSessionResponse {
  uploadId: string;
}

type StartedDuplicateJob = DuplicateProgressState & { jobId: string };
const LAST_DATASET_ID_KEY = "mcp4cm:lastDatasetId";

export default function App() {
  const uploadChunkSize = 200;
  const [language, setLanguage] = useState<Language>("uml");
  const [format, setFormat] = useState<UploadFormat>(defaultFormatForLanguage("uml"));
  const [files, setFiles] = useState<File[]>([]);
  const [datasetId, setDatasetId] = useState("");
  const [stats, setStats] = useState<StatisticsPayload | null>(null);
  const [afterDummyStats, setAfterDummyStats] = useState<StatisticsPayload | null>(null);
  const [uploadSummary, setUploadSummary] = useState<UploadSummary | null>(null);
  const [uploadParseJob, setUploadParseJob] = useState<UploadParseJob | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState(0);
  const [dummyResponse, setDummyResponse] = useState<DummyResponse | null>(null);
  const [dummyProgress, setDummyProgress] = useState<DummyProgressState | null>(null);
  const [selectedOutcomeModelId, setSelectedOutcomeModelId] = useState<string | null>(null);
  const [duplicateResult, setDuplicateResult] = useState<DuplicateResult | null>(null);
  const [duplicateProgress, setDuplicateProgress] = useState<DuplicateProgressState | null>(null);
  const [pairInspectModelId, setPairInspectModelId] = useState<string | null>(null);
  const [pairInspectBoth, setPairInspectBoth] = useState<{ leftId: string; rightId: string } | null>(null);
  const [selected, setSelected] = useState<string[]>(["hash", "tfidf"]);
  const [mandatory, setMandatory] = useState<string[]>(["hash"]);
  const [minVotes, setMinVotes] = useState(2);
  const [thresholds, setThresholds] = useState<Thresholds>(defaultThresholds);
  const [representation, setRepresentation] = useState<RepresentationProfile>({
    includeAttributes: true,
    includeOperations: true,
    includeParameters: true,
    includeModelRootNode: true,
  });
  const [dummyFilterConfigs, setDummyFilterConfigs] = useState(() => clonePreset("uml"));
  const [busy, setBusy] = useState<BusyState>("");
  const [error, setError] = useState("");
  const [selectedModel, setSelectedModel] = useState<ParsedModelSummary | null>(null);
  const [inspectorTab, setInspectorTab] = useState<"warnings" | "model">("warnings");
  const afterDummyStatsRequestRef = useRef(0);

  const selectedInspectModelId = selectedModel?.modelId || null;
  const selectedModelInspect = useModelInspect(datasetId, selectedInspectModelId);
  const pairModelInspect = useModelInspect(datasetId, pairInspectModelId);
  const leftPairModelInspect = useModelInspect(datasetId, pairInspectBoth?.leftId || null);
  const rightPairModelInspect = useModelInspect(datasetId, pairInspectBoth?.rightId || null);

  const canRun = Boolean(datasetId);
  const selectedTechniques = useMemo(() => new Set(selected), [selected]);
  const formatOptions = formatOptionsByLanguage[language];
  const selectedFormat = formatOptions.find((option) => option.value === format) || formatOptions[0];
  const directoryMode = selectedFormat.directoryPreferred;
  const representationEnabled = language === "uml" && format === "xmi";
  const warningsList = uploadSummary?.warningsList || [];
  const statsLoading =
    !stats &&
    (busy === "parse" || uploadParseJob?.status === "queued" || uploadParseJob?.status === "running");
  const [activeSection, setActiveSection] = useState("upload");
  const fileDropText = directoryMode
    ? files.length
      ? `${files.length} file(s) selected from directory`
      : "Choose model directory"
    : files.length
      ? `${files.length} file(s) selected`
      : "Choose JSON files";

  useEffect(() => {
    if (!error) return;
    toast.error(error);
  }, [error]);

  useEffect(() => {
    const savedDatasetId = window.localStorage.getItem(LAST_DATASET_ID_KEY);
    if (savedDatasetId) setDatasetId(savedDatasetId);
  }, []);

  useEffect(() => {
    if (datasetId) {
      window.localStorage.setItem(LAST_DATASET_ID_KEY, datasetId);
    } else {
      window.localStorage.removeItem(LAST_DATASET_ID_KEY);
    }
  }, [datasetId]);

  useEffect(() => {
    if (!datasetId || stats || busy === "parse" || uploadParseJob?.status === "queued" || uploadParseJob?.status === "running") {
      return;
    }
    let cancelled = false;
    getDatasetStatistics(datasetId)
      .then((payload) => {
        if (!cancelled) setStats(payload);
      })
      .catch(() => {
        if (!cancelled) setDatasetId("");
      });
    return () => {
      cancelled = true;
    };
  }, [busy, datasetId, stats, uploadParseJob?.status]);

  useEffect(() => {
    const readHash = () => setActiveSection((window.location.hash || "#upload").replace(/^#/, ""));
    readHash();
    window.addEventListener("hashchange", readHash);
    return () => window.removeEventListener("hashchange", readHash);
  }, []);

  function uploadSessionPayload(): UploadSessionPayload {
    const payload: UploadSessionPayload = { language, format };
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
    setDummyProgress(null);
    afterDummyStatsRequestRef.current += 1;
    setAfterDummyStats(null);
    setSelectedOutcomeModelId(null);
    setDuplicateResult(null);
    setDuplicateProgress(null);
    setPairInspectModelId(null);
    setPairInspectBoth(null);
    closeModelInspector();

    try {
      const session = await postJson<UploadSessionResponse>("/api/uploads/start", uploadSessionPayload());
      const uploadId = String(session.uploadId);
      const total = nextFiles.length;

      for (let start = 0; start < total; start += uploadChunkSize) {
        const chunk = nextFiles.slice(start, start + uploadChunkSize);
        const formData = new FormData();
        chunk.forEach((file) => formData.append("files", file, file.webkitRelativePath || file.name));
        await postForm(`/api/uploads/${uploadId}/chunks`, formData);
        setUploadedFiles(Math.min(start + chunk.length, total));
      }

      const startedJob = await postJson<UploadParseJob>(`/api/uploads/${uploadId}/parse`, {});
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
    } catch (err: unknown) {
      setError(errorMessage(err, "Parsing failed."));
    } finally {
      setBusy("");
    }
  }

  async function runDummyFilters() {
    setError("");
    setBusy("dummy");
    setDummyResponse(null);
    setDummyProgress(null);
    setAfterDummyStats(null);
    try {
      const startedJob = await postJson<DummyProgressState>("/api/dummy/jobs", { datasetId, filterConfigs: dummyFilterConfigs });
      setDummyProgress(startedJob);
      const finishedJob = await pollDummyJob(startedJob.jobId, setDummyProgress);
      const response = finishedJob.result;
      if (!response) {
        throw new Error("Dummy cleansing finished without a result.");
      }
      setDummyResponse(response);
      setAfterDummyStats(response.statistics || null);
      setSelectedOutcomeModelId(null);
      if (!response.statistics && response.statisticsJobId) {
        void pollAfterDummyStatistics(datasetId, response.statisticsJobId);
      }
    } catch (err: unknown) {
      setError(errorMessage(err, "Dummy filter execution failed."));
    } finally {
      setBusy("");
    }
  }

  async function pollAfterDummyStatistics(currentDatasetId: string, jobId: string) {
    const requestId = afterDummyStatsRequestRef.current + 1;
    afterDummyStatsRequestRef.current = requestId;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await delay(1000);
      if (afterDummyStatsRequestRef.current !== requestId) return;
      try {
        const payload = await getDatasetAfterDummyStatistics(currentDatasetId);
        if ("visualizations" in payload) {
          if (afterDummyStatsRequestRef.current === requestId) setAfterDummyStats(payload);
          return;
        }
        if (payload.status === "error") {
          throw new Error(payload.error || "After-cleansing visualization statistics failed.");
        }
        if (payload.jobId && payload.jobId !== jobId) return;
      } catch (err: unknown) {
        if (afterDummyStatsRequestRef.current === requestId) {
          toast.error(errorMessage(err, "After-cleansing visualizations failed."));
        }
        return;
      }
    }
  }

  async function runDuplicateDetection() {
    setError("");
    setBusy("duplicates");
    setDuplicateResult(null);
    setDuplicateProgress(null);
    setPairInspectModelId(null);
    setPairInspectBoth(null);

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
      const thresholdPayload = {
        ...thresholds,
        ngramRange: [thresholds.ngramRangeMin, thresholds.ngramRangeMax],
      };
      const payload = {
        datasetId,
        techniques: selectedBackendTechniques,
        selectedTechniques: selectedBackendTechniques,
        mandatoryTechniques: activeMandatory,
        minVotes,
        tfidfTokenMode: thresholds.tfidfTokenMode,
        tfidfSimilarityThreshold: thresholds.tfidfSimilarityThreshold,
        thresholds: thresholdPayload,
      };

      const job = await postJson<StartedDuplicateJob>("/api/duplicates/jobs", payload);
      setDuplicateProgress(job);
      const result = await pollDuplicateJob(job.jobId, (nextJob) => {
        setDuplicateProgress(nextJob);
      });
      setDuplicateProgress(result);
      if (!result.result) {
        throw new Error("Duplicate detection completed without a result payload.");
      }
      setDuplicateResult(result.result);
    } catch (err: unknown) {
      setError(errorMessage(err, "Duplicate detection failed."));
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
  }

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
    setDummyProgress(null);
    afterDummyStatsRequestRef.current += 1;
    setAfterDummyStats(null);
    setSelectedOutcomeModelId(null);
    setDatasetId("");
    setStats(null);
    setUploadSummary(null);
    setUploadParseJob(null);
    setUploadedFiles(0);
    closeModelInspector();
    setPairInspectModelId(null);
    setPairInspectBoth(null);
    if (nextLanguage !== "uml") {
      setRepresentation({
        includeAttributes: true,
        includeOperations: true,
        includeParameters: true,
        includeModelRootNode: true,
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
    setDummyProgress(null);
    afterDummyStatsRequestRef.current += 1;
    setAfterDummyStats(null);
    setSelectedOutcomeModelId(null);
    closeModelInspector();
    setPairInspectModelId(null);
    setPairInspectBoth(null);
    if (!(language === "uml" && nextFormat === "xmi")) {
      setRepresentation({
        includeAttributes: true,
        includeOperations: true,
        includeParameters: true,
        includeModelRootNode: true,
      });
    }
  }

  function updateDummyFilter(index: number, patch: Partial<FilterConfig>) {
    setDummyFilterConfigs((current) =>
      current.map((filter, i) => (i === index ? ({ ...filter, ...patch } as FilterConfig) : filter)),
    );
    setDummyResponse(null);
    setDummyProgress(null);
    afterDummyStatsRequestRef.current += 1;
    setAfterDummyStats(null);
    setSelectedOutcomeModelId(null);
  }

  function resetDummyFilters() {
    setDummyFilterConfigs(clonePreset(language));
    setDummyResponse(null);
    setDummyProgress(null);
    afterDummyStatsRequestRef.current += 1;
    setAfterDummyStats(null);
    setSelectedOutcomeModelId(null);
  }

  return (
    <SidebarProvider className="appShell">
      <Toaster richColors position="top-right" />
      <AppSidebar activeSection={activeSection} />
      <SidebarInset>
        <section className="workspaceShell">
          <section className="workspace">
            <header className="topbar">
              <div>
                <h1>MCP4CM</h1>
                <p>Model Cleansing Pipeline for Conceptual ModelSets</p>
              </div>
              <div className="topbarState">
                <Status datasetId={datasetId} busy={busy} />
              </div>
            </header>

            {error && <div className="error">{error}</div>}

            <UploadPanel
              language={language}
              format={format}
              formatOptions={formatOptions}
              files={files}
              directoryMode={directoryMode}
              selectedFormat={selectedFormat}
              representationEnabled={representationEnabled}
              representation={representation}
              busy={busy}
              datasetId={datasetId}
              uploadParseJob={uploadParseJob}
              uploadedFiles={uploadedFiles}
              fileDropText={fileDropText}
              onLanguageChange={changeLanguage}
              onFormatChange={changeFormat}
              onFilesChange={(nextFiles) => {
                setFiles(nextFiles);
                setUploadParseJob(null);
                setUploadedFiles(0);
              }}
              onRepresentationChange={(patch) =>
                setRepresentation((current) => ({
                  ...current,
                  ...patch,
                }))
              }
              onParse={() => parseDataset()}
            />

            <StatisticsPanel
              datasetId={datasetId}
              uploadSummary={uploadSummary}
              warningsList={warningsList}
              stats={stats}
              statsLoading={statsLoading}
              uploadParseJob={uploadParseJob}
              onInspect={openModelInspector}
            />

            <VisualizationPanel
              beforeData={stats?.visualizations || null}
              afterData={afterDummyStats?.visualizations || null}
              beforeModelCount={stats?.summary.models || null}
              afterModelCount={afterDummyStats?.summary.models || null}
            />

            <DummyPanel
              filters={dummyFilterConfigs}
              onUpdateFilter={updateDummyFilter}
              onResetFilters={resetDummyFilters}
              onRun={runDummyFilters}
              canRun={canRun}
              busy={busy}
              progress={dummyProgress}
              result={dummyResponse}
              selectedModelId={selectedOutcomeModelId}
              onSelectModelId={setSelectedOutcomeModelId}
            />

            <DuplicatePanel
              canRun={canRun}
              busy={busy}
              selected={selected}
              mandatory={mandatory}
              thresholds={thresholds}
              minVotes={minVotes}
              duplicateProgress={duplicateProgress}
              duplicateResult={duplicateResult}
              onToggleSelection={toggleSelection}
              onToggleMandatory={toggleMandatory}
              onThresholdsChange={setThresholds}
              onMinVotesChange={setMinVotes}
              onRun={runDuplicateDetection}
              onInspectModel={(modelId) => {
                setPairInspectBoth(null);
                setPairInspectModelId(modelId);
              }}
              onInspectBoth={(leftId, rightId) => {
                setPairInspectModelId(null);
                setPairInspectBoth({ leftId, rightId });
              }}
            />
          </section>
        </section>
      </SidebarInset>

      {selectedModel && (
        <WarningInspectorDrawer
          model={selectedModel}
          warnings={warningsList.filter((entry) => (entry.modelId || "") === selectedModel.modelId)}
          tab={inspectorTab}
          onTabChange={setInspectorTab}
          onClose={closeModelInspector}
          inspectLoading={selectedModelInspect.loading}
          inspectError={selectedModelInspect.error}
          inspectModel={selectedModelInspect.payload}
        />
      )}
      {pairInspectModelId && (
        <ModelGraphDrawer
          title="Duplicate Pair Model Inspect"
          modelId={pairInspectModelId}
          onClose={() => setPairInspectModelId(null)}
          inspectLoading={pairModelInspect.loading}
          inspectError={pairModelInspect.error}
          inspectModel={pairModelInspect.payload}
        />
      )}
      {pairInspectBoth && (
        <PairCompareModal
          leftId={pairInspectBoth.leftId}
          rightId={pairInspectBoth.rightId}
          onClose={() => setPairInspectBoth(null)}
          leftInspectLoading={leftPairModelInspect.loading}
          leftInspectError={leftPairModelInspect.error}
          leftInspectModel={leftPairModelInspect.payload}
          rightInspectLoading={rightPairModelInspect.loading}
          rightInspectError={rightPairModelInspect.error}
          rightInspectModel={rightPairModelInspect.payload}
        />
      )}
    </SidebarProvider>
  );
}

function AppSidebar({ activeSection }: { activeSection: string }) {
  const { isMobile, setOpenMobile } = useSidebar();

  const onNavigate = () => {
    if (isMobile) {
      setOpenMobile(false);
    }
  };

  return (
    <Sidebar className="appSidebar" collapsible="icon">
      <SidebarHeader>
        <div className="sidebarHeaderTop">
          <SidebarTrigger className="sidebarTriggerInSidebar" />
        </div>
        <div className="brand">
          <img className="brandMark bg-white" src="/mcp4cm-icon-new.png" alt="" />
          <div className="brandText">
            <strong>MCP4CM</strong>
            <span>Model Cleansing Pipeline</span>
          </div>
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Upload" isActive={activeSection === "upload"}>
              <a href="#upload" onClick={onNavigate}>
                <FileUp size={18} />
                <span className="sidebarLinkLabel">Upload</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Statistics" isActive={activeSection === "stats"}>
              <a href="#stats" onClick={onNavigate}>
                <BarChart3 size={18} />
                <span className="sidebarLinkLabel">Statistics</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Visualizations" isActive={activeSection === "visualizations"}>
              <a href="#visualizations" onClick={onNavigate}>
                <Network size={18} />
                <span className="sidebarLinkLabel">Visualizations</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Dummy Filters" isActive={activeSection === "dummy"}>
              <a href="#dummy" onClick={onNavigate}>
                <Filter size={18} />
                <span className="sidebarLinkLabel">Dummy Filters</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton asChild tooltip="Duplicates" isActive={activeSection === "duplicates"}>
              <a href="#duplicates" onClick={onNavigate}>
                <GitCompare size={18} />
                <span className="sidebarLinkLabel">Duplicates</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarContent>
    </Sidebar>
  );
}

function Status({ datasetId, busy }: { datasetId: string; busy: BusyState }) {
  const label =
    busy === "parse"
      ? "Parsing models"
      : busy === "dummy"
        ? "Running dummy filters"
        : busy === "duplicates"
          ? "Running duplicate detection"
          : datasetId
            ? "Models parsed"
            : "Ready";

  return (
    <div className="status">
      {busy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
      {label}
    </div>
  );
}
