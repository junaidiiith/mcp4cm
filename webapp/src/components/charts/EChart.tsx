import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import ReactEChartsCore from "echarts-for-react/lib/core";
import { chartTheme } from "./theme";
import { echarts, type ChartOption, type EChartInstance } from "./echarts";

interface EChartProps {
  option: ChartOption;
  className?: string;
  height?: number | string;
  style?: CSSProperties;
  ariaLabel?: string;
  onChartReady?: (chart: EChartInstance) => void;
}

export function EChart({
  option,
  className,
  height = 300,
  style,
  ariaLabel,
  onChartReady,
}: EChartProps) {
  const reactChartRef = useRef<ReactEChartsCore | null>(null);
  const [chart, setChart] = useState<EChartInstance | null>(null);

  const handleReady = useCallback((instance: EChartInstance) => {
    setChart(instance);
    requestAnimationFrame(() => instance.resize());
    onChartReady?.(instance);
  }, [onChartReady]);

  useEffect(() => {
    const element = reactChartRef.current?.ele;
    if (!chart || !element || typeof ResizeObserver === "undefined") return undefined;

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(element);
    return () => observer.disconnect();
  }, [chart]);

  return (
    <ReactEChartsCore
      ref={reactChartRef}
      echarts={echarts}
      option={option}
      theme={chartTheme}
      className={["eChart", className].filter(Boolean).join(" ")}
      style={{ width: "100%", height, ...style }}
      opts={{ renderer: "svg" }}
      notMerge
      lazyUpdate
      autoResize
      onChartReady={handleReady}
      aria-label={ariaLabel}
    />
  );
}
