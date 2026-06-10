import type { HistogramBin, StatisticItem, VisualizationPayload } from "@/types";
import { round } from "@/utils";
import type { ChartOption } from "../echarts";
import { chartColors, chartPalette } from "../theme";

const axisLabel = {
  color: chartColors.muted,
  fontSize: 11,
  overflow: "truncate" as const,
};

const splitLine = {
  lineStyle: {
    color: "#dbe4ec",
  },
};

const grid = {
  left: 12,
  right: 18,
  top: 18,
  bottom: 28,
  containLabel: true,
};

interface FormatterParam {
  name?: string;
  value?: unknown;
  dataIndex?: number;
  treePathInfo?: Array<{ name?: string }>;
}

function formatterParam(params: unknown): FormatterParam {
  return (Array.isArray(params) ? params[0] : params) as FormatterParam;
}

function numericMax(values: number[]) {
  return Math.max(...values, 1);
}

function percent(value: number) {
  return `${round(value * 100)}%`;
}

export function statisticItemsToBarOption(
  items: StatisticItem[],
  options: { name?: string; valueLabel?: string } = {},
): ChartOption {
  const sorted = [...items].sort((a, b) => a.count - b.count);

  return {
    grid,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      valueFormatter: (value) => String(round(Number(value))),
    },
    xAxis: {
      type: "value",
      name: options.valueLabel,
      nameLocation: "middle",
      nameGap: 24,
      axisLabel,
      splitLine,
    },
    yAxis: {
      type: "category",
      data: sorted.map((item) => item.label),
      axisLabel: { ...axisLabel, width: 140 },
    },
    series: [
      {
        name: options.name || "Count",
        type: "bar",
        data: sorted.map((item) => item.count),
        barMaxWidth: 22,
        itemStyle: {
          borderRadius: [0, 5, 5, 0],
          color: chartColors.primarySoft,
        },
        emphasis: {
          focus: "series",
          itemStyle: { color: chartColors.primary },
        },
      },
    ],
  };
}

export function binsToHistogramOption(
  bins: HistogramBin[],
  options: { useDisplayCount?: boolean; ratioAxis?: boolean } = {},
): ChartOption {
  const values = bins.map((bin) => options.useDisplayCount ? bin.displayCount : bin.count);
  const labels = bins.map((bin) => {
    if (options.ratioAxis) return `${percent(bin.start)}-${percent(bin.end)}`;
    return `${round(bin.start)}-${round(bin.end)}`;
  });

  return {
    grid: { ...grid, bottom: options.ratioAxis ? 58 : 34 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const first = Array.isArray(params) ? params[0] : params;
        const bin = bins[first.dataIndex];
        const range = options.ratioAxis
          ? `${percent(bin.start)} to ${percent(bin.end)}`
          : `${round(bin.start)} to ${round(bin.end)}`;
        return `${range}<br/>${bin.count.toLocaleString()} model(s)`;
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: {
        ...axisLabel,
        rotate: options.ratioAxis ? 45 : 0,
        interval: options.ratioAxis ? Math.max(Math.floor(bins.length / 8), 0) : "auto",
      },
    },
    yAxis: {
      type: "value",
      name: "Models",
      nameGap: 32,
      axisLabel,
      splitLine,
    },
    series: [
      {
        name: "Models",
        type: "bar",
        data: values,
        barMinHeight: 2,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: chartColors.primarySoft,
        },
        emphasis: {
          itemStyle: { color: chartColors.primary },
        },
      },
    ],
  };
}

export function statisticItemsToTreemapOption(items: StatisticItem[]): ChartOption {
  return {
    tooltip: {
      formatter: (params) => {
        const info = formatterParam(params);
        return `${info.name}<br/>${Number(info.value || 0).toLocaleString()}`;
      },
    },
    series: [
      {
        type: "treemap",
        roam: false,
        nodeClick: false,
        breadcrumb: { show: false },
        color: chartPalette,
        label: {
          color: "#173d40",
          fontWeight: 700,
          formatter: "{b}",
        },
        upperLabel: { show: false },
        itemStyle: {
          borderColor: chartColors.white,
          borderWidth: 3,
          gapWidth: 3,
        },
        data: items.map((item) => ({
          name: item.label,
          value: item.count,
        })),
      },
    ],
  };
}

export function typeConceptLinksToTreemapOption(links: VisualizationPayload["typeConceptLinks"]): ChartOption {
  const groups = links.reduce<Record<string, Array<{ name: string; value: number }>>>((result, link) => {
    (result[link.type] ||= []).push({ name: link.concept, value: link.count });
    return result;
  }, {});

  return {
    tooltip: {
      formatter: (params) => {
        const info = formatterParam(params);
        const treePath = info.treePathInfo?.map((path) => path.name).filter(Boolean).join(" / ");
        return `${treePath || info.name}<br/>${Number(info.value || 0).toLocaleString()}`;
      },
    },
    series: [
      {
        type: "treemap",
        roam: true,
        nodeClick: "zoomToNode",
        breadcrumb: {
          show: true,
          bottom: 0,
          itemStyle: { color: chartColors.surface, textStyle: { color: chartColors.text } },
        },
        color: chartPalette,
        label: {
          show: true,
          color: "#173d40",
          formatter: "{b}",
        },
        upperLabel: {
          show: true,
          height: 24,
          color: chartColors.text,
        },
        itemStyle: {
          borderColor: chartColors.white,
          borderWidth: 2,
          gapWidth: 2,
        },
        levels: [
          { itemStyle: { borderWidth: 0, gapWidth: 4 } },
          { itemStyle: { borderColor: chartColors.white, borderWidth: 3, gapWidth: 3 } },
          { itemStyle: { borderColor: chartColors.white, borderWidth: 2, gapWidth: 2 } },
        ],
        data: Object.entries(groups).map(([type, children]) => ({
          name: type,
          value: children.reduce((sum, child) => sum + child.value, 0),
          children,
        })),
      },
    ],
  };
}

export function vocabularyHeatmapToOption(data: VisualizationPayload["vocabularyHeatmap"]): ChartOption {
  const values = data.rows.flatMap((row, rowIndex) => row.values.map((value, tokenIndex) => [tokenIndex, rowIndex, value]));
  const max = numericMax(values.map((entry) => Number(entry[2])));

  return {
    grid: { left: 12, right: 18, top: 12, bottom: 80, containLabel: true },
    tooltip: {
      position: "top",
      formatter: (params) => {
        const [tokenIndex, rowIndex, value] = formatterParam(params).value as [number, number, number];
        return `${data.rows[rowIndex].label} / ${data.tokens[tokenIndex]}<br/>${percent(value)}`;
      },
    },
    xAxis: {
      type: "category",
      data: data.tokens,
      axisLabel: { ...axisLabel, rotate: 45 },
      splitArea: { show: true },
    },
    yAxis: {
      type: "category",
      data: data.rows.map((row) => row.label),
      axisLabel: { ...axisLabel, width: 130 },
      splitArea: { show: true },
    },
    visualMap: {
      min: 0,
      max,
      calculable: true,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      inRange: {
        color: [chartColors.surface, "#bfe2de", chartColors.primary],
      },
    },
    series: [
      {
        name: "Relative frequency",
        type: "heatmap",
        data: values,
        label: { show: false },
        emphasis: {
          itemStyle: {
            shadowBlur: 8,
            shadowColor: "rgba(15, 118, 110, .28)",
          },
        },
      },
    ],
  };
}

export function modelVocabularyScatterToOption(points: VisualizationPayload["modelVocabularyScatter"]): ChartOption {
  const ratios = points.map((point) => point.missingNameRatio);
  const maxSize = numericMax(points.map((point) => point.tokens));

  return scatterOption({
    name: "Model",
    xLabel: "Named elements",
    yLabel: "Unique names",
    minValue: Math.min(...ratios, 0),
    maxValue: Math.max(...ratios, 1),
    visualLabel: "Missing-name ratio",
    data: points.map((point) => ({
      label: point.id,
      x: point.namedElements,
      y: point.uniqueNames,
      value: point.missingNameRatio,
      size: 8 + Math.sqrt((point.tokens / maxSize) || 0) * 20,
      extra: `Tokens: ${point.tokens.toLocaleString()}<br/>Missing: ${percent(point.missingNameRatio)}`,
    })),
  });
}

export function topicScatterToOption(points: NonNullable<VisualizationPayload["topicModel"]["points"]>): ChartOption {
  const strengths = points.map((point) => point.topicStrength);
  const maxSize = numericMax(points.map((point) => point.namedElements));

  return scatterOption({
    name: "Topic",
    xLabel: "Component 1",
    yLabel: "Component 2",
    minValue: Math.min(...strengths, 0),
    maxValue: Math.max(...strengths, 1),
    visualLabel: "Topic strength",
    data: points.map((point) => ({
      label: `${point.id} | ${point.topic}`,
      x: point.x,
      y: point.y,
      value: point.topicStrength,
      size: 8 + Math.sqrt((point.namedElements / maxSize) || 0) * 20,
      extra: `Topic: ${point.topic}<br/>Strength: ${percent(point.topicStrength)}`,
    })),
  });
}

function scatterOption({
  name,
  xLabel,
  yLabel,
  visualLabel,
  minValue,
  maxValue,
  data,
}: {
  name: string;
  xLabel: string;
  yLabel: string;
  visualLabel: string;
  minValue: number;
  maxValue: number;
  data: Array<{ label: string; x: number; y: number; value: number; size: number; extra: string }>;
}): ChartOption {
  return {
    grid,
    tooltip: {
      trigger: "item",
      formatter: (params) => {
        const point = data[formatterParam(params).dataIndex || 0];
        return `${point.label}<br/>${xLabel}: ${round(point.x)}<br/>${yLabel}: ${round(point.y)}<br/>${point.extra}`;
      },
    },
    xAxis: {
      type: "value",
      name: xLabel,
      nameLocation: "middle",
      nameGap: 28,
      axisLabel,
      splitLine,
    },
    yAxis: {
      type: "value",
      name: yLabel,
      nameLocation: "middle",
      nameGap: 42,
      axisLabel,
      splitLine,
    },
    visualMap: {
      min: minValue,
      max: maxValue,
      dimension: 2,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      text: [visualLabel, ""],
      calculable: true,
      inRange: {
        color: ["#bddbd8", chartColors.primary],
      },
    },
    series: [
      {
        name,
        type: "scatter",
        data: data.map((point) => [point.x, point.y, point.value, point.label]),
        symbolSize: (_value, params) => data[params.dataIndex].size,
        itemStyle: {
          opacity: 0.82,
          borderColor: chartColors.primary,
          borderWidth: 1,
        },
        emphasis: {
          focus: "self",
          itemStyle: {
            opacity: 1,
            borderWidth: 2,
          },
        },
      },
    ],
  };
}

export function boxplotSummaryToOption(summary: VisualizationPayload["nameCountBoxplot"]): ChartOption {
  return {
    grid: { ...grid, bottom: 34 },
    tooltip: {
      trigger: "item",
      formatter: `Min: ${round(summary.min)}<br/>Q1: ${round(summary.q1)}<br/>Median: ${round(summary.median)}<br/>Q3: ${round(summary.q3)}<br/>Max: ${round(summary.max)}`,
    },
    xAxis: {
      type: "category",
      data: ["Name counts"],
      axisLabel,
    },
    yAxis: {
      type: "value",
      name: "Names",
      axisLabel,
      splitLine,
    },
    series: [
      {
        name: "Name counts",
        type: "boxplot",
        data: [[summary.min, summary.q1, summary.median, summary.q3, summary.max]],
        itemStyle: {
          color: "#d7efed",
          borderColor: chartColors.primary,
          borderWidth: 2,
        },
      },
    ],
  };
}

export function typeConceptLinksToBarOption(links: VisualizationPayload["typeConceptLinks"]): ChartOption {
  return statisticItemsToBarOption(
    links.map((link) => ({ label: `${link.type} -> ${link.concept}`, count: link.count })),
    { name: "Links", valueLabel: "Count" },
  );
}

export function duplicatePieOption({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  tone: "duplicate" | "unique";
}): ChartOption {
  const color = tone === "duplicate" ? chartColors.destructive : chartColors.primarySoft;
  const other = Math.max(total - value, 0);
  const percentValue = total ? Math.round((value / total) * 100) : 0;

  return {
    color: [color, chartColors.surface],
    tooltip: {
      trigger: "item",
      formatter: "{b}<br/>{c} ({d}%)",
    },
    legend: { show: false },
    series: [
      {
        name: label,
        type: "pie",
        radius: ["58%", "78%"],
        avoidLabelOverlap: true,
        data: [
          { name: label, value },
          { name: "Other models", value: other },
        ],
        label: {
          show: true,
          position: "center",
          formatter: `${percentValue}%\n${value.toLocaleString()}`,
          color: chartColors.text,
          fontSize: 13,
          fontWeight: 700,
          lineHeight: 18,
        },
        labelLine: { show: false },
        emphasis: {
          scale: true,
          scaleSize: 4,
        },
      },
    ],
  };
}
