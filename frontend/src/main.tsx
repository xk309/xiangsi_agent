import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronRight,
  Database,
  FileClock,
  FlaskConical,
  Layers3,
  LoaderCircle,
  MapPin,
  Search,
  Wind,
  X,
} from "lucide-react";
import type { Batch, Health } from "./types";
import "./style.css";

import { statusNames, formatScore } from "./visualizations";
import { api } from "./api";
import { CandidateDetails } from "./CandidateDetails";
import { useTaskController } from "./useTaskController";

function App() {
  const [health, setHealth] = useState<Health>();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [batchIndex, setBatchIndex] = useState(0);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [shouldReview, setShouldReview] = useState(true);
  const {
    task,
    history,
    error,
    setError,
    running,
    refreshHistory,
    loadTask: fetchTask,
  } = useTaskController();
  const [isSubmitting, setSubmitting] = useState(false);
  const [view, setView] = useState("match");
  const [stage, setStage] = useState("fine");
  const [selectedDate, setSelectedDate] = useState("");
  const [openImage, setOpenImage] = useState("");
  const chosenBatch = batches[batchIndex];
  useEffect(() => {
    api<Health>("/api/health")
      .then(setHealth)
      .catch(() => setError("无法连接服务"));
    api<Batch[]>("/api/batches")
      .then((data) => {
        setBatches(data);
        if (data.length) {
          setStart(data[0].dates[0]);
          setEnd(data[0].dates[Math.min(2, data[0].dates.length - 1)]);
        }
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    if (!openImage) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenImage("");
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [openImage]);
  function loadTask(id: string) {
    setSelectedDate("");
    setView("match");
    fetchTask(id);
  }
  async function startTask() {
    if (!chosenBatch) return;
    setSubmitting(true);
    setError("");
    try {
      const result = await api<{ task_id: string }>("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          forecast_start_time: chosenBatch.forecast_start_time,
          window_start_date: start,
          window_end_date: end,
          should_review: shouldReview,
        }),
      });
      loadTask(result.task_id);
      refreshHistory();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }
  function chooseBatch(index: number) {
    setBatchIndex(index);
    setStart(batches[index].dates[0]);
    setEnd(batches[index].dates[Math.min(2, batches[index].dates.length - 1)]);
  }
  const allCandidates = task?.candidates || [];
  const successful = allCandidates
    .filter((c) => c.final_rank)
    .sort((a, b) => a.final_rank! - b.final_rank!);
  const candidates =
    stage === "final"
      ? successful
      : stage === "coarse"
        ? [...allCandidates].sort((a, b) => a.coarse_rank - b.coarse_rank)
        : allCandidates.filter((c) => c.fine_rank <= 10);
  const selected =
    allCandidates.find((c) => c.history_start_date === selectedDate) ||
    candidates[0];
  const length =
    start && end
      ? Math.round((Date.parse(end) - Date.parse(start)) / 86400000) + 1
      : 0;
  const validSelection =
    chosenBatch &&
    length >= 1 &&
    length <= 7 &&
    Array.from({ length }, (_, i) =>
      new Date(Date.parse(start) + i * 86400000).toISOString().slice(0, 10),
    ).every((d) => chosenBatch.dates.includes(d));
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/">
          <span className="brand-symbol">
            <Wind size={24} />
          </span>
          <div>
            相似过程<span>SHANGHAI · AIR INSIGHT</span>
          </div>
        </a>
        <div className="nav-label">研究工作台</div>
        <button
          className={view === "match" ? "nav-item active" : "nav-item"}
          onClick={() => setView("match")}
        >
          <Layers3 size={19} />
          过程匹配
          <ChevronRight size={15} />
        </button>
        <button
          className={view === "history" ? "nav-item active" : "nav-item"}
          onClick={() => {
            setView("history");
            refreshHistory();
          }}
        >
          <FileClock size={19} />
          历史任务<span className="count">{history.length}</span>
        </button>
        <button
          className={view === "data" ? "nav-item active" : "nav-item"}
          onClick={() => setView("data")}
        >
          <Database size={19} />
          数据与模型
        </button>
        <div className="sidebar-note">
          <FlaskConical size={20} />
          <strong>2025 联调数据集</strong>
          <p>
            合成日均气象场
            <br />
            项目检索统计口径
          </p>
          <span>仅用于流程与算法验证</span>
        </div>
        <div className="sidebar-bottom">
          <span
            className={`status-dot ${health?.database_ready ? "online" : ""}`}
          />
          {health?.database_ready ? "数据库已连接" : "等待数据库连接"}
          <small>规则 V2.1</small>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <span className="breadcrumb">研究工作台</span>
            <ChevronRight size={13} />
            <span>
              {view === "history"
                ? "历史任务"
                : view === "data"
                  ? "数据与模型"
                  : "污染过程相似度匹配"}
            </span>
          </div>
          <span className="location">
            <MapPin size={14} />
            上海 · 中国标准时间
          </span>
        </header>
        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">POLLUTION PROCESS ANALOGUE</div>
              <h1>
                {view === "history"
                  ? "每一次匹配，都有迹可循"
                  : view === "data"
                    ? "数据与模型"
                    : "寻找相似的污染过程"}
              </h1>
              <p>以污染物变化与气象背景为依据，让历史案例成为可比较的参考。</p>
            </div>
            <div className="edition">
              DEVELOPMENT<span>联调版 / V2.1</span>
            </div>
          </div>
          <div className="notice">
            <FlaskConical size={17} />
            <span>
              当前使用 2025
              年固定数据。气象为合成日均场，污染物为时刻值派生指标；结果不作为正式空气质量评价。
            </span>
          </div>
          {error && (
            <div className="error" role="alert">
              {error}
              <button aria-label="关闭错误提示" onClick={() => setError("")}>
                <X size={16} />
              </button>
            </div>
          )}
          {view === "data" ? (
            <section className="panel settings-panel">
              <h2>连接状态</h2>
              <dl>
                <dt>污染物数据库</dt>
                <dd>
                  {health?.database_ready
                    ? "已连接 PolarDB"
                    : "连接失败，请检查本地 .env"}
                </dd>
                <dt>气象基础场</dt>
                <dd>{health?.weather_ready ? "NC 文件可用" : "NC 文件缺失"}</dd>
                <dt>多模态模型</dt>
                <dd>
                  {health?.model_name || "—"} ·{" "}
                  {health?.model_configured
                    ? "已配置密钥（调用可用性以任务结果为准）"
                    : "未配置密钥"}
                </dd>
                <dt>可用预测批次</dt>
                <dd>{batches.length.toLocaleString()} 个</dd>
                <dt>图片与证据</dt>
                <dd>数据库持久保存，图片按内容去重</dd>
              </dl>
              <p className="muted">
                模型名称、接口地址与数据库连接在服务端本地环境配置中维护。页面不显示密钥。
              </p>
            </section>
          ) : view === "history" ? (
            <section className="panel">
              <div className="panel-heading">
                <h2>最近的匹配任务</h2>
                <span>最多显示 50 条</span>
              </div>
              {history.length ? (
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>选择窗口</th>
                        <th>创建时间</th>
                        <th>任务状态</th>
                        <th>处理阶段</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((row) => (
                        <tr key={row.task_id}>
                          <td>
                            {row.window_start_date} → {row.window_end_date}
                          </td>
                          <td>
                            {new Date(row.created_at).toLocaleString("zh-CN")}
                          </td>
                          <td>
                            <span className="badge">
                              {statusNames[row.status]}
                            </span>
                          </td>
                          <td>{row.stage}</td>
                          <td>
                            <button
                              className="text-button"
                              onClick={() => loadTask(row.task_id)}
                            >
                              查看结果 <ArrowUpRight size={14} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="empty-small">
                  暂无历史任务，创建一次匹配后将在这里保存。
                </div>
              )}
            </section>
          ) : (
            <>
              <section className="panel query-panel">
                <div className="panel-heading">
                  <h2>
                    <CalendarDays size={19} />
                    选择匹配窗口
                  </h2>
                  <span>同一预测批次 · 连续 1—7 天</span>
                </div>
                <div className="query-fields">
                  <label className="batch-field">
                    污染物预测起报批次
                    <select
                      value={batchIndex}
                      onChange={(e) => chooseBatch(Number(e.target.value))}
                      disabled={!batches.length || running}
                    >
                      {batches.map((batch, index) => (
                        <option key={batch.forecast_start_time} value={index}>
                          {batch.forecast_start_time.replace("T", " ")}
                          {index === 0 ? " · 最新可用" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    开始日期
                    <select
                      value={start}
                      onChange={(e) => {
                        setStart(e.target.value);
                        if (e.target.value > end) setEnd(e.target.value);
                      }}
                      disabled={running}
                    >
                      {chosenBatch?.dates.map((day) => (
                        <option key={day}>{day}</option>
                      ))}
                    </select>
                  </label>
                  <span className="date-arrow">
                    <ArrowRight size={18} />
                  </span>
                  <label>
                    结束日期
                    <select
                      value={end}
                      onChange={(e) => setEnd(e.target.value)}
                      disabled={running}
                    >
                      {chosenBatch?.dates
                        .filter((day) => day >= start)
                        .map((day) => (
                          <option key={day}>{day}</option>
                        ))}
                    </select>
                  </label>
                  <button
                    className="primary-button"
                    onClick={startTask}
                    disabled={
                      !validSelection ||
                      running ||
                      isSubmitting ||
                      !health?.database_ready
                    }
                  >
                    {running || isSubmitting ? (
                      <LoaderCircle className="spin" size={18} />
                    ) : (
                      <Search size={18} />
                    )}{" "}
                    {running ? "正在匹配" : "开始匹配"}
                  </button>
                </div>
                <div className="query-footer">
                  <div className="date-chips">
                    {chosenBatch?.dates.map((day) => (
                      <span
                        key={day}
                        className={day >= start && day <= end ? "selected" : ""}
                      >
                        {day.slice(5)}
                      </span>
                    ))}
                    <small>
                      {validSelection
                        ? `已选 ${length} 天`
                        : "请选择连续且完整的日期"}
                    </small>
                  </div>
                  <label className="check-label">
                    <input
                      type="checkbox"
                      checked={shouldReview}
                      onChange={(e) => setShouldReview(e.target.checked)}
                      disabled={running}
                    />
                    启用模型四图复核
                  </label>
                </div>
              </section>
              <div className="pipeline">
                {[
                  ["01", "联合检索", "Top 50"],
                  ["02", "数值精排", "Top 10"],
                  ["03", "气象图复核", "四类空间场"],
                  ["04", "相似案例", "Top 3 / Top 1"],
                ].map(([number, title, subtitle], index) => (
                  <div
                    className={`pipeline-step ${allCandidates.length && (index < 2 || task?.status === "SUCCEEDED") ? "done" : ""}`}
                    key={number}
                  >
                    <span>
                      {allCandidates.length &&
                      (index < 2 || task?.status === "SUCCEEDED") ? (
                        <Check size={16} />
                      ) : (
                        number
                      )}
                    </span>
                    <div>
                      <strong>{title}</strong>
                      <small>{subtitle}</small>
                    </div>
                    {index < 3 && <ChevronRight size={15} />}
                  </div>
                ))}
              </div>
              {task && (
                <div className="task-progress" aria-live="polite">
                  <div>
                    <span>{statusNames[task.status]}</span>
                    <strong>{task.stage}</strong>
                    <small>{Math.round(task.progress)}%</small>
                  </div>
                  <div className="progress-track">
                    <span style={{ width: `${task.progress}%` }} />
                  </div>
                  {(task.error || task.result_message) && (
                    <p className={task.error ? "text-error" : ""}>
                      {task.error || task.result_message}
                    </p>
                  )}
                </div>
              )}
              {!allCandidates.length ? (
                <section className="empty-state">
                  <div className="orbital">
                    <div />
                    <div />
                    <div />
                    <Wind size={45} />
                  </div>
                  <div className="eyebrow">从一个时间窗口开始</div>
                  <h2>把当前预测，放进历史中比较</h2>
                  <p>
                    选定日期后，将联合比较九宫格污染物与气象背景，
                    <br />
                    逐步筛选、复核，并保留每一次匹配的依据。
                  </p>
                  <div className="empty-metrics">
                    <div>
                      <strong>54</strong>
                      <span>固定监测站</span>
                    </div>
                    <div>
                      <strong>9 × 4</strong>
                      <span>污染物格日维度</span>
                    </div>
                    <div>
                      <strong>4</strong>
                      <span>气象空间图</span>
                    </div>
                  </div>
                </section>
              ) : (
                <>
                  <div className="result-heading">
                    <div>
                      <h2>
                        匹配结果{" "}
                        <span>
                          {task?.dates[0]} — {task?.dates.at(-1)}
                        </span>
                      </h2>
                      <p>
                        符合条件 {task?.baseline?.qualified_window_count} 个窗口
                        · 去重后 {allCandidates.length} 个 · 已复核{" "}
                        {
                          allCandidates.filter((c) => c.image_score != null)
                            .length
                        }{" "}
                        个
                      </p>
                    </div>
                    <span className="score-note">
                      相似度 0—100 · 非预测准确率
                    </span>
                  </div>
                  <div className="results-layout">
                    <section className="panel candidate-panel">
                      <div
                        className="stage-tabs"
                        role="tablist"
                        aria-label="结果阶段"
                      >
                        {[
                          ["coarse", "联合 Top50"],
                          ["fine", "数值 Top10"],
                          ["final", "最终排序"],
                        ].map(([key, label]) => (
                          <button
                            role="tab"
                            aria-selected={stage === key}
                            className={stage === key ? "active" : ""}
                            onClick={() => {
                              setStage(key);
                              setSelectedDate("");
                            }}
                            key={key}
                          >
                            {label}
                          </button>
                        ))}
                      </div>
                      <div className="candidate-list">
                        {candidates.length ? (
                          candidates.map((candidate) => (
                            <button
                              key={candidate.history_start_date}
                              className={`candidate ${selected?.history_start_date === candidate.history_start_date ? "selected" : ""}`}
                              onClick={() =>
                                setSelectedDate(candidate.history_start_date)
                              }
                            >
                              <span className="rank">
                                {String(
                                  stage === "coarse"
                                    ? candidate.coarse_rank
                                    : stage === "final"
                                      ? candidate.final_rank
                                      : candidate.fine_rank,
                                ).padStart(2, "0")}
                              </span>
                              <div>
                                <strong>{candidate.history_start_date}</strong>
                                <span>至 {candidate.history_end_date}</span>
                                {candidate.is_low_similarity && (
                                  <small className="low-badge">
                                    低相似参考
                                  </small>
                                )}
                                {candidate.review_error && (
                                  <small className="low-badge">复核失败</small>
                                )}
                              </div>
                              <div className="candidate-score">
                                <strong>
                                  {formatScore(
                                    stage === "coarse"
                                      ? candidate.coarse_score
                                      : stage === "final"
                                        ? candidate.final_score
                                        : candidate.fine_score,
                                  )}
                                </strong>
                                <span>
                                  {candidate.final_rank === 1
                                    ? "最终 Top1"
                                    : "相似度"}
                                </span>
                              </div>
                            </button>
                          ))
                        ) : (
                          <div className="empty-small">
                            尚未形成完整最终排序；可查看数值候选。
                          </div>
                        )}
                      </div>
                    </section>
                    {selected && (
                      <CandidateDetails
                        key={task!.task_id}
                        task={task!}
                        selected={selected}
                        onOpen={setOpenImage}
                        onSelectCandidate={(historyStartDate) => {
                          setStage("final");
                          setSelectedDate(historyStartDate);
                        }}
                      />
                    )}
                  </div>
                </>
              )}
            </>
          )}
          <footer>
            <span>上海污染过程相似度匹配</span>
            <span>固定九宫格 · 联合检索 · 证据可追溯</span>
          </footer>
        </div>
      </main>
      {openImage && (
        <div
          className="image-modal"
          role="dialog"
          aria-modal="true"
          aria-label="气象图预览"
          onClick={() => setOpenImage("")}
        >
          <button
            className="modal-close"
            aria-label="关闭预览"
            autoFocus
            onClick={() => setOpenImage("")}
          >
            <X />
          </button>
          <img
            src={openImage}
            alt="放大的气象空间图"
            onClick={(event) => event.stopPropagation()}
          />
          <a
            href={openImage}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
          >
            在新窗口查看原图
          </a>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
