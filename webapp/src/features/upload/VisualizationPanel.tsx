import { hierarchy, treemap, treemapSquarify, type HierarchyRectangularNode } from "d3-hierarchy";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Cloud, Expand, Grid2X2, Info, ListTree, Network, Plus, Search, Table } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { errorMessage, getLabelPipelineRows } from "@/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { HistogramBin, StatisticItem, VisualizationPayload } from "../../types";
import { round } from "../../utils";

type VisualizationSnapshot = "before" | "after";

export function VisualizationPanel({
  datasetId,
  beforeData,
  afterData,
  beforeModelCount,
  afterModelCount,
  onInspectModel,
}: {
  datasetId: string;
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
  const categories = useMemo(
    () => data ? visualizationCategories(data, onInspectModel, datasetId, snapshot) : [],
    [data, datasetId, onInspectModel, snapshot],
  );
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

type VisualizationCategoryId = "quality" | "labels";
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
  datasetId: string,
  snapshot: VisualizationSnapshot,
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
          description: "Semantic, missing, and placeholder names grouped by normalized node type.",
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
          description: "Models at risk for low semantic naming, high missingness, high placeholder naming, and repeated names.",
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
          render: () => <LabelPipelineTable datasetId={datasetId} snapshot={snapshot} />,
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
          id: "type-vocabulary-table",
          title: "Type-Specific Vocabulary",
          description: "Top normalized names within each normalized node type in the corpus.",
          render: () => <TypeVocabularyTable rows={data.typeVocabularyTable || []} />,
        },
        {
          id: "name-reuse-distribution",
          title: "Normalized Name Reuse Distribution",
          description: "How many distinct normalized names appear in one model versus many models.",
          render: () => <NameReuseDistributionChart items={data.nameReuseDistribution || []} />,
        },
        {
          id: "element-type-treemap",
          title: "Normalized Node Types in the Corpus",
          description: "Treemap area is proportional to normalized node type count.",
          render: () => <Treemap items={data.elementTypeTreemap} />,
        },
        {
          id: "model-vocabulary-scatter",
          title: "Model Size vs Vocabulary Richness",
          description: "Compare graph size against per-model name vocabulary metrics; color follows missing-name ratio.",
          render: () => <Scatter points={data.modelVocabularyScatter} />,
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

function VocabularySummary({ summary }: { summary?: VisualizationPayload["vocabularySummary"] }) {
  if (!summary) return <EmptyChart />;
  return (
    <div className="vocabularySummary">
      <SummaryStat label="Unique Names" value={summary.uniqueNames} />
      <SummaryStat label="Occurrences" value={summary.totalOccurrences} />
      <SummaryStat label="Semantic Names" value={summary.semanticNames} />
      <SummaryStat label="Placeholder Names" value={summary.placeholderNames} />
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
type LabelPipelineClassificationFilter = "all" | "semantic" | "placeholder" | "missing";

const labelPipelineColumns: Array<{ key: LabelPipelineSortKey; label: string }> = [
  { key: "rawName", label: "Raw Name" },
  { key: "normalizedName", label: "Normalized Name" },
  { key: "rawType", label: "Raw Type" },
  { key: "normalizedType", label: "Normalized Type" },
  { key: "occurrences", label: "Occurrences" },
  { key: "documentFrequency", label: "Models" },
];

const labelPipelineClassificationFilters: Array<{ key: LabelPipelineClassificationFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "semantic", label: "Semantic" },
  { key: "placeholder", label: "Placeholder" },
  { key: "missing", label: "Missing" },
];

const labelPipelinePageSizes = [25, 50, 100, 250];

function LabelPipelineTable({ datasetId, snapshot }: { datasetId: string; snapshot: VisualizationSnapshot }) {
  const [sortKey, setSortKey] = useState<LabelPipelineSortKey>("documentFrequency");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");
  const [query, setQuery] = useState("");
  const [classification, setClassification] = useState<LabelPipelineClassificationFilter>("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [payload, setPayload] = useState<Awaited<ReturnType<typeof getLabelPipelineRows>> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setPage(1);
  }, [classification, datasetId, pageSize, query, snapshot]);

  useEffect(() => {
    if (!datasetId) return;
    let cancelled = false;
    const timeout = window.setTimeout(() => {
      setLoading(true);
      setError("");
      getLabelPipelineRows(datasetId, {
        snapshot,
        page,
        pageSize,
        query,
        classification,
        sort: sortKey,
        order: sortDirection,
      })
        .then((nextPayload) => {
          if (!cancelled) setPayload(nextPayload);
        })
        .catch((err) => {
          if (!cancelled) setError(errorMessage(err, "Label rows could not be loaded."));
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
    };
  }, [classification, datasetId, page, pageSize, query, snapshot, sortDirection, sortKey]);

  const visibleRows = payload?.rows || [];
  const total = payload?.total || 0;
  const totalPages = payload?.totalPages || 0;
  const firstRow = total ? ((payload?.page || page) - 1) * (payload?.pageSize || pageSize) + 1 : 0;
  const lastRow = total ? firstRow + visibleRows.length - 1 : 0;

  const onSort = (key: LabelPipelineSortKey) => {
    if (key === sortKey) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection(key === "occurrences" || key === "documentFrequency" ? "desc" : "asc");
    }
    setPage(1);
  };
  if (!datasetId) return <EmptyChart />;
  return (
    <div className="labelPipeline">
      <div className="labelPipelineToolbar">
        <label className="labelPipelineSearch">
          <Search size={15} />
          <input
            aria-label="Search label rows"
            placeholder="Search labels, types, tokens"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <select
          aria-label="Filter by classification"
          value={classification}
          onChange={(event) => setClassification(event.target.value as LabelPipelineClassificationFilter)}
        >
          {labelPipelineClassificationFilters.map((filter) => (
            <option key={filter.key} value={filter.key}>{filter.label}</option>
          ))}
        </select>
        <label className="chartLimit">
          Page size
          <select
            aria-label="Label pipeline page size"
            value={pageSize}
            onChange={(event) => setPageSize(Number(event.target.value))}
          >
            {labelPipelinePageSizes.map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </label>
      </div>
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
            {visibleRows.map((row) => (
              <tr key={`${row.rawName}:${row.rawType}:${row.normalizedName}:${row.normalizedType}:${row.classification}`}>
                <td title={row.rawName}>{row.rawName || <span className="mutedCell">empty</span>}</td>
                <td title={row.normalizedName}><strong>{row.normalizedName || "empty"}</strong></td>
                <td title={row.rawType}>{row.rawType || <span className="mutedCell">empty</span>}</td>
                <td title={row.normalizedType}><strong>{row.normalizedType || "empty"}</strong></td>
                <td>{row.occurrences.toLocaleString()}</td>
                <td>{row.documentFrequency.toLocaleString()}</td>
                <td><TokenList tokens={row.nameTokens} /></td>
                <td><TokenList tokens={row.typeTokens} /></td>
                <td>
                  <span className={`vocabularyBadge ${row.classification}`}>
                    {classificationDisplayLabel(row.classification)}
                  </span>
                </td>
              </tr>
            ))}
            {!visibleRows.length && !loading && (
              <tr>
                <td colSpan={9}><span className="mutedCell">{error || "No label rows found."}</span></td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="labelPipelineFooter">
        <span>{loading ? "Loading..." : `${firstRow.toLocaleString()}-${lastRow.toLocaleString()} of ${total.toLocaleString()}`}</span>
        <div className="labelPipelinePager">
          <Button
            aria-label="Previous label rows page"
            title="Previous page"
            type="button"
            variant="secondary"
            size="sm"
            disabled={loading || page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
          >
            <ChevronLeft size={16} />
          </Button>
          <span>{totalPages ? `${payload?.page || page} / ${totalPages}` : "0 / 0"}</span>
          <Button
            aria-label="Next label rows page"
            title="Next page"
            type="button"
            variant="secondary"
            size="sm"
            disabled={loading || !totalPages || page >= totalPages}
            onClick={() => setPage((current) => current + 1)}
          >
            <ChevronRight size={16} />
          </Button>
        </div>
      </div>
    </div>
  );
}

function TokenList({ tokens }: { tokens: string[] }) {
  if (!tokens.length) return <span className="mutedCell">none</span>;
  return <span className="tokenList">{tokens.map((token, index) => <b key={`${token}:${index}`}>{token}</b>)}</span>;
}

function classificationDisplayLabel(classification: VisualizationPayload["labelPipelineRows"][number]["classification"]) {
  return classification.charAt(0).toUpperCase() + classification.slice(1);
}

type VocabularyFilter = "all" | "semantic" | "placeholder" | "mixed";
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
  { key: "mixed", label: "Mixed" },
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

type TypeVocabularyView = "table" | "cloud";

function TypeVocabularyTable({ rows }: { rows: VisualizationPayload["typeVocabularyTable"] }) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<TypeVocabularyView>("table");
  const normalizedQuery = query.trim().toLowerCase();
  const visibleRows = useMemo(
    () => (normalizedQuery
      ? rows.filter((row) => row.type.toLowerCase().includes(normalizedQuery))
      : rows),
    [normalizedQuery, rows],
  );
  if (!rows.length) return <EmptyChart />;
  return (
    <div className="typeVocabularyPanel">
      <div className="typeVocabularyToolbar">
        <label className="typeVocabularySearch">
          <Search size={14} aria-hidden="true" />
          <input
            aria-label="Filter normalized types"
            placeholder="Filter types"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <div className="typeVocabularyToolbarActions">
          <div className="typeVocabularyViewControl" aria-label="Type vocabulary view">
            <button
              className={view === "table" ? "active" : ""}
              type="button"
              title="Table view"
              onClick={() => setView("table")}
            >
              <Table size={14} aria-hidden="true" />
              Table
            </button>
            <button
              className={view === "cloud" ? "active" : ""}
              type="button"
              title="Tag cloud view"
              onClick={() => setView("cloud")}
            >
              <Cloud size={14} aria-hidden="true" />
              Cloud
            </button>
          </div>
          <span className="typeVocabularyStatus">
            {visibleRows.length.toLocaleString()} of {rows.length.toLocaleString()} types
          </span>
        </div>
      </div>
      {!visibleRows.length ? <EmptyChart /> : view === "table" ? (
        <div className="typeVocabularyFrame">
          <table className="typeQualityTable typeVocabularyTable">
            <thead>
              <tr>
                <th>Normalized Type</th>
                <th>Named Occurrences</th>
                <th>Top Normalized Names</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <tr key={row.type}>
                  <td title={row.type}><strong>{row.type}</strong></td>
                  <td>
                    {row.namedOccurrences.toLocaleString()}
                    {row.totalOccurrences !== row.namedOccurrences && (
                      <small className="typeVocabularySubtle">
                        {row.totalOccurrences.toLocaleString()} slots
                      </small>
                    )}
                  </td>
                  <td>
                    {row.names.length ? (
                      <div className="typeVocabularyNames">
                        {row.names.map((name) => (
                          <TypeVocabularyNameTag key={`${row.type}:${name.name}`} row={row} name={name} />
                        ))}
                      </div>
                    ) : (
                      <span className="typeVocabularyEmpty">No named vocabulary</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <TypeVocabularyCloud rows={visibleRows} />
      )}
    </div>
  );
}

function TypeVocabularyNameTag({
  row,
  name,
  size = "default",
}: {
  row: VisualizationPayload["typeVocabularyTable"][number];
  name: VisualizationPayload["typeVocabularyTable"][number]["names"][number];
  size?: "default" | "cloud";
}) {
  return (
    <span
      className={`typeVocabularyName ${name.classification}${size === "cloud" ? " cloud" : ""}`}
      style={size === "cloud" ? typeVocabularyCloudTagStyle(name) : undefined}
      title={typeVocabularyNameTitle(row.type, name)}
    >
      <strong>{name.name}</strong>
      <small>{name.occurrences.toLocaleString()} · {percentage(name.share)}</small>
      <i>{vocabularyClassificationLabel(name.classification)}</i>
    </span>
  );
}

function typeVocabularyNameTitle(
  type: string,
  name: VisualizationPayload["typeVocabularyTable"][number]["names"][number],
) {
  return `${name.name}: ${name.occurrences.toLocaleString()} occurrences, ${percentage(name.share)} within ${type}, ${vocabularyClassificationLabel(name.classification)}`;
}

function typeVocabularyCloudTagStyle(
  name: VisualizationPayload["typeVocabularyTable"][number]["names"][number],
) {
  const scale = Math.max(0.72, Math.min(1.35, 0.72 + name.share * 1.8));
  return {
    flexGrow: Math.max(name.occurrences, 1),
    fontSize: `${round(11 * scale)}px`,
    minWidth: `${Math.round(108 * scale)}px`,
  };
}

function TypeVocabularyCloud({ rows }: { rows: VisualizationPayload["typeVocabularyTable"] }) {
  return (
    <div className="typeVocabularyCloud">
      {rows.map((row) => (
        <section className="typeVocabularyCloudGroup" key={row.type}>
          <header className="typeVocabularyCloudHeader">
            <strong title={row.type}>{row.type}</strong>
            <span>
              {row.namedOccurrences.toLocaleString()} named
              {row.totalOccurrences !== row.namedOccurrences && (
                <> · {row.totalOccurrences.toLocaleString()} slots</>
              )}
            </span>
          </header>
          {row.names.length ? (
            <div className="typeVocabularyCloudTags">
              {row.names.map((name) => (
                <TypeVocabularyNameTag key={`${row.type}:${name.name}`} row={row} name={name} size="cloud" />
              ))}
            </div>
          ) : (
            <p className="typeVocabularyEmpty">No named vocabulary</p>
          )}
        </section>
      ))}
    </div>
  );
}

function vocabularyFilterMatches(row: VisualizationPayload["vocabularyRanking"][number], filter: VocabularyFilter) {
  if (filter === "semantic") return row.classification === "semantic";
  if (filter === "placeholder") return row.classification === "placeholder";
  if (filter === "mixed") return row.classification === "mixed";
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
      title={`Semantic ${row.semantic.toLocaleString()}, placeholder ${row.placeholder.toLocaleString()}`}
    >
      {label}
    </span>
  );
}

function vocabularyClassificationLabel(classification: VisualizationPayload["vocabularyRanking"][number]["classification"]) {
  if (classification === "semantic") return "Semantic";
  if (classification === "placeholder") return "Placeholder";
  if (classification === "mixed") return "Mixed";
  return "Unknown";
}

const qualitySegments = [
  { key: "semantic", label: "Semantic", className: "semantic" },
  { key: "missing", label: "Missing", className: "missing" },
  { key: "placeholder", label: "Placeholder", className: "placeholder" },
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

type TypeQualityCountKey = "semantic" | "missing" | "placeholder";
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
  return row[key];
}

function QualityRateCell({
  value,
  total,
  kind,
}: {
  value: number;
  total: number;
  kind: "semantic" | "missing" | "placeholder";
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

function NameReuseDistributionChart({ items }: { items: StatisticItem[] }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  const total = items.reduce((sum, item) => sum + item.count, 0);
  const singletonCount = items.find((item) => item.label === "1")?.count ?? 0;
  if (!items.length) return <EmptyChart />;
  return (
    <div
      className="nameReuseChart"
      role="img"
      aria-label="Normalized name reuse distribution grouped by model coverage per distinct name"
    >
      <p className="nameReuseChartExplainer">
        Distinct normalized names grouped by how many models each name appears in.
        Bar length compares bucket sizes, not share of the vocabulary.
        {singletonCount > 0 && (
          <>
            {" "}
            <strong>{percentage(singletonCount / Math.max(total, 1))}</strong> appear in only one model.
          </>
        )}
      </p>
      <div className="labeledHistogramHeader nameReuseChartHeader" aria-hidden="true">
        <span>Models per name</span>
        <span />
        <span>Names</span>
        <span>Share</span>
      </div>
      <div className="labeledHistogram nameReuseChartHistogram">
        {items.map((item) => {
          const share = percentage(item.count / Math.max(total, 1));
          return (
            <div className="labeledHistogramBar nameReuseChartBar" key={item.label}>
              <span>{item.label}</span>
              <i title={`${item.label} models per name: ${item.count.toLocaleString()} names (${share} of vocabulary)`}>
                <b style={{ width: `${item.count / max * 100}%` }} />
              </i>
              <strong>{item.count.toLocaleString()}</strong>
              <small>{share}</small>
            </div>
          );
        })}
      </div>
    </div>
  );
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
        title="Highest Placeholder Among Named"
        rows={watchlists.highPlaceholderRatio || []}
        metric={(row) => `${percentage(row.placeholderRatio)} placeholder`}
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

interface TreemapDatum {
  name?: string;
  value?: number;
  children?: TreemapDatum[];
}

function Treemap({ items }: { items: StatisticItem[] }) {
  const width = 760;
  const height = 320;
  const leaves = useMemo(() => {
    if (!items.length) return [];
    const root = hierarchy<TreemapDatum>({
      children: items.map((item) => ({ name: item.label, value: item.count })),
    })
      .sum((datum) => datum.value ?? 0)
      .sort((left, right) => (right.value ?? 0) - (left.value ?? 0));
    treemap<TreemapDatum>()
      .tile(treemapSquarify)
      .size([width, height])
      .paddingInner(3)
      .round(true)(root);
    return (root.leaves() as HierarchyRectangularNode<TreemapDatum>[]).map((node) => ({
      label: node.data.name ?? "",
      count: node.value ?? 0,
      x0: node.x0,
      y0: node.y0,
      x1: node.x1,
      y1: node.y1,
    }));
  }, [items]);
  if (!items.length) return <EmptyChart />;
  return (
    <svg
      className="treemapPlot"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="Normalized node types treemap"
    >
      {leaves.map((leaf) => {
        const rectWidth = Math.max(leaf.x1 - leaf.x0, 0);
        const rectHeight = Math.max(leaf.y1 - leaf.y0, 0);
        const showLabel = rectWidth >= 54 && rectHeight >= 34;
        return (
          <g key={leaf.label} className="treemapCell">
            <rect
              className="treemapRect"
              height={rectHeight}
              width={rectWidth}
              x={leaf.x0}
              y={leaf.y0}
            >
              <title>{`${leaf.label}: ${leaf.count.toLocaleString()}`}</title>
            </rect>
            {showLabel && (
              <>
                <text className="treemapLabel" x={leaf.x0 + 8} y={leaf.y0 + 18}>
                  {truncateTreemapLabel(leaf.label, rectWidth)}
                </text>
                <text className="treemapValue" x={leaf.x0 + 8} y={leaf.y0 + rectHeight - 8}>
                  {leaf.count.toLocaleString()}
                </text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function truncateTreemapLabel(label: string, width: number) {
  const maxChars = Math.max(4, Math.floor((width - 16) / 7));
  return label.length > maxChars ? `${label.slice(0, Math.max(maxChars - 1, 1))}…` : label;
}

type ModelVocabularyPoint = VisualizationPayload["modelVocabularyScatter"][number];
type ModelScatterMetric = {
  key: keyof ModelVocabularyPoint | "graphSize";
  label: string;
  value: (point: ModelVocabularyPoint) => number;
};

const modelSizeMetrics: ModelScatterMetric[] = [
  { key: "graphSize", label: "Nodes + edges", value: (point) => (point.graphSize ?? ((point.nodeCount ?? 0) + (point.edgeCount ?? 0))) || point.nameSlots },
  { key: "nodeCount", label: "Nodes", value: (point) => point.nodeCount ?? point.nameSlots },
  { key: "edgeCount", label: "Edges", value: (point) => point.edgeCount ?? 0 },
  { key: "nameSlots", label: "Name slots", value: (point) => point.nameSlots },
];

const vocabularyMetrics: ModelScatterMetric[] = [
  { key: "uniqueTokens", label: "Unique name tokens", value: (point) => point.uniqueTokens },
  { key: "uniqueNames", label: "Unique normalized names", value: (point) => point.uniqueNames },
  { key: "namedElements", label: "Named elements", value: (point) => point.namedElements },
  { key: "semanticNameCount", label: "Semantic names", value: (point) => point.semanticNameCount ?? point.namedElements },
  { key: "tokens", label: "Name token occurrences", value: (point) => point.tokens },
];

function Scatter({ points }: { points: VisualizationPayload["modelVocabularyScatter"] }) {
  const [xMetricKey, setXMetricKey] = useState(modelSizeMetrics[0].key);
  const [yMetricKey, setYMetricKey] = useState(vocabularyMetrics[0].key);
  const xMetric = modelSizeMetrics.find((metric) => metric.key === xMetricKey) || modelSizeMetrics[0];
  const yMetric = vocabularyMetrics.find((metric) => metric.key === yMetricKey) || vocabularyMetrics[0];
  const plottedPoints = points.map((point) => ({
    x: xMetric.value(point),
    y: yMetric.value(point),
    label: point.id,
    value: point.missingNameRatio,
    size: point.nameSlots,
    detail: [
      `${xMetric.label}: ${formatNumber(xMetric.value(point))}`,
      `${yMetric.label}: ${formatNumber(yMetric.value(point))}`,
      `Missing names: ${percentage(point.missingNameRatio)}`,
    ].join(", "),
  }));
  return (
    <div className="modelScatterPanel">
      <div className="chartControls">
        <label>
          Model size
          <select value={xMetricKey} onChange={(event) => setXMetricKey(event.target.value as ModelScatterMetric["key"])}>
            {modelSizeMetrics.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}
          </select>
        </label>
        <label>
          Name metric
          <select value={yMetricKey} onChange={(event) => setYMetricKey(event.target.value as ModelScatterMetric["key"])}>
            {vocabularyMetrics.map((metric) => <option key={metric.key} value={metric.key}>{metric.label}</option>)}
          </select>
        </label>
        <span>Color: missing-name ratio</span>
      </div>
      <SvgScatter points={plottedPoints} xLabel={xMetric.label} yLabel={yMetric.label} zeroBased />
    </div>
  );
}

function SvgScatter({
  points,
  xLabel,
  yLabel,
  zeroBased = false,
}: {
  points: Array<{ x: number; y: number; label: string; value: number; size: number; detail?: string }>;
  xLabel: string;
  yLabel: string;
  zeroBased?: boolean;
}) {
  if (!points.length) return <EmptyChart />;
  const width = 760;
  const height = 340;
  const margin = { top: 22, right: 26, bottom: 54, left: 72 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const xValues = points.map((point) => point.x);
  const yValues = points.map((point) => point.y);
  const xDomain = numericDomain(xValues, zeroBased);
  const yDomain = numericDomain(yValues, zeroBased);
  const xTicks = chartTicks(xDomain[0], xDomain[1]);
  const yTicks = chartTicks(yDomain[0], yDomain[1]);
  const xScale = (value: number) => scaleLinear(value, xDomain[0], xDomain[1], margin.left, margin.left + plotWidth);
  const yScale = (value: number) => scaleLinear(value, yDomain[0], yDomain[1], margin.top + plotHeight, margin.top);
  return (
    <svg className="scatter" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${xLabel} versus ${yLabel}`}>
      {xTicks.map((tick) => {
        const x = xScale(tick);
        return <g key={`x:${tick}`}><line className="chartGridLine" x1={x} x2={x} y1={margin.top} y2={margin.top + plotHeight} /><text className="chartTick" x={x} y={height - 28}>{formatNumber(tick)}</text></g>;
      })}
      {yTicks.map((tick) => {
        const y = yScale(tick);
        return <g key={`y:${tick}`}><line className="chartGridLine" x1={margin.left} x2={margin.left + plotWidth} y1={y} y2={y} /><text className="chartTick" x={margin.left - 10} y={y + 4} textAnchor="end">{formatNumber(tick)}</text></g>;
      })}
      <line className="chartAxisLine" x1={margin.left} x2={margin.left + plotWidth} y1={margin.top + plotHeight} y2={margin.top + plotHeight} />
      <line className="chartAxisLine" x1={margin.left} x2={margin.left} y1={margin.top} y2={margin.top + plotHeight} />
      {points.map((point, index) => (
        <circle
          key={`${point.label}:${index}`}
          cx={xScale(point.x)}
          cy={yScale(point.y)}
          r={Math.min(3.5 + Math.sqrt(point.size || 1), 11)}
          fill={`rgba(15, 118, 110, ${Math.max(0.25, Math.min(0.95, point.value + 0.2))})`}
        >
          <title>{`${point.label}: ${point.detail || `${xLabel} ${formatNumber(point.x)}, ${yLabel} ${formatNumber(point.y)}`}`}</title>
        </circle>
      ))}
      <text className="chartAxisLabel" x={margin.left + plotWidth / 2} y={height - 6}>{xLabel}</text>
      <text className="chartAxisLabel" transform={`translate(18 ${margin.top + plotHeight / 2}) rotate(-90)`}>{yLabel}</text>
    </svg>
  );
}

function numericDomain(values: number[], zeroBased: boolean): [number, number] {
  const finiteValues = values.filter(Number.isFinite);
  if (!finiteValues.length) return [0, 1];
  let min = Math.min(...finiteValues);
  let max = Math.max(...finiteValues);
  if (zeroBased && min > 0) min = 0;
  if (min === max) {
    if (max === 0) return [0, 1];
    return zeroBased ? [0, max] : [min - Math.abs(max) * 0.1, max + Math.abs(max) * 0.1];
  }
  const padding = (max - min) * 0.04;
  return [zeroBased ? Math.min(0, min) : min - padding, max + padding];
}

function scaleLinear(value: number, min: number, max: number, start: number, end: number) {
  return start + (value - min) / (max - min || 1) * (end - start);
}

function chartTicks(min: number, max: number, count = 5) {
  if (max <= min) return [min];
  const step = niceStep((max - min) / Math.max(count - 1, 1));
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [];
  for (let value = start; value <= max + step * 0.5; value += step) {
    ticks.push(Number(value.toFixed(10)));
  }
  return ticks.length ? ticks : [min, max];
}

function niceStep(value: number) {
  const exponent = Math.floor(Math.log10(value || 1));
  const magnitude = 10 ** exponent;
  const normalized = value / magnitude;
  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function formatNumber(value: number) {
  return round(value).toLocaleString();
}

function EmptyChart() { return <p className="visualizationNote">No matching values in this dataset.</p>; }
