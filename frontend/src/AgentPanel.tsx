import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";

type Evidence = { evidence_id: string; tool: string; data: Record<string, unknown> };
type Report = {
  specialist_name: string; status: string;
  findings: { text: string; evidence_ids: string[] }[];
  limitations: string[]; evidence: Evidence[];
};
type Run = {
  run_id: string; conversation_id: string; status: string; question: string;
  result: { answer?: string; reports?: Report[] };
};
const titles: Record<string, string> = { pollution: "污染过程", meteorology: "气象背景", matching: "案例与偏差" };
const statusNames: Record<string, string> = {
  queued: "等待分析", running: "正在分析", completed: "分析完成", partial: "部分完成",
  failed: "未能完成", cancelled: "已取消", timed_out: "达到时限", interrupted: "服务重启中断",
};
const terminal = new Set(["completed", "partial", "failed", "cancelled", "timed_out", "interrupted"]);
const examples = [
  ["污染风险", "当前预测中哪些九宫格区域的污染物浓度较高？"],
  ["时空演变", "这次污染过程哪天最高，变化趋势如何？"],
  ["成因分析", "本次气象条件对污染扩散有什么影响？"],
  ["历史与偏差", "Top3历史相似过程有哪些差异，历史偏差有什么参考？"],
  ["专业知识", "什么是逆温，它如何影响污染扩散？"],
];

export function AgentPanel({ taskId }: { taskId?: string }) {
  const storageKey = "similarity-agent:" + (taskId || "knowledge");
  const [question, setQuestion] = useState("");
  const [run, setRun] = useState<Run>();
  const [reports, setReports] = useState<Report[]>([]);
  const [progress, setProgress] = useState("选择问题类型，或直接输入你的问题。");
  const [error, setError] = useState("");
  const [isSubmitting, setSubmitting] = useState(false);
  const conversation = useRef<string | undefined>(undefined);
  const isMounted = useRef(true);
  const isRunning = !!run && !terminal.has(run.status);

  useEffect(() => {
    isMounted.current = true;
    const saved = sessionStorage.getItem(storageKey);
    if (saved) api<Run>(`/api/agent/runs/${saved}`).then(value => {
      if (!isMounted.current) return;
      conversation.current = value.conversation_id;
      setRun(value); setReports(value.result.reports || []); setQuestion(value.question);
    }).catch(() => { if (isMounted.current) setError("暂时无法恢复上次分析，可以稍后刷新或重新提问。"); });
    return () => { isMounted.current = false; };
  }, [storageKey]);

  useEffect(() => {
    if (!run || terminal.has(run.status)) return;
    const source = new EventSource(`/api/agent/runs/${run.run_id}/events`);
    source.addEventListener("analysis_plan", event => {
      const data = JSON.parse((event as MessageEvent).data);
      setProgress(data.specialists.length ? `正在组织${data.specialists.map((name: string) => titles[name]).join("、")}分析` : "正在确认问题范围");
    });
    source.addEventListener("specialist_started", event => {
      const data = JSON.parse((event as MessageEvent).data);
      setProgress(`正在分析${titles[data.specialist] || "业务证据"}`);
    });
    source.addEventListener("specialist_completed", event => {
      const data = JSON.parse((event as MessageEvent).data) as Report;
      setReports(previous => [...previous.filter(item => item.specialist_name !== data.specialist_name), data]);
    });
    source.addEventListener("run_finished", event => {
      const data = JSON.parse((event as MessageEvent).data);
      setRun(previous => previous && { ...previous, status: data.status, result: data.result });
      setReports(data.result.reports || []);
      setProgress(statusNames[data.status]); setError(""); source.close();
    });
    source.onerror = () => setProgress("连接中断，正在自动恢复分析进度…");
    return () => source.close();
  }, [run?.run_id, run?.status]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (question.trim().length < 2 || isRunning || isSubmitting) return;
    setSubmitting(true); setError(""); setReports([]);
    try {
      const created = await api<Run>("/api/agent/runs", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim(), task_id: taskId || null, conversation_id: conversation.current || null }),
      });
      sessionStorage.setItem(storageKey, created.run_id);
      if (!isMounted.current) return;
      conversation.current = created.conversation_id;
      setRun(created); setProgress("已开始分析，正在核对可用证据。");
    } catch (caught) { if (isMounted.current) setError((caught as Error).message); }
    finally { if (isMounted.current) setSubmitting(false); }
  }

  async function cancel() {
    if (!run) return;
    try { const value = await api<Run>(`/api/agent/runs/${run.run_id}/cancel`, { method: "POST" }); setRun(value); setReports(value.result.reports || []); }
    catch (caught) { setError((caught as Error).message); }
  }

  return <section className="agent-panel" aria-label="空气质量预报助手">
    <div className="agent-heading"><div><span className="agent-eyebrow">FORECAST ASSISTANT</span><h2>空气质量预报助手</h2></div>
      <span>{taskId ? "已关联当前匹配任务" : "未选择任务 · 可咨询专业知识"}</span></div>
    <p>结合污染过程、天气背景与历史案例分析。所有建议仅供预报员参考。</p>
    <div className="agent-examples">{examples.map(([label, text]) => <button key={label} type="button" disabled={isRunning} onClick={() => setQuestion(text)}>{label}</button>)}</div>
    <form onSubmit={submit}>
      <label htmlFor="agent-question">你的问题</label>
      <textarea id="agent-question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} rows={3}
        placeholder="例如：当前有哪些污染风险，天气原因是什么，历史案例能提供什么偏差参考？" disabled={isRunning || isSubmitting} />
      <div className="agent-controls"><span role="status">{run && terminal.has(run.status) ? statusNames[run.status] : progress}</span>
        {isRunning ? <button type="button" onClick={cancel}>停止分析</button> : <button type="submit" disabled={isSubmitting || question.trim().length < 2}>{isSubmitting ? "正在提交…" : "开始分析"}</button>}</div>
    </form>
    {error && <p role="alert" className="agent-error">{error}</p>}
    {run?.result.answer && <div className="agent-answer">{run.result.answer}</div>}
    <div className="agent-reports">{reports.map(report => <article key={report.specialist_name}>
      <h3>{titles[report.specialist_name]} <small>{statusNames[report.status]}</small></h3>
      {report.findings.map((finding, index) => <p key={index}>{finding.text}</p>)}
      {report.limitations.map((item, index) => <p className="agent-limitation" key={index}>{item}</p>)}
      {report.evidence.length > 0 && <details><summary>查看分析依据（{report.evidence.length}项）</summary>
        {report.evidence.map(item => <div className="agent-evidence" key={item.evidence_id}><strong>{item.evidence_id}</strong>
          <pre>{JSON.stringify(item.data, null, 2)}</pre></div>)}</details>}
    </article>)}</div>
  </section>;
}
