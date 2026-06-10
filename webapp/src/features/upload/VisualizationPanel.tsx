import { Expand, Grid2X2, ListTree, Network, Plus } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { EChart } from "@/components/charts/EChart";
import {
  binsToHistogramOption,
  boxplotSummaryToOption,
  modelVocabularyScatterToOption,
  statisticItemsToBarOption,
  statisticItemsToTreemapOption,
  topicScatterToOption,
  typeConceptLinksToBarOption,
  typeConceptLinksToTreemapOption,
  vocabularyHeatmapToOption,
} from "@/components/charts/builders";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { HistogramBin, StatisticItem, VisualizationPayload } from "../../types";

type VisualizationSnapshot = "before" | "after";

export function VisualizationPanel({
  beforeData,
  afterData,
  beforeModelCount,
  afterModelCount,
}: {
  beforeData: VisualizationPayload | null;
  afterData: VisualizationPayload | null;
  beforeModelCount: number | null;
  afterModelCount: number | null;
}) {
  const [activeCategory, setActiveCategory] = useState<VisualizationCategoryId>("quality");
  const [selectedChartId, setSelectedChartId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [expandedChartId, setExpandedChartId] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<VisualizationSnapshot>("before");
  const data = snapshot === "after" && afterData ? afterData : beforeData;
  const categories = useMemo(() => data ? visualizationCategories(data) : [], [data]);
  const activeCharts = categories.find((category) => category.id === activeCategory)?.charts || categories[0]?.charts || [];
  const selectedChart = activeCharts.find((chart) => chart.id === selectedChartId) || activeCharts[0] || null;
  const expandedChart = categories.flatMap((category) => category.charts).find((chart) => chart.id === expandedChartId) || null;
  const selectedModelCount = snapshot === "after" ? afterModelCount : beforeModelCount;
  const modelCountLabel = selectedModelCount === null ? "" : `${selectedModelCount.toLocaleString()} models`;

  useEffect(() => {
    if (snapshot === "after" && !afterData) setSnapshot("before");
  }, [afterData, snapshot]);

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
                  <div className="visualizationSnapshotControl" aria-label="Visualization dataset snapshot">
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
                      disabled={!afterData}
                      title={afterData ? "After cleansing" : "Run dummy filters to enable after-cleansing visualizations."}
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

type VisualizationCategoryId = "quality" | "vocabulary" | "structure" | "topics";

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

function visualizationCategories(data: VisualizationPayload): VisualizationCategory[] {
  return [
    {
      id: "quality",
      label: "Quality",
      charts: [
        {
          id: "missing-name-ratio",
          title: "Distribution of Missing-Name Ratio per Model",
          description: "Share of name slots recorded as empty name.",
          render: () => <Histogram bins={data.missingNameRatioHistogram} ratioAxis />,
        },
        {
          id: "missing-names-by-type",
          title: "Missing Names by Element Type",
          description: "Number of missing names grouped by normalized element type.",
          render: () => <LimitedHorizontalBars items={data.missingNamesByType} ariaLabel="Missing names by element type count" />,
        },
      ],
    },
    {
      id: "vocabulary",
      label: "Vocabulary",
      charts: [
        {
          id: "frequent-names",
          title: "Most Frequent Names",
          description: "Name occurrences across the complete corpus.",
          render: () => <LimitedHorizontalBars items={data.topConcepts} ariaLabel="Most frequent names count" />,
        },
        {
          id: "name-document-frequency",
          title: "Names by Document Frequency",
          description: "Number of models containing each name.",
          render: () => <LimitedHorizontalBars items={data.topConceptDocumentFrequency} ariaLabel="Names by document frequency count" />,
        },
        {
          id: "filtered-frequent-names",
          title: "Top Names Excluding Type-Based Placeholders",
          description: "Generic names such as class and class1 are excluded.",
          render: () => <LimitedHorizontalBars items={data.topConceptsWithoutTypePlaceholders} ariaLabel="Names excluding type-based placeholders count" />,
        },
        {
          id: "filtered-name-document-frequency",
          title: "Document Frequency Excluding Type-Based Placeholders",
          description: "Number of models containing each filtered name.",
          render: () => <LimitedHorizontalBars items={data.topConceptDocumentFrequencyWithoutTypePlaceholders} ariaLabel="Document frequency excluding type-based placeholders count" />,
        },
        {
          id: "type-vocabulary-heatmap",
          title: "Type-Specific Vocabulary Heatmap",
          description: "Relative token frequency within each major element type.",
          render: () => <Heatmap data={data.vocabularyHeatmap} />,
        },
        {
          id: "top-names-per-model",
          title: "Top 20 Names by Model Frequency",
          description: "Each name contributes at most once per model.",
          render: () => <HorizontalBars items={data.topNamesPerModel} />,
        },
      ],
    },
    {
      id: "structure",
      label: "Structure",
      charts: [
        {
          id: "element-type-treemap",
          title: "Element Types in the Corpus",
          description: "Treemap area is proportional to element count.",
          render: () => <Treemap items={data.elementTypeTreemap} />,
        },
        {
          id: "type-name-links",
          title: "Element Type to Frequent Names",
          description: "Strongest type-to-name links.",
          render: () => <TypeConceptLinks links={data.typeConceptLinks} />,
        },
        {
          id: "names-within-types",
          title: "Frequent Names within Element Types",
          description: "Hierarchical treemap grouped by major type.",
          render: () => <ConceptTreemap links={data.typeConceptLinks} />,
        },
        {
          id: "model-vocabulary-scatter",
          title: "Model Size vs Vocabulary Richness",
          description: "Point size follows token count; color follows missing-name ratio.",
          render: () => <Scatter points={data.modelVocabularyScatter} />,
        },
        {
          id: "name-count-boxplot",
          title: "Boxplot of Name Counts in Models",
          description: "Five-number summary of extracted name slots.",
          render: () => <Boxplot summary={data.nameCountBoxplot} />,
        },
        {
          id: "name-count-histogram-log",
          title: "Histogram of Name Counts (Log Scale)",
          description: "Log-scaled model frequency.",
          render: () => <Histogram bins={data.nameCountHistogramLog} useDisplayCount />,
        },
        {
          id: "few-names-histogram",
          title: "Models with Fewer Than Five Names",
          description: "Name-count distribution for small models.",
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
          description: "NMF topic assignment projected into two dimensions.",
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
  if (!items.length) return <EmptyChart />;
  return (
    <EChart
      ariaLabel="Horizontal bar chart"
      height={barChartHeight(items.length)}
      option={statisticItemsToBarOption(items, { valueLabel: "Count" })}
    />
  );
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

function Histogram({ bins, useDisplayCount = false, ratioAxis = false }: { bins: HistogramBin[]; useDisplayCount?: boolean; ratioAxis?: boolean }) {
  if (!bins.length) return <EmptyChart />;
  return <EChart ariaLabel="Histogram" height={ratioAxis ? 340 : 280} option={binsToHistogramOption(bins, { useDisplayCount, ratioAxis })} />;
}

function Treemap({ items }: { items: StatisticItem[] }) {
  if (!items.length) return <EmptyChart />;
  return <EChart ariaLabel="Element type treemap" height={340} option={statisticItemsToTreemapOption(items)} />;
}

function ConceptTreemap({ links }: { links: VisualizationPayload["typeConceptLinks"] }) {
  if (!links.length) return <EmptyChart />;
  return <EChart ariaLabel="Names within element types treemap" height={380} option={typeConceptLinksToTreemapOption(links)} />;
}

function Heatmap({ data }: { data: VisualizationPayload["vocabularyHeatmap"] }) {
  if (!data.tokens.length || !data.rows.length) return <EmptyChart />;
  return <EChart ariaLabel="Type-specific vocabulary heatmap" height={heatmapHeight(data.rows.length)} option={vocabularyHeatmapToOption(data)} />;
}

function TypeConceptLinks({ links }: { links: VisualizationPayload["typeConceptLinks"] }) {
  if (!links.length) return <EmptyChart />;
  return <EChart ariaLabel="Type to name links" height={barChartHeight(links.length)} option={typeConceptLinksToBarOption(links)} />;
}

function Scatter({ points }: { points: VisualizationPayload["modelVocabularyScatter"] }) {
  if (!points.length) return <EmptyChart />;
  return <EChart ariaLabel="Model size versus vocabulary richness scatter plot" height={360} option={modelVocabularyScatterToOption(points)} />;
}

function TopicScatter({ points }: { points: NonNullable<VisualizationPayload["topicModel"]["points"]> }) {
  if (!points.length) return <EmptyChart />;
  return <EChart ariaLabel="Topic map scatter plot" height={360} option={topicScatterToOption(points)} />;
}

function Boxplot({ summary }: { summary: VisualizationPayload["nameCountBoxplot"] }) {
  return <EChart ariaLabel="Name count boxplot" height={280} option={boxplotSummaryToOption(summary)} />;
}

function barChartHeight(length: number) {
  return Math.max(260, Math.min(720, length * 30 + 90));
}

function heatmapHeight(rows: number) {
  return Math.max(320, Math.min(720, rows * 28 + 150));
}

function EmptyChart() { return <p className="visualizationNote">No matching values in this dataset.</p>; }
