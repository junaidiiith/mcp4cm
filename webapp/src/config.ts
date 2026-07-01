import type { FilterConfig, FormatOption, Language, TechniqueOption, Thresholds, UploadFormat } from "./types";

export const API_URL = import.meta.env.VITE_MCP4CM_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:8765" : "");

export const techniques: TechniqueOption[] = [
  { id: "hash", label: "Hash", detail: "Exact match on normalized model names (optional type-aware mode)" },
  { id: "tfidf", label: "TF-IDF", detail: "Near-duplicate text similarity with configurable tokenization" },
  { id: "graph_similarity", label: "Graph metrics", detail: "Jaccard, degree, size, and density similarity" },
  { id: "gnn", label: "Contrastive GNN", detail: "GraphCL training over sentence-encoded node and edge text" },
  { id: "bert_semantic", label: "BERT semantic", detail: "bert-base-uncased semantic similarity on model names and types" },
];

export const filterLabels: Record<string, [string, string]> = {
  min_size: ["Minimum size", "Remove models below node/edge thresholds."],
  too_few_named_elements: ["Naming density", "Minimum number of semantic names required."],
  short_median_name_length: ["Short median name", "Median semantic name length must meet the minimum."],
  placeholder_name_ratio: ["Placeholder ratio", "Placeholder/non-semantic names among named nodes must stay below threshold."],
  low_vocabulary: ["Low vocabulary", "Minimum unique token count across semantic names."],
  name_repetition_ratio: ["Name repetition", "Most frequent normalized name ratio among named nodes."],
  regex_rule: ["Regex rule", "Custom regex rule over names/types."],
  language: ["Language", "Retain only models detected in selected natural languages."],
};

export const filterGroups: Record<string, string> = {
  min_size: "Size",
  too_few_named_elements: "Naming Density",
  short_median_name_length: "Naming Density",
  placeholder_name_ratio: "Placeholder Detection",
  name_repetition_ratio: "Placeholder Detection",
  low_vocabulary: "Vocabulary",
  regex_rule: "Custom",
  language: "Language",
};

export const filterFormulaPreviews: Record<string, string> = {
  min_size: "nodeCount < minNodes OR edgeCount < minEdges",
  too_few_named_elements: "semanticNameCount < minNames",
  short_median_name_length: "median(semanticNameLength) < minMedianLength",
  placeholder_name_ratio: "placeholderCount / namedCount >= threshold",
  low_vocabulary: "uniqueSemanticTokens < minUniqueWords",
  name_repetition_ratio: "mostFrequentNameCount / namedCount >= threshold",
  regex_rule: "regexMatchCount(targetField, scope) >= minMatches",
  language: "detectedLanguage(modelNames) NOT IN selectedLanguages",
};

const canonicalPreset: FilterConfig[] = [
  { id: "min_size", enabled: true, minNodes: 5, minEdges: 4 },
  { id: "too_few_named_elements", enabled: true, minNames: 5 },
  { id: "short_median_name_length", enabled: true, minMedianLength: 4 },
  { id: "placeholder_name_ratio", enabled: true, threshold: 0.3 },
  { id: "low_vocabulary", enabled: true, minUniqueWords: 3 },
  { id: "name_repetition_ratio", enabled: true, threshold: 0.5 },
  { id: "regex_rule", enabled: false, pattern: "", targetField: "name", scope: "eligible_only", minMatches: 1 },
  { id: "language", enabled: true, languages: ["en"] },
];

export const naturalLanguageOptions = [
  { value: "en", label: "English" },
  { value: "de", label: "German" },
  { value: "fr", label: "French" },
  { value: "es", label: "Spanish" },
  { value: "it", label: "Italian" },
  { value: "pt", label: "Portuguese" },
  { value: "nl", label: "Dutch" },
  { value: "sv", label: "Swedish" },
  { value: "no", label: "Norwegian" },
  { value: "da", label: "Danish" },
  { value: "fi", label: "Finnish" },
  { value: "pl", label: "Polish" },
  { value: "cs", label: "Czech" },
  { value: "tr", label: "Turkish" },
];

export const dummyFilterPresets: Record<Language, FilterConfig[]> = {
  uml: canonicalPreset,
  ecore: canonicalPreset,
  archimate: canonicalPreset,
  bpmn: canonicalPreset,
};

export const formatOptionsByLanguage: Record<Language, FormatOption[]> = {
  uml: [
    { value: "json", label: "JSON", directoryPreferred: true, accept: ".json" },
    { value: "xmi", label: "XMI / XML", directoryPreferred: true, accept: ".xmi,.xml" },
    { value: "xml-pyecore", label: "XML / XMI (PyEcore)", directoryPreferred: true, accept: ".xmi,.uml,.xml" },
  ],
  archimate: [
    { value: "json", label: "JSON", directoryPreferred: true, accept: ".json" },
    { value: "xmi", label: "Archi .archimate / XML", directoryPreferred: true, accept: ".archimate,.xml" },
  ],
  ecore: [
    { value: "json", label: "JSON", directoryPreferred: true, accept: ".json" },
    { value: "ecore", label: "Ecore (.ecore)", directoryPreferred: true, accept: ".ecore" },
  ],
  bpmn: [
    { value: "signavio", label: "Signavio JSON", directoryPreferred: true, accept: ".json" },
  ],
};

export const defaultThresholds: Thresholds = {
  hashIncludeTypes: false,
  minNamedNodes: 0,
  deduplicateNameTokens: false,
  tfidfTokenMode: "names",
  tfidfSimilarityThreshold: 0.9,
  tfidfMaxFeatures: 50000,
  minDf: 1,
  ngramRangeMin: 1,
  ngramRangeMax: 1,
  stopwordsMode: "none",
  graphSimilarity: 0.85,
  graphWeights: {
    nodeNameJaccard: 0.25,
    nodeTypeJaccard: 0.2,
    edgeTypeJaccard: 0.15,
    degreeHistogram: 0.15,
    inDegreeHistogram: 0.15,
    outDegreeHistogram: 0.15,
    sizeSimilarity: 0.15,
    densitySimilarity: 0.1,
  },
  useDirectedMetrics: false,
  normalizeParallelEdges: false,
  graphEmbedding: 0.9,
  graphEmbeddingThreshold: 0.9,
  graphEmbeddingDimensions: 32,
  graphEmbeddingWalkLength: 5,
  graphEmbeddingNumWalks: 5,
  graphEmbeddingWorkers: 1,
  graphEmbeddingSeed: 42,
  gnnThreshold: 0.85,
  gnnDimensions: 128,
  gnnLayers: 2,
  gnnEpochs: 20,
  gnnLearningRate: 0.001,
  gnnTemperature: 0.2,
  gnnEdgeDropout: 0.15,
  gnnFeatureMaskRate: 0.1,
  gnnBatchSize: 32,
  gnnModelName: "sentence-transformers/all-MiniLM-L6-v2",
  gnnSeed: 42,
  gnnDevice: "auto",
  bertSemantic: 0.8,
  semanticTextMode: "names_types_bag",
  bertModelName: "sentence-transformers/all-MiniLM-L6-v2",
  bertBatchSize: 8,
  bertMaxLength: 256,
  ignoreDirection: false,
  matchParallelEdgeMultiplicity: true,
};

export function clonePreset(language: Language): FilterConfig[] {
  return (dummyFilterPresets[language] || dummyFilterPresets.uml).map((filter) => ({ ...filter }));
}

export function defaultFormatForLanguage(language: Language): UploadFormat {
  // Prefer directory-oriented source formats when available (e.g. UML XMI datasets).
  const options = formatOptionsByLanguage[language];
  const preferred = options.find((option) => option.directoryPreferred && option.value !== "json")
    || options.find((option) => option.directoryPreferred);
  return (preferred || options[0]).value;
}
