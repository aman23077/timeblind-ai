from datetime import timedelta

from app.modules.tasks.schemas import (
    DecomposedTaskStep,
    TaskDecompositionRequest,
    TaskDecompositionResponse,
)


BASE_MINUTES_BY_TYPE: dict[str, int] = {
    "assignment": 90,
    "reading": 40,
    "study": 60,
    "writing": 75,
    "coding": 90,
    "meeting_prep": 45,
    "admin": 30,
    "errand": 35,
    "chore": 40,
    "exercise": 45,
    "creative": 60,
    "generic": 45,
}

DIFFICULTY_MULTIPLIER: dict[str, float] = {
    "easy": 0.85,
    "medium": 1.0,
    "hard": 1.25,
}

QUANTITY_RULES: dict[str, tuple[int, int]] = {
    "assignment": (25, 90),
    "reading": (2, 20),
    "study": (20, 60),
    "writing": (15, 75),
    "coding": (30, 90),
    "exercise": (10, 45),
}

READING_KEYWORDS = ("read", "chapter", "pages", "page", "book", "article", "notes")
PROBLEM_SOLVING_KEYWORDS = ("dsa", "problem", "questions", "question", "leetcode", "exercise", "sheet")
WRITING_KEYWORDS = ("write", "essay", "draft", "report", "summary", "statement", "blog")
CODING_KEYWORDS = ("build", "implement", "fix", "debug", "feature", "api", "component", "code")
STUDY_KEYWORDS = ("study", "revise", "learn", "review", "practice", "prepare", "dbms", "os", "cn")
CLEANUP_KEYWORDS = ("clean", "organize", "arrange", "room", "desk", "closet")
ACADEMIC_READING_KEYWORDS = ("study", "revise", "review", "notes", "exam", "syllabus", "lecture", "dbms", "os", "cn")


def decompose_task(
    payload: TaskDecompositionRequest,
    personalization_multiplier: float = 1.0,
    prediction_confidence: str = "low",
) -> TaskDecompositionResponse:
    base_estimate_minutes = _base_estimate(payload)
    personalized_estimate_minutes = max(15, round(base_estimate_minutes * personalization_multiplier))
    urgency = _compute_urgency(payload)
    available_minutes = _available_minutes(payload)
    fit_status, overflow_minutes, guidance = _fit_analysis(
        personalized_estimate_minutes, available_minutes, payload.task_type, payload.quantity_value
    )
    steps = _build_steps(payload, personalized_estimate_minutes, available_minutes, fit_status)

    return TaskDecompositionResponse(
        task_title=payload.title,
        urgency=urgency,
        base_estimate_minutes=base_estimate_minutes,
        personalized_estimate_minutes=personalized_estimate_minutes,
        prediction_confidence=prediction_confidence,
        personalization_multiplier=round(personalization_multiplier, 2),
        available_minutes=available_minutes,
        fit_status=fit_status,
        overflow_minutes=overflow_minutes,
        guidance=guidance,
        total_suggested_minutes=sum(step.suggested_minutes for step in steps),
        steps=steps,
    )


def _base_estimate(payload: TaskDecompositionRequest) -> int:
    base_minutes = BASE_MINUTES_BY_TYPE.get(payload.task_type, BASE_MINUTES_BY_TYPE["generic"])
    quantity_minutes = _quantity_estimate(payload, base_minutes)
    minutes = quantity_minutes if quantity_minutes is not None else base_minutes
    minutes = round(minutes * DIFFICULTY_MULTIPLIER.get(payload.difficulty, 1.0))
    minutes = round(minutes * _title_complexity_multiplier(payload.title))
    if payload.estimated_minutes is not None:
        minutes = round((minutes * 0.7) + (payload.estimated_minutes * 0.3))
    return max(15, minutes)


def _quantity_estimate(payload: TaskDecompositionRequest, fallback_minutes: int) -> int | None:
    if payload.quantity_value is None:
        return None

    task_pattern = _detect_task_pattern(payload)
    if task_pattern == "reading":
        if _is_academic_reading(payload.title):
            return max(25, payload.quantity_value * 3)
        return max(20, payload.quantity_value * 2)

    per_unit, minimum = QUANTITY_RULES.get(payload.task_type, (None, None))
    if per_unit is None:
        return max(minimum or fallback_minutes, payload.quantity_value * max(5, fallback_minutes // 3))

    return max(minimum, payload.quantity_value * per_unit)


def _title_complexity_multiplier(title: str) -> float:
    lowered = title.lower()
    multiplier = 1.0
    if len(title.split()) >= 8:
        multiplier += 0.08
    if any(keyword in lowered for keyword in ["research", "analysis", "report", "debug", "project", "exam"]):
        multiplier += 0.12
    return multiplier


def _compute_urgency(payload: TaskDecompositionRequest) -> str:
    if payload.deadline_at is None:
        return None
    current_time = payload.current_time or (payload.deadline_at - timedelta(days=1))
    remaining_hours = (payload.deadline_at - current_time).total_seconds() / 3600
    if remaining_hours <= 12:
        return "high"
    if remaining_hours <= 48:
        return "medium"
    return "low"


def _available_minutes(payload: TaskDecompositionRequest) -> int:
    if payload.deadline_at is None:
        return None
    current_time = payload.current_time or (payload.deadline_at - timedelta(days=1))
    return max(0, round((payload.deadline_at - current_time).total_seconds() / 60))


def _fit_analysis(
    predicted_minutes: int, available_minutes: int | None, task_type: str, quantity_value: int | None
) -> tuple[str, int, str]:
    if available_minutes is None:
        return None, None, "This task has no deadline yet, so the estimate is for planning and later scheduling."

    overflow_minutes = max(0, predicted_minutes - available_minutes)
    if available_minutes == 0:
        return "overflow", predicted_minutes, "The deadline has already arrived, so this task will need a recovery plan."
    if overflow_minutes <= 0:
        if predicted_minutes >= max(15, round(available_minutes * 0.85)):
            return "tight", 0, "This can fit, but there is very little slack, so keep the scope tight and avoid context switching."
        return "fits", 0, "This should fit before the deadline if you start promptly and stay on the main task."

    if quantity_value and task_type in {"assignment", "study", "writing", "coding"}:
        unit_minutes = QUANTITY_RULES.get(task_type, (predicted_minutes, predicted_minutes))[0]
        possible_units = max(1, available_minutes // max(1, unit_minutes))
        return (
            "overflow",
            overflow_minutes,
            f"This likely will not fit. Aim for about {possible_units} unit(s) before the deadline and defer the rest.",
        )

    return "overflow", overflow_minutes, "This likely will not fit before the deadline, so use a smaller first block."


def _build_steps(
    payload: TaskDecompositionRequest, predicted_minutes: int, available_minutes: int | None, fit_status: str | None
) -> list[DecomposedTaskStep]:
    task_label = _clean_task_label(payload.title)
    task_pattern = _detect_task_pattern(payload)
    first_block = max(10, min(25, round(predicted_minutes * 0.18)))
    main_block = max(15, min(60, round(predicted_minutes * 0.52)))
    close_block = max(10, predicted_minutes - first_block - main_block)

    if fit_status == "overflow":
        return _build_overflow_steps(task_pattern, task_label, available_minutes or predicted_minutes, payload)

    return _build_pattern_steps(task_pattern, task_label, first_block, main_block, close_block, payload)


def _clean_task_label(title: str) -> str:
    return " ".join(title.split()).strip() or "this task"


def _detect_task_pattern(payload: TaskDecompositionRequest) -> str:
    lowered = payload.title.lower()

    if payload.task_type == "writing" or any(keyword in lowered for keyword in WRITING_KEYWORDS):
        return "writing"
    if payload.task_type == "coding" or any(keyword in lowered for keyword in CODING_KEYWORDS):
        return "coding"
    if payload.task_type == "reading":
        return "reading"
    if payload.task_type == "study" or any(keyword in lowered for keyword in STUDY_KEYWORDS):
        if any(keyword in lowered for keyword in READING_KEYWORDS):
            return "reading"
        return "study"
    if payload.task_type == "assignment" or any(keyword in lowered for keyword in PROBLEM_SOLVING_KEYWORDS):
        return "problem_solving"
    if any(keyword in lowered for keyword in READING_KEYWORDS):
        return "reading"
    if payload.task_type == "chore" or any(keyword in lowered for keyword in CLEANUP_KEYWORDS):
        return "cleanup"
    if payload.task_type == "meeting_prep":
        return "meeting_prep"
    if payload.task_type == "exercise":
        return "exercise"
    return "generic"


def _build_pattern_steps(
    task_pattern: str,
    task_label: str,
    first_block: int,
    main_block: int,
    close_block: int,
    payload: TaskDecompositionRequest,
) -> list[DecomposedTaskStep]:
    quantity_label = _quantity_label(payload)

    if task_pattern == "problem_solving":
        return [
            DecomposedTaskStep(
                title=f"Pick {quantity_label} and decide the order for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="Choosing the order first prevents you from wasting momentum on the wrong starting point.",
            ),
            DecomposedTaskStep(
                title=f"Solve the main set for {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="The core time should go into actually solving rather than repeatedly resetting context.",
            ),
            DecomposedTaskStep(
                title=f"Review mistakes, patterns, or stuck points from {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="A quick review turns raw effort into something reusable next time.",
            ),
        ]

    if task_pattern == "reading":
        if _is_academic_reading(payload.title):
            close_title = f"Write quick notes or a short recall summary for {task_label}"
            close_rationale = "A short recap helps you retain what you read and spot what still feels fuzzy."
        else:
            close_title = f"Pause and capture the main takeaway from {task_label}"
            close_rationale = "A light recap is enough here, because the goal is finishing the reading without adding heavy study overhead."
        return [
            DecomposedTaskStep(
                title=f"Open the material and define the reading target for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="A clear page or section target makes it easier to stay engaged.",
            ),
            DecomposedTaskStep(
                title=f"Read through the main portion of {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="Use the biggest block for uninterrupted reading before attention drifts.",
            ),
            DecomposedTaskStep(
                title=close_title,
                suggested_minutes=close_block,
                order=3,
                rationale=close_rationale,
            ),
        ]

    if task_pattern == "study":
        return [
            DecomposedTaskStep(
                title=f"Set the topic list and first checkpoint for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="A small study checkpoint keeps the session from turning vague.",
            ),
            DecomposedTaskStep(
                title=f"Work through the main concepts or examples in {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="This is the main understanding block, so protect it from switching away too early.",
            ),
            DecomposedTaskStep(
                title=f"Test recall and note weak spots from {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="Checking what still feels weak tells you what needs another pass later.",
            ),
        ]

    if task_pattern == "writing":
        return [
            DecomposedTaskStep(
                title=f"Sketch the structure and key points for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="A quick outline reduces blank-page friction and makes the draft easier to start.",
            ),
            DecomposedTaskStep(
                title=f"Draft the main body of {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="Protect the middle block for drafting so you can stay in the same train of thought.",
            ),
            DecomposedTaskStep(
                title=f"Edit for clarity and finish the close-out for {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="A short revision pass helps the work feel finished instead of abruptly stopped.",
            ),
        ]

    if task_pattern == "coding":
        return [
            DecomposedTaskStep(
                title=f"Set up the scope and first change for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="A small setup step narrows the problem so implementation starts faster.",
            ),
            DecomposedTaskStep(
                title=f"Implement or debug the core part of {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="The core coding block works best when you stay in one context and push through the main issue.",
            ),
            DecomposedTaskStep(
                title=f"Test, verify, and note the next follow-up for {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="A short verification pass prevents leaving the task in an uncertain state.",
            ),
        ]

    if task_pattern == "cleanup":
        return [
            DecomposedTaskStep(
                title=f"Choose the zones and order for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="Picking zones first keeps cleanup from turning into random movement.",
            ),
            DecomposedTaskStep(
                title=f"Do the main reset for {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="The bulk of the session should go toward the visible reset, not small edge details.",
            ),
            DecomposedTaskStep(
                title=f"Put away loose items and finish the final pass on {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="A final pass prevents the space from looking almost-done but still cluttered.",
            ),
        ]

    if task_pattern == "meeting_prep":
        return [
            DecomposedTaskStep(
                title=f"Collect the agenda, context, and materials for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="Pulling everything together first prevents last-minute scrambling.",
            ),
            DecomposedTaskStep(
                title=f"Prepare the main talking points or review items for {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="The main prep block should go toward the content you need to speak through clearly.",
            ),
            DecomposedTaskStep(
                title=f"Do a quick final check for {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="A short review helps you enter the meeting with less friction and fewer surprises.",
            ),
        ]

    if task_pattern == "exercise":
        return [
            DecomposedTaskStep(
                title=f"Set up and get into motion for {task_label}",
                suggested_minutes=first_block,
                order=1,
                rationale="A gentle start lowers the barrier to actually beginning the session.",
            ),
            DecomposedTaskStep(
                title=f"Do the main block of {task_label}",
                suggested_minutes=main_block,
                order=2,
                rationale="The biggest share of time should go to the main active work while energy is highest.",
            ),
            DecomposedTaskStep(
                title=f"Cool down and wrap up {task_label}",
                suggested_minutes=close_block,
                order=3,
                rationale="Closing the session properly makes the task feel complete and easier to repeat later.",
            ),
        ]

    return [
        DecomposedTaskStep(
            title=f"Set up and define the first target for {task_label}",
            suggested_minutes=first_block,
            order=1,
            rationale="A small setup step reduces startup friction and makes the work concrete.",
        ),
        DecomposedTaskStep(
            title=f"Do the main work block for {task_label}",
            suggested_minutes=main_block,
            order=2,
            rationale="Protect the biggest block for the core effort instead of scattering attention.",
        ),
        DecomposedTaskStep(
            title=f"Review progress and close the loop on {task_label}",
            suggested_minutes=close_block,
            order=3,
            rationale="A final pass helps you finish cleanly and see what remains.",
        ),
    ]


def _build_overflow_steps(
    task_pattern: str,
    task_label: str,
    available_minutes: int,
    payload: TaskDecompositionRequest,
) -> list[DecomposedTaskStep]:
    available_focus = max(10, min(available_minutes, max(15, available_minutes - 10)))
    setup_minutes = min(10, available_focus)
    main_minutes = max(5, available_focus - setup_minutes)
    quantity_label = _quantity_label(payload)

    if task_pattern == "problem_solving":
        return [
            DecomposedTaskStep(
                title=f"Pick the easiest high-value part of {quantity_label} for {task_label}",
                suggested_minutes=setup_minutes,
                order=1,
                rationale="When time is short, narrowing down to the best starting point prevents overload.",
            ),
            DecomposedTaskStep(
                title=f"Solve as much of the first useful chunk of {task_label} as possible",
                suggested_minutes=main_minutes,
                order=2,
                rationale="A smaller completed chunk is more useful than starting everything and finishing nothing.",
            ),
        ]

    if task_pattern == "reading":
        return [
            DecomposedTaskStep(
                title=f"Choose the most important pages or section from {task_label}",
                suggested_minutes=setup_minutes,
                order=1,
                rationale="Picking the highest-value section first protects the session from spreading too thin.",
            ),
            DecomposedTaskStep(
                title=f"Read that priority section and note the key ideas from {task_label}",
                suggested_minutes=main_minutes,
                order=2,
                rationale="A focused pass on the most useful section is better than skimming everything.",
            ),
        ]

    if task_pattern == "coding":
        return [
            DecomposedTaskStep(
                title=f"Choose the smallest shippable change inside {task_label}",
                suggested_minutes=setup_minutes,
                order=1,
                rationale="When time is constrained, aiming for one contained change is safer than broad exploration.",
            ),
            DecomposedTaskStep(
                title=f"Implement or debug just that key slice of {task_label}",
                suggested_minutes=main_minutes,
                order=2,
                rationale="A small verified change gives you forward motion without pretending the whole task fits.",
            ),
        ]

    return [
        DecomposedTaskStep(
            title=f"Set up and choose the smallest useful target for {task_label}",
            suggested_minutes=setup_minutes,
            order=1,
            rationale="When time is short, narrowing the scope prevents shutdown.",
        ),
        DecomposedTaskStep(
            title=f"Do the highest-value part of {task_label}",
            suggested_minutes=main_minutes,
            order=2,
            rationale="Use the remaining time on the part most likely to move the task forward.",
        ),
    ]


def _quantity_label(payload: TaskDecompositionRequest) -> str:
    if payload.quantity_value is None:
        return "the main pieces"

    task_pattern = _detect_task_pattern(payload)
    if task_pattern == "problem_solving":
        return f"{payload.quantity_value} problem(s)"
    if task_pattern == "reading":
        return f"{payload.quantity_value} page(s)"
    if task_pattern in {"study", "writing"}:
        return f"{payload.quantity_value} section(s)"
    if task_pattern == "coding":
        return f"{payload.quantity_value} main change(s)"
    return f"{payload.quantity_value} unit(s)"


def _is_academic_reading(title: str) -> bool:
    lowered = title.lower()
    return any(keyword in lowered for keyword in ACADEMIC_READING_KEYWORDS)
