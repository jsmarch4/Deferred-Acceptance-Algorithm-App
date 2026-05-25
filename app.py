from shiny import App, ui, render, reactive


# -----------------------------
# Parsing helpers
# -----------------------------

def parse_preferences(text, agents, choices):
    prefs = {}

    for line in text.strip().splitlines():
        if ":" not in line:
            continue

        agent, ranking = line.split(":", 1)
        agent = agent.strip()
        ranking = [x.strip() for x in ranking.split(",") if x.strip()]

        if agent in agents:
            acceptable = []

            for x in ranking:
                if x == agent:
                    break
                if x in choices and x not in acceptable:
                    acceptable.append(x)

            if agent not in ranking:
                missing = [x for x in choices if x not in acceptable]
                acceptable = acceptable + missing

            prefs[agent] = acceptable

    for agent in agents:
        if agent not in prefs:
            prefs[agent] = choices.copy()

    return prefs


def parse_capacities(text, hospitals, default_capacity=1):
    capacities = {h: default_capacity for h in hospitals}

    for line in text.strip().splitlines():
        if ":" not in line:
            continue

        hospital, cap = line.split(":", 1)
        hospital = hospital.strip()

        if hospital in hospitals:
            try:
                capacities[hospital] = max(0, int(cap.strip()))
            except ValueError:
                capacities[hospital] = default_capacity

    return capacities


def default_doctor_pref_text(num_doctors, num_hospitals):
    hospitals = [f"H{i}" for i in range(1, num_hospitals + 1)]
    return "\n".join([f"D{i}: {','.join(hospitals)}" for i in range(1, num_doctors + 1)])


def default_hospital_pref_text(num_doctors, num_hospitals):
    doctors = [f"D{i}" for i in range(1, num_doctors + 1)]
    return "\n".join([f"H{i}: {','.join(doctors)}" for i in range(1, num_hospitals + 1)])


def default_capacity_text(num_hospitals):
    return "\n".join([f"H{i}: 1" for i in range(1, num_hospitals + 1)])


# -----------------------------
# Market helpers
# -----------------------------

def make_market(num_doctors, num_hospitals, capacity_text, doctor_pref_text, hospital_pref_text):
    doctors = [f"D{i}" for i in range(1, num_doctors + 1)]
    hospitals = [f"H{i}" for i in range(1, num_hospitals + 1)]

    doctor_prefs = parse_preferences(doctor_pref_text, doctors, hospitals)
    hospital_prefs = parse_preferences(hospital_pref_text, hospitals, doctors)
    capacities = parse_capacities(capacity_text, hospitals)

    return doctors, hospitals, doctor_prefs, hospital_prefs, capacities


def initialize_state(doctors, hospitals, algorithm):
    if algorithm == "doctor":
        proposers = doctors.copy()
        receivers = hospitals.copy()
    else:
        proposers = hospitals.copy()
        receivers = doctors.copy()

    return {
        "round": 0,
        "active": proposers.copy(),
        "next_choice_index": {p: 0 for p in proposers},
        "held_by_receiver": {r: [] for r in receivers},
        "log": [],
        "done": False,
        "last_step": "Click Next Round to begin.",
        "algorithm": algorithm,
    }


def get_market_for_algorithm(doctors, hospitals, doctor_prefs, hospital_prefs, capacities, algorithm):
    if algorithm == "doctor":
        proposers = doctors
        receivers = hospitals
        proposer_prefs = doctor_prefs
        receiver_prefs = hospital_prefs
        receiver_caps = capacities
    else:
        proposers = hospitals
        receivers = doctors
        proposer_prefs = hospital_prefs
        receiver_prefs = doctor_prefs
        receiver_caps = {d: 1 for d in doctors}

    return proposers, receivers, proposer_prefs, receiver_prefs, receiver_caps


def receiver_rank(receiver, proposer, receiver_prefs):
    return receiver_prefs[receiver].index(proposer)


def run_one_round(s, doctors, hospitals, doctor_prefs, hospital_prefs, capacities):
    if s["done"]:
        s["last_step"] = "Algorithm already complete."
        return s

    algorithm = s["algorithm"]

    proposers, receivers, proposer_prefs, receiver_prefs, receiver_caps = get_market_for_algorithm(
        doctors,
        hospitals,
        doctor_prefs,
        hospital_prefs,
        capacities,
        algorithm,
    )

    s["round"] += 1
    lines = [f"Round {s['round']}"]

    proposals = {r: [] for r in receivers}
    new_active = []

    for p in s["active"]:
        i = s["next_choice_index"][p]

        if i < len(proposer_prefs[p]):
            r = proposer_prefs[p][i]
            proposals[r].append(p)
            s["next_choice_index"][p] += 1
            lines.append(f"{p} → {r}")
        else:
            lines.append(f"{p} has no acceptable options left.")

    for r in receivers:
        applicants = s["held_by_receiver"][r] + proposals[r]

        if not applicants:
            continue

        acceptable = [p for p in applicants if p in receiver_prefs[r]]
        unacceptable = [p for p in applicants if p not in receiver_prefs[r]]

        ranked = sorted(acceptable, key=lambda p: receiver_rank(r, p, receiver_prefs))

        cap = receiver_caps[r]
        accepted = ranked[:cap]
        rejected = ranked[cap:] + unacceptable

        s["held_by_receiver"][r] = accepted

        if accepted:
            lines.append(f"{r} holds: {', '.join(accepted)}")
        else:
            lines.append(f"{r} holds nobody.")

        for p in rejected:
            if p in unacceptable:
                lines.append(f"{r} rejects {p} as unacceptable.")
            else:
                lines.append(f"{r} rejects: {p}")

            if s["next_choice_index"][p] < len(proposer_prefs[p]):
                new_active.append(p)
            else:
                lines.append(f"{p} has no acceptable options left.")

    s["active"] = new_active

    if not s["active"]:
        s["done"] = True
        lines.append("Complete.")

    s["last_step"] = "\n".join(lines)
    s["log"].append(s["last_step"])

    return s


def extract_doctor_hospital_matches(s):
    matches = []

    if s["algorithm"] == "doctor":
        for h, held_doctors in s["held_by_receiver"].items():
            for d in held_doctors:
                matches.append((d, h))
    else:
        for d, held_hospitals in s["held_by_receiver"].items():
            for h in held_hospitals:
                matches.append((d, h))

    return matches


# -----------------------------
# UI
# -----------------------------

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.tags.style("""
        .radio label {
            white-space: nowrap;
        }

        .form-group {
            margin-bottom: 18px;
        }

        .sidebar .form-group label {
            margin-bottom: 8px;
        }
        """),

        ui.h3("Market Setup"),

        ui.div(
            {"style": "margin-bottom: 24px;"},
            ui.input_radio_buttons(
                "algorithm",
                "Algorithm",
                {
                    "doctor": "Doctor-proposing DAA",
                    "hospital": "Hospital-proposing DAA",
                },
                selected="doctor",
                width="100%",
            ),
        ),

        ui.input_slider("num_doctors", "Number of doctors", 2, 10, 4),
        ui.input_slider("num_hospitals", "Number of hospitals", 1, 8, 3),

        ui.hr(),

        ui.input_text_area(
            "capacity_text",
            "Hospital capacities",
            value=default_capacity_text(3),
            rows=4,
        ),

        ui.input_text_area(
            "doctor_pref_text",
            "Doctor preferences",
            value=default_doctor_pref_text(4, 3),
            rows=6,
        ),

        ui.input_text_area(
            "hospital_pref_text",
            "Hospital preferences",
            value=default_hospital_pref_text(4, 3),
            rows=6,
        ),

        ui.input_action_button("fill_defaults", "Fill Default Preferences"),
        ui.input_action_button("build_market", "Build / Reset Market"),

        ui.hr(),

        ui.input_action_button("next_round", "Next Round"),
        ui.input_action_button("run_full", "Run Full Algorithm"),
        ui.input_action_button("reset", "Reset Current Market"),
    ),

    ui.h2("Gale-Shapley Deferred Acceptance Visualizer"),
    ui.p("Choose doctor-proposing or hospital-proposing deferred acceptance."),

    ui.h3("Input Format"),
    ui.p("Preferences: D1: H1,H2,H3"),
    ui.p("Unacceptable cutoff: D1: H1,D1,H2 means D1 only finds H1 acceptable."),
    ui.p("Hospital cutoff: H1: D2,H1,D3 means H1 only finds D2 acceptable."),
    ui.p("Capacities: H1: 1"),

    ui.h3("Current Market"),
    ui.output_text_verbatim("market_text"),

    ui.h3("Current Step"),
    ui.output_text_verbatim("step_text"),

    ui.h3("Current Tentative Matching"),
    ui.output_text_verbatim("matching_text"),

    ui.h3("Full Algorithm Log"),
    ui.output_text_verbatim("log_text"),
)


# -----------------------------
# Server
# -----------------------------

def server(input, output, session):
    initial_doctor_text = default_doctor_pref_text(4, 3)
    initial_hospital_text = default_hospital_pref_text(4, 3)
    initial_capacity_text = default_capacity_text(3)

    initial_market = make_market(
        4,
        3,
        initial_capacity_text,
        initial_doctor_text,
        initial_hospital_text,
    )

    market = reactive.Value(initial_market)

    doctors, hospitals, _, _, _ = initial_market
    state = reactive.Value(initialize_state(doctors, hospitals, "doctor"))

    @reactive.effect
    @reactive.event(input.fill_defaults)
    def _():
        ui.update_text_area(
            "doctor_pref_text",
            value=default_doctor_pref_text(input.num_doctors(), input.num_hospitals()),
        )
        ui.update_text_area(
            "hospital_pref_text",
            value=default_hospital_pref_text(input.num_doctors(), input.num_hospitals()),
        )
        ui.update_text_area(
            "capacity_text",
            value=default_capacity_text(input.num_hospitals()),
        )

    @reactive.effect
    @reactive.event(input.build_market)
    def _():
        new_market = make_market(
            input.num_doctors(),
            input.num_hospitals(),
            input.capacity_text(),
            input.doctor_pref_text(),
            input.hospital_pref_text(),
        )

        market.set(new_market)

        doctors, hospitals, _, _, _ = new_market
        state.set(initialize_state(doctors, hospitals, input.algorithm()))

    @reactive.effect
    @reactive.event(input.reset)
    def _():
        doctors, hospitals, _, _, _ = market.get()
        state.set(initialize_state(doctors, hospitals, input.algorithm()))

    @reactive.effect
    @reactive.event(input.next_round)
    def _():
        doctors, hospitals, doctor_prefs, hospital_prefs, capacities = market.get()

        if state.get()["algorithm"] != input.algorithm():
            state.set(initialize_state(doctors, hospitals, input.algorithm()))

        s = state.get().copy()

        state.set(
            run_one_round(
                s,
                doctors,
                hospitals,
                doctor_prefs,
                hospital_prefs,
                capacities,
            )
        )

    @reactive.effect
    @reactive.event(input.run_full)
    def _():
        doctors, hospitals, doctor_prefs, hospital_prefs, capacities = market.get()

        if state.get()["algorithm"] != input.algorithm():
            state.set(initialize_state(doctors, hospitals, input.algorithm()))

        s = state.get().copy()

        while not s["done"]:
            s = run_one_round(
                s,
                doctors,
                hospitals,
                doctor_prefs,
                hospital_prefs,
                capacities,
            )

        state.set(s)

    @output
    @render.text
    def market_text():
        doctors, hospitals, doctor_prefs, hospital_prefs, capacities = market.get()

        lines = []
        lines.append(
            "Algorithm: "
            + ("Doctor-proposing DAA" if input.algorithm() == "doctor" else "Hospital-proposing DAA")
        )

        lines.append("")
        lines.append(f"Doctors: {', '.join(doctors)}")
        lines.append(f"Hospitals: {', '.join(hospitals)}")

        lines.append("")
        lines.append("Capacities:")
        lines.extend([f"  {h}: {capacities[h]}" for h in hospitals])

        lines.append("")
        lines.append("Acceptable doctor preferences:")
        lines.extend(
            [
                f"  {d}: {' > '.join(doctor_prefs[d]) if doctor_prefs[d] else 'none'}"
                for d in doctors
            ]
        )

        lines.append("")
        lines.append("Acceptable hospital preferences:")
        lines.extend(
            [
                f"  {h}: {' > '.join(hospital_prefs[h]) if hospital_prefs[h] else 'none'}"
                for h in hospitals
            ]
        )

        return "\n".join(lines)

    @output
    @render.text
    def step_text():
        return state.get()["last_step"]

    @output
    @render.text
    def matching_text():
        doctors, hospitals, _, _, _ = market.get()
        s = state.get()

        matches = extract_doctor_hospital_matches(s)

        lines = []

        if matches:
            for d, h in sorted(matches):
                lines.append(f"{d} — {h}")
        else:
            lines.append("No tentative matches yet.")

        matched_doctors = [d for d, h in matches]
        unmatched_doctors = [d for d in doctors if d not in matched_doctors]

        lines.append("")
        lines.append(
            "Unmatched doctors: "
            + (", ".join(unmatched_doctors) if unmatched_doctors else "none")
        )

        return "\n".join(lines)

    @output
    @render.text
    def log_text():
        s = state.get()
        return "\n\n".join(s["log"]) if s["log"] else "No rounds have been run yet."


app = App(app_ui, server)