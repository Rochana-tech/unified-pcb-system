from __future__ import annotations

from decimal import Decimal
from .ai import AI_INSTRUCTION, EvidenceOrderer, validated_order
from .models import AlertInput, Answer, Comparison, Evidence, Explanation, SourceStatus

QUESTIONS = {
    "what_happened": "WHAT HAPPENED?",
    "anomaly_detected": "WHAT ANOMALY WAS DETECTED?",
    "possible_causes": "WHY MIGHT THIS HAVE HAPPENED?",
    "production_impact": "HOW DOES IT AFFECT PRODUCTION?",
    "human_correction": "CAN A HUMAN CORRECT IT QUICKLY?",
    "delayed_correction": "WHAT HAPPENS IF THE HUMAN TAKES TOO LONG?",
    "machine_takeover": "CAN ANOTHER MACHINE TAKE OVER?",
    "what_if": "WHAT DOES THE WHAT-IF SIMULATION SHOW?",
}
MISSING = {
    "what_happened": ("No current operational observations were provided.", "Current machine observations or events"),
    "anomaly_detected": ("No current ANN anomaly result was provided.", "ANN anomaly result"),
    "possible_causes": ("The backend has not supplied a suspected cause. A cause cannot be determined here.", "Backend-supported cause hypotheses"),
    "production_impact": ("No current digital-twin production-impact result was provided.", "Digital-twin production-impact result"),
    "human_correction": ("Whether a human can correct this quickly is unknown.", "Human correction assessment and repair-time estimate"),
    "delayed_correction": ("The consequences of a longer repair have not been provided.", "Delayed-repair impact or scheduler response"),
    "machine_takeover": ("No alternative-machine assessment was provided. This does not establish that no alternative exists.", "Compatibility and availability assessment"),
    "what_if": ("No current what-if simulation results were provided.", "What-if simulation results"),
}
SOURCES = ("data_acquisition", "ann_fault_detection", "digital_twin", "decision_recovery")


def compare_scenarios(payload: AlertInput) -> Comparison:
    r = payload.decision_recovery
    if r.status != SourceStatus.AVAILABLE or not r.baseline_scenario_id or not r.recovery_scenario_id:
        return Comparison(status="not_provided", reason="A current baseline/recovery comparison pair was not supplied.")
    by_id = {s.id: s for s in r.scenarios}
    a, b = by_id[r.baseline_scenario_id], by_id[r.recovery_scenario_id]
    common = dict(baseline_scenario_id=a.id, recovery_scenario_id=b.id)
    if any(getattr(s, k) is None for s in (a, b) for k in ("horizon_minutes", "starting_state_id", "output_scope")):
        return Comparison(status="insufficient_metadata", reason="A common horizon, starting state, and output scope are required before comparing results.", **common)
    fields = ("horizon_minutes", "starting_state_id", "output_scope", "throughput_unit")
    if any(getattr(a, k) != getattr(b, k) for k in fields):
        return Comparison(status="not_comparable", reason="The supplied scenarios differ in horizon, starting state, output scope, or throughput unit. No improvement is calculated.", **common)
    difference = float(Decimal(str(b.throughput)) - Decimal(str(a.throughput)))
    return Comparison(status="comparable", reason="Both results use the same supplied horizon, starting state, output scope, and throughput unit.", throughput_difference=difference, throughput_unit=a.throughput_unit, horizon_minutes=a.horizon_minutes, **common)


def explain_alert(payload: AlertInput | dict, orderer: EvidenceOrderer | None = None) -> Explanation:
    if not isinstance(payload, AlertInput):
        payload = AlertInput.model_validate(payload)
    sentences: dict[str, dict[str, str]] = {key: {} for key in QUESTIONS}
    evidence: dict[str, Evidence] = {}
    details: dict[str, list[dict]] = {key: [] for key in QUESTIONS}
    gaps: dict[str, list[str]] = {key: [] for key in QUESTIONS}
    warnings: list[str] = []

    def add(section, source_name, record, sentence):
        source = getattr(payload, source_name)
        ref = source_name + "." + record.id
        evidence[ref] = Evidence(id=ref, source=source_name, record_id=record.id, reported_at=source.reported_at, data=record.model_dump(mode="json"))
        sentences[section][ref] = sentence
        details[section].append({"evidence_id": ref, **record.model_dump(mode="json")})

    for name in SOURCES:
        source = getattr(payload, name)
        if source.status == SourceStatus.STALE:
            warnings.append(f"{name} is stale; its records were not used for current explanations.")
        elif source.status == SourceStatus.MISSING:
            warnings.append(f"{name} is not provided.")

    d = payload.data_acquisition
    if d.status == SourceStatus.AVAILABLE:
        for o in d.observations:
            parts = []
            if o.value is not None:
                parts.append(f"{o.signal}: {o.value:g} {o.unit}.")
            if o.trend != "unknown":
                parts.append(f"The backend reports {o.signal} as {o.trend}.")
            if o.description:
                parts.append(f"Reported observation: {o.description}")
            add("what_happened", "data_acquisition", o, " ".join(parts))

    ann = payload.ann_fault_detection
    if ann.status == SourceStatus.AVAILABLE:
        for a in ann.anomalies:
            sentence = f"The ANN reported an anomaly: {a.label}."
            if a.description:
                sentence += f" Backend detail: {a.description}"
            if a.confidence_score is not None:
                sentence += f" Supplied model score: {a.confidence_score:g}; this is not a calibrated failure probability."
            add("anomaly_detected", "ann_fault_detection", a, sentence)
        for cause in ann.suspected_causes:
            add("possible_causes", "ann_fault_detection", cause, f"Backend-supplied possible cause: {cause.label}. This is a hypothesis, not a confirmed diagnosis.")
        if ann.suspected_causes and d.status != SourceStatus.AVAILABLE:
            gaps["possible_causes"].append("Current operational evidence to inspect alongside the cause hypotheses")

    twin = payload.digital_twin
    if twin.status == SourceStatus.AVAILABLE:
        for impact in twin.impacts:
            add("production_impact", "digital_twin", impact, f"Digital-twin result: {impact.description}")

    r = payload.decision_recovery
    if r.status == SourceStatus.AVAILABLE:
        if r.human:
            h = r.human
            possibility = {
                "yes": "The backend assessment says human correction may be possible.",
                "no": "The backend assessment says human correction is not currently feasible.",
                "unknown": "Whether a human can correct the issue has not been assessed.",
            }[h.correction_possible]
            speed = {
                "yes": "The backend classifies correction as quick.",
                "no": "The backend does not classify correction as quick.",
                "unknown": "Whether correction would be quick is unknown.",
            }[h.quick_correction]
            sentence = possibility + " " + speed
            if h.estimated_minutes:
                sentence += f" Supplied repair-time estimate: {h.estimated_minutes.minimum:g}–{h.estimated_minutes.maximum:g} minutes; this is an estimate, not a guarantee."
                if h.estimate_basis:
                    sentence += f" Estimate basis: {h.estimate_basis}"
            else:
                gaps["human_correction"].append("Repair-time estimate")
            if h.correction_possible == "unknown":
                gaps["human_correction"].append("Human correction feasibility")
            if h.quick_correction == "unknown":
                gaps["human_correction"].append("Quick-correction assessment")
            if h.approved_actions:
                sentence += " Backend-approved actions: " + " | ".join(h.approved_actions)
            else:
                sentence += " No maintenance procedure was supplied."
            add("human_correction", "decision_recovery", h, sentence)
        for consequence in r.delay_consequences:
            add("delayed_correction", "decision_recovery", consequence, f"Backend-supplied delayed-repair consequence: {consequence.description}")
        for alt in r.alternatives:
            if alt.compatibility == "confirmed" and alt.available is True:
                sentence = f"{alt.machine_id} — {alt.machine_name} is reported as compatible and available."
            elif alt.compatibility == "incompatible":
                sentence = f"{alt.machine_id} — {alt.machine_name} cannot take over this operation according to the backend compatibility assessment."
            elif alt.available is False:
                sentence = f"{alt.machine_id} — {alt.machine_name} is reported as unavailable."
            else:
                sentence = f"Takeover by {alt.machine_id} — {alt.machine_name} is not established."
            if alt.compatibility == "unknown":
                gaps["machine_takeover"].append(f"Compatibility confirmation for {alt.machine_id}")
            if alt.available is None:
                gaps["machine_takeover"].append(f"Availability confirmation for {alt.machine_id}")
            sentence += f" Backend allocation status: {alt.allocation_status.replace('_', ' ')}."
            if alt.reason:
                sentence += f" Backend reason: {alt.reason}"
            add("machine_takeover", "decision_recovery", alt, sentence)
        for scenario in r.scenarios:
            sentence = f"Simulation '{scenario.name}' reports {scenario.throughput:g} {scenario.throughput_unit}."
            if scenario.horizon_minutes is not None:
                sentence += f" Simulation horizon: {scenario.horizon_minutes:g} minutes."
            if scenario.assumptions:
                sentence += " Supplied assumptions: " + " | ".join(scenario.assumptions)
            add("what_if", "decision_recovery", scenario, sentence)

    comparison = compare_scenarios(payload)
    if sentences["what_if"] and comparison.status != "comparable":
        gaps["what_if"].append(comparison.reason)

    order = {key: list(sentences[key]) for key in QUESTIONS}
    mode = "evidence_templates"
    if orderer is not None:
        # Provider output is never displayed as narrative. Even valid selection cannot
        # drop caveats or omit unfavorable alternatives: all IDs must be retained.
        context = {
            "instruction": AI_INSTRUCTION,
            "questions": {key: {"question": QUESTIONS[key], "evidence_ids": ids} for key, ids in order.items()},
            "evidence": [item.model_dump(mode="json") for item in evidence.values()],
        }
        try:
            order = validated_order(orderer.order_evidence(context), order)
            mode = "ai_ordered_evidence"
        except Exception:
            warnings.append("AI evidence ordering was unavailable or invalid; the evidence-only renderer was used.")

    answers = []
    for key, question in QUESTIONS.items():
        ids = order[key]
        if not ids:
            answer, missing = MISSING[key]
            answers.append(Answer(key=key, question=question, status="unavailable", answer=answer, evidence_ids=[], missing_information=[missing]))
            continue
        answer = " ".join(sentences[key][ref] for ref in ids)
        if key == "what_if":
            if comparison.status == "comparable":
                difference = comparison.throughput_difference
                answer += f" Recovery minus baseline: {difference:+g} {comparison.throughput_unit}. This difference is calculated from the supplied simulation results, not a new simulation."
            else:
                answer += " " + comparison.reason
            if r.recommended_scenario_id:
                answer += f" The backend recommends scenario '{r.recommended_scenario_id}'; this layer does not choose or execute a recovery."
        if key == "machine_takeover":
            answer += " This explanation layer does not allocate work or control machines."
        detail_map = {item["evidence_id"]: item for item in details[key]}
        answers.append(Answer(key=key, question=question, status="partial" if gaps[key] else "supported", answer=answer, evidence_ids=ids, details=[detail_map[ref] for ref in ids], missing_information=gaps[key]))

    return Explanation(alert=payload.alert, explanation_mode=mode, answers=answers, evidence=list(evidence.values()), comparison=comparison, recommended_scenario_id=r.recommended_scenario_id if r.status == SourceStatus.AVAILABLE else None, warnings=warnings)

