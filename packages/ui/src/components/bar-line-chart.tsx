import { cn } from "../lib/utils";

export interface BarLinePoint {
  /** The x-axis label ("3"); `title` is the longer tooltip ("3 nov"). */
  label: string;
  title?: string;
  bar: number;
  line: number;
}

interface BarLineChartProps {
  data: BarLinePoint[];
  barLabel: string;
  lineLabel: string;
  formatBar?: (value: number) => string;
  formatLine?: (value: number) => string;
  className?: string;
}

const WIDTH = 640;
const HEIGHT = 200;
const PAD = { top: 12, right: 36, bottom: 24, left: 48 };

/** Bars (left axis) and a line (right axis) over the same days: e.g. cost and conversations.
 * Plain SVG: one chart did not justify a charting library. */
function BarLineChart({
  data,
  barLabel,
  lineLabel,
  formatBar = String,
  formatLine = String,
  className,
}: BarLineChartProps) {
  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const maxBar = Math.max(...data.map((point) => point.bar), 0) || 1;
  const maxLine = Math.max(...data.map((point) => point.line), 0) || 1;
  const step = data.length ? plotWidth / data.length : plotWidth;
  const barWidth = Math.max(step * 0.6, 1);
  const x = (index: number) => PAD.left + index * step + step / 2;
  const yBar = (value: number) => PAD.top + plotHeight - (value / maxBar) * plotHeight;
  const yLine = (value: number) => PAD.top + plotHeight - (value / maxLine) * plotHeight;
  const labelEvery = Math.ceil(data.length / 10) || 1;
  const path = data
    .map((point, index) => `${index === 0 ? "M" : "L"}${x(index)},${yLine(point.line)}`)
    .join(" ");

  return (
    <figure data-slot="bar-line-chart" className={cn("flex flex-col gap-2", className)}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${barLabel} (barras) y ${lineLabel} (línea) por día`}
        className="h-auto w-full text-muted-foreground"
      >
        <line
          x1={PAD.left}
          x2={WIDTH - PAD.right}
          y1={PAD.top + plotHeight}
          y2={PAD.top + plotHeight}
          stroke="currentColor"
          strokeOpacity={0.3}
        />
        <text x={PAD.left - 6} y={PAD.top + 4} textAnchor="end" fontSize={10} fill="currentColor">
          {formatBar(maxBar)}
        </text>
        <text
          x={WIDTH - PAD.right + 6}
          y={PAD.top + 4}
          fontSize={10}
          fill="currentColor"
        >
          {formatLine(maxLine)}
        </text>
        {data.map((point, index) => (
          <g key={point.label + index}>
            <rect
              data-slot="bar"
              x={x(index) - barWidth / 2}
              y={yBar(point.bar)}
              width={barWidth}
              height={PAD.top + plotHeight - yBar(point.bar)}
              className="fill-primary/70"
            >
              <title>
                {`${point.title ?? point.label}: ${barLabel} ${formatBar(point.bar)} · ${lineLabel} ${formatLine(point.line)}`}
              </title>
            </rect>
            {index % labelEvery === 0 ? (
              <text
                x={x(index)}
                y={HEIGHT - 6}
                textAnchor="middle"
                fontSize={10}
                fill="currentColor"
              >
                {point.label}
              </text>
            ) : null}
          </g>
        ))}
        {data.length ? (
          <path d={path} fill="none" strokeWidth={2} className="stroke-foreground" />
        ) : null}
      </svg>
      <figcaption className="flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <span aria-hidden="true" className="inline-block size-3 rounded-sm bg-primary/70" />
          {barLabel}
        </span>
        <span className="flex items-center gap-1">
          <span aria-hidden="true" className="inline-block h-0.5 w-4 bg-foreground" />
          {lineLabel}
        </span>
      </figcaption>
    </figure>
  );
}

export { BarLineChart };
