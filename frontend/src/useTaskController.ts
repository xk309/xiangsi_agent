import { useCallback, useEffect, useState } from "react";
import type { Task, TaskSummary } from "./types";
import { api } from "./api";

export function useTaskController() {
  const [task, setTask] = useState<Task>();
  const [history, setHistory] = useState<TaskSummary[]>([]);
  const [error, setError] = useState("");
  const running = task?.status === "RUNNING";
  const refreshHistory = useCallback(
    () =>
      api<TaskSummary[]>("/api/tasks")
        .then(setHistory)
        .catch(() => setError("无法读取历史任务，请检查服务连接")),
    [],
  );
  const loadTask = useCallback(async (id: string) => {
    setError("");
    try {
      const result = await api<Task>(`/api/tasks/${id}`);
      setTask(result);
      window.history.replaceState(null, "", `?task=${id}`);
    } catch (error) {
      setError((error as Error).message);
    }
  }, []);
  useEffect(() => {
    refreshHistory();
    const id = new URLSearchParams(location.search).get("task");
    if (id) loadTask(id);
  }, [refreshHistory, loadTask]);
  useEffect(() => {
    if (!task || !running) return;
    const controller = new AbortController();
    let isFetching = false;
    const timer = setInterval(async () => {
      if (isFetching) return;
      isFetching = true;
      try {
        const result = await api<Task>(`/api/tasks/${task.task_id}`, {
          signal: controller.signal,
        });
        setTask(result);
        if (result.status !== "RUNNING") refreshHistory();
      } catch (error) {
        if (!controller.signal.aborted) setError((error as Error).message);
      } finally {
        isFetching = false;
      }
    }, 1800);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [task?.task_id, running, refreshHistory]);
  return { task, history, error, setError, running, refreshHistory, loadTask };
}
