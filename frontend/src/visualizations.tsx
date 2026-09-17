import { Fragment } from "react";
import type { CSSProperties } from "react";
import type { Images } from "./types";
export const gridNames = [
  "西北",
  "北中",
  "东北",
  "中西",
  "中心",
  "中东",
  "西南",
  "南中",
  "东南",
];
export const pollutants = ["PM2.5", "PM10", "NO2", "O3"];
const products: Record<string, string> = {
  temperature: "近地面温度",
  humidity: "近地面湿度",
  pressure_wind: "气压与10米风",
  circulation_500: "500 hPa 环流",
};
export const formatScore = (value: number | undefined | null) =>
  value == null ? "—" : value.toFixed(1);
export const statusNames: Record<string, string> = {
  RUNNING: "执行中",
  SUCCEEDED: "已完成",
  PARTIALLY_COMPLETED: "部分完成",
  FAILED: "失败",
};

export function LineChart({
  current,
  historical,
  dates,
}: {
  current: number[];
  historical: number[];
  dates: string[];
}) {
  const high = Math.max(...current, ...historical, 1) * 1.18;
  const x = (i: number) => 48 + i * (520 / Math.max(1, current.length - 1));
  const y = (v: number) => 166 - (v / high) * 140;
  const points = (values: number[]) =>
    values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  return (
    <svg
      className="line-chart"
      viewBox="0 0 610 210"
      role="img"
      aria-label="当前预测与历史真实浓度曲线，数值也显示在下方表格中"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((n) => (
        <g key={n}>
          <line
            x1="48"
            x2="568"
            y1={y(high * n)}
            y2={y(high * n)}
            stroke="#e7ece8"
          />
          <text x="38" y={y(high * n) + 4} textAnchor="end">
            {Math.round(high * n)}
          </text>
        </g>
      ))}
      <polyline
        points={points(historical)}
        fill="none"
        stroke="#c0884a"
        strokeWidth="2.5"
        strokeDasharray="6 4"
      />
      <polyline
        points={points(current)}
        fill="none"
        stroke="#1a7770"
        strokeWidth="3"
      />
      {current.map((v, i) => (
        <g key={i}>
          <circle cx={x(i)} cy={y(v)} r="4" fill="#1a7770" />
          <circle cx={x(i)} cy={y(historical[i])} r="3" fill="#c0884a" />
          <text x={x(i)} y="193" textAnchor="middle">
            D{i + 1} · {dates[i]?.slice(5)}
          </text>
        </g>
      ))}
    </svg>
  );
}

export type ImageColumn = {
  label: string;
  note?: string;
  caption?: string;
  isActive?: boolean;
  images?: Images;
  onSelect?: () => void;
};

export function ImageMatrix({
  columns,
  onOpen,
}: {
  columns: ImageColumn[];
  onOpen: (url: string) => void;
}) {
  return (
    <div className="image-matrix-wrap">
      <div
        className="image-matrix"
        style={{ "--window-count": columns.length } as CSSProperties}
      >
        <div className="image-matrix-corner" aria-hidden="true" />
        {columns.map((column) => (
          <div
            className={`image-matrix-head ${column.isActive ? "active" : ""}`}
            key={column.label}
          >
            {column.onSelect ? (
              <button
                className="image-matrix-select"
                onClick={column.onSelect}
                aria-label={`查看${column.label}的完整对比结果`}
              >
                <strong>{column.label}</strong>
                {column.note && <span>{column.note}</span>}
              </button>
            ) : (
              <>
                <strong>{column.label}</strong>
                {column.note && <span>{column.note}</span>}
              </>
            )}
            {column.caption && <small>{column.caption}</small>}
          </div>
        ))}
        {Object.entries(products).map(([key, title]) => (
          <Fragment key={key}>
            <div className="image-matrix-label">{title}</div>
            {columns.map((column) => {
              const hash = column.images?.[key];
              return (
                <div className="image-matrix-cell" key={column.label + key}>
                  {hash ? (
                    <button
                      className="image-button"
                      onClick={() => onOpen(`/api/images/${hash}`)}
                      aria-label={`放大${column.label}${title}`}
                    >
                      <img
                        src={`/api/images/${hash}`}
                        loading="lazy"
                        alt={`${column.label}${title}合成气象图`}
                      />
                    </button>
                  ) : (
                    <div className="image-placeholder">尚未生成</div>
                  )}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

export function ImageComparison({
  current,
  historical,
  onOpen,
}: {
  current?: Images;
  historical?: Images;
  onOpen: (url: string) => void;
}) {
  return (
    <div className="image-grid">
      {Object.entries(products).map(([key, title]) => (
        <section className="image-pair" key={key}>
          <h4>{title}</h4>
          {[
            ["当前窗口", current?.[key]],
            ["历史窗口", historical?.[key]],
          ].map(([label, hash]) => (
            <div key={label}>
              <span>{label}</span>
              {hash ? (
                <button
                  className="image-button"
                  onClick={() => onOpen(`/api/images/${hash}`)}
                  aria-label={`放大${label}${title}`}
                >
                  <img
                    src={`/api/images/${hash}`}
                    loading="lazy"
                    alt={`${label}${title}合成气象图`}
                  />
                </button>
              ) : (
                <div className="image-placeholder">尚未生成</div>
              )}
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
