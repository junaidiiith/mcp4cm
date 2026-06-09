import { Expand, Grid2X2, ListTree, Network, Plus } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { HistogramBin, StatisticItem, VisualizationPayload } from "../../types";
import { round } from "../../utils";

export function VisualizationPanel({ data }: { data: VisualizationPayload | null }) {
  const [activeCategory, setActiveCategory] = useState<VisualizationCategoryId>("quality");
  const [selectedChartId, setSelectedChartId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [expandedChartId, setExpandedChartId] = useState<string | null>(null);
  const categories = useMemo(() => data ? visualizationCategories(data) : [], [data]);
  const activeCharts = categories.find((category) => category.id === activeCategory)?.charts || categories[0]?.charts || [];
  const selectedChart = activeCharts.find((chart) => chart.id === selectedChartId) || activeCharts[0] || null;
  const expandedChart = categories.flatMap((category) => category.charts).find((chart) => chart.id === expandedChartId) || null;

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
                <Button className="visualizationModeButton" type="button" variant="secondary" size="sm" onClick={() => setShowAll((current) => !current)}>
                  {showAll ? <ListTree size={16} /> : <Grid2X2 size={16} />}
                  {showAll ? "Focused" : "Show all"}
                </Button>
              </div>

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

function RatioHistogram({ bins }: { bins: HistogramBin[] }) {
  const width = 760, height = 280;
  const margin = { top: 24, right: 12, bottom: 52, left: 58 };
  const plotWidth = width - margin.left - margin.right, plotHeight = height - margin.top - margin.bottom;
  const max = Math.max(...bins.map((bin) => bin.count), 1);
  const barWidth = plotWidth / bins.length;
  const populatedBins = bins.filter((bin) => bin.count > 0);
  const yTicks = Array.from(new Set(Array.from({ length: 5 }, (_, index) => Math.round(max * index / 4))));
  const xTickIndexes = Array.from(new Set(Array.from({ length: 7 }, (_, index) => Math.round(bins.length * index / 6))));
  const percentage = (value: number) => `${round(value * 100)}%`;
  const binWidth = bins.length ? bins[0].end - bins[0].start : 0;
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
      <text className="histogramAxisLabel" x={margin.left + plotWidth / 2} y={height - 4} textAnchor="middle">Missing-name ratio</text>
      <text className="histogramAxisLabel" transform={`translate(14 ${margin.top + plotHeight / 2}) rotate(-90)`} textAnchor="middle">Number of models</text>
    </svg>
    <p className="histogramSummary">Each bar spans {percentage(binWidth)}. {populatedBins.length} populated ratio range(s); highest range contains {max} model(s).</p>
  </div>;
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
  if (!data.tokens.length || !data.rows.length) return <EmptyChart />;
  return <div className="heatmap"><div className="heatmapHeader"><b /><>{data.tokens.map((token) => <span key={token}>{token}</span>)}</></div>{data.rows.map((row) => <div className="heatmapRow" key={row.label}><b>{row.label}</b>{row.values.map((value, index) => <span key={`${row.label}:${data.tokens[index]}`} style={{ background: `rgba(15, 118, 110, ${Math.min(value * 8, 1)})` }} title={`${row.label} / ${data.tokens[index]}: ${round(value * 100)}%`} />)}</div>)}</div>;
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
