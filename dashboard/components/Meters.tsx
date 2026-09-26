/**
 * Readouts for the three Jev question types.
 *
 * Each renders the number *and* what the number is out of, because a bare "1.57" tells
 * you nothing about whether that is a calm customer or a furious one. Thresholds are
 * drawn on the track so you can see how close a decision was, not just which way it went.
 */

export function ConfidenceBar({
  value,
  label,
  accent = "var(--jev)",
  threshold,
  thresholdLabel,
}: {
  value: number;
  label: string;
  accent?: string;
  threshold?: number;
  thresholdLabel?: string;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[0.7rem]" style={{ color: "var(--text-dim)" }}>
          {label}
        </span>
        <span className="mono font-semibold" style={{ color: accent }}>
          {value.toFixed(2)}
        </span>
      </div>
      <div className="meter mt-1">
        <span style={{ width: `${pct}%`, background: accent }} />
        {threshold !== undefined && (
          <i
            className="tick"
            style={{ left: `${threshold * 100}%` }}
            title={thresholdLabel ?? `threshold ${threshold}`}
          />
        )}
      </div>
      {threshold !== undefined && thresholdLabel && (
        <div
          className="mt-0.5 text-[0.62rem]"
          style={{ color: "var(--text-faint)" }}
        >
          {thresholdLabel}
        </div>
      )}
    </div>
  );
}

/** A `Score` question: an expected value over an ordered rubric, so it can be fractional. */
export function RubricMeter({
  value,
  levels,
  label,
  accent = "var(--jev)",
  threshold,
  thresholdLabel,
}: {
  value: number;
  levels: string[];
  label: string;
  accent?: string;
  threshold?: number;
  thresholdLabel?: string;
}) {
  const max = levels.length - 1;
  const pct = Math.max(0, Math.min(max, value)) / max;
  const nearest = levels[Math.min(max, Math.round(value))];

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[0.7rem]" style={{ color: "var(--text-dim)" }}>
          {label}
        </span>
        <span className="mono font-semibold" style={{ color: accent }}>
          {value.toFixed(2)}
          <span style={{ color: "var(--text-faint)" }}>/{max}</span>
        </span>
      </div>
      <div className="meter mt-1">
        <span style={{ width: `${pct * 100}%`, background: accent }} />
        {threshold !== undefined && (
          <i className="tick" style={{ left: `${(threshold / max) * 100}%` }} />
        )}
      </div>
      <div className="mt-1 flex justify-between gap-1">
        {levels.map((level, i) => (
          <span
            key={level}
            className="text-[0.6rem] leading-tight"
            style={{
              color:
                level === nearest ? "var(--text)" : "var(--text-faint)",
              fontWeight: level === nearest ? 600 : 400,
              textAlign: i === 0 ? "left" : i === max ? "right" : "center",
              flex: 1,
            }}
          >
            {level}
          </span>
        ))}
      </div>
      {thresholdLabel && (
        <div
          className="mt-0.5 text-[0.62rem]"
          style={{ color: "var(--text-faint)" }}
        >
          {thresholdLabel}
        </div>
      )}
    </div>
  );
}

/** Frustration across a whole thread — the signal the remedy ladder keys off. */
export function Sparkline({
  values,
  threshold,
}: {
  values: number[];
  threshold: number;
}) {
  if (!values.length) return null;
  const max = 2;
  const w = Math.max(60, values.length * 26);
  const h = 26;
  const x = (i: number) =>
    values.length === 1 ? w / 2 : (i / (values.length - 1)) * (w - 8) + 4;
  const y = (v: number) => h - 3 - (Math.min(max, v) / max) * (h - 6);

  return (
    <svg width={w} height={h} className="overflow-visible" aria-hidden>
      <line
        x1="0"
        x2={w}
        y1={y(threshold)}
        y2={y(threshold)}
        stroke="var(--border-strong)"
        strokeDasharray="2 3"
        strokeWidth="1"
      />
      <polyline
        points={values.map((v, i) => `${x(i)},${y(v)}`).join(" ")}
        fill="none"
        stroke="var(--jev)"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {values.map((v, i) => (
        <circle
          key={i}
          cx={x(i)}
          cy={y(v)}
          r={2.5}
          fill={v >= threshold ? "var(--deny)" : "var(--jev)"}
        />
      ))}
    </svg>
  );
}
