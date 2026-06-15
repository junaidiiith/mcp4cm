import type { FilterConfig, FormatOption, Language, TechniqueOption, Thresholds, UploadFormat } from "./types";

export const API_URL = import.meta.env.VITE_MCP4CM_API_URL || (import.meta.env.DEV ? "http://127.0.0.1:8765" : "");

export const techniques: TechniqueOption[] = [
  { id: "hash", label: "Hash", detail: "Exact match on normalized model names (optional type-aware mode)" },
  { id: "tfidf", label: "TF-IDF", detail: "Near-duplicate text similarity with configurable tokenization" },
  { id: "graph_similarity", label: "Graph metrics", detail: "Jaccard, degree, size, and density similarity" },
  { id: "graph_embedding", label: "Graph embeddings", detail: "Node2Vec graph embedding cosine similarity" },
  { id: "bert_semantic", label: "BERT semantic", detail: "bert-base-uncased semantic similarity on model names and types" },
  { id: "graph_isomorphism", label: "Isomorphism", detail: "Exact structural graph match" },
];

export const filterLabels: Record<string, [string, string]> = {
  min_size: ["Minimum size", "Remove models below node/edge thresholds."],
  too_few_named_elements: ["Naming density", "Minimum number of semantic names required."],
  short_median_name_length: ["Short median name", "Median semantic name length must meet the minimum."],
  placeholder_name_ratio: ["Placeholder ratio", "Placeholder/non-semantic names among named nodes must stay below threshold."],
  low_vocabulary: ["Low vocabulary", "Minimum unique token count across semantic names."],
  name_repetition_ratio: ["Name repetition", "Most frequent normalized name ratio among named nodes."],
  regex_rule: ["Regex rule", "Custom regex rule over names/types."],
};

export const filterGroups: Record<string, string> = {
  min_size: "Size",
  too_few_named_elements: "Naming Density",
  short_median_name_length: "Naming Density",
  placeholder_name_ratio: "Placeholder Detection",
  name_repetition_ratio: "Placeholder Detection",
  low_vocabulary: "Vocabulary",
  regex_rule: "Custom",
};

export const filterFormulaPreviews: Record<string, string> = {
  min_size: "nodeCount < minNodes OR edgeCount < minEdges",
  too_few_named_elements: "semanticNameCount < minNames",
  short_median_name_length: "median(semanticNameLength) < minMedianLength",
  placeholder_name_ratio: "placeholderCount / namedCount >= threshold",
  low_vocabulary: "uniqueSemanticTokens < minUniqueWords",
  name_repetition_ratio: "mostFrequentNameCount / namedCount >= threshold",
  regex_rule: "regexMatchCount(targetField, scope) >= minMatches",
};

const canonicalPreset: FilterConfig[] = [
  { id: "min_size", enabled: true, minNodes: 5, minEdges: 4 },
  { id: "too_few_named_elements", enabled: true, minNames: 5 },
  { id: "short_median_name_length", enabled: true, minMedianLength: 4 },
  { id: "placeholder_name_ratio", enabled: true, threshold: 0.3 },
  { id: "low_vocabulary", enabled: true, minUniqueWords: 3 },
  { id: "name_repetition_ratio", enabled: true, threshold: 0.5 },
  { id: "regex_rule", enabled: false, pattern: "", targetField: "name", scope: "eligible_only", minMatches: 1 },
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
  graphEmbeddingUseNodeNames: true,
  graphEmbeddingUseNodeTypes: true,
  graphEmbeddingUseEdgeTypes: true,
  graphEmbeddingPoolFeatures: false,
  graphEmbeddingPooling: "mean",
  bertSemantic: 0.9,
  semanticTextMode: "names_types_bag",
  bertModelName: "bert-base-uncased",
  bertBatchSize: 8,
  bertMaxLength: 256,
  isomorphismMode: "names",
  matchEdgeTypes: true,
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
