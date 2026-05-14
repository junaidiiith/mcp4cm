export type Language = "uml" | "ecore" | "archimate" | "bpmn";
export type UploadFormat = "json" | "xmi" | "ecore" | "signavio";

export interface TechniqueOption {
  id: string;
  label: string;
  detail: string;
}

export interface GraphWeights {
  nodeNameJaccard: number;
  nodeTypeJaccard: number;
  edgeTypeJaccard: number;
  degreeHistogram: number;
  sizeSimilarity: number;
  densitySimilarity: number;
}

export interface Thresholds {
  hashIncludeTypes: boolean;
  tfidfIncludeTypes: boolean;
  tfidfNames: number;
  tfidfNamesTypes: number;
  tfidfMaxFeatures: number;
  graphSimilarity: number;
  graphWeights: GraphWeights;
  graphEmbedding: number;
  graphEmbeddingDimensions: number;
  graphEmbeddingWalkLength: number;
  graphEmbeddingNumWalks: number;
  graphEmbeddingWorkers: number;
  graphEmbeddingSeed: number;
  bertSemantic: number;
  bertModelName: string;
  bertBatchSize: number;
  bertMaxLength: number;
  isomorphismMode: string;
  matchEdgeTypes: boolean;
}

export interface UploadSummary {
  files: number;
  payloads: number;
  records: number;
  errors: number;
  warnings?: number;
  warningsByType?: Record<string, number>;
  warningsList?: WarningEntry[];
  warningFiles?: WarningFileSummary[];
  parsedModels?: ParsedModelSummary[];
  format?: UploadFormat;
  representationProfile?: {
    includeAttributes: boolean;
    includeOperations: boolean;
    includeParameters: boolean;
    includeModelRootNode: boolean;
  };
}

export interface RepresentationProfile {
  includeAttributes: boolean;
  includeOperations: boolean;
  includeParameters: boolean;
  includeModelRootNode: boolean;
}

export interface WarningEntry {
  type: string;
  message: string;
  path?: string;
  modelId?: string;
}

export interface WarningFileSummary {
  path: string;
  warnings: number;
  types: Record<string, number>;
  modelId?: string;
  hasDetails?: boolean;
}

export interface ParsedModelSummary {
  modelId: string;
  name?: string;
  path: string;
  language?: string;
  warnings: number;
  types: Record<string, number>;
}

export interface UploadParseJob {
  jobId: string;
  uploadId: string;
  status: "queued" | "running" | "complete" | "error";
  progress: number;
  processedFiles: number;
  totalFiles: number;
  stage?: "queued" | "parse" | "complete";
  parseProcessedFiles?: number;
  parseTotalFiles?: number;
  message: string;
  error?: string;
  datasetId?: string;
  statistics?: StatisticsPayload;
  uploadSummary?: UploadSummary;
}

export interface StatisticItem {
  label: string;
  count: number;
}

export interface StatisticsPayload {
  summary: {
    models: number;
    nodes: { mean: number };
    edges: { mean: number };
    names: { median: number };
  };
  topTypes: StatisticItem[];
  topNames: StatisticItem[];
}

export interface ModelInspectPayload {
  model: {
    id: string;
    language: string;
    name: string;
    sourcePath: string;
    nodeCount: number;
    edgeCount: number;
    metadata: Record<string, unknown>;
  };
  nodes: Array<{ id: string; attrs?: Record<string, unknown> }>;
  edges: Array<{ source: string; target: string; key?: string; attrs?: Record<string, unknown> }>;
  truncated: {
    nodes: boolean;
    edges: boolean;
  };
}

export interface DuplicateProgressState {
  status: string;
  progress: number;
  currentTechnique?: string;
  completedTechniques?: string[];
  selectedTechniques?: string[];
  totalTechniques?: number;
  totalModels?: number;
  techniqueProgress?: number;
  processedItems?: number;
  totalItems?: number;
  elapsedMs?: number;
  message?: string;
  jobId?: string;
  result?: DuplicateResult;
  error?: string;
}

export interface DuplicateResult {
  duplicatePairs: number;
  votedDuplicatePairs?: number;
  elapsedMs: number;
  techniqueCounts: Record<string, number>;
  modelCounts: Record<string, { duplicateModels: number; uniqueModels: number; totalModels: number; pairCount: number; elapsedMs: number }>;
  decisions: Array<{ leftId: string; rightId: string; isDuplicate: boolean; voteCount: number; techniques: string[] }>;
}

export interface DummyRow {
  filterName: string;
  filteredCount: number;
  remainingCount: number;
  examples?: Array<{ evidence?: string[] }>;
}

export interface DummyFilterSummary {
  filterId: string;
  filteredCount: number;
  remainingCount: number;
  triggeredModelIds: string[];
}

export interface DummyModelOutcome {
  modelId: string;
  removed: boolean;
  primaryRemovalReason: string | null;
  allTriggeredFilters: string[];
}

export interface DummyFinding {
  modelId: string;
  filterId: string;
  reason: string;
  score: number;
  threshold: number;
  decision: "removed" | "kept";
  evidence: string[];
  evidenceNodes: string[];
  metrics: Record<string, unknown>;
}

export interface DummyRunSummary {
  totalModels: number;
  removedModels: number;
  remainingModels: number;
  removalRate: number;
}

export interface DummyResponse {
  runSummary: DummyRunSummary;
  filterSummaries: DummyFilterSummary[];
  modelOutcomes: DummyModelOutcome[];
  findings: DummyFinding[];
  rows?: DummyRow[];
}

export type FilterConfig = Record<string, any>;

export interface FormatOption {
  value: UploadFormat;
  label: string;
  directoryPreferred: boolean;
  accept: string;
}
