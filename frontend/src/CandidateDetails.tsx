import { useState } from "react";
import { ArrowUpRight } from "lucide-react";
import type { Task, Candidate } from "./types";
import {
  gridNames,
  pollutants,
  formatScore,
  LineChart,
  ImageComparison,
} from "./visualizations";
export function CandidateDetails({
  task,
  selected,
  onOpen,
}: {
  task: Task;
  selected: Candidate;
  onOpen: (url: string) => void;
}) {
  const [detailTab, setDetailTab] = useState("comparison");
  const [pollutant, setPollutant] = useState(0);
  const [grid, setGrid] = useState(4);
  const [relativeDay, setRelativeDay] = useState(0);
  const currentSeries =
    task.current_values?.map((day) => day[grid][pollutant]) || [];
  const historicalSeries = selected.historical_values.map(
    (day) => day[grid][pollutant],
  );
  return (
    <section className="panel detail-panel">
      <div className="detail-heading">
        <div>
          <div className="eyebrow">HISTORICAL ANALOGUE</div>
          <h2>
            {selected.history_start_date}{" "}
            <span>— {selected.history_end_date}</span>
          </h2>
        </div>
        {selected.final_rank === 1 && <span className="best-badge">TOP 1</span>}
      </div>
      <div className="score-grid">
        <div>
          <span>污染物精排</span>
          <strong>{formatScore(selected.fine_pollutant_score)}</strong>
          <small>最终权重 60%</small>
        </div>
        <div>
          <span>气象数值</span>
          <strong>{formatScore(selected.meteorology_score)}</strong>
          <small>最终权重 20%</small>
        </div>
        <div>
          <span>图像复核</span>
          <strong>{formatScore(selected.image_score)}</strong>
          <small>最终权重 20%</small>
        </div>
        <div className="total-score">
          <span>最终综合</span>
          <strong>{formatScore(selected.final_score)}</strong>
          <small>
            {selected.final_rank ? "已完成排序" : "待复核 / 未定名次"}
          </small>
        </div>
      </div>
      <div className="detail-tabs">
        {[
          ["comparison", "污染物对比"],
          ["weather", "气象四图"],
          ["evidence", "评分证据"],
          ["residual", "历史误差"],
        ].map(([key, title]) => (
          <button
            className={detailTab === key ? "active" : ""}
            key={key}
            onClick={() => setDetailTab(key)}
          >
            {title}
          </button>
        ))}
      </div>
      {detailTab === "comparison" ? (
        <div className="comparison">
          <div className="chart-controls">
            <div className="pill-group">
              {pollutants.map((name, index) => (
                <button
                  className={pollutant === index ? "active" : ""}
                  key={name}
                  onClick={() => setPollutant(index)}
                >
                  {name}
                </button>
              ))}
            </div>
            <label>
              格子
              <select
                value={grid}
                onChange={(e) => setGrid(Number(e.target.value))}
              >
                {gridNames.map((name, index) => (
                  <option value={index} key={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="chart-title">
            <h3>
              {gridNames[grid]}格 · {pollutants[pollutant]} <small>μg/m³</small>
            </h3>
            <div className="legend">
              <span>当前预测</span>
              <span>历史真实</span>
            </div>
          </div>
          <LineChart
            current={currentSeries}
            historical={historicalSeries}
            dates={task!.dates}
          />
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>相对日</th>
                  {task!.dates.map((day, i) => (
                    <th key={day}>D{i + 1}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>当前预测</td>
                  {currentSeries.map((v, i) => (
                    <td key={i}>{v.toFixed(1)}</td>
                  ))}
                </tr>
                <tr>
                  <td>历史真实</td>
                  {historicalSeries.map((v, i) => (
                    <td key={i}>{v.toFixed(1)}</td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
          <section className="daily-labels">
            <h3>
              逐日检索标签 · {gridNames[grid]}格 {pollutants[pollutant]}
            </h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>相对日</th>
                    <th>来源</th>
                    <th>评价浓度</th>
                    <th>分指数</th>
                    <th>档位</th>
                    <th>超检索阈值</th>
                  </tr>
                </thead>
                <tbody>
                  {task.dates.flatMap((day, index) =>
                    [
                      task.current_labels?.[index]?.[grid]?.[pollutant],
                      selected.historical_labels?.[index]?.[grid]?.[pollutant],
                    ].map(
                      (label, side) =>
                        label && (
                          <tr key={`${day}-${side}`}>
                            <td>D{index + 1}</td>
                            <td>{side ? "历史真实" : "当前预测"}</td>
                            <td>{label.evaluation_concentration}</td>
                            <td>{label.air_quality_subindex}</td>
                            <td>
                              {
                                [
                                  "0—50",
                                  "51—100",
                                  "101—150",
                                  "151—200",
                                  "201—300",
                                  "大于300",
                                ][label.band]
                              }
                            </td>
                            <td>
                              {label.is_above_threshold ? "是" : "否"}
                              {label.is_above_index_table ? " · 超表范围" : ""}
                            </td>
                          </tr>
                        ),
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </section>
          <div className="process-summary">
            {[
              task?.current_features?.[grid * 4 + pollutant],
              selected.historical_features[grid * 4 + pollutant],
            ].map(
              (feature, index) =>
                feature && (
                  <div key={index}>
                    <span>{index ? "历史过程" : "当前过程"}</span>
                    <strong>
                      {feature.pattern}
                      {feature.has_stable_stage ? " · 含平稳阶段" : ""}
                    </strong>
                    <small>
                      窗口最高 D{feature.peak_positions.join("/D")} · 超阈值{" "}
                      {feature.exceedance_days} 天 · 最长连续{" "}
                      {feature.longest_run} 天
                    </small>
                  </div>
                ),
            )}
          </div>
          <div className="grid-heading">
            <h3>污染物九宫格</h3>
            <label>
              相对日
              <select
                value={relativeDay}
                onChange={(e) => setRelativeDay(Number(e.target.value))}
              >
                {task!.dates.map((day, i) => (
                  <option value={i} key={day}>
                    D{i + 1} · {day}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="spatial-grids">
            {[task!.current_values!, selected.historical_values].map(
              (values, index) => (
                <div key={index}>
                  <h4>{index ? "历史真实" : "当前预测"}</h4>
                  <div className="nine-grid">
                    {gridNames.map((name, cell) => (
                      <button
                        className={cell === grid ? "selected" : ""}
                        key={name}
                        onClick={() => setGrid(cell)}
                      >
                        <span>{name}</span>
                        <strong>
                          {values[relativeDay]?.[cell][pollutant].toFixed(1)}
                        </strong>
                      </button>
                    ))}
                  </div>
                </div>
              ),
            )}
          </div>
        </div>
      ) : detailTab === "weather" ? (
        <div className="weather-content">
          <p className="muted">
            同类图使用统一范围与色标；点击放大。星号为上海位置。
          </p>
          <ImageComparison
            current={task?.current_images}
            historical={selected.images}
            onOpen={onOpen}
          />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>相对日</th>
                  <th>当前中心格气象标签</th>
                  <th>历史中心格气象标签</th>
                </tr>
              </thead>
              <tbody>
                {task?.dates.map((day, i) => (
                  <tr key={day}>
                    <td>D{i + 1}</td>
                    <td>{task.current_weather_labels?.[i].join(" / ")}</td>
                    <td>{selected.historical_weather_labels[i].join(" / ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : detailTab === "evidence" ? (
        <div className="evidence-content">
          <h3>分项计算</h3>
          <dl className="evidence-scores">
            {[
              ["污染物浓度", selected.numeric_score],
              ["日档位", selected.daily_band_score],
              ["变化方向", selected.transition_score],
              ["污染物粗筛", selected.coarse_pollutant_score],
              ["气象标签", selected.meteorology_label_score],
              ["联合粗筛", selected.coarse_score],
              ["详细过程", selected.process_score],
              ["数值精排", selected.fine_score],
            ].map(([label, value]) => (
              <div key={String(label)}>
                <dt>{label}</dt>
                <dd>{formatScore(value as number | null)}</dd>
              </div>
            ))}
          </dl>
          <h3>模型复核证据</h3>
          {selected.review ? (
            <>
              <p>{selected.review.summary}</p>
              {selected.review.days.map((day) => (
                <div className="review-day" key={day.relative_day}>
                  <strong>第 {day.relative_day} 天</strong>
                  <div className="review-scores">
                    风 {day.wind_score} · 气压 {day.pressure_score} · 温湿{" "}
                    {day.temperature_humidity_score} · 高空{" "}
                    {day.circulation_500_score}
                  </div>
                  <p>
                    <b>相同：</b>
                    {day.similarities}
                  </p>
                  <p>
                    <b>差异：</b>
                    {day.differences}
                  </p>
                  <p>
                    <b>上海位置：</b>
                    {day.shanghai_position}
                  </p>
                </div>
              ))}
              <a
                className="text-button"
                href={`/api/reviews/${selected.review_cache_key}`}
                target="_blank"
                rel="noreferrer"
              >
                查看原始复核记录 <ArrowUpRight size={14} />
              </a>
            </>
          ) : (
            <p className="muted">
              {selected.review_error || "该候选尚未完成模型复核。"}
            </p>
          )}
          <details>
            <summary>任务基准与排除统计</summary>
            <pre>{JSON.stringify(task?.baseline, null, 2)}</pre>
          </details>
        </div>
      ) : (
        <div className="residual-content">
          {selected.final_rank === 1 && task?.residuals ? (
            <>
              <p>{task.residuals.reason}</p>
              <p className="muted">{task.residuals.comparability_assumption}</p>
              <div className="table-scroll residual-table">
                <table>
                  <thead>
                    <tr>
                      <th>历史日期</th>
                      <th>站点</th>
                      <th>污染物</th>
                      <th>预测</th>
                      <th>真实</th>
                      <th>误差</th>
                    </tr>
                  </thead>
                  <tbody>
                    {task.residuals.rows
                      .filter(
                        (row) => row.pollutant_name === pollutants[pollutant],
                      )
                      .map((row, i) => (
                        <tr key={i}>
                          <td>{row.history_date}</td>
                          <td>{row.station_name}</td>
                          <td>{row.pollutant_name}</td>
                          <td>{row.historical_forecast.toFixed(1)}</td>
                          <td>{row.historical_observed.toFixed(1)}</td>
                          <td>
                            {row.residual > 0 ? "+" : ""}
                            {row.residual.toFixed(1)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              <label>
                污染物
                <select
                  value={pollutant}
                  onChange={(e) => setPollutant(Number(e.target.value))}
                >
                  {pollutants.map((name, i) => (
                    <option key={name} value={i}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            </>
          ) : (
            <div className="empty-small">
              历史误差仅在形成正式 Top1 后展示。
              <br />
              请在最终排序中选择第一名。
            </div>
          )}
        </div>
      )}
    </section>
  );
}
