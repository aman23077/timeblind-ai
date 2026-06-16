export type UserDetail = {
  id: string;
  email: string;
  display_name: string;
  time_zone: string;
  preferred_nudge_style: string;
  model_profile: {
    chronotype: string;
    optimal_session_minutes: number;
    break_recovery_minutes: number;
  };
};

export type EventPlanResponse = {
  event_title: string;
  ready_by: string;
  leave_by: string;
  prep_start_at: string;
  total_prep_minutes: number;
  steps: Array<{
    kind: string;
    title: string;
    start_at: string;
    end_at: string;
    minutes: number;
  }>;
  nudges: Array<{
    trigger_at: string;
    message: string;
    severity: string;
  }>;
  risk: {
    level: string;
    reason: string;
  };
};

export type TaskDecompositionResponse = {
  task_title: string;
  urgency: string;
  base_estimate_minutes: number;
  personalized_estimate_minutes: number;
  prediction_confidence: string;
  personalization_multiplier: number;
  available_minutes: number;
  fit_status: "fits" | "tight" | "overflow";
  overflow_minutes: number;
  guidance: string;
  total_suggested_minutes: number;
  steps: Array<{
    title: string;
    suggested_minutes: number;
    order: number;
    rationale: string;
  }>;
};

export type TaskSummary = {
  id: string;
  title: string;
  status: string;
  deadline_at: string | null;
  difficulty: string;
  quantity_value: number | null;
  estimated_minutes: number | null;
  actual_minutes: number | null;
  task_type: string;
  created_at: string;
  updated_at: string;
};

export type TaskDetail = TaskSummary & {
  user_id: string;
  goal_id: string | null;
  description: string;
  priority: string;
  difficulty: string;
  quantity_value: number | null;
  created_at: string;
  updated_at: string;
  steps: Array<{
    id: string;
    task_id: string;
    title: string;
    description: string;
    order_index: number;
    suggested_minutes: number;
    status: string;
    rationale: string;
    created_at: string;
    updated_at: string;
  }>;
  dependencies: Array<{
    id: string;
    task_id: string;
    depends_on_task_id: string;
    dependency_kind: string;
    created_at: string;
    updated_at: string;
  }>;
};

export type SessionRecord = {
  id: string;
  user_id: string;
  task_id: string | null;
  time_block_id: string | null;
  started_at: string;
  ended_at: string | null;
  actual_start: string | null;
  actual_end: string | null;
  elapsed_minutes: number | null;
  delay_minutes: number;
  overrun_minutes: number;
  attention_state: string;
  energy_level: string;
  difficulty_feedback: string;
  feedback_reasons: string;
  feedback_notes: string;
  notes: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type ScheduleGenerationResponse = {
  id: string;
  user_id: string;
  plan_date: string;
  status: string;
  generated_by: string;
  created_at: string;
  updated_at: string;
  time_blocks: Array<{
    id: string;
    schedule_id: string;
    user_id: string;
    task_id: string | null;
    event_id: string | null;
    title: string;
    kind: string;
    start_at: string;
    end_at: string;
    planned_duration_minutes: number | null;
    risk_level: string | null;
    risk_buffer_minutes: number | null;
    risk_reason: string | null;
    actual_start: string | null;
    actual_end: string | null;
    delay_minutes: number;
    overrun_minutes: number;
    buffer_before_minutes: number;
    buffer_after_minutes: number;
    status: string;
    created_at: string;
    updated_at: string;
  }>;
  unscheduled_tasks?: Array<{
    task_id: string;
    title: string;
    estimated_minutes: number;
    reason: string;
  }>;
};

export type ScheduleRecoveryResponse = {
  schedule: Omit<ScheduleGenerationResponse, "unscheduled_tasks">;
  next_time_block: ScheduleGenerationResponse["time_blocks"][number] | null;
  suggested_break_minutes: number;
  message: string;
  rescheduled: boolean;
  deferred_tasks: Array<{
    task_id: string;
    title: string;
    estimated_minutes: number;
    reason: string;
  }>;
};

export type InsightsResponse = {
  window: {
    period: string;
    anchor_date: string;
    window_start: string;
    window_end: string;
  };
  summary: {
    completed_tasks: number;
    completed_sessions: number;
    completed_blocks: number;
    missed_blocks: number;
    average_prediction_delta_minutes: number;
    average_prediction_delta_percent: number;
    average_delay_minutes: number;
    average_overrun_minutes: number;
    top_friction_reason: string | null;
  };
  leakage: {
    observed_drift_minutes: number;
    average_drift_minutes: number;
    drift_rate_percent: number;
    delayed_blocks: number;
    overrun_blocks: number;
    focus_drift_sessions: number;
    top_observed_signal: string | null;
    predicted_risk_level: string;
    predicted_risk_score: number;
    predicted_risk_reason: string;
  };
  review_narrative: string;
  recommended_actions: string[];
  top_insights: Array<{
    title: string;
    detail: string;
    metric_label: string;
    metric_value: string;
    category: string;
  }>;
  task_type_breakdown: Array<{
    task_type: string;
    completed_tasks: number;
    average_estimated_minutes: number;
    average_actual_minutes: number;
    average_delta_minutes: number;
    average_delay_minutes: number;
    average_overrun_minutes: number;
  }>;
  feedback_breakdown: Array<{
    reason: string;
    count: number;
  }>;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers ?? {})
    },
    cache: "no-store"
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function ensureUser(payload: {
  email: string;
  display_name: string;
  time_zone: string;
  preferred_nudge_style: string;
}) {
  return request<UserDetail>("/api/v1/users/ensure", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listTasks(userId: string) {
  return request<TaskSummary[]>(`/api/v1/tasks?user_id=${encodeURIComponent(userId)}`);
}

export async function getTask(taskId: string) {
  return request<TaskDetail>(`/api/v1/tasks/${taskId}`);
}

export async function listEvents(userId: string) {
  return request<Array<{ id: string; title: string; start_at: string; location: string }>>(
    `/api/v1/events?user_id=${encodeURIComponent(userId)}`
  );
}

export async function createTask(payload: Record<string, unknown>) {
  return request<{ id: string }>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function updateTask(taskId: string, payload: Record<string, unknown>) {
  return request<TaskSummary>(`/api/v1/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function addTaskStep(taskId: string, payload: Record<string, unknown>) {
  return request(`/api/v1/tasks/${taskId}/steps`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function decomposeTask(payload: Record<string, unknown>) {
  return request<TaskDecompositionResponse>("/api/v1/tasks/decompose", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function createEvent(payload: Record<string, unknown>) {
  return request<{ id: string }>("/api/v1/events", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function addPrepItem(eventId: string, payload: Record<string, unknown>) {
  return request(`/api/v1/events/${eventId}/prep-items`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function prepareStoredEvent(eventId: string) {
  return request<EventPlanResponse>(`/api/v1/events/${eventId}/prepare-plan`, {
    method: "POST"
  });
}

export async function createSession(payload: Record<string, unknown>) {
  return request<SessionRecord>("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listSessions(userId: string, taskId?: string, timeBlockId?: string) {
  const params = new URLSearchParams({ user_id: userId });
  if (taskId) {
    params.set("task_id", taskId);
  }
  if (timeBlockId) {
    params.set("time_block_id", timeBlockId);
  }

  return request<SessionRecord[]>(`/api/v1/sessions?${params.toString()}`);
}

export async function endSession(sessionId: string, payload: Record<string, unknown>) {
  return request<SessionRecord>(`/api/v1/sessions/${sessionId}/end`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function generateSchedule(payload: Record<string, unknown>) {
  return request<ScheduleGenerationResponse>("/api/v1/schedules/generate", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getSchedule(scheduleId: string) {
  return request<ScheduleGenerationResponse>(`/api/v1/schedules/${scheduleId}`);
}

export async function getTimeBlock(timeBlockId: string) {
  return request<ScheduleGenerationResponse["time_blocks"][number]>(`/api/v1/schedules/time-blocks/${timeBlockId}`);
}

export async function startTimeBlockSession(timeBlockId: string, payload: Record<string, unknown>) {
  return request<{
    time_block: ScheduleGenerationResponse["time_blocks"][number];
    session: SessionRecord;
  }>(`/api/v1/schedules/time-blocks/${timeBlockId}/start`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getInsights(userId: string, period = "week", anchorDate?: string) {
  const params = new URLSearchParams({ user_id: userId, period });
  if (anchorDate) {
    params.set("anchor_date", anchorDate);
  }
  return request<InsightsResponse>(`/api/v1/insights?${params.toString()}`);
}

export async function recoverScheduleFromBlock(timeBlockId: string, payload: Record<string, unknown>) {
  return request<ScheduleRecoveryResponse>(`/api/v1/schedules/time-blocks/${timeBlockId}/recover`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}
