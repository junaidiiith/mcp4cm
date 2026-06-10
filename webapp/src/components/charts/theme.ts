export const chartColors = {
  primary: "#0f766e",
  primarySoft: "#2d7d7d",
  surface: "#e6edf3",
  surfaceSoft: "#f7fbfc",
  border: "#d2dce9",
  text: "#243d49",
  muted: "#5a6874",
  destructive: "#b42318",
  warning: "#c27d12",
  white: "#ffffff",
};

export const chartPalette = [
  chartColors.primary,
  chartColors.primarySoft,
  "#5eb8b1",
  "#80c7c0",
  "#7a95aa",
  chartColors.warning,
  "#4f7ca2",
  "#7c6f9f",
];

export const chartFontFamily = "\"IBM Plex Sans\", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif";

export const chartTheme = {
  color: chartPalette,
  backgroundColor: "transparent",
  textStyle: {
    color: chartColors.text,
    fontFamily: chartFontFamily,
  },
  legend: {
    textStyle: {
      color: chartColors.muted,
      fontFamily: chartFontFamily,
    },
  },
};
