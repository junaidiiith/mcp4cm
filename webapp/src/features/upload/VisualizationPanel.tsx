import { ArrowDown, ArrowUp, ArrowUpDown, Expand, Grid2X2, Info, ListTree, Network, Plus } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { HistogramBin, StatisticItem, VisualizationPayload } from "../../types";
import { round } from "../../utils";

type VisualizationSnapshot = "before" | "after";

export function VisualizationPanel({
  beforeData,
  afterData,
  beforeModelCount,
  afterModelCount,
  onInspectModel,
}: {
  beforeData: VisualizationPayload | null;
  afterData: VisualizationPayload | null;
  beforeModelCount: number | null;
  afterModelCount: number | null;
  onInspectModel: (modelId: string) => void;
}) {
  const [activeCategory, setActiveCategory] = useState<VisualizationCategoryId>("quality");
  const [selectedChartId, setSelectedChartId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [expandedChartId, setExpandedChartId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<VisualizationSnapshot>("before");
  const data = snapshot === "after" && afterData ? afterData : beforeData;
  const afterDataAvailable = Boolean(afterData);
  const categories = useMemo(() => data ? visualizationCategories(data, onInspectModel) : [], [data, onInspectModel]);
  const activeCharts = categories.find((category) => category.id === activeCategory)?.charts || categories[0]?.charts || [];
  const selectedChart = activeCharts.find((chart) => chart.id === selectedChartId) || activeCharts[0] || null;
  const expandedChart = categories.flatMap((category) => category.charts).find((chart) => chart.id === expandedChartId) || null;
  const selectedModelCount = snapshot === "after" ? afterModelCount : beforeModelCount;
  const modelCountLabel = selectedModelCount === null ? "" : `${selectedModelCount.toLocaleString()} models`;

  useEffect(() => {
    if (snapshot === "after" && !afterData) setSnapshot("before");
  }, [afterData, snapshot]);

  useEffect(() => {
    if (!categories.length) {
      if (selectedChartId) setSelectedChartId(null);
      return;
    }

    const category = categories.find((item) => item.id === activeCategory);
    if (!category) {
      setActiveCategory(categories[0].id);
      setSelectedChartId(categories[0].charts[0]?.id || null);
      return;
    }

    if (!selectedChartId || !category.charts.some((chart) => chart.id === selectedChartId)) {
      setSelectedChartId(category.charts[0]?.id || null);
    }
  }, [activeCategory, categories, selectedChartId]);

  return (
    <Card className="panel" id="visualizations">
      <CardHeader className="panelHeader">
        <h2><Network size={20} />Dataset Visualizations</h2>
      </CardHeader>
      <CardContent>
        {!data ? <div className="empty"><Plus size={18} />Parse a dataset to render visualizations.</div> : (
          <>
            <Tabs
              className="visualizationTabs"
              value={activeCategory}
              onValueChange={(value) => {
                const nextCategory = value as VisualizationCategoryId;
                setActiveCategory(nextCategory);
                setSelectedChartId(categories.find((category) => category.id === nextCategory)?.charts[0]?.id || null);
              }}
            >
              <div className="visualizationToolbar">
                <TabsList className="visualizationTabList">
                  {categories.map((category) => (
                    <TabsTrigger key={category.id} value={category.id}>{category.label}</TabsTrigger>
                  ))}
                </TabsList>
                <div className="visualizationToolbarActions">
                  <div
                    className="visualizationSnapshotControl"
                    aria-label="Visualization dataset snapshot"
                    key={afterDataAvailable ? "after-available" : "after-unavailable"}
                  >
                    <button
                      className={snapshot === "before" ? "active" : ""}
                      type="button"
                      onClick={() => setSnapshot("before")}
                    >
                      Before
                    </button>
                    <button
                      className={snapshot === "after" ? "active" : ""}
                      type="button"
                      disabled={!afterDataAvailable}
                      title={afterDataAvailable ? "After cleansing" : "Run dummy filters to enable after-cleansing visualizations."}
                      onClick={() => setSnapshot("after")}
                    >
                      After
                    </button>
                  </div>
                  <Button className="visualizationModeButton" type="button" variant="secondary" size="sm" onClick={() => setShowAll((current) => !current)}>
                    {showAll ? <ListTree size={16} /> : <Grid2X2 size={16} />}
                    {showAll ? "Focused" : "Show all"}
                  </Button>
                </div>
              </div>
              {modelCountLabel && (
                <div className="visualizationSnapshotStatus">
                  {snapshot === "after" ? "After cleansing" : "Before cleansing"}: {modelCountLabel}
                </div>
              )}

              {categories.map((category) => (
                <TabsContent key={category.id} value={category.id}>
                  {showAll ? (
                    <div className="visualizationShowAllGrid">
                      {category.charts.map((chart) => (
                        <ChartPreview key={chart.id} chart={chart} onExpand={() => setExpandedChartId(chart.id)} />
                      ))}
                    </div>
                  ) : (
                    <div className="visualizationWorkbench">
                      <nav className="visualizationChartNav" aria-label={`${category.label} charts`}>
                        {category.charts.map((chart) => (
                          <button
                            className={chart.id === selectedChart?.id ? "active" : ""}
                            key={chart.id}
                            type="button"
                            onClick={() => setSelectedChartId(chart.id)}
                          >
                            <strong>{chart.title}</strong>
                            <span>{chart.description}</span>
                          </button>
                        ))}
                      </nav>
                      {selectedChart && <ChartPreview chart={selectedChart} featured onExpand={() => setExpandedChartId(selectedChart.id)} />}
                    </div>
                  )}
                </TabsContent>
              ))}
            </Tabs>

            <Dialog open={Boolean(expandedChart)} onOpenChange={(open) => !open && setExpandedChartId(null)}>
              {expandedChart && (
                <DialogContent className="visualizationDialog">
                  <DialogHeader>
                    <DialogTitle>{expandedChart.title}</DialogTitle>
                    <DialogDescription>{expandedChart.description}</DialogDescription>
                  </DialogHeader>
                  <div className="visualizationDialogBody">{expandedChart.render()}</div>
                </DialogContent>
              )}
            </Dialog>
          </>
        )}
      </CardContent>
    </Card>
  );
}

type VisualizationCategoryId = "quality" | "labels" | "structure" | "topics";
interface VisualizationChartDefinition {
  id: string;
  title: string;
  description: string;
  render: () => ReactNode;
}

interface VisualizationCategory {
  id: VisualizationCategoryId;
  label: string;
  charts: VisualizationChartDefinition[];
}

function visualizationCategories(
  data: VisualizationPayload,
  onInspectModel: (modelId: string) => void,
): VisualizationCategory[] {
  return [
    {
      id: "quality",
      label: "Quality",
      charts: [
        {
          id: "missing-name-ratio",
          title: "Distribution of Missing-Name Ratio per Model",
          description: "Share of derived node name slots classified as missing.",
          render: () => <RatioQualityChart bins={data.missingNameRatioBands || data.missingNameRatioHistogram} summary={data.missingNameRatioSummary} />,
        },
        {
          id: "name-classification-overview",
          title: "Name Classification Overview",
          description: "All derived node name slots grouped by classification.",
          render: () => <NameClassificationOverview items={data.nameClassificationOverview || []} />,
        },
        {
          id: "name-classification-by-type",
          title: "Name Classification by Normalized Type",
          description: "Semantic, missing, placeholder, and type-like names grouped by normalized node type.",
          render: () => <TypeQualityTable rows={data.elementTypeQualityMatrix || []} />,
        },
        {
          id: "semantic-name-count-distribution",
          title: "Semantic Name Count Distribution",
          description: "Model counts grouped by derived semantic-name counts.",
          render: () => <LabeledHistogram items={data.semanticNameCountHistogram || []} />,
        },
        {
          id: "at-risk-models",
          title: "Models at Risk",
          description: "Models at risk for low semantic naming, high missingness, and repeated names.",
          render: () => <ModelQualityWatchlists watchlists={data.modelQualityWatchlists} onInspectModel={onInspectModel} />,
        },
      ],
    },
    {
      id: "labels",
      label: "Labels",
      charts: [
        {
          id: "label-pipeline",
          title: "Raw to Normalized Labels and Tokens",
          description: "Parser-observed names and types beside the derived normalized labels, tokens, and classification.",
          render: () => <LabelPipelineTable rows={data.labelPipelineRows || []} />,
        },
        {
          id: "vocabulary-summary",
          title: "Normalized Name Vocabulary Summary",
          description: "Corpus-level counts for derived normalized names and reuse.",
          render: () => <VocabularySummary summary={data.vocabularySummary} />,
        },
        {
          id: "vocabulary-ranking",
          title: "Normalized Name Vocabulary Ranking",
          description: "Derived normalized names ranked by occurrence, model coverage, and classification.",
          render: () => <VocabularyRanking rows={data.vocabularyRanking || []} />,
        },
        {
          id: "type-vocabulary-heatmap",
          title: "Name Tokens by Normalized Type",
          description: "Relative derived name-token frequency within each major normalized node type.",
          render: () => <Heatmap data={data.vocabularyHeatmap} />,
        },
        {
          id: "name-reuse-distribution",
          title: "Normalized Name Reuse Distribution",
          description: "How many distinct normalized names appear in one model versus many models.",
          render: () => <LabeledHistogram items={data.nameReuseDistribution || []} />,
        },
      ],
    },
    {
      id: "structure",
      label: "Structure",
      charts: [
        {
          id: "element-type-treemap",
          title: "Normalized Node Types in the Corpus",
          description: "Treemap area is proportional to normalized node type count.",
          render: () => <Treemap items={data.elementTypeTreemap} />,
        },
        {
          id: "type-name-links",
          title: "Normalized Type to Frequent Names",
          description: "Strongest links between normalized node types and normalized names.",
          render: () => <TypeConceptLinks links={data.typeConceptLinks} />,
        },
        {
          id: "names-within-types",
          title: "Frequent Normalized Names within Types",
          description: "Hierarchical treemap grouped by major normalized node type.",
          render: () => <ConceptTreemap links={data.typeConceptLinks} />,
        },
        {
          id: "model-vocabulary-scatter",
          title: "Model Size vs Vocabulary Richness",
          description: "Point size follows derived name-token count; color follows missing-name ratio.",
          render: () => <Scatter points={data.modelVocabularyScatter} />,
        },
        {
          id: "name-count-boxplot",
          title: "Boxplot of Name Counts in Models",
          description: "Five-number summary of parser-observed model name counts.",
          render: () => <Boxplot summary={data.nameCountBoxplot} />,
        },
        {
          id: "name-count-histogram-log",
          title: "Histogram of Name Counts (Log Scale)",
          description: "Log-scaled model frequency for parser-observed model name counts.",
          render: () => <Histogram bins={data.nameCountHistogramLog} useDisplayCount />,
        },
        {
          id: "few-names-histogram",
          title: "Models with Fewer Than Five Names",
          description: "Parser-observed name-count distribution for small models.",
          render: () => <Histogram bins={data.fewNamesHistogram} />,
        },
        {
          id: "language-distribution",
          title: "Modeling Language Distribution",
          description: "Parsed model count by modeling language.",
          render: () => <HorizontalBars items={data.languageDistribution} />,
        },
      ],
    },
    {
      id: "topics",
      label: "Topics",
      charts: data.topicModel.available ? [
        {
          id: "topic-map",
          title: `Document Topic Map (${data.topicModel.projectionMethod} projection)`,
          description: "NMF topic assignment from derived name tokens projected into two dimensions.",
          render: () => <TopicScatter points={data.topicModel.points || []} />,
        },
        {
          id: "topic-prevalence",
          title: "Average Topic Prevalence in the Corpus",
          description: "Mean NMF topic weight.",
          render: () => <HorizontalBars items={data.topicModel.prevalence || []} />,
        },
      ] : [
        {
          id: "topics-unavailable",
          title: "Topic Model",
          description: "Topic modeling is unavailable for this dataset.",
          render: () => <p className="visualizationNote">{data.topicModel.reason}</p>,
        },
      ],
    },
  ];
}

function ChartPreview({ chart, featured, onExpand }: { chart: VisualizationChartDefinition; featured?: boolean; onExpand: () => void }) {
  return (
    <article className={`visualizationCard${featured ? " featured" : ""}`}>
      <div className="visualizationCardHeader">
        <div>
          <h4>{chart.title}</h4>
          <p>{chart.description}</p>
        </div>
        <Button aria-label={`Expand ${chart.title}`} type="button" variant="ghost" size="icon" onClick={onExpand}>
          <Expand size={16} />
        </Button>
      </div>
      <div className="chartBody">{chart.render()}</div>
    </article>
  );
}

function HorizontalBars({ items }: { items: StatisticItem[] }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  if (!items.length) return <EmptyChart />;
  return <div className="horizontalBars">{items.map((item) => <div className="horizontalBarRow" key={item.label} title={`${item.label}: ${round(item.count)}`}><span>{item.label}</span><i><b style={{ width: `${item.count / max * 100}%` }} /></i><strong>{round(item.count)}</strong></div>)}</div>;
}

function LimitedHorizontalBars({ items, ariaLabel }: { items: StatisticItem[]; ariaLabel: string }) {
  const [limit, setLimit] = useState(10);
  const visibleItems = items.slice(0, limit);
  return (
    <>
      <label className="chartLimit">
        Top N
        <input
          aria-label={ariaLabel}
          type="number"
          min={1}
          value={limit}
          onChange={(event) => {
            const value = Number(event.target.value);
            if (Number.isInteger(value)) setLimit(Math.max(value, 1));
          }}
        />
      </label>
      <div className={limit > 10 ? "chartRowsScrollable" : ""}>
        <HorizontalBars items={visibleItems} />
      </div>
    </>
  );
}

function VocabularySummary({ summary }: { summary?: VisualizationPayload["vocabularySummary"] }) {
  if (!summary) return <EmptyChart />;
  return (
    <div className="vocabularySummary">
      <SummaryStat label="Unique Names" value={summary.uniqueNames} />
      <SummaryStat label="Occurrences" value={summary.totalOccurrences} />
      <SummaryStat label="Semantic Names" value={summary.semanticNames} />
      <SummaryStat label="Placeholder / Type-like" value={summary.placeholderOrTypeLikeNames} />
      <SummaryStat label="Singleton Names" value={summary.singletonNames} />
      <SummaryStat
        label="Most Reused"
        value={summary.mostReusedName || "None"}
        suffix={summary.mostReusedName ? `${summary.mostReusedDocumentFrequency.toLocaleString()} models` : undefined}
      />
    </div>
  );
}

type LabelPipelineSortKey = "occurrences" | "documentFrequency" | "rawName" | "normalizedName" | "rawType" | "normalizedType";

const labelPipelineColumns: Array<{ key: LabelPipelineSortKey; label: string }> = [
  { key: "rawName", label: "Raw Name" },
  { key: "normalizedName", label: "Normalized Name" },
  { key: "rawType", label: "Raw Type" },
  { key: "normalizedType", label: "Normalized Type" },
  { key: "occurrences", label: "Occurrences" },
  { key: "documentFrequency", label: "Models" },
];

function LabelPipelineTable({ rows }: { rows: VisualizationPayload["labelPipelineRows"] }) {
  const [sortKey, setSortKey] = useState<LabelPipelineSortKey>("occurrences");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [limit, setLimit] = useState(50);
  const sortedRows = useMemo(() => {
    const direction = sortDirection === "asc" ? 1 : -1;
    return [...rows].sort((left, right) => {
      const leftValue = left[sortKey];
      const rightValue = right[sortKey];
      if (typeof leftValue === "number" && typeof rightValue === "number") {
        const diff = leftValue - rightValue;
        if (diff !== 0) return diff * direction;
      } else {
        const diff = String(leftValue).localeCompare(String(rightValue));
        if (diff !== 0) return diff * direction;
      }
      return left.normalizedName.localeCompare(right.normalizedName);
    });
  }, [rows, sortDirection, sortKey]);
  const visibleRows = sortedRows.slice(0, limit);
  const onSort = (key: LabelPipelineSortKey) => {
    if (key === sortKey) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection(key === "occurrences" || key === "documentFrequency" ? "desc" : "asc");
    }
  };
  if (!rows.length) return <EmptyChart />;
  return (
    <div className="labelPipeline">
      <label className="chartLimit">
        Rows
        <input
          aria-label="Label pipeline row count"
          type="number"
          min={1}
          value={limit}
          onChange={(event) => {
            const value = Number(event.target.value);
            if (Number.isInteger(value)) setLimit(Math.max(value, 1));
          }}
        />
      </label>
      <div className="labelPipelineFrame">
        <table className="typeQualityTable labelPipelineTable">
          <thead>
            <tr>
              {labelPipelineColumns.map((column) => (
                <th key={column.key} aria-sort={sortKey === column.key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
                  <button
                    className={sortKey === column.key ? "active" : ""}
                    type="button"
                    onClick={() => onSort(column.key)}
                  >
                    {column.label}
                    {sortKey === column.key
                      ? sortDirection === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />
                      : <ArrowUpDown size={12} />}
                  </button>
                </th>
              ))}
              <th>Name Tokens</th>
              <th>Type Tokens</th>
              <th>Classification</th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={`${row.rawName}:${row.rawType}:${row.normalizedName}:${row.normalizedType}:${row.classification}:${index}`}>
                <td title={row.rawName}>{row.rawName || <span className="mutedCell">empty</span>}</td>
                <td title={row.normalizedName}><strong>{row.normalizedName || "empty"}</strong></td>
                <td title={row.rawType}>{row.rawType || <span className="mutedCell">empty</span>}</td>
                <td title={row.normalizedType}><strong>{row.normalizedType || "empty"}</strong></td>
                <td>{row.occurrences.toLocaleString()}</td>
                <td>{row.documentFrequency.toLocaleString()}</td>
                <td><TokenList tokens={row.nameTokens} /></td>
                <td><TokenList tokens={row.typeTokens} /></td>
                <td>
                  <span className={`vocabularyBadge ${classificationClassName(row.classification)}`}>
                    {classificationDisplayLabel(row.classification)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TokenList({ tokens }: { tokens: string[] }) {
  if (!tokens.length) return <span className="mutedCell">none</span>;
  return <span className="tokenList">{tokens.map((token, index) => <b key={`${token}:${index}`}>{token}</b>)}</span>;
}

function classificationClassName(classification: VisualizationPayload["labelPipelineRows"][number]["classification"]) {
  return classification === "type_like" ? "typeLike" : classification;
}

function classificationDisplayLabel(classification: VisualizationPayload["labelPipelineRows"][number]["classification"]) {
  if (classification === "type_like") return "Type-like";
  return classification.charAt(0).toUpperCase() + classification.slice(1);
}

type VocabularyFilter = "all" | "semantic" | "placeholder" | "typeLike" | "nonSemantic" | "excludeNonSemantic";
type VocabularySortKey =
  | "name"
  | "occurrences"
  | "documentFrequency"
  | "coverage"
  | "occurrencesPerModel"
  | "occurrencesPerUsedModel";

const vocabularyFilters: Array<{ key: VocabularyFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "semantic", label: "Semantic" },
  { key: "placeholder", label: "Placeholder" },
  { key: "typeLike", label: "Type-like" },
  { key: "nonSemantic", label: "Placeholder + Type-like" },
  { key: "excludeNonSemantic", label: "Exclude Placeholder / Type-like" },
];

const vocabularyColumns: Array<{ key: VocabularySortKey; label: string }> = [
  { key: "name", label: "Name" },
  { key: "occurrences", label: "Occurrences" },
  { key: "documentFrequency", label: "Models" },
  { key: "coverage", label: "Coverage" },
  { key: "occurrencesPerModel", label: "Occ/model" },
  { key: "occurrencesPerUsedModel", label: "Occ/used model" },
];

function VocabularyRanking({ rows }: { rows: VisualizationPayload["vocabularyRanking"] }) {
  const [filter, setFilter] = useState<VocabularyFilter>("all");
  const [sortKey, setSortKey] = useState<VocabularySortKey>("occurrences");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [limit, setLimit] = useState(50);
  const filteredRows = useMemo(() => rows.filter((row) => vocabularyFilterMatches(row, filter)), [filter, rows]);
  const sortedRows = useMemo(() => {
    const direction = sortDirection === "asc" ? 1 : -1;
    return [...filteredRows].sort((left, right) => {
      if (sortKey === "name") return left.name.localeCompare(right.name) * direction;
      const diff = left[sortKey] - right[sortKey];
      if (diff !== 0) return diff * direction;
      return left.name.localeCompare(right.name);
    });
  }, [filteredRows, sortDirection, sortKey]);
  const visibleRows = sortedRows.slice(0, limit);
  const maxOccurrences = Math.max(...filteredRows.map((row) => row.occurrences), 1);
  const maxDocumentFrequency = Math.max(...filteredRows.map((row) => row.documentFrequency), 1);
  const onSort = (key: VocabularySortKey) => {
    if (key === sortKey) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection(key === "name" ? "asc" : "desc");
    }
  };
  if (!rows.length) return <EmptyChart />;
  return (
    <div className="vocabularyRanking">
      <div className="vocabularyRankingToolbar">
        <div className="vocabularyFilterControl" aria-label="Vocabulary classification filter">
          {vocabularyFilters.map((item) => (
            <button
              className={filter === item.key ? "active" : ""}
              key={item.key}
              type="button"
              onClick={() => setFilter(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="chartLimit">
          Rows
          <input
            aria-label="Vocabulary ranking row count"
            type="number"
            min={1}
            value={limit}
            onChange={(event) => {
              const value = Number(event.target.value);
              if (Number.isInteger(value)) setLimit(Math.max(value, 1));
            }}
          />
        </label>
      </div>
      {!visibleRows.length ? <EmptyChart /> : (
        <div className="vocabularyTableFrame">
          <table className="typeQualityTable vocabularyTable">
            <thead>
              <tr>
                {vocabularyColumns.map((column) => (
                  <th key={column.key} aria-sort={sortKey === column.key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
                    <button
                      className={sortKey === column.key ? "active" : ""}
                      type="button"
                      onClick={() => onSort(column.key)}
                    >
                      {column.label}
                      {sortKey === column.key
                        ? sortDirection === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />
                        : <ArrowUpDown size={12} />}
                    </button>
                  </th>
                ))}
                <th>Classification</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.name}>
                  <td title={row.name}><strong>{row.name}</strong></td>
                  <td><VocabularyMetricCell value={row.occurrences} max={maxOccurrences} /></td>
                  <td><VocabularyMetricCell value={row.documentFrequency} max={maxDocumentFrequency} /></td>
                  <td>{percentage(row.coverage)}</td>
                  <td>{round(row.occurrencesPerModel)}</td>
                  <td>{round(row.occurrencesPerUsedModel)}</td>
                  <td><VocabularyClassification row={row} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function vocabularyFilterMatches(row: VisualizationPayload["vocabularyRanking"][number], filter: VocabularyFilter) {
  if (filter === "semantic") return row.classification === "semantic";
  if (filter === "placeholder") return row.placeholder > 0;
  if (filter === "typeLike") return row.typeLike > 0;
  if (filter === "nonSemantic") return row.placeholder > 0 || row.typeLike > 0;
  if (filter === "excludeNonSemantic") return row.placeholder === 0 && row.typeLike === 0;
  return true;
}

function VocabularyMetricCell({ value, max }: { value: number; max: number }) {
  return (
    <div className="vocabularyMetricCell">
      <span>{round(value).toLocaleString()}</span>
      <i><b style={{ width: `${value / Math.max(max, 1) * 100}%` }} /></i>
    </div>
  );
}

function VocabularyClassification({ row }: { row: VisualizationPayload["vocabularyRanking"][number] }) {
  const label = vocabularyClassificationLabel(row.classification);
  return (
    <span
      className={`vocabularyBadge ${row.classification}`}
      title={`Semantic ${row.semantic.toLocaleString()}, placeholder ${row.placeholder.toLocaleString()}, type-like ${row.typeLike.toLocaleString()}`}
    >
      {label}
    </span>
  );
}

function vocabularyClassificationLabel(classification: VisualizationPayload["vocabularyRanking"][number]["classification"]) {
  if (classification === "typeLike") return "Type-like";
  if (classification === "semantic") return "Semantic";
  if (classification === "placeholder") return "Placeholder";
  if (classification === "mixed") return "Mixed";
  return "Unknown";
}

const qualitySegments = [
  { key: "semantic", label: "Semantic", className: "semantic" },
  { key: "missing", label: "Missing", className: "missing" },
  { key: "placeholder", label: "Placeholder", className: "placeholder" },
  { key: "typeLike", label: "Type-like", className: "typeLike" },
] as const;

function NameClassificationOverview({ items }: { items: Array<StatisticItem & { key?: string }> }) {
  const total = items.reduce((sum, item) => sum + item.count, 0);
  const segmentItems = qualitySegments.map((segment) => {
    const item = items.find((entry) => entry.key === segment.key || entry.label.toLowerCase() === segment.label.toLowerCase());
    return { ...segment, count: item?.count || 0 };
  });
  if (!total) return <EmptyChart />;
  return (
    <div className="qualityOverview">
      <StackedMeter
        segments={segmentItems.map((item) => ({
          label: item.label,
          value: item.count,
          className: item.className,
        }))}
      />
      <div className="qualityStatGrid">
        {segmentItems.map((item) => (
          <div className="qualityStat" key={item.key}>
            <span>{item.label}</span>
            <strong>{item.count.toLocaleString()}</strong>
            <small>{percentage(item.count / total)}</small>
          </div>
        ))}
      </div>
    </div>
  );
}

type TypeQualityCountKey = "semantic" | "missing" | "placeholder" | "typeLike";
type TypeQualitySortKey =
  | "type"
  | "total"
  | TypeQualityCountKey
  | `${TypeQualityCountKey}Rate`;
type SortDirection = "asc" | "desc";

const typeQualityColumns: Array<{ key: TypeQualitySortKey; label: string }> = [
  { key: "type", label: "Normalized Type" },
  { key: "total", label: "Total Slots" },
  { key: "semantic", label: "Semantic Count" },
  { key: "semanticRate", label: "Semantic %" },
  { key: "missing", label: "Missing Count" },
  { key: "missingRate", label: "Missing %" },
  { key: "placeholder", label: "Placeholder Count" },
  { key: "placeholderRate", label: "Placeholder %" },
  { key: "typeLike", label: "Type-like Count" },
  { key: "typeLikeRate", label: "Type-like %" },
];

function TypeQualityTable({ rows }: { rows: VisualizationPayload["elementTypeQualityMatrix"] }) {
  const [sortKey, setSortKey] = useState<TypeQualitySortKey>("semantic");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const sortedRows = useMemo(() => {
    const direction = sortDirection === "asc" ? 1 : -1;
    return [...rows].sort((left, right) => {
      if (sortKey === "type") return left.type.localeCompare(right.type) * direction;
      const diff = typeQualitySortValue(left, sortKey) - typeQualitySortValue(right, sortKey);
      if (diff !== 0) return diff * direction;
      return left.type.localeCompare(right.type);
    });
  }, [rows, sortDirection, sortKey]);
  const onSort = (key: TypeQualitySortKey) => {
    if (key === sortKey) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection(key === "type" ? "asc" : "desc");
    }
  };
  if (!rows.length) return <EmptyChart />;
  return (
    <div className="typeQualityTableFrame">
      <table className="typeQualityTable">
        <thead>
          <tr>
            {typeQualityColumns.map((column) => (
              <th key={column.key} aria-sort={sortKey === column.key ? (sortDirection === "asc" ? "ascending" : "descending") : "none"}>
                <button
                  className={sortKey === column.key ? "active" : ""}
                  type="button"
                  onClick={() => onSort(column.key)}
                >
                  {column.label}
                  {sortKey === column.key
                    ? sortDirection === "asc" ? <ArrowUp size={12} /> : <ArrowDown size={12} />
                    : <ArrowUpDown size={12} />}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row) => (
            <tr key={row.type}>
              <td title={row.type}><strong>{row.type}</strong></td>
              <td>{row.total.toLocaleString()}</td>
              <td>{row.semantic.toLocaleString()}</td>
              <QualityRateCell value={row.semantic} total={row.total} kind="semantic" />
              <td>{row.missing.toLocaleString()}</td>
              <QualityRateCell value={row.missing} total={row.total} kind="missing" />
              <td>{row.placeholder.toLocaleString()}</td>
              <QualityRateCell value={row.placeholder} total={row.total} kind="placeholder" />
              <td>{row.typeLike.toLocaleString()}</td>
              <QualityRateCell value={row.typeLike} total={row.total} kind="typeLike" />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function typeQualitySortValue(row: VisualizationPayload["elementTypeQualityMatrix"][number], key: TypeQualitySortKey) {
  if (key === "total") return row.total;
  if (key === "type") return 0;
  if (key === "semanticRate") return row.semantic / Math.max(row.total, 1);
  if (key === "missingRate") return row.missing / Math.max(row.total, 1);
  if (key === "placeholderRate") return row.placeholder / Math.max(row.total, 1);
  if (key === "typeLikeRate") return row.typeLike / Math.max(row.total, 1);
  return row[key];
}

function QualityRateCell({
  value,
  total,
  kind,
}: {
  value: number;
  total: number;
  kind: "semantic" | "missing" | "placeholder" | "typeLike";
}) {
  const rate = value / Math.max(total, 1);
  return (
    <td>
      <div className="qualityRateCell">
        <span>{percentage(rate)}</span>
        <i><b className={`qualitySegment ${kind}`} style={{ width: `${value / Math.max(total, 1) * 100}%` }} /></i>
      </div>
    </td>
  );
}

function StackedMeter({ segments }: { segments: Array<{ label: string; value: number; className: string }> }) {
  const total = segments.reduce((sum, segment) => sum + segment.value, 0);
  if (!total) return <div className="stackedMeter empty" />;
  return (
    <div className="stackedMeter">
      {segments.filter((segment) => segment.value > 0).map((segment) => (
        <span
          className={`qualitySegment ${segment.className}`}
          key={segment.label}
          style={{ width: `${segment.value / total * 100}%` }}
          title={`${segment.label}: ${segment.value.toLocaleString()} (${percentage(segment.value / total)})`}
        />
      ))}
    </div>
  );
}

function RatioQualityChart({
  bins,
  summary,
  label = "Missing-name ratio",
}: {
  bins: HistogramBin[];
  summary?: VisualizationPayload["missingNameRatioSummary"];
  label?: string;
}) {
  return (
    <div className="ratioQualityChart">
      {summary && (
        <div className="qualityStatGrid compact">
          <SummaryStat label="0%" value={summary.zero} suffix="models" />
          <SummaryStat label="Median" value={percentage(summary.median)} />
          <SummaryStat label="P90" value={percentage(summary.p90)} />
          <SummaryStat label=">= 70%" value={summary.above70} suffix="models" />
        </div>
      )}
      <RatioHistogram bins={bins} label={label} />
    </div>
  );
}

function SummaryStat({ label, value, suffix }: { label: string; value: string | number; suffix?: string }) {
  return <div className="qualityStat"><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>{suffix && <small>{suffix}</small>}</div>;
}

function LabeledHistogram({ items }: { items: StatisticItem[] }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  const total = items.reduce((sum, item) => sum + item.count, 0);
  if (!items.length) return <EmptyChart />;
  return (
    <div className="labeledHistogram">
      {items.map((item) => (
        <div className="labeledHistogramBar" key={item.label}>
          <span>{item.label}</span>
          <i title={`${item.label}: ${item.count.toLocaleString()} model(s)`}><b style={{ width: `${item.count / max * 100}%` }} /></i>
          <strong>{item.count.toLocaleString()}</strong>
          <small>{percentage(item.count / Math.max(total, 1))}</small>
        </div>
      ))}
    </div>
  );
}

function ModelQualityWatchlists({
  watchlists,
  onInspectModel,
}: {
  watchlists?: VisualizationPayload["modelQualityWatchlists"];
  onInspectModel: (modelId: string) => void;
}) {
  if (!watchlists) return <EmptyChart />;
  return (
    <div className="modelWatchlists">
      <ModelWatchlist
        title="Few Semantic Names"
        rows={watchlists.fewSemanticNames}
        metric={(row) => `${row.semanticNames}/${row.nameSlots} semantic`}
        onInspectModel={onInspectModel}
      />
      <ModelWatchlist
        title="Highest Missing Ratio"
        rows={watchlists.highMissingRatio}
        metric={(row) => `${percentage(row.missingRatio)} missing`}
        onInspectModel={onInspectModel}
      />
      <ModelWatchlist
        title="Highest Name Repetition"
        rows={watchlists.highNameDominance}
        metric={(row) => row.dominantName ? `${percentage(row.dominantNameRatio)} "${row.dominantName}"` : "No dominant name"}
        onInspectModel={onInspectModel}
      />
    </div>
  );
}

function ModelWatchlist({
  title,
  rows,
  metric,
  onInspectModel,
}: {
  title: string;
  rows: VisualizationPayload["modelQualityWatchlists"]["fewSemanticNames"];
  metric: (row: VisualizationPayload["modelQualityWatchlists"]["fewSemanticNames"][number]) => string;
  onInspectModel: (modelId: string) => void;
}) {
  return (
    <section className="modelWatchlist">
      <h5>{title}</h5>
      {!rows.length ? <p className="visualizationNote">No matching models.</p> : rows.map((row) => (
        <div className="modelWatchlistRow" key={`${title}:${row.id}`}>
          <strong title={row.id}>{row.id}</strong>
          <span>{metric(row)}</span>
          <button
            type="button"
            className="tableInfoButton modelWatchlistInspectButton"
            aria-label={`Inspect ${row.id}`}
            title={`Inspect ${row.id}`}
            onClick={() => onInspectModel(row.id)}
          >
            <Info size={15} />
          </button>
        </div>
      ))}
    </section>
  );
}

function Histogram({ bins, useDisplayCount = false, ratioAxis = false }: { bins: HistogramBin[]; useDisplayCount?: boolean; ratioAxis?: boolean }) {
  const max = Math.max(...bins.map((bin) => useDisplayCount ? bin.displayCount : bin.count), 1);
  if (!bins.length) return <EmptyChart />;
  if (ratioAxis) return <RatioHistogram bins={bins} />;
  return <div className="histogramFrame">
    <div className="histogram">{bins.map((bin) => {
      const value = useDisplayCount ? bin.displayCount : bin.count;
      return <span key={`${bin.start}:${bin.end}`} style={{ height: `${value / max * 100}%` }} title={`${bin.start} to ${bin.end}: ${bin.count} model(s)`} />;
    })}</div>
  </div>;
}

function RatioHistogram({ bins, label = "Missing-name ratio" }: { bins: HistogramBin[]; label?: string }) {
  if (!bins.length) return <EmptyChart />;
  const width = 760, height = 280;
  const margin = { top: 24, right: 12, bottom: 52, left: 58 };
  const plotWidth = width - margin.left - margin.right, plotHeight = height - margin.top - margin.bottom;
  const max = Math.max(...bins.map((bin) => bin.count), 1);
  const barWidth = plotWidth / bins.length;
  const yTicks = Array.from(new Set(Array.from({ length: 5 }, (_, index) => Math.round(max * index / 4))));
  const xTickIndexes = Array.from(new Set(Array.from({ length: 7 }, (_, index) => Math.round(bins.length * index / 6))));
  return <div className="ratioHistogram">
    <svg className="ratioHistogramPlot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Missing-name ratio distribution with model counts by ratio range">
      {yTicks.map((tick) => {
        const y = margin.top + plotHeight - tick / max * plotHeight;
        return <g key={`y:${tick}`}><line className="histogramGridLine" x1={margin.left} x2={width - margin.right} y1={y} y2={y} /><text className="histogramTick" x={margin.left - 8} y={y + 4} textAnchor="end">{tick}</text></g>;
      })}
      {bins.map((bin, index) => {
        const barHeight = bin.count / max * plotHeight;
        const x = margin.left + index * barWidth + 1;
        const y = margin.top + plotHeight - barHeight;
        return <g key={`${bin.start}:${bin.end}`}>
          <rect className="ratioHistogramBar" x={x} y={y} width={Math.max(barWidth - 2, 1)} height={barHeight}>
            <title>{`${percentage(bin.start)} to ${percentage(bin.end)}: ${bin.count} model(s)`}</title>
          </rect>
          {bin.count > 0 && <text className="histogramBarValue" x={x + Math.max(barWidth - 2, 1) / 2} y={Math.max(y - 5, 12)} textAnchor="middle">{bin.count}</text>}
        </g>;
      })}
      {xTickIndexes.map((index) => {
        const value = index === bins.length ? bins[bins.length - 1].end : bins[index].start;
        const x = margin.left + index * barWidth;
        return <g key={`x:${index}`}><line className="histogramTickLine" x1={x} x2={x} y1={margin.top + plotHeight} y2={margin.top + plotHeight + 5} /><text className="histogramTick" x={x} y={height - 28} textAnchor="middle">{percentage(value)}</text></g>;
      })}
      <text className="histogramAxisLabel" x={margin.left + plotWidth / 2} y={height - 4} textAnchor="middle">{label}</text>
      <text className="histogramAxisLabel" transform={`translate(14 ${margin.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Number of models</text>
    </svg>
  </div>;
}

function percentage(value: number) {
  return `${round(value * 100)}%`;
}

function Treemap({ items }: { items: StatisticItem[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0) || 1;
  if (!items.length) return <EmptyChart />;
  return <div className="treemap">{items.map((item) => <span key={item.label} style={{ flexGrow: item.count, flexBasis: `${item.count / total * 100}%` }} title={`${item.label}: ${item.count}`}><b>{item.label}</b><small>{item.count}</small></span>)}</div>;
}

function ConceptTreemap({ links }: { links: VisualizationPayload["typeConceptLinks"] }) {
  const groups = Object.entries(links.reduce<Record<string, typeof links>>((result, link) => {
    (result[link.type] ||= []).push(link);
    return result;
  }, {}));
  if (!groups.length) return <EmptyChart />;
  return <div className="conceptTreemap">{groups.map(([type, entries]) => <section key={type}><b>{type}</b><div>{(entries || []).map((entry) => <span style={{ flexGrow: entry.count }} title={`${entry.type} → ${entry.concept}: ${entry.count}`} key={`${entry.type}:${entry.concept}`}>{entry.concept}</span>)}</div></section>)}</div>;
}

function Heatmap({ data }: { data: VisualizationPayload["vocabularyHeatmap"] }) {
  const [tokenLimit, setTokenLimit] = useState(Math.min(18, data.tokens.length));
  const [typeLimit, setTypeLimit] = useState(Math.min(10, data.rows.length));
  if (!data.tokens.length || !data.rows.length) return <EmptyChart />;
  const tokens = data.tokens.slice(0, tokenLimit);
  const rows = data.rows.slice(0, typeLimit);
  const max = Math.max(...rows.flatMap((row) => row.values.slice(0, tokenLimit)), 0.01);
  return (
    <div className="heatmapPanel">
      <div className="heatmapToolbar">
        <label className="chartLimit">
          Tokens
          <input
            aria-label="Vocabulary heatmap token count"
            type="number"
            min={1}
            max={data.tokens.length}
            value={tokenLimit}
            onChange={(event) => {
              const value = Number(event.target.value);
              if (Number.isInteger(value)) setTokenLimit(Math.min(Math.max(value, 1), data.tokens.length));
            }}
          />
        </label>
        <label className="chartLimit">
          Types
          <input
            aria-label="Vocabulary heatmap type count"
            type="number"
            min={1}
            max={data.rows.length}
            value={typeLimit}
            onChange={(event) => {
              const value = Number(event.target.value);
              if (Number.isInteger(value)) setTypeLimit(Math.min(Math.max(value, 1), data.rows.length));
            }}
          />
        </label>
        <div className="heatmapLegend" aria-label="Heatmap color legend">
          <span>Low</span>
          <i />
          <span>High</span>
        </div>
      </div>
      <div className="heatmap" style={{ gridTemplateColumns: `150px repeat(${tokens.length}, minmax(42px, 1fr))` }}>
        <b />
        {tokens.map((token) => <span className="heatmapToken" key={token} title={token}>{token}</span>)}
        {rows.map((row) => (
          <div className="heatmapRow" style={{ display: "contents" }} key={row.label}>
            <b title={row.label}>{row.label}</b>
            {tokens.map((token, index) => {
              const value = row.values[index] || 0;
              return (
                <span
                  className="heatmapCell"
                  key={`${row.label}:${token}`}
                  style={{ backgroundColor: heatmapColor(value / max) }}
                  title={`${row.label} / ${token}: ${round(value * 100)}% relative frequency`}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function heatmapColor(intensity: number) {
  const value = Math.max(0, Math.min(1, intensity));
  const lightness = 96 - value * 42;
  const saturation = 26 + value * 24;
  return `hsl(176  ${saturation}% ${lightness}%)`;
}

function TypeConceptLinks({ links }: { links: VisualizationPayload["typeConceptLinks"] }) {
  const max = Math.max(...links.map((link) => link.count), 1);
  if (!links.length) return <EmptyChart />;
  return <div className="typeConceptLinks">{links.map((link) => <div key={`${link.type}:${link.concept}`} title={`${link.type} → ${link.concept}: ${link.count}`}><b>{link.type}</b><i><span style={{ width: `${link.count / max * 100}%` }} /></i><strong>{link.concept}</strong><small>{link.count}</small></div>)}</div>;
}

function Scatter({ points }: { points: VisualizationPayload["modelVocabularyScatter"] }) {
  return <SvgScatter points={points.map((point) => ({ ...point, x: point.namedElements, y: point.uniqueNames, label: point.id, value: point.missingNameRatio, size: point.tokens }))} xLabel="Named elements" yLabel="Unique concepts" />;
}

function TopicScatter({ points }: { points: NonNullable<VisualizationPayload["topicModel"]["points"]> }) {
  return <SvgScatter points={points.map((point) => ({ ...point, label: `${point.id} | ${point.topic}`, value: point.topicStrength, size: point.namedElements }))} xLabel="Component 1" yLabel="Component 2" />;
}

function SvgScatter({ points, xLabel, yLabel }: { points: Array<{ x: number; y: number; label: string; value: number; size: number }>; xLabel: string; yLabel: string }) {
  if (!points.length) return <EmptyChart />;
  const xValues = points.map((point) => point.x), yValues = points.map((point) => point.y);
  const minX = Math.min(...xValues), maxX = Math.max(...xValues), minY = Math.min(...yValues), maxY = Math.max(...yValues);
  const scale = (value: number, min: number, max: number, start: number, end: number) => start + (value - min) / (max - min || 1) * (end - start);
  return <svg className="scatter" viewBox="0 0 640 300" role="img" aria-label={`${xLabel} versus ${yLabel}`}><text x="320" y="294">{xLabel}</text><text transform="translate(14 160) rotate(-90)">{yLabel}</text>{points.map((point, index) => <circle key={`${point.label}:${index}`} cx={scale(point.x, minX, maxX, 42, 625)} cy={scale(point.y, minY, maxY, 270, 15)} r={Math.min(4 + Math.sqrt(point.size || 1), 14)} fill={`rgba(15, 118, 110, ${Math.max(.25, Math.min(.95, point.value + .2))})`}><title>{`${point.label}: ${xLabel} ${round(point.x)}, ${yLabel} ${round(point.y)}`}</title></circle>)}</svg>;
}

function Boxplot({ summary }: { summary: VisualizationPayload["nameCountBoxplot"] }) {
  const max = summary.max || 1;
  const left = (summary.q1 / max) * 100, width = ((summary.q3 - summary.q1) / max) * 100;
  return <div className="boxplot" title={`min ${summary.min}, Q1 ${round(summary.q1)}, median ${round(summary.median)}, Q3 ${round(summary.q3)}, max ${summary.max}`}><i /><span style={{ left: `${left}%`, width: `${width}%` }} /><b style={{ left: `${summary.median / max * 100}%` }} /><small>min {summary.min}</small><small>median {round(summary.median)}</small><small>max {summary.max}</small></div>;
}

function EmptyChart() { return <p className="visualizationNote">No matching values in this dataset.</p>; }
