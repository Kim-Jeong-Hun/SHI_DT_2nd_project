import { useMemo } from "react";
import type { ComponentProps } from "react";
import EChartsReact from "echarts-for-react";
import { translateText, useI18n } from "../../i18n";

function localizeOption(value: unknown): unknown {
  if (typeof value === "string") return translateText(value);
  if (typeof value === "function") {
    return (...args: unknown[]) => {
      const result = (value as (...params: unknown[]) => unknown)(...args);
      return typeof result === "string" ? translateText(result) : result;
    };
  }
  if (Array.isArray(value)) return value.map(localizeOption);
  if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, localizeOption(item)]));
  return value;
}

export default function LocalizedECharts(props: ComponentProps<typeof EChartsReact>) {
  const { language } = useI18n();
  const option = useMemo(() => language === "en" ? localizeOption(props.option) : props.option, [language, props.option]);
  return <EChartsReact {...props} option={option as ComponentProps<typeof EChartsReact>["option"]} key={language} />;
}
