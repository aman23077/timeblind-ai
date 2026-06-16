"use client";

import Link from "next/link";
import { useEffect, useState, useTransition } from "react";
import type { FormEvent, ReactNode } from "react";

import {
  addPrepItem,
  addTaskStep,
  createEvent,
  createTask,
  decomposeTask,
  ensureUser,
  generateSchedule,
  getInsights,
  listEvents,
  listTasks,
  prepareStoredEvent,
  startTimeBlockSession
} from "../lib/api";
import type {
  EventPlanResponse,
  InsightsResponse,
  ScheduleGenerationResponse,
  TaskDecompositionResponse,
  TaskSummary,
  UserDetail
} from "../lib/api";

const SESSION_KEY = "timeblind-user";
const THEME_KEY = "timeblind-theme";

const defaultTaskForm = {
  title: "",
  deadlineAt: "",
  taskType: "assignment",
  difficulty: "medium",
  quantityValue: ""
};

const defaultEventForm = {
  title: "",
  startAt: "",
  location: "",
  commuteMinutes: 20,
  getReadyMinutes: 15,
  departureBufferMinutes: 10,
  prepItems: "Find documents:5\nPack essentials:3"
};

const defaultScheduleForm = {
  planDate: new Date().toISOString().slice(0, 10),
  windowStart: "16:00",
  windowEnd: "22:00",
  breakMinutes: 10
};

type AppPage = "dashboard" | "tasks" | "schedule" | "focus" | "review" | "settings";
type ReviewPeriod = "day" | "week" | "month" | "all";
type PendingSort = "urgency" | "deadline" | "newest" | "shortest";
type CompletedSort = "recent" | "oldest" | "longest" | "title";

const navItems: Array<{ id: AppPage; label: string; icon: string }> = [
  { id: "dashboard", label: "Dashboard", icon: "D" },
  { id: "tasks", label: "Tasks", icon: "T" },
  { id: "schedule", label: "Schedule", icon: "S" },
  { id: "focus", label: "Focus Session", icon: "F" },
  { id: "review", label: "Review", icon: "R" },
  { id: "settings", label: "Settings", icon: "G" }
];

export function TimeblindShell() {
  const [user, setUser] = useState<UserDetail | null>(null);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [events, setEvents] = useState<Array<{ id: string; title: string; start_at: string; location: string }>>([]);
  const [taskForm, setTaskForm] = useState(defaultTaskForm);
  const [eventForm, setEventForm] = useState(defaultEventForm);
  const [taskPlan, setTaskPlan] = useState<TaskDecompositionResponse | null>(null);
  const [eventPlan, setEventPlan] = useState<EventPlanResponse | null>(null);
  const [scheduleForm, setScheduleForm] = useState(defaultScheduleForm);
  const [schedulePlan, setSchedulePlan] = useState<ScheduleGenerationResponse | null>(null);
  const [insights, setInsights] = useState<InsightsResponse | null>(null);
  const [reviewPeriod, setReviewPeriod] = useState<ReviewPeriod>("week");
  const [reviewAnchorDate, setReviewAnchorDate] = useState(new Date().toISOString().slice(0, 10));
  const [pendingSort, setPendingSort] = useState<PendingSort>("urgency");
  const [completedSort, setCompletedSort] = useState<CompletedSort>("recent");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [activePage, setActivePage] = useState<AppPage>("dashboard");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isTaskModalOpen, setIsTaskModalOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = window.localStorage.getItem(SESSION_KEY);
    if (!stored) {
      return;
    }

    try {
      const parsed = JSON.parse(stored) as UserDetail;
      setUser(parsed);
    } catch {
      window.localStorage.removeItem(SESSION_KEY);
    }

    const storedTheme = window.localStorage.getItem(THEME_KEY);
    if (storedTheme === "light" || storedTheme === "dark") {
      setTheme(storedTheme);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    if (!user) {
      return;
    }

    startTransition(() => {
      void loadDashboard(user.id);
    });
  }, [reviewAnchorDate, reviewPeriod, user]);

  async function loadDashboard(userId: string) {
    try {
      const [taskItems, eventItems, insightItems] = await Promise.all([
        listTasks(userId),
        listEvents(userId),
        getInsights(userId, reviewPeriod, reviewAnchorDate)
      ]);
      setTasks(taskItems);
      setEvents(eventItems);
      setInsights(insightItems);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load dashboard.");
    }
  }

  async function handleOnboarding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isPending) {
      return;
    }

    setError(null);
    const formData = new FormData(event.currentTarget);
    const payload = {
      email: String(formData.get("email") ?? ""),
      display_name: String(formData.get("displayName") ?? ""),
      time_zone: String(formData.get("timeZone") ?? "Asia/Kolkata"),
      preferred_nudge_style: "supportive"
    };

    try {
      const nextUser = await ensureUser(payload);
      window.localStorage.setItem(SESSION_KEY, JSON.stringify(nextUser));
      setUser(nextUser);
      setActivePage("dashboard");
      await loadDashboard(nextUser.id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not start session.");
    }
  }

  async function handleTaskPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) {
      return;
    }

    setError(null);
    startTransition(() => {
      void (async () => {
        try {
          const quantityValue = parseOptionalNumber(taskForm.quantityValue);
          const plan = await decomposeTask({
            user_id: user.id,
            title: taskForm.title,
            deadline_at: taskForm.deadlineAt ? new Date(taskForm.deadlineAt).toISOString() : null,
            task_type: taskForm.taskType,
            difficulty: taskForm.difficulty,
            quantity_value: quantityValue,
            current_time: new Date().toISOString()
          });

          const task = await createTask({
            user_id: user.id,
            title: taskForm.title,
            task_type: taskForm.taskType,
            priority: "high",
            difficulty: taskForm.difficulty,
            quantity_value: quantityValue,
            estimated_minutes: plan.personalized_estimate_minutes,
            deadline_at: taskForm.deadlineAt ? new Date(taskForm.deadlineAt).toISOString() : null
          });

          for (const step of plan.steps) {
            await addTaskStep(task.id, {
              title: step.title,
              order_index: step.order,
              suggested_minutes: step.suggested_minutes,
              rationale: step.rationale
            });
          }

          setTaskPlan(plan);
          setTaskForm(defaultTaskForm);
          setIsTaskModalOpen(false);
          setActivePage("tasks");
          await loadDashboard(user.id);
        } catch (submitError) {
          setError(submitError instanceof Error ? submitError.message : "Could not create task plan.");
        }
      })();
    });
  }

  async function handleEventPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) {
      return;
    }

    setError(null);
    startTransition(() => {
      void (async () => {
        try {
          const createdEvent = await createEvent({
            user_id: user.id,
            title: eventForm.title,
            start_at: new Date(eventForm.startAt).toISOString(),
            end_at: new Date(new Date(eventForm.startAt).getTime() + 60 * 60 * 1000).toISOString(),
            location: eventForm.location,
            commute_minutes: eventForm.commuteMinutes,
            get_ready_minutes: eventForm.getReadyMinutes,
            departure_buffer_minutes: eventForm.departureBufferMinutes
          });

          const prepItems = eventForm.prepItems
            .split("\n")
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line, index) => {
              const [title, minutes = "5"] = line.split(":");
              return {
                title: title.trim(),
                minutes: Number(minutes),
                required: true,
                order_index: index + 1
              };
            });

          for (const item of prepItems) {
            await addPrepItem(createdEvent.id, item);
          }

          const plan = await prepareStoredEvent(createdEvent.id);
          setEventPlan(plan);
          setEventForm(defaultEventForm);
          await loadDashboard(user.id);
        } catch (submitError) {
          setError(submitError instanceof Error ? submitError.message : "Could not create event plan.");
        }
      })();
    });
  }

  async function handleGenerateSchedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!user) {
      return;
    }

    setError(null);
    startTransition(() => {
      void (async () => {
        try {
          const generated = await generateSchedule({
            user_id: user.id,
            plan_date: scheduleForm.planDate,
            window_start: scheduleForm.windowStart,
            window_end: scheduleForm.windowEnd,
            break_minutes: scheduleForm.breakMinutes
          });
          setSchedulePlan(generated);
          await loadDashboard(user.id);
        } catch (submitError) {
          setError(submitError instanceof Error ? submitError.message : "Could not generate schedule.");
        }
      })();
    });
  }

  async function handleStartScheduledBlock(blockId: string) {
    if (!user) {
      return;
    }

    setError(null);
    startTransition(() => {
      void (async () => {
        try {
          const { session, time_block: timeBlock } = await startTimeBlockSession(blockId, {
            user_id: user.id,
            started_at: new Date().toISOString()
          });
          setSchedulePlan((current) =>
            current
              ? {
                ...current,
                time_blocks: current.time_blocks.map((block) => (block.id === timeBlock.id ? timeBlock : block))
              }
              : current
          );

          if (session.task_id) {
            window.location.href = `/session?taskId=${encodeURIComponent(session.task_id)}&timeBlockId=${encodeURIComponent(
              timeBlock.id
            )}`;
          }
        } catch (startError) {
          setError(startError instanceof Error ? startError.message : "Could not start scheduled session.");
        }
      })();
    });
  }

  function signOut() {
    window.localStorage.removeItem(SESSION_KEY);
    setUser(null);
    setTaskPlan(null);
    setEventPlan(null);
    setSchedulePlan(null);
    setTasks([]);
    setEvents([]);
  }

  function renderTaskForm() {
    return (
      <form className="stack-form" onSubmit={handleTaskPlan}>
        <label>
          Task title
          <input
            value={taskForm.title}
            onChange={(event) => setTaskForm((current) => ({ ...current, title: event.target.value }))}
            placeholder="e.g. Solve 5 DSA problems"
            required
          />
        </label>
        <label>
          Deadline (optional)
          <input
            type="datetime-local"
            value={taskForm.deadlineAt}
            onChange={(event) => setTaskForm((current) => ({ ...current, deadlineAt: event.target.value }))}
          />
        </label>
        <div className="form-grid">
          <label>
            Task type
            <select
              value={taskForm.taskType}
              onChange={(event) => setTaskForm((current) => ({ ...current, taskType: event.target.value }))}
            >
              <option value="assignment">Assignment</option>
              <option value="reading">Reading</option>
              <option value="study">Study</option>
              <option value="writing">Writing</option>
              <option value="coding">Coding</option>
              <option value="meeting_prep">Meeting prep</option>
              <option value="admin">Admin</option>
              <option value="errand">Errand</option>
              <option value="chore">Chore</option>
              <option value="exercise">Exercise</option>
              <option value="creative">Creative</option>
              <option value="generic">Generic</option>
            </select>
          </label>
          <label>
            Difficulty
            <select
              value={taskForm.difficulty}
              onChange={(event) => setTaskForm((current) => ({ ...current, difficulty: event.target.value }))}
            >
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
        </div>
        <label>
          {getQuantityLabel(taskForm.taskType)}
          <input
            type="number"
            min={1}
            value={taskForm.quantityValue}
            onChange={(event) => setTaskForm((current) => ({ ...current, quantityValue: event.target.value }))}
            placeholder={getQuantityPlaceholder(taskForm.taskType)}
          />
        </label>
        <button type="submit" disabled={isPending}>
          {isPending ? "Planning..." : "Create task plan"}
        </button>
      </form>
    );
  }

  if (!user) {
    return (
      <div className="app-shell session-app-shell" data-theme={theme}>
        <main className="content-shell session-content-shell">
          <section className="hero-card">
            <div className="hero-copy">
              <p className="eyebrow">Timeblind AI</p>
              <h1>Build a calmer relationship with time.</h1>
              <p className="lede">
                Plan tasks, schedule realistic blocks, run focus sessions, and learn where time actually goes.
              </p>
            </div>

            <form className="onboarding-card" onSubmit={handleOnboarding}>
              <h2>Start your workspace</h2>
              <label>
                Email
                <input name="email" type="email" required placeholder="you@example.com" />
              </label>
              <label>
                Name
                <input name="displayName" required placeholder="Aarush" />
              </label>
              <label>
                Time zone
                <input name="timeZone" defaultValue="Asia/Kolkata" required />
              </label>
              <button type="submit" disabled={isPending}>
                {isPending ? "Creating your space..." : "Enter dashboard"}
              </button>
              {error ? <p className="error-banner">{error}</p> : null}
            </form>
          </section>
        </main>
      </div>
    );
  }

  const pendingTasks = sortPendingTasks(tasks.filter((task) => !isCompletedTask(task)), pendingSort);
  const completedTasks = sortCompletedTasks(tasks.filter((task) => isCompletedTask(task)), completedSort);
  const highUrgencyTasks = pendingTasks.filter((task) => getTaskUrgency(task) === "high");
  const nextTask = pendingTasks[0] ?? null;
  const shouldShowFloatingAddButton = activePage !== "dashboard" && activePage !== "tasks";

  return (
    <AppLayout
      activePage={activePage}
      completedCount={completedTasks.length}
      isSidebarCollapsed={isSidebarCollapsed}
      onSignOut={signOut}
      onNavigate={setActivePage}
      onOpenPendingTasks={() => setActivePage("tasks")}
      onToggleTheme={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
      onToggleSidebar={() => setIsSidebarCollapsed((current) => !current)}
      pendingCount={pendingTasks.length}
      theme={theme}
      user={user}
    >
      {error ? <p className="error-banner">{error}</p> : null}

      {activePage === "dashboard" ? (
        <DashboardPage
          completedTasks={completedTasks}
          events={events}
          nextTask={nextTask}
          onAddTask={() => setIsTaskModalOpen(true)}
          onStartScheduledBlock={handleStartScheduledBlock}
          onNavigate={setActivePage}
          pendingTasks={pendingTasks}
          schedulePlan={schedulePlan}
          user={user}
        />
      ) : null}

      {activePage === "tasks" ? (
        <TasksPage
          completedTasks={completedTasks}
          completedSort={completedSort}
          onAddTask={() => setIsTaskModalOpen(true)}
          onCompletedSortChange={setCompletedSort}
          onPendingSortChange={setPendingSort}
          pendingTasks={pendingTasks}
          pendingSort={pendingSort}
          taskPlan={taskPlan}
        />
      ) : null}

      {activePage === "schedule" ? (
        <SchedulePage
          eventForm={eventForm}
          eventPlan={eventPlan}
          events={events}
          isPending={isPending}
          onEventFormChange={setEventForm}
          onGenerateSchedule={handleGenerateSchedule}
          onStartScheduledBlock={handleStartScheduledBlock}
          onSubmitEvent={handleEventPlan}
          scheduleForm={scheduleForm}
          schedulePlan={schedulePlan}
          setScheduleForm={setScheduleForm}
        />
      ) : null}

      {activePage === "focus" ? <FocusPage nextTask={nextTask} pendingTasks={pendingTasks} /> : null}

      {activePage === "review" ? (
        <ReviewPage
          completedTasks={completedTasks}
          highUrgencyTasks={highUrgencyTasks}
          insights={insights}
          onReviewAnchorDateChange={setReviewAnchorDate}
          onReviewPeriodChange={setReviewPeriod}
          pendingTasks={pendingTasks}
          reviewAnchorDate={reviewAnchorDate}
          reviewPeriod={reviewPeriod}
        />
      ) : null}

      {activePage === "settings" ? <SettingsPage onToggleTheme={() => setTheme((current) => (current === "light" ? "dark" : "light"))} theme={theme} user={user} /> : null}

      {shouldShowFloatingAddButton ? (
        <button className="floating-add-button" type="button" onClick={() => setIsTaskModalOpen(true)}>
          + Add Task
        </button>
      ) : null}

      {isTaskModalOpen ? (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Add task">
          <section className="modal-card">
            <div className="panel-header">
              <div>
                <p className="eyebrow">New Task</p>
                <h2>Plan one task</h2>
                <p>Estimate it, break it down, and add it to your pending queue.</p>
              </div>
              <button className="ghost-button" type="button" onClick={() => setIsTaskModalOpen(false)}>
                Close
              </button>
            </div>
            {renderTaskForm()}
          </section>
        </div>
      ) : null}
    </AppLayout>
  );
}

function AppLayout({
  activePage,
  children,
  completedCount,
  isSidebarCollapsed,
  onNavigate,
  onSignOut,
  onOpenPendingTasks,
  onToggleTheme,
  onToggleSidebar,
  pendingCount,
  theme,
  user
}: {
  activePage: AppPage;
  children: ReactNode;
  completedCount: number;
  isSidebarCollapsed: boolean;
  onNavigate: (page: AppPage) => void;
  onSignOut: () => void;
  onOpenPendingTasks: () => void;
  onToggleTheme: () => void;
  onToggleSidebar: () => void;
  pendingCount: number;
  theme: "light" | "dark";
  user: UserDetail;
}) {
  return (
    <div className={`app-shell ${isSidebarCollapsed ? "sidebar-collapsed" : ""}`} data-theme={theme}>
      <Sidebar
        activePage={activePage}
        completedCount={completedCount}
        isCollapsed={isSidebarCollapsed}
        onNavigate={onNavigate}
        onToggleTheme={onToggleTheme}
        onToggle={onToggleSidebar}
        pendingCount={pendingCount}
        theme={theme}
      />
      <div className="app-main">
        <Header
          activePage={activePage}
          onNavigate={onNavigate}
          onOpenPendingTasks={onOpenPendingTasks}
          onSignOut={onSignOut}
          pendingCount={pendingCount}
          user={user}
        />
        <main className="content-shell">{children}</main>
      </div>
    </div>
  );
}

function Sidebar({
  activePage,
  completedCount,
  isCollapsed,
  onNavigate,
  onToggleTheme,
  onToggle,
  pendingCount,
  theme
}: {
  activePage: AppPage;
  completedCount: number;
  isCollapsed: boolean;
  onNavigate: (page: AppPage) => void;
  onToggleTheme: () => void;
  onToggle: () => void;
  pendingCount: number;
  theme: "light" | "dark";
}) {
  return (
    <aside className="app-sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">T</span>
        {!isCollapsed ? <strong>TimeBlindAI</strong> : null}
      </div>
      <button
        className="sidebar-toggle"
        type="button"
        onClick={onToggle}
        aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        title={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {isCollapsed ? ">" : "<"}
      </button>
      <nav className="sidebar-nav" aria-label="Main navigation">
        {navItems.map((item) => (
          <button
            key={item.id}
            className={activePage === item.id ? "active" : ""}
            type="button"
            onClick={() => onNavigate(item.id)}
            title={item.label}
          >
            <span>{item.icon}</span>
            {!isCollapsed ? <strong>{item.label}</strong> : null}
          </button>
        ))}
      </nav>
      {!isCollapsed ? (
        <div className="sidebar-meta">
          <button className="theme-switch" type="button" onClick={onToggleTheme}>
            <span>{theme === "light" ? "Dark mode" : "Light mode"}</span>
            <strong>{theme === "light" ? "Off" : "On"}</strong>
          </button>
          <span>{pendingCount} pending</span>
          <span>{completedCount} completed</span>
        </div>
      ) : null}
    </aside>
  );
}

function Header({
  activePage,
  onNavigate,
  onOpenPendingTasks,
  onSignOut,
  pendingCount,
  user
}: {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
  onOpenPendingTasks: () => void;
  onSignOut: () => void;
  pendingCount: number;
  user: UserDetail;
}) {
  return (
    <header className="app-header">
      <div className="header-copy">
        <p className="eyebrow">Workspace</p>
        <h1>{formatPageTitle(activePage)}</h1>
        <div className="header-shortcuts" role="navigation" aria-label="Quick pages">
          {(["tasks", "schedule", "review"] as AppPage[]).map((page) => (
            <button
              key={page}
              className={activePage === page ? "active" : ""}
              type="button"
              onClick={() => onNavigate(page)}
            >
              {formatPageTitle(page)}
            </button>
          ))}
        </div>
      </div>
      <div className="header-actions">
        <button className="status-pill status-pill-button" type="button" onClick={onOpenPendingTasks}>
          {pendingCount ? `${pendingCount} task(s) waiting` : "Queue is clear"}
        </button>
        <div className="profile-badge">
          <span>Signed in</span>
          <strong>{user.display_name}</strong>
        </div>
        <button className="ghost-button" type="button" onClick={onSignOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}

function DashboardPage({
  completedTasks,
  events,
  nextTask,
  onAddTask,
  onStartScheduledBlock,
  onNavigate,
  pendingTasks,
  schedulePlan,
  user
}: {
  completedTasks: TaskSummary[];
  events: Array<{ id: string; title: string; start_at: string; location: string }>;
  nextTask: TaskSummary | null;
  onAddTask: () => void;
  onStartScheduledBlock: (blockId: string) => void;
  onNavigate: (page: AppPage) => void;
  pendingTasks: TaskSummary[];
  schedulePlan: ScheduleGenerationResponse | null;
  user: UserDetail;
}) {
  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h2>{user.display_name}&rsquo;s workspace</h2>
          <p>Plan what matters, build a realistic day, and keep the next task easy to start.</p>
        </div>
        <button type="button" onClick={onAddTask}>
          Add task
        </button>
      </section>

      <section className="stat-grid">
        <StatCard label="Pending" value={pendingTasks.length} />
        <StatCard label="Completed" value={completedTasks.length} />
        <StatCard label="Events" value={events.length} />
        <StatCard label="Scheduled today" value={schedulePlan?.time_blocks.length ?? 0} />
      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>Today preview</h2>
              <p>{schedulePlan ? "Your latest generated time blocks." : "Generate a schedule to see your day here."}</p>
            </div>
            <button className="ghost-button" type="button" onClick={() => onNavigate("schedule")}>
              Schedule
            </button>
          </div>
          {schedulePlan?.time_blocks.length ? (
            <SchedulePreview onStartBlock={onStartScheduledBlock} schedulePlan={schedulePlan} />
          ) : (
            <EmptyState text="No schedule generated yet." />
          )}
        </article>

        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>Next task</h2>
              <p>The best next task based on urgency and what is still open.</p>
            </div>
            <button className="ghost-button" type="button" onClick={() => onNavigate("tasks")}>
              Tasks
            </button>
          </div>
          {nextTask ? <TaskCard task={nextTask} showFocusLink /> : <EmptyState text="No pending tasks. Add one to begin." />}
        </article>
      </section>
    </div>
  );
}

function TasksPage({
  completedTasks,
  completedSort,
  onAddTask,
  onCompletedSortChange,
  onPendingSortChange,
  pendingTasks,
  pendingSort,
  taskPlan
}: {
  completedTasks: TaskSummary[];
  completedSort: CompletedSort;
  onAddTask: () => void;
  onCompletedSortChange: (value: CompletedSort) => void;
  onPendingSortChange: (value: PendingSort) => void;
  pendingTasks: TaskSummary[];
  pendingSort: PendingSort;
  taskPlan: TaskDecompositionResponse | null;
}) {
  const todaysCompletedTasks = completedTasks.filter((task) => isTodayTask(task));
  const olderCompletedTasks = completedTasks.filter((task) => !isTodayTask(task));

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Tasks</p>
          <h2>Plan, queue, and launch work</h2>
          <p>Use the modal to create a plan, then open any pending task to start a focus session.</p>
        </div>
        <button type="button" onClick={onAddTask}>
          Plan one task
        </button>
      </section>

      {taskPlan ? <TaskPlanSummary taskPlan={taskPlan} /> : null}

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>Pending tasks</h2>
              <p>Keep the active queue light, then change the sort when you want a different lens on it.</p>
            </div>
            <label className="inline-control">
              Sort by
              <select value={pendingSort} onChange={(event) => onPendingSortChange(event.target.value as PendingSort)}>
                <option value="urgency">Urgency</option>
                <option value="deadline">Deadline</option>
                <option value="newest">Newest</option>
                <option value="shortest">Shortest first</option>
              </select>
            </label>
          </div>
          <TaskList emptyText="No pending tasks. Add a task to begin." showFocusLink tasks={pendingTasks} />
        </article>
        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>Completed tasks</h2>
              <p>Show today&apos;s finished work first and keep older completions tucked away as history.</p>
            </div>
            <label className="inline-control">
              Sort by
              <select
                value={completedSort}
                onChange={(event) => onCompletedSortChange(event.target.value as CompletedSort)}
              >
                <option value="recent">Most recent</option>
                <option value="oldest">Oldest</option>
                <option value="longest">Longest actual time</option>
                <option value="title">Title</option>
              </select>
            </label>
          </div>
          <TaskList emptyText="No completed tasks today yet." tasks={todaysCompletedTasks} />
          {olderCompletedTasks.length ? (
            <details className="task-history-toggle">
              <summary>Older completed tasks ({olderCompletedTasks.length})</summary>
              <TaskList emptyText="No older completed tasks." tasks={olderCompletedTasks} />
            </details>
          ) : null}
        </article>
      </section>
    </div>
  );
}

function SchedulePage({
  eventForm,
  eventPlan,
  events,
  isPending,
  onEventFormChange,
  onGenerateSchedule,
  onStartScheduledBlock,
  onSubmitEvent,
  scheduleForm,
  schedulePlan,
  setScheduleForm
}: {
  eventForm: typeof defaultEventForm;
  eventPlan: EventPlanResponse | null;
  events: Array<{ id: string; title: string; start_at: string; location: string }>;
  isPending: boolean;
  onEventFormChange: (value: typeof defaultEventForm | ((current: typeof defaultEventForm) => typeof defaultEventForm)) => void;
  onGenerateSchedule: (event: FormEvent<HTMLFormElement>) => void;
  onStartScheduledBlock: (blockId: string) => void;
  onSubmitEvent: (event: FormEvent<HTMLFormElement>) => void;
  scheduleForm: typeof defaultScheduleForm;
  schedulePlan: ScheduleGenerationResponse | null;
  setScheduleForm: (value: typeof defaultScheduleForm | ((current: typeof defaultScheduleForm) => typeof defaultScheduleForm)) => void;
}) {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Schedule</p>
          <h2>Shape today around real time</h2>
          <p>Generate a task window, then add leave-time event planning only when you need help getting somewhere on time.</p>
        </div>
      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Generate schedule</h2>
            <p>Choose a work window and the app will fit the most important tasks first, with lighter protection for drift.</p>
          </div>
          <form className="stack-form" onSubmit={onGenerateSchedule}>
            <label>
              Plan date
              <input
                type="date"
                value={scheduleForm.planDate}
                onChange={(event) => setScheduleForm((current) => ({ ...current, planDate: event.target.value }))}
                required
              />
            </label>
            <div className="form-grid">
              <label>
                Start
                <input
                  type="time"
                  value={scheduleForm.windowStart}
                  onChange={(event) => setScheduleForm((current) => ({ ...current, windowStart: event.target.value }))}
                  required
                />
              </label>
              <label>
                End
                <input
                  type="time"
                  value={scheduleForm.windowEnd}
                  onChange={(event) => setScheduleForm((current) => ({ ...current, windowEnd: event.target.value }))}
                  required
                />
              </label>
              <label>
                Break
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={scheduleForm.breakMinutes}
                  onChange={(event) => setScheduleForm((current) => ({ ...current, breakMinutes: Number(event.target.value) || 0 }))}
                />
              </label>
            </div>
            <button type="submit" disabled={isPending}>
              {isPending ? "Generating..." : "Generate schedule"}
            </button>
          </form>
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Generated preview</h2>
            <p>Review the latest plan, then start directly from a scheduled block.</p>
          </div>
          {schedulePlan ? (
            <SchedulePreview onStartBlock={onStartScheduledBlock} schedulePlan={schedulePlan} />
          ) : (
            <EmptyState text="Generate a schedule to preview time blocks." />
          )}
        </article>
      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Event backlog</h2>
            <p>Use this for appointments that need prep, commute time, or a clear leave-by target.</p>
          </div>
          <EventList events={events} />
        </article>

        <article className="panel">
          <div className="panel-header">
            <div>
              <h2>Leave-time planner</h2>
              <p>Best for classes, appointments, travel, or any outing where “be there by 5” really means starting much earlier.</p>
            </div>
          </div>
          <form className="stack-form" onSubmit={onSubmitEvent}>
            <label>
              Event title
              <input value={eventForm.title} onChange={(event) => onEventFormChange((current) => ({ ...current, title: event.target.value }))} required />
            </label>
            <label>
              Start time
              <input
                type="datetime-local"
                value={eventForm.startAt}
                onChange={(event) => onEventFormChange((current) => ({ ...current, startAt: event.target.value }))}
                required
              />
            </label>
            <label>
              Location
              <input value={eventForm.location} onChange={(event) => onEventFormChange((current) => ({ ...current, location: event.target.value }))} />
            </label>
            <div className="form-grid">
              <label>
                Commute
                <input type="number" value={eventForm.commuteMinutes} onChange={(event) => onEventFormChange((current) => ({ ...current, commuteMinutes: Number(event.target.value) }))} />
              </label>
              <label>
                Get ready
                <input type="number" value={eventForm.getReadyMinutes} onChange={(event) => onEventFormChange((current) => ({ ...current, getReadyMinutes: Number(event.target.value) }))} />
              </label>
              <label>
                Buffer
                <input
                  type="number"
                  value={eventForm.departureBufferMinutes}
                  onChange={(event) => onEventFormChange((current) => ({ ...current, departureBufferMinutes: Number(event.target.value) }))}
                />
              </label>
            </div>
            <label>
              Prep items
              <textarea rows={4} value={eventForm.prepItems} onChange={(event) => onEventFormChange((current) => ({ ...current, prepItems: event.target.value }))} />
            </label>
            <button type="submit" disabled={isPending}>
              {isPending ? "Building leave plan..." : "Create event plan"}
            </button>
          </form>
          {eventPlan ? (
            <div className="result-card">
              <div className="result-row">
                <span>Prep starts</span>
                <strong>{formatDate(eventPlan.prep_start_at)}</strong>
              </div>
              <div className="result-row">
                <span>Leave by</span>
                <strong>{formatDate(eventPlan.leave_by)}</strong>
              </div>
              <div className="result-row">
                <span>Total prep</span>
                <strong>{formatDurationMinutes(eventPlan.total_prep_minutes)}</strong>
              </div>
              <div className="result-row">
                <span>Risk</span>
                <strong>{eventPlan.risk.level}</strong>
              </div>
              <p className="subtle-copy">{eventPlan.risk.reason}</p>
              {eventPlan.steps.length ? (
                <ul className="timeline-list">
                  {eventPlan.steps.map((step) => (
                    <li key={`${step.kind}-${step.start_at}-${step.title}`}>
                      <strong>{step.title}</strong>
                      <span>
                        {formatTime(step.start_at)} to {formatTime(step.end_at)}
                      </span>
                      <p>{formatDurationMinutes(step.minutes)}</p>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </article>
      </section>
    </div>
  );
}

function FocusPage({ nextTask, pendingTasks }: { nextTask: TaskSummary | null; pendingTasks: TaskSummary[] }) {
  return (
    <div className="page-stack">
      <section className="hero-panel">
        <div>
          <p className="eyebrow">Focus</p>
          <h2>{nextTask ? nextTask.title : "Choose a pending task"}</h2>
          <p>The full timer opens on a task-specific session page so actual time and feedback stay attached.</p>
        </div>
        {nextTask ? (
          <Link className="task-link-button" href={`/session?taskId=${encodeURIComponent(nextTask.id)}`}>
            Open timer
          </Link>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Start a focus session</h2>
          <p>Select one pending task. Start/stop and post-session feedback happen on the timer page.</p>
        </div>
        <TaskList emptyText="No pending tasks available for focus." showFocusLink tasks={pendingTasks} />
      </section>
    </div>
  );
}

function ReviewPage({
  completedTasks,
  highUrgencyTasks,
  insights,
  onReviewAnchorDateChange,
  onReviewPeriodChange,
  pendingTasks,
  reviewAnchorDate,
  reviewPeriod
}: {
  completedTasks: TaskSummary[];
  highUrgencyTasks: TaskSummary[];
  insights: InsightsResponse | null;
  onReviewAnchorDateChange: (value: string) => void;
  onReviewPeriodChange: (value: ReviewPeriod) => void;
  pendingTasks: TaskSummary[];
  reviewAnchorDate: string;
  reviewPeriod: ReviewPeriod;
}) {
  const plannedTotal = completedTasks.reduce((total, task) => total + (task.estimated_minutes ?? 0), 0);
  const actualTotal = completedTasks.reduce((total, task) => total + (task.actual_minutes ?? 0), 0);

  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Review</p>
          <h2>Patterns over time</h2>
          <p>Switch between daily, weekly, monthly, and full-history views to compare drift, feedback, and planning accuracy.</p>
        </div>
        <div className="review-controls">
          <div className="period-switch" role="tablist" aria-label="Review period">
            {(["day", "week", "month", "all"] as ReviewPeriod[]).map((period) => (
              <button
                key={period}
                className={reviewPeriod === period ? "active" : ""}
                type="button"
                onClick={() => onReviewPeriodChange(period)}
              >
                {formatReviewPeriod(period)}
              </button>
            ))}
          </div>
          <label className="review-date-control">
            Anchor date
            <input
              type="date"
              value={reviewAnchorDate}
              onChange={(event) => onReviewAnchorDateChange(event.target.value)}
            />
          </label>
        </div>
      </section>

      <section className="stat-grid">
        <StatCard label="Completed" value={insights?.summary.completed_tasks ?? completedTasks.length} />
        <StatCard label="Still pending" value={pendingTasks.length} />
        <StatCard label="Average delay" value={formatDurationMinutes(insights?.summary.average_delay_minutes ?? 0)} />
        <StatCard label="Average overrun" value={formatDurationMinutes(insights?.summary.average_overrun_minutes ?? 0)} />
      </section>

      <section className="stat-grid leakage-stat-grid">
        <StatCard label="Leakage risk" value={formatRiskLevel(insights?.leakage.predicted_risk_level ?? "low")} />
        <StatCard label="Observed drift" value={formatDurationMinutes(insights?.leakage.observed_drift_minutes ?? 0)} />
        <StatCard label="Drift rate" value={formatSignedPercent(insights?.leakage.drift_rate_percent ?? 0)} />
        <StatCard label="Top leakage signal" value={insights?.leakage.top_observed_signal ?? "Still learning"} />
      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header review-panel-header">
            <div>
              <h2>Top insights</h2>
              <p>The strongest patterns the app can see from your completed work so far.</p>
            </div>
          </div>
          {insights?.top_insights.length ? (
            <ul className="insight-grid">
              {insights.top_insights.map((insight) => (
                <li key={`${insight.category}-${insight.title}`} className={`insight-card insight-${insight.category}`}>
                  <strong>{insight.title}</strong>
                  <span>
                    {insight.metric_label}: {insight.metric_value}
                  </span>
                  <p>{insight.detail}</p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="Complete a few task sessions and scheduled blocks to start seeing patterns here." />
          )}
        </article>

        <article className="panel review-hero-card">
          <div className="panel-header review-panel-header">
            <div>
              <h2>Period read</h2>
              <p>A plain-language read on the strongest pattern in this review window.</p>
            </div>
          </div>
          <div className="review-hero-copy">
            <strong>
              {insights?.review_narrative ??
                "The review becomes more useful once a few completed sessions and scheduled blocks are available."}
            </strong>
            <p className="subtle-copy">
              {insights
                ? `This is based on ${insights.summary.completed_tasks} completed task(s), ${insights.summary.completed_sessions} completed session(s), and ${insights.summary.completed_blocks} completed schedule block(s).`
                : "Keep logging work and feedback so the app can turn raw numbers into a more specific read."}
            </p>
          </div>
        </article>

        <article className="panel">
          <div className="panel-header review-panel-header">
            <div>
              <h2>What to try next</h2>
              <p>Small changes that should improve the next set of schedules and sessions.</p>
            </div>
          </div>
          {insights?.recommended_actions.length ? (
            <ul className="action-list">
              {insights.recommended_actions.map((action) => (
                <li key={action}>{action}</li>
              ))}
            </ul>
          ) : (
            <EmptyState text="Action suggestions will appear here as more execution data arrives." />
          )}
        </article>
      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header review-panel-header">
            <div>
              <h2>Time leakage</h2>
              <p>Drift is what the schedule can observe directly. Leakage risk is the app&apos;s best prediction of where time may quietly stretch again.</p>
            </div>
          </div>
          <div className="result-card">
            <div className="result-row">
              <span>Observed drift</span>
              <strong>{formatDurationMinutes(insights?.leakage.observed_drift_minutes ?? 0)}</strong>
            </div>
            <div className="result-row">
              <span>Average drift</span>
              <strong>{formatDurationMinutes(insights?.leakage.average_drift_minutes ?? 0)}</strong>
            </div>
            <div className="result-row">
              <span>Drift rate</span>
              <strong>{formatSignedPercent(insights?.leakage.drift_rate_percent ?? 0)}</strong>
            </div>
            <div className="result-row">
              <span>Delayed blocks</span>
              <strong>{insights?.leakage.delayed_blocks ?? 0}</strong>
            </div>
            <div className="result-row">
              <span>Overrun blocks</span>
              <strong>{insights?.leakage.overrun_blocks ?? 0}</strong>
            </div>
            <div className="result-row">
              <span>Focus drift sessions</span>
              <strong>{insights?.leakage.focus_drift_sessions ?? 0}</strong>
            </div>
            <div className="result-row">
              <span>Predicted leakage risk</span>
              <strong>{formatRiskLevel(insights?.leakage.predicted_risk_level ?? "low")}</strong>
            </div>
            <div className="result-row">
              <span>Predicted risk score</span>
              <strong>{insights?.leakage.predicted_risk_score ?? 0}</strong>
            </div>
            <p className="subtle-copy">
              {insights
                ? `${insights.leakage.predicted_risk_reason}${insights.leakage.top_observed_signal
                  ? ` Most common observed signal: ${insights.leakage.top_observed_signal}.`
                  : ""
                }`
                : "As you complete more scheduled blocks, the app will build a better leakage-risk prediction."}
            </p>
          </div>
        </article>

        <article className="panel">
          <div className="panel-header review-panel-header">
            <div>
              <h2>Planned vs actual</h2>
              <p>
                {insights
                  ? `${formatReviewPeriod(reviewPeriod)} view ending ${formatShortDate(insights.window.anchor_date)}.`
                  : "Early progress overview from completed tasks."}
              </p>
            </div>
          </div>
          <div className="result-card">
            <div className="result-row">
              <span>Planned</span>
              <strong>{formatDurationMinutes(plannedTotal)}</strong>
            </div>
            <div className="result-row">
              <span>Actual</span>
              <strong>{formatDurationMinutes(actualTotal)}</strong>
            </div>
            <div className="result-row">
              <span>Difference</span>
              <strong>{formatDelta(plannedTotal, actualTotal)}</strong>
            </div>
          </div>
        </article>

      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Task-type breakdown</h2>
            <p>Which kinds of work are drifting most from plan.</p>
          </div>
          {insights?.task_type_breakdown.length ? (
            <ul className="compact-list">
              {insights.task_type_breakdown.map((item) => (
                <li key={item.task_type}>
                  <strong>{formatTaskType(item.task_type)}</strong>
                  <span>{item.completed_tasks} completed task(s)</span>
                  <p>
                    Planned {formatDurationMinutes(item.average_estimated_minutes)} | Actual{" "}
                    {formatDurationMinutes(item.average_actual_minutes)} | Drift{" "}
                    {formatSignedDuration(item.average_delta_minutes)}
                  </p>
                  <p>
                    Delay {formatDurationMinutes(item.average_delay_minutes)} | Overrun{" "}
                    {formatDurationMinutes(item.average_overrun_minutes)}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="No task-type patterns yet." />
          )}
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Feedback patterns</h2>
            <p>What tends to come up when work runs differently than expected.</p>
          </div>
          {insights?.feedback_breakdown.length ? (
            <ul className="compact-list feedback-list">
              {insights.feedback_breakdown.map((item) => (
                <li key={item.reason}>
                  <strong>{item.reason}</strong>
                  <span>{item.count} session(s)</span>
                  <p>
                    {item.reason === insights.summary.top_friction_reason
                      ? "This is the most common friction signal in your recent feedback."
                      : "This reason has shown up often enough to be worth tracking."}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState text="Session feedback will show up here after a few completed runs." />
          )}
        </article>
      </section>

      <section className="dashboard-grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Completed tasks</h2>
            <p>Finished work that now contributes to learning.</p>
          </div>
          <TaskList emptyText="No completed tasks yet." tasks={completedTasks} />
        </article>

        <article className="panel">
          <div className="panel-header">
            <h2>Review summary</h2>
            <p>Quick markers for prediction accuracy and schedule execution.</p>
          </div>
          <div className="result-card">
            <div className="result-row">
              <span>High urgency pending</span>
              <strong>{highUrgencyTasks.length}</strong>
            </div>
            <div className="result-row">
              <span>Actual logged</span>
              <strong>{formatDurationMinutes(actualTotal)}</strong>
            </div>
            <div className="result-row">
              <span>Average prediction drift</span>
              <strong>{formatSignedDuration(insights?.summary.average_prediction_delta_minutes ?? 0)}</strong>
            </div>
            <div className="result-row">
              <span>Prediction drift %</span>
              <strong>{formatSignedPercent(insights?.summary.average_prediction_delta_percent ?? 0)}</strong>
            </div>
            <div className="result-row">
              <span>Missed blocks</span>
              <strong>{insights?.summary.missed_blocks ?? 0}</strong>
            </div>
            <p className="subtle-copy">
              {insights?.summary.top_friction_reason
                ? `Most common friction signal: ${insights.summary.top_friction_reason}.`
                : "Keep running tasks through the scheduler and feedback prompt to make this review sharper."}
            </p>
          </div>
        </article>
      </section>
    </div>
  );
}

function SettingsPage({
  onToggleTheme,
  theme,
  user
}: {
  onToggleTheme: () => void;
  theme: "light" | "dark";
  user: UserDetail;
}) {
  return (
    <div className="page-stack">
      <section className="page-heading">
        <div>
          <p className="eyebrow">Settings</p>
          <h2>Keep the workspace comfortable</h2>
          <p>Appearance and planning preferences live here, along with the profile details the app is using right now.</p>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Preferences</h2>
          <p>A cleaner view of the settings the app is already learning from.</p>
        </div>
        <div className="settings-grid">
          <article className="stat-card profile-card">
            <span>Profile</span>
            <strong>{user.display_name}</strong>
            <p>{user.email}</p>
          </article>
          <article className="stat-card">
            <span>Appearance</span>
            <strong>{theme === "light" ? "Light" : "Dark"}</strong>
            <p>{theme === "light" ? "Bright and airy across the whole app." : "High-contrast, calmer late-night mode."}</p>
            <button className="ghost-button" type="button" onClick={onToggleTheme}>
              Switch to {theme === "light" ? "dark" : "light"}
            </button>
          </article>
          <article className="stat-card">
            <span>Focus rhythm</span>
            <strong>{user.model_profile.optimal_session_minutes}m</strong>
            <p>The session length the app currently treats as your default healthy block.</p>
          </article>
          <article className="stat-card">
            <span>Break recovery</span>
            <strong>{user.model_profile.break_recovery_minutes}m</strong>
            <p>The reset window used when the schedule needs a gentler recovery before the next block.</p>
          </article>
          <article className="stat-card">
            <span>Chronotype</span>
            <strong>{formatChronotype(user.model_profile.chronotype)}</strong>
            <p>This will get more specific once the app sees more real schedule and session data.</p>
          </article>
          <article className="stat-card">
            <span>Nudge style</span>
            <strong>{formatTaskType(user.preferred_nudge_style)}</strong>
            <p>Subtle, low-pressure prompts are kept on by default.</p>
          </article>
        </div>
      </section>
    </div>
  );
}

function TaskPlanSummary({ taskPlan }: { taskPlan: TaskDecompositionResponse }) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Latest plan</h2>
        <p>{taskPlan.guidance}</p>
      </div>
      <div className="result-card">
        <div className="result-row">
          <span>Baseline estimate</span>
          <strong>{formatDurationMinutes(taskPlan.base_estimate_minutes)}</strong>
        </div>
        <div className="result-row">
          <span>Predicted for you</span>
          <strong>{formatDurationMinutes(taskPlan.personalized_estimate_minutes)}</strong>
        </div>
        <div className="result-row">
          <span>Confidence</span>
          <strong>{taskPlan.prediction_confidence}</strong>
        </div>
      </div>
      <ul className="timeline-list">
        {taskPlan.steps.map((step) => (
          <li key={`${step.order}-${step.title}`}>
            <strong>{step.title}</strong>
            <span>{formatDurationMinutes(step.suggested_minutes)}</span>
            <p>{step.rationale}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}

function TaskList({ emptyText, showFocusLink = false, tasks }: { emptyText: string; showFocusLink?: boolean; tasks: TaskSummary[] }) {
  if (!tasks.length) {
    return <EmptyState text={emptyText} />;
  }

  return (
    <ul className="compact-list">
      {tasks.map((task) => (
        <TaskCard key={task.id} showFocusLink={showFocusLink} task={task} />
      ))}
    </ul>
  );
}

function TaskCard({ showFocusLink = false, task }: { showFocusLink?: boolean; task: TaskSummary }) {
  const urgency = getTaskUrgency(task);
  return (
    <li>
      <strong>{task.title}</strong>
      <span>{formatTaskStatus(task.status)}</span>
      <p>
        {task.deadline_at ? formatDate(task.deadline_at) : "No deadline yet"} | Urgency {formatUrgency(urgency)}
      </p>
      <p>
        Planned {formatDurationMinutes(task.estimated_minutes)} | Actual {formatDurationMinutes(task.actual_minutes)}
      </p>
      <p>
        {task.task_type} | {task.difficulty}
        {task.quantity_value ? ` | ${task.quantity_value} unit(s)` : ""}
      </p>
      {showFocusLink && !isCompletedTask(task) ? (
        <Link className="ghost-button task-link-button" href={`/session?taskId=${encodeURIComponent(task.id)}`}>
          Open focus session
        </Link>
      ) : null}
    </li>
  );
}

function SchedulePreview({
  onStartBlock,
  schedulePlan
}: {
  onStartBlock?: (blockId: string) => void;
  schedulePlan: ScheduleGenerationResponse;
}) {
  const unscheduledTasks = schedulePlan.unscheduled_tasks ?? [];

  return (
    <div className="result-card">
      <div className="result-row">
        <span>Scheduled blocks</span>
        <strong>{schedulePlan.time_blocks.length}</strong>
      </div>
      <div className="result-row">
        <span>Deferred tasks</span>
        <strong>{unscheduledTasks.length}</strong>
      </div>
      <ul className="timeline-list">
        {schedulePlan.time_blocks.map((block) => (
          <li key={block.id}>
            <div className="schedule-block-heading">
              <strong>{block.title}</strong>
              <span className={`status-chip status-${block.status}`}>{formatBlockStatus(block.status)}</span>
            </div>
            <span>
              {formatTime(block.start_at)} to {formatTime(block.end_at)}
            </span>
            <p>
              {formatDurationMinutes(block.planned_duration_minutes ?? getBlockMinutes(block.start_at, block.end_at))}
              {block.risk_buffer_minutes ? ` + ${formatDurationMinutes(block.risk_buffer_minutes)} protective buffer` : ""}
              {block.buffer_after_minutes ? ` + ${formatDurationMinutes(block.buffer_after_minutes)} break` : ""}
            </p>
            <p>
              Risk {formatRiskLevel(block.risk_level ?? "low")}
              {block.risk_reason ? ` | ${block.risk_reason}` : ""}
            </p>
            {block.delay_minutes > 0 ? <p>Started late by {formatDurationMinutes(block.delay_minutes)}</p> : null}
            {block.overrun_minutes > 0 ? <p>Overran by {formatDurationMinutes(block.overrun_minutes)}</p> : null}
            <div className="schedule-block-actions">
              {block.status === "planned" && block.task_id && onStartBlock ? (
                <button type="button" onClick={() => onStartBlock(block.id)}>
                  Start session
                </button>
              ) : null}
              {block.status === "active" && block.task_id ? (
                <Link
                  className="ghost-button task-link-button"
                  href={`/session?taskId=${encodeURIComponent(block.task_id)}&timeBlockId=${encodeURIComponent(block.id)}`}
                >
                  Resume
                </Link>
              ) : null}
              {block.status === "completed" ? <span className="subtle-copy">Completed</span> : null}
              {block.status === "missed" ? <span className="subtle-copy">Missed block</span> : null}
            </div>
          </li>
        ))}
      </ul>
      {unscheduledTasks.length ? (
        <>
          <p className="subtle-copy">Didn&apos;t fit</p>
          <ul className="compact-list">
            {unscheduledTasks.map((task) => (
              <li key={task.task_id}>
                <strong>{task.title}</strong>
                <span>{formatDurationMinutes(task.estimated_minutes)}</span>
                <p>{task.reason}</p>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function EventList({ events }: { events: Array<{ id: string; title: string; start_at: string; location: string }> }) {
  if (!events.length) {
    return <EmptyState text="No events yet." />;
  }

  return (
    <ul className="compact-list">
      {events.map((calendarEvent) => (
        <li key={calendarEvent.id}>
          <strong>{calendarEvent.title}</strong>
          <span>{calendarEvent.location || "No location"}</span>
          <p>{formatDate(calendarEvent.start_at)}</p>
        </li>
      ))}
    </ul>
  );
}

function StatCard({ label, value }: { label: string; value: ReactNode }) {
  return (
    <article className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="empty-state">{text}</p>;
}

function formatPageTitle(page: AppPage) {
  switch (page) {
    case "dashboard":
      return "Dashboard";
    case "tasks":
      return "Tasks";
    case "schedule":
      return "Schedule";
    case "focus":
      return "Focus Session";
    case "review":
      return "Review";
    case "settings":
      return "Settings";
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    timeStyle: "short"
  }).format(new Date(value));
}

function formatDurationMinutes(value: number | null) {
  if (value === null) {
    return "Not tracked";
  }

  const hours = Math.floor(value / 60);
  const minutes = value % 60;

  if (hours === 0) {
    return `${minutes}m`;
  }

  if (minutes === 0) {
    return `${hours}h`;
  }

  return `${hours}h ${minutes}m`;
}

function formatDelta(estimatedMinutes: number | null, actualMinutes: number | null) {
  if (estimatedMinutes === null || actualMinutes === null) {
    return "Pending";
  }

  const delta = actualMinutes - estimatedMinutes;
  if (delta === 0) {
    return "On target";
  }

  return `${delta > 0 ? "+" : ""}${formatDurationMinutes(Math.abs(delta))}`;
}

function formatSignedDuration(value: number) {
  if (value === 0) {
    return "On target";
  }

  return `${value > 0 ? "+" : "-"}${formatDurationMinutes(Math.abs(value))}`;
}

function formatSignedPercent(value: number) {
  if (value === 0) {
    return "0%";
  }

  return `${value > 0 ? "+" : ""}${value}%`;
}

function getBlockMinutes(startAt: string, endAt: string) {
  return Math.max(0, Math.round((new Date(endAt).getTime() - new Date(startAt).getTime()) / 60000));
}

function parseOptionalNumber(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function getQuantityLabel(taskType: string) {
  switch (taskType) {
    case "assignment":
      return "Problem count or units";
    case "reading":
      return "Pages";
    case "study":
      return "Topics or sections";
    case "writing":
      return "Paragraphs or sections";
    case "coding":
      return "Features or tickets";
    case "exercise":
      return "Target blocks";
    default:
      return "Quantity (optional)";
  }
}

function getQuantityPlaceholder(taskType: string) {
  switch (taskType) {
    case "assignment":
      return "e.g. 5";
    case "reading":
      return "e.g. 20";
    case "study":
      return "e.g. 3";
    case "writing":
      return "e.g. 4";
    case "coding":
      return "e.g. 2";
    case "exercise":
      return "e.g. 3";
    default:
      return "Optional";
  }
}

function isCompletedTask(task: TaskSummary) {
  return task.status === "completed" || (task.actual_minutes ?? 0) > 0;
}

function sortTasksByUrgency(tasks: TaskSummary[]) {
  return [...tasks].sort((left, right) => {
    const urgencyDiff = getUrgencyRank(getTaskUrgency(left)) - getUrgencyRank(getTaskUrgency(right));
    if (urgencyDiff !== 0) {
      return urgencyDiff;
    }

    const leftDeadline = left.deadline_at ? new Date(left.deadline_at).getTime() : Number.POSITIVE_INFINITY;
    const rightDeadline = right.deadline_at ? new Date(right.deadline_at).getTime() : Number.POSITIVE_INFINITY;

    if (leftDeadline !== rightDeadline) {
      return leftDeadline - rightDeadline;
    }

    return left.title.localeCompare(right.title);
  });
}

function sortPendingTasks(tasks: TaskSummary[], sortBy: PendingSort) {
  const items = [...tasks];
  switch (sortBy) {
    case "deadline":
      return items.sort((left, right) => {
        const leftDeadline = left.deadline_at ? new Date(left.deadline_at).getTime() : Number.POSITIVE_INFINITY;
        const rightDeadline = right.deadline_at ? new Date(right.deadline_at).getTime() : Number.POSITIVE_INFINITY;
        if (leftDeadline !== rightDeadline) {
          return leftDeadline - rightDeadline;
        }
        return left.title.localeCompare(right.title);
      });
    case "newest":
      return items.sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
    case "shortest":
      return items.sort((left, right) => {
        const leftMinutes = left.estimated_minutes ?? Number.POSITIVE_INFINITY;
        const rightMinutes = right.estimated_minutes ?? Number.POSITIVE_INFINITY;
        if (leftMinutes !== rightMinutes) {
          return leftMinutes - rightMinutes;
        }
        return getUrgencyRank(getTaskUrgency(left)) - getUrgencyRank(getTaskUrgency(right));
      });
    case "urgency":
    default:
      return sortTasksByUrgency(items);
  }
}

function sortCompletedTasks(tasks: TaskSummary[], sortBy: CompletedSort) {
  const items = [...tasks];
  switch (sortBy) {
    case "oldest":
      return items.sort((left, right) => completionTimestamp(left) - completionTimestamp(right));
    case "longest":
      return items.sort((left, right) => (right.actual_minutes ?? 0) - (left.actual_minutes ?? 0));
    case "title":
      return items.sort((left, right) => left.title.localeCompare(right.title));
    case "recent":
    default:
      return items.sort((left, right) => completionTimestamp(right) - completionTimestamp(left));
  }
}

function formatTaskStatus(status: string) {
  switch (status) {
    case "completed":
      return "Completed";
    case "cancelled":
      return "Cancelled";
    case "in_progress":
      return "In progress";
    default:
      return "Active";
  }
}

function completionTimestamp(task: TaskSummary) {
  return new Date(task.updated_at).getTime();
}

function isTodayTask(task: TaskSummary) {
  const completedAt = new Date(task.updated_at);
  const now = new Date();
  return (
    completedAt.getFullYear() === now.getFullYear() &&
    completedAt.getMonth() === now.getMonth() &&
    completedAt.getDate() === now.getDate()
  );
}

function formatBlockStatus(status: string) {
  switch (status) {
    case "active":
      return "Active";
    case "completed":
      return "Completed";
    case "missed":
      return "Missed";
    default:
      return "Planned";
  }
}

function getTaskUrgency(task: TaskSummary): "high" | "medium" | "low" {
  if (!task.deadline_at) {
    return "low";
  }

  const minutesUntilDeadline = Math.max(0, Math.round((new Date(task.deadline_at).getTime() - Date.now()) / 60000));
  if (minutesUntilDeadline <= 180) {
    return "high";
  }
  if (minutesUntilDeadline <= 24 * 60) {
    return "medium";
  }
  return "low";
}

function getUrgencyRank(urgency: "high" | "medium" | "low") {
  switch (urgency) {
    case "high":
      return 0;
    case "medium":
      return 1;
    case "low":
      return 2;
  }
}

function formatUrgency(urgency: "high" | "medium" | "low") {
  switch (urgency) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
  }
}

function formatTaskType(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatChronotype(value: string | null | undefined) {
  if (!value || value.toLowerCase() === "unknown") {
    return "Still learning";
  }
  return formatTaskType(value);
}

function formatRiskLevel(value: string) {
  switch (value) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    default:
      return "Low";
  }
}

function formatReviewPeriod(period: ReviewPeriod) {
  switch (period) {
    case "day":
      return "Day";
    case "week":
      return "Week";
    case "month":
      return "Month";
    case "all":
      return "All time";
  }
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium" }).format(new Date(value));
}
