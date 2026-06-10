import * as echarts from "echarts/core";
import {
  BarChart,
  BoxplotChart,
  HeatmapChart,
  PieChart,
  ScatterChart,
  TreemapChart,
} from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";
import type { EChartsType } from "echarts/core";

echarts.use([
  BarChart,
  PieChart,
  ScatterChart,
  TreemapChart,
  HeatmapChart,
  BoxplotChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  SVGRenderer,
]);

export { echarts };
export type ChartOption = EChartsOption;
export type EChartInstance = EChartsType;
