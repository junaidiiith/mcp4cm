import type { CSSProperties } from "react";
import type { HistogramBin, StatisticItem, VisualizationPayload } from "@/types";
import { round } from "@/utils";

export function LegacyHorizontalBars({ items }: { items: StatisticItem[] }) {
  const max = Math.max(...items.map((item) => item.count), 1);
  if (!items.length) return <LegacyEmptyChart />;
  return <div className="horizontalBars">{items.map((item) => <div className="horizontalBarRow" key={item.label} title={`${item.label}: ${round(item.count)}`}><span>{item.label}</span><i><b style={{ width: `${item.count / max * 100}%` }} /></i><strong>{round(item.count)}</strong></div>)}</div>;
}

export function LegacyLimitedHorizontalBars({ items, ariaLabel }: { items: StatisticItem[]; ariaLabel: string }) {
  void ariaLabel;
  return <LegacyHorizontalBars items={items.slice(0, 10)} />;
}

export function LegacyHistogram({ bins, useDisplayCount = false, ratioAxis = false }: { bins: HistogramBin[]; useDisplayCount?: boolean; ratioAxis?: boolean }) {
  const max = Math.max(...bins.map((bin) => useDisplayCount ? bin.displayCount : bin.count), 1);
  if (!bins.length) return <LegacyEmptyChart />;
  if (ratioAxis) return <LegacyRatioHistogram bins={bins} />;
  return <div className="histogramFrame">
    <div className="histogram">{bins.map((bin) => {
      const value = useDisplayCount ? bin.displayCount : bin.count;
      return <span key={`${bin.start}:${bin.end}`} style={{ height: `${value / max * 100}%` }} title={`${bin.start} to ${bin.end}: ${bin.count} model(s)`} />;
    })}</div>
  </div>;
}

export function LegacyRatioHistogram({ bins }: { bins: HistogramBin[] }) {
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

export function LegacyTreemap({ items }: { items: StatisticItem[] }) {
  const total = items.reduce((sum, item) => sum + item.count, 0) || 1;
  if (!items.length) return <LegacyEmptyChart />;
  return <div className="treemap">{items.map((item) => <span key={item.label} style={{ flexGrow: item.count, flexBasis: `${item.count / total * 100}%` }} title={`${item.label}: ${item.count}`}><b>{item.label}</b><small>{item.count}</small></span>)}</div>;
}

export function LegacyConceptTreemap({ links }: { links: VisualizationPayload["typeConceptLinks"] }) {
  const groups = Object.entries(links.reduce<Record<string, typeof links>>((result, link) => {
    (result[link.type] ||= []).push(link);
    return result;
  }, {}));
  if (!groups.length) return <LegacyEmptyChart />;
  return <div className="conceptTreemap">{groups.map(([type, entries]) => <section key={type}><b>{type}</b><div>{(entries || []).map((entry) => <span style={{ flexGrow: entry.count }} title={`${entry.type} -> ${entry.concept}: ${entry.count}`} key={`${entry.type}:${entry.concept}`}>{entry.concept}</span>)}</div></section>)}</div>;
}

export function LegacyHeatmap({ data }: { data: VisualizationPayload["vocabularyHeatmap"] }) {
  if (!data.tokens.length || !data.rows.length) return <LegacyEmptyChart />;
  return <div className="heatmap"><div className="heatmapHeader"><b /><>{data.tokens.map((token) => <span key={token}>{token}</span>)}</></div>{data.rows.map((row) => <div className="heatmapRow" key={row.label}><b>{row.label}</b>{row.values.map((value, index) => <span key={`${row.label}:${data.tokens[index]}`} style={{ background: `rgba(15, 118, 110, ${Math.min(value * 8, 1)})` }} title={`${row.label} / ${data.tokens[index]}: ${round(value * 100)}%`} />)}</div>)}</div>;
}

export function LegacyTypeConceptLinks({ links }: { links: VisualizationPayload["typeConceptLinks"] }) {
  const max = Math.max(...links.map((link) => link.count), 1);
  if (!links.length) return <LegacyEmptyChart />;
  return <div className="typeConceptLinks">{links.map((link) => <div key={`${link.type}:${link.concept}`} title={`${link.type} -> ${link.concept}: ${link.count}`}><b>{link.type}</b><i><span style={{ width: `${link.count / max * 100}%` }} /></i><strong>{link.concept}</strong><small>{link.count}</small></div>)}</div>;
}

export function LegacyScatter({ points }: { points: VisualizationPayload["modelVocabularyScatter"] }) {
  return <LegacySvgScatter points={points.map((point) => ({ ...point, x: point.namedElements, y: point.uniqueNames, label: point.id, value: point.missingNameRatio, size: point.tokens }))} xLabel="Named elements" yLabel="Unique concepts" />;
}

export function LegacyTopicScatter({ points }: { points: NonNullable<VisualizationPayload["topicModel"]["points"]> }) {
  return <LegacySvgScatter points={points.map((point) => ({ ...point, label: `${point.id} | ${point.topic}`, value: point.topicStrength, size: point.namedElements }))} xLabel="Component 1" yLabel="Component 2" />;
}

export function LegacySvgScatter({ points, xLabel, yLabel }: { points: Array<{ x: number; y: number; label: string; value: number; size: number }>; xLabel: string; yLabel: string }) {
  if (!points.length) return <LegacyEmptyChart />;
  const xValues = points.map((point) => point.x), yValues = points.map((point) => point.y);
  const minX = Math.min(...xValues), maxX = Math.max(...xValues), minY = Math.min(...yValues), maxY = Math.max(...yValues);
  const scale = (value: number, min: number, max: number, start: number, end: number) => start + (value - min) / (max - min || 1) * (end - start);
  return <svg className="scatter" viewBox="0 0 640 300" role="img" aria-label={`${xLabel} versus ${yLabel}`}><text x="320" y="294">{xLabel}</text><text transform="translate(14 160) rotate(-90)">{yLabel}</text>{points.map((point, index) => <circle key={`${point.label}:${index}`} cx={scale(point.x, minX, maxX, 42, 625)} cy={scale(point.y, minY, maxY, 270, 15)} r={Math.min(4 + Math.sqrt(point.size || 1), 14)} fill={`rgba(15, 118, 110, ${Math.max(.25, Math.min(.95, point.value + .2))})`}><title>{`${point.label}: ${xLabel} ${round(point.x)}, ${yLabel} ${round(point.y)}`}</title></circle>)}</svg>;
}

export function LegacyBoxplot({ summary }: { summary: VisualizationPayload["nameCountBoxplot"] }) {
  const max = summary.max || 1;
  const left = (summary.q1 / max) * 100, width = ((summary.q3 - summary.q1) / max) * 100;
  return <div className="boxplot" title={`min ${summary.min}, Q1 ${round(summary.q1)}, median ${round(summary.median)}, Q3 ${round(summary.q3)}, max ${summary.max}`}><i /><span style={{ left: `${left}%`, width: `${width}%` }} /><b style={{ left: `${summary.median / max * 100}%` }} /><small>min {summary.min}</small><small>median {round(summary.median)}</small><small>max {summary.max}</small></div>;
}

export function LegacyPieStat({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  tone: string;
}) {
  const percent = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="pieStat">
      <div
        className={`pie ${tone}`}
        style={{ "--percent": `${percent}%` } as CSSProperties}
        aria-label={`${label}: ${value} of ${total}`}
      />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        <small>
          {percent}% of {total}
        </small>
      </div>
    </div>
  );
}

export function LegacyEmptyChart() { return <p className="visualizationNote">No matching values in this dataset.</p>; }
