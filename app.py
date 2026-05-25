from shiny import App, ui, render, reactive


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

            # If agent never put itself in the list, missing choices are acceptable by default
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


def make_market(num_doctors, num_hospitals, capacity_text, doctor_pref_text, hospital_pref_text):
    doctors = [f"D{i}" for i in range(1, num_doctors + 1)]
    hospitals = [f"H{i}" for i in range(1, num_hospitals + 1)]

    doctor_prefs = parse_preferences(doctor_pref_text, doctors, hospitals)
    hospital_prefs = parse_preferences(hospital_pref_text, hospitals, doctors)
    capacities = parse_capacities(capacity_text, hospitals)

    return doctors, hospitals, doctor_prefs, hospital_prefs, capacities


def initialize_state(doctors, hospitals):
    return {
        "round": 0,
        "unmatched": doctors.copy(),
        "next_choice_index": {d: 0 for d in doctors},
        "held": {h: [] for h in hospitals},
        "log": [],
        "done": False,
        "last_step": "Click Next Round to begin.",
    }


def hospital_rank(hospital, doctor, hospital_prefs):
    return hospital_prefs[hospital].index(doctor)


def run_one_round(s, doctors, hospitals, doctor_prefs, hospital_prefs, capacities):
    if s["done"]:
        s["last_step"] = "Algorithm already complete."
        return s

    s["round"] += 1
    lines = [f"Round {s['round']}"]

    proposals = {h: [] for h in hospitals}
    new_unmatched = []

    for d in s["unmatched"]:
        i = s["next_choice_index"][d]

        if i < len(doctor_prefs[d]):
            h = doctor_prefs[d][i]
            proposals[h].append(d)
            s["next_choice_index"][d] += 1
            lines.append(f"{d} → {h}")
        else:
            lines.append(f"{d} has no acceptable hospitals left.")

    for h in hospitals:
        applicants = s["held"][h] + proposals[h]

        if not applicants:
            continue

        acceptable_applicants = [d for d in applicants if d in hospital_prefs[h]]
        unacceptable_applicants = [d for d in applicants if d not in hospital_prefs[h]]

        ranked = sorted(
            acceptable_applicants,
            key=lambda d: hospital_rank(h, d, hospital_prefs),
        )

        accepted = ranked[:capacities[h]]
        rejected = ranked[capacities[h]:] + unacceptable_applicants

        s["held"][h] = accepted

        if accepted:
            lines.append(f"{h} holds: {', '.join(accepted)}")
        else:
            lines.append(f"{h} holds nobody.")

        for d in rejected:
            if d in unacceptable_applicants:
                lines.append(f"{h} rejects {d} as unacceptable.")
            else:
                lines.append(f"{h} rejects: {d}")

            if s["next_choice_index"][d] < len(doctor_prefs[d]):
                new_unmatched.append(d)
            else:
                lines.append(f"{d} has no acceptable hospitals left.")

    s["unmatched"] = new_unmatched

    if not s["unmatched"]:
        s["done"] = True
        lines.append("Complete.")

    s["last_step"] = "\n".join(lines)
    s["log"].append(s["last_step"])

    return s


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h3("Market Setup"),

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
    ui.p("Doctor-proposing deferred acceptance with custom preferences, capacities, and unacceptable matches."),

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
    state = reactive.Value(initialize_state(doctors, hospitals))

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
        state.set(initialize_state(doctors, hospitals))

    @reactive.effect
    @reactive.event(input.reset)
    def _():
        doctors, hospitals, _, _, _ = market.get()
        state.set(initialize_state(doctors, hospitals))

    @reactive.effect
    @reactive.event(input.next_round)
    def _():
        doctors, hospitals, doctor_prefs, hospital_prefs, capacities = market.get()
        s = state.get().copy()
        state.set(run_one_round(s, doctors, hospitals, doctor_prefs, hospital_prefs, capacities))

    @reactive.effect
    @reactive.event(input.run_full)
    def _():
        doctors, hospitals, doctor_prefs, hospital_prefs, capacities = market.get()
        s = state.get().copy()

        while not s["done"]:
            s = run_one_round(s, doctors, hospitals, doctor_prefs, hospital_prefs, capacities)

        state.set(s)

    @output
    @render.text
    def market_text():
        doctors, hospitals, doctor_prefs, hospital_prefs, capacities = market.get()

        lines = []
        lines.append(f"Doctors: {', '.join(doctors)}")
        lines.append(f"Hospitals: {', '.join(hospitals)}")

        lines.append("")
        lines.append("Capacities:")
        lines.extend([f"  {h}: {capacities[h]}" for h in hospitals])

        lines.append("")
        lines.append("Acceptable doctor preferences:")
        lines.extend([f"  {d}: {' > '.join(doctor_prefs[d]) if doctor_prefs[d] else 'none'}" for d in doctors])

        lines.append("")
        lines.append("Acceptable hospital preferences:")
        lines.extend([f"  {h}: {' > '.join(hospital_prefs[h]) if hospital_prefs[h] else 'none'}" for h in hospitals])

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

        lines = []

        for h in hospitals:
            if s["held"][h]:
                for d in s["held"][h]:
                    lines.append(f"{d} — {h}")
            else:
                lines.append(f"{h}: empty")

        lines.append("")
        lines.append(
            "Still active/unmatched: " + (", ".join(s["unmatched"]) if s["unmatched"] else "none")
        )

        matched_doctors = [d for held in s["held"].values() for d in held]
        permanently_unmatched = [
            d for d in doctors
            if d not in matched_doctors and d not in s["unmatched"]
        ]

        lines.append(
            "Permanently unmatched: "
            + (", ".join(permanently_unmatched) if permanently_unmatched else "none")
        )

        return "\n".join(lines)

    @output
    @render.text
    def log_text():
        s = state.get()
        return "\n\n".join(s["log"]) if s["log"] else "No rounds have been run yet."


app = App(app_ui, server)