export type Language = "uml" | "ecore" | "archimate" | "bpmn";
export type UploadFormat = "json" | "xmi" | "xml-pyecore" | "ecore" | "signavio";
export type BusyState = "" | "parse" | "dummy" | "duplicates";

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
  inDegreeHistogram: number;
  outDegreeHistogram: number;
  sizeSimilarity: number;
  densitySimilarity: number;
}

export interface Thresholds {
  hashIncludeTypes: boolean;
  minNamedNodes: number;
  deduplicateNameTokens: boolean;
  tfidfTokenMode: "names" | "names_types_bag" | "typed_name_pairs";
  tfidfSimilarityThreshold: number;
  tfidfMaxFeatures: number;
  minDf: number;
  ngramRangeMin: number;
  ngramRangeMax: number;
  stopwordsMode: "none" | "english";
  graphSimilarity: number;
  graphWeights: GraphWeights;
  useDirectedMetrics: boolean;
  normalizeParallelEdges: boolean;
  graphEmbedding: number;
  graphEmbeddingThreshold: number;
  graphEmbeddingDimensions: number;
  graphEmbeddingWalkLength: number;
  graphEmbeddingNumWalks: number;
  graphEmbeddingWorkers: number;
  graphEmbeddingSeed: number;
  gnnThreshold: number;
  gnnDimensions: number;
  gnnLayers: number;
  gnnEpochs: number;
  gnnLearningRate: number;
  gnnTemperature: number;
  gnnEdgeDropout: number;
  gnnFeatureMaskRate: number;
  gnnBatchSize: number;
  gnnModelName: string;
  gnnSeed: number;
  gnnDevice: "auto" | "cpu" | "cuda";
  bertSemantic: number;
  semanticTextMode: "names" | "names_types_bag" | "typed_name_pairs";
  bertModelName: string;
  bertBatchSize: number;
  bertMaxLength: number;
  ignoreDirection: boolean;
  matchParallelEdgeMultiplicity: boolean;
}

export interface UploadSummary {
  files: number;
  payloads: number;
  records: number;
  errors: number;
  emptyFiles?: string[];
  invalidFiles?: string[];
  ignoredFiles?: string[];
  warnings?: number;
  warningsByType?: Record<string, number>;
  warningsList?: WarningEntry[];
  warningFiles?: WarningFileSummary[];
  parsedModels?: ParsedModelSummary[];
  format?: UploadFormat;
  language?: Language;
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

export interface EcoreParseOptions {
  resolveExternalRefs: boolean;
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
  nodeCount: number;
  edgeCount: number;
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
  stage?: "queued" | "parse" | "statistics" | "complete";
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
    nodes: Distribution;
    edges: Distribution;
    names: Distribution;
  };
  topTypes: StatisticItem[];
  topNames: StatisticItem[];
  visualizations: VisualizationPayload;
}

export interface Distribution {
  min: number;
  max: number;
  mean: number;
  median: number;
}

export interface HistogramBin {
  start: number;
  end: number;
  count: number;
  displayCount: number;
}

export interface VisualizationPayload {
  missingNameRatioHistogram: HistogramBin[];
  missingNameRatioBands: HistogramBin[];
  missingNameRatioSummary: RatioSummary;
  nameClassificationOverview: Array<StatisticItem & { key: string }>;
  elementTypeQualityMatrix: TypeQualityRow[];
  semanticNameCountHistogram: StatisticItem[];
  modelQualityWatchlists: ModelQualityWatchlists;
  topConcepts: StatisticItem[];
  topConceptDocumentFrequency: StatisticItem[];
  topConceptsWithoutPlaceholders: StatisticItem[];
  topConceptDocumentFrequencyWithoutPlaceholders: StatisticItem[];
  vocabularySummary: {
    uniqueNames: number;
    totalOccurrences: number;
    semanticNames: number;
    placeholderNames: number;
    singletonNames: number;
    mostReusedName: string;
    mostReusedDocumentFrequency: number;
  };
  vocabularyRanking: VocabularyRankingRow[];
  typeVocabularyTable: TypeVocabularyRow[];
  labelPipelineRows: LabelPipelineRow[];
  nameReuseDistribution: StatisticItem[];
  elementTypeTreemap: StatisticItem[];
  modelVocabularyScatter: Array<{
    id: string;
    nodeCount?: number;
    edgeCount?: number;
    graphSize?: number;
    namedElements: number;
    semanticNameCount?: number;
    placeholderNameCount?: number;
    uniqueNames: number;
    tokens: number;
    uniqueTokens: number;
    nameSlots: number;
    missingNames: number;
    missingNameRatio: number;
  }>;
  topNamesPerModel: StatisticItem[];
}

export interface VocabularyRankingRow {
  name: string;
  occurrences: number;
  documentFrequency: number;
  coverage: number;
  occurrencesPerModel: number;
  occurrencesPerUsedModel: number;
  semantic: number;
  placeholder: number;
  classification: "semantic" | "placeholder" | "mixed" | "unknown";
}

export interface TypeVocabularyRow {
  type: string;
  totalOccurrences: number;
  namedOccurrences: number;
  names: Array<{
    name: string;
    occurrences: number;
    share: number;
    classification: "semantic" | "placeholder" | "mixed" | "unknown";
  }>;
}

export interface LabelPipelineRow {
  rawName: string;
  normalizedName: string;
  nameTokens: string[];
  rawType: string;
  normalizedType: string;
  typeTokens: string[];
  classification: "semantic" | "placeholder" | "missing";
  occurrences: number;
  documentFrequency: number;
}

export interface LabelPipelinePage {
  datasetId: string;
  snapshot: "before" | "after";
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  rows: LabelPipelineRow[];
}

export interface RatioSummary {
  models: number;
  zero: number;
  median: number;
  p90: number;
  above30: number;
  above70: number;
}

export interface TypeQualityRow {
  type: string;
  total: number;
  semantic: number;
  missing: number;
  placeholder: number;
}

export interface ModelQualityWatchlists {
  fewSemanticNames: ModelQualityRow[];
  highMissingRatio: ModelQualityRow[];
  highPlaceholderRatio: ModelQualityRow[];
  highNameDominance: ModelQualityRow[];
}

export interface ModelQualityRow {
  id: string;
  nameSlots: number;
  semanticNames: number;
  placeholderNames: number;
  missingRatio: number;
  placeholderRatio: number;
  dominantName: string;
  dominantNameRatio: number;
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
  diagnostics?: {
    parseStatus: string;
    warningCount: number;
    warningsByType: Record<string, number>;
    warningMessagesByType: Record<string, string[]>;
    errorMessage: string;
    elementsLoaded: number;
    elementsSkipped: number;
    parseTimeMs: number;
    sourcePath: string;
  };
  nodes: Array<{ id: string; attrs?: Record<string, unknown> }>;
  edges: Array<{ source: string; target: string; key?: string; attrs?: Record<string, unknown> }>;
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
  candidatePairs?: number;
  approvedPairs?: number;
  duplicateGroups?: number;
  affectedModels?: number;
  largestGroupSize?: number;
  votedDuplicatePairs?: number;
  totalDecisions?: number;
  elapsedMs: number;
  jobId?: string;
  datasetId?: string;
  techniqueStatus?: Record<string, { status: string; reason?: string; pairCount?: number; elapsedMs?: number }>;
  configEcho?: Record<string, unknown>;
  techniqueCounts: Record<string, number>;
  modelCounts: Record<string, { duplicateModels: number; uniqueModels: number; totalModels: number; pairCount: number; elapsedMs: number }>;
  groupSummary?: DuplicateGroupSummary;
  groups?: DuplicateGroup[];
  groupsPage?: DuplicateGroupsPage;
  pairsPage?: DuplicatePairsPage;
  decisions: DuplicatePairDecision[];
}

export interface DuplicatePairDecision {
  leftId: string;
  rightId: string;
  groupId?: string;
  isDuplicate: boolean;
  voteCount: number;
  requiredVotes?: number;
  mandatorySatisfied?: boolean;
  minVotesSatisfied?: boolean;
  techniques: string[];
  scores?: Record<string, number>;
  metrics?: Record<string, Record<string, number>>;
}

export interface DuplicateGroupSummary {
  totalGroups: number;
  affectedModels: number;
  largestGroupSize: number;
  strongGroups: number;
  highGroups: number;
  moderateGroups: number;
  lowGroups: number;
}

export interface DuplicateModelSummary {
  modelId: string;
  name?: string;
  path?: string;
  language?: string;
  nodeCount?: number;
  edgeCount?: number;
  namedElements?: number;
  warnings?: number;
}

export interface DuplicateGroup {
  groupId: string;
  modelIds: string[];
  size: number;
  approvedInternalPairs: number;
  candidateRejectedInternalPairs: number;
  missingInternalPairs: number;
  possibleInternalPairs: number;
  density: number;
  confidence: "strong" | "high" | "moderate" | "low" | string;
  warnings: string[];
  techniques: string[];
  canonicalModelId: string;
  canonicalReason?: string;
  scoreStats?: { min: number; max: number; avg: number };
  modelSummaries?: DuplicateModelSummary[];
}

export interface DuplicateGroupsPage {
  groups: DuplicateGroup[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface DuplicatePairsPage {
  pairs: DuplicatePairDecision[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface DuplicateGroupDetail {
  group: DuplicateGroup;
  pairs: DuplicatePairDecision[];
  modelSummaries: DuplicateModelSummary[];
}

export interface DuplicateCanonicalSelection {
  groupId: string;
  canonicalModelId: string;
  duplicateModelIds: string[];
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
  statistics?: StatisticsPayload;
  statisticsJobId?: string;
}

export interface DummyProgressState {
  jobId: string;
  datasetId: string;
  status: "queued" | "running" | "complete" | "error";
  stage: "queued" | "loading" | "filtering" | "summarizing" | "complete" | "error";
  progress: number;
  processedModels: number;
  totalModels: number;
  message: string;
  elapsedMs: number;
  result?: DummyResponse | null;
  error?: string;
}

export type AfterDummyStatisticsResponse =
  | StatisticsPayload
  | {
      status: "pending" | "running" | "error";
      jobId?: string;
      error?: string;
    };

interface BaseFilterConfig {
  enabled: boolean;
}

export interface MinSizeFilterConfig extends BaseFilterConfig {
  id: "min_size";
  minNodes: number;
  minEdges: number;
}

export interface TooFewNamedElementsFilterConfig extends BaseFilterConfig {
  id: "too_few_named_elements";
  minNames: number;
}

export interface ShortMedianNameLengthFilterConfig extends BaseFilterConfig {
  id: "short_median_name_length";
  minMedianLength: number;
}

export interface PlaceholderNameRatioFilterConfig extends BaseFilterConfig {
  id: "placeholder_name_ratio";
  threshold: number;
}

export interface LowVocabularyFilterConfig extends BaseFilterConfig {
  id: "low_vocabulary";
  minUniqueWords: number;
}

export interface NameRepetitionRatioFilterConfig extends BaseFilterConfig {
  id: "name_repetition_ratio";
  threshold: number;
}

export interface RegexRuleFilterConfig extends BaseFilterConfig {
  id: "regex_rule";
  pattern: string;
  targetField: "name" | "name+type" | "type";
  scope: "eligible_only" | "all_named_nodes";
  minMatches: number;
}

export interface LanguageFilterConfig extends BaseFilterConfig {
  id: "language";
  languages: string[];
}

export type FilterConfig =
  | MinSizeFilterConfig
  | TooFewNamedElementsFilterConfig
  | ShortMedianNameLengthFilterConfig
  | PlaceholderNameRatioFilterConfig
  | LowVocabularyFilterConfig
  | NameRepetitionRatioFilterConfig
  | RegexRuleFilterConfig
  | LanguageFilterConfig;

export interface FormatOption {
  value: UploadFormat;
  label: string;
  directoryPreferred: boolean;
  accept: string;
}
