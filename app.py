from itertools import product
from math import cos, pi, sin

from flask import Flask, render_template, request

from cfg_to_cnf import (
    EPSILON,
    VARIABLE_PATTERN,
    _tokenize_production,
    convert_to_cnf,
    parse_cfg,
    remove_epsilon_productions,
    remove_unit_productions,
)
from cyk import build_parse_tree, cyk_algorithm, cyk_with_backpointers


app = Flask(__name__)


def format_cfg(cfg):
    formatted = []
    for var, productions in cfg.items():
        formatted.append(f"{var} -> {' | '.join(productions)}")
    return "\n".join(formatted)


def format_set(values):
    if not values:
        return "no variables"
    return "{ " + ", ".join(sorted(values)) + " }"


def get_terminal_alphabet(cfg):
    terminals = set()

    for productions in cfg.values():
        for production in productions:
            for token in _tokenize_production(production):
                if token != EPSILON and not VARIABLE_PATTERN.fullmatch(token):
                    terminals.add(token)

    return sorted(terminals)


def build_language_examples(cfg, start_symbol, max_length=4, max_examples=16):
    alphabet = get_terminal_alphabet(cfg)
    examples = []

    if EPSILON in cfg.get(start_symbol, []):
        examples.append(EPSILON)

    for length in range(1, max_length + 1):
        for candidate_tokens in product(alphabet, repeat=length):
            candidate = "".join(candidate_tokens)
            _, accepted = cyk_algorithm(cfg, candidate, start_symbol)
            if accepted:
                examples.append(candidate)
                if len(examples) >= max_examples:
                    return {
                        "alphabet": alphabet,
                        "examples": examples,
                        "max_length": max_length,
                        "max_examples": max_examples,
                    }

    return {
        "alphabet": alphabet,
        "examples": examples,
        "max_length": max_length,
        "max_examples": max_examples,
    }


def build_state_diagram_data(cfg, start_symbol):
    states = list(cfg.keys())
    final_state = "ACCEPT"
    accepting_states = set()
    transitions = {}

    for variable, productions in cfg.items():
        for production in productions:
            tokens = _tokenize_production(production)

            if tokens == [EPSILON]:
                if variable != start_symbol:
                    return {
                        "available": False,
                        "message": "State diagram is available only for regular grammars with epsilon allowed on the start symbol.",
                    }
                accepting_states.add(variable)
                continue

            if len(tokens) == 1 and not VARIABLE_PATTERN.fullmatch(tokens[0]):
                transitions.setdefault((variable, final_state), set()).add(tokens[0])
                continue

            if len(tokens) == 2 and not VARIABLE_PATTERN.fullmatch(tokens[0]) and VARIABLE_PATTERN.fullmatch(tokens[1]):
                transitions.setdefault((variable, tokens[1]), set()).add(tokens[0])
                continue

            return {
                "available": False,
                "message": f"State diagram is available only for regular grammars with rules like A -> aB, A -> a, or {start_symbol} -> {EPSILON}.",
            }

    if transitions and final_state not in states:
        states.append(final_state)
    if final_state in states:
        accepting_states.add(final_state)

    return {
        "available": True,
        "states": states,
        "start_state": start_symbol,
        "accepting_states": accepting_states,
        "transitions": [
            {
                "from": source,
                "to": target,
                "label": ", ".join(sorted(labels)),
            }
            for (source, target), labels in sorted(transitions.items())
        ],
    }


def render_state_diagram_svg(diagram):
    states = diagram["states"]
    accepting_states = set(diagram["accepting_states"])
    start_state = diagram["start_state"]
    transitions = diagram["transitions"]

    node_radius = 30
    loop_radius = 18
    width = max(360, 180 * len(states))
    height = 320
    center_x = width / 2
    center_y = height / 2 + 10
    orbit = max(90, min(width, height) / 2 - 70)

    if len(states) == 1:
        positions = {states[0]: (center_x, center_y)}
    else:
        positions = {}
        for index, state in enumerate(states):
            angle = (2 * pi * index / len(states)) - (pi / 2)
            positions[state] = (
                center_x + orbit * cos(angle),
                center_y + orbit * sin(angle),
            )

    svg = [
        f'<svg class="state-diagram-svg" viewBox="0 0 {int(width)} {int(height)}" xmlns="http://www.w3.org/2000/svg">',
        '<defs>',
        '<marker id="arrowhead" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">',
        '<path d="M0,0 L10,4 L0,8 Z" fill="#49607c"></path>',
        "</marker>",
        "</defs>",
    ]

    start_x, start_y = positions[start_state]
    svg.append(
        f'<line x1="{start_x - 80:.1f}" y1="{start_y:.1f}" x2="{start_x - node_radius:.1f}" y2="{start_y:.1f}" '
        'stroke="#49607c" stroke-width="2.5" marker-end="url(#arrowhead)"></line>'
    )

    for transition in transitions:
        source = transition["from"]
        target = transition["to"]
        label = transition["label"]
        x1, y1 = positions[source]
        x2, y2 = positions[target]

        if source == target:
            svg.append(
                f'<path d="M {x1 - 16:.1f} {y1 - node_radius + 2:.1f} '
                f'C {x1 - 44:.1f} {y1 - 72:.1f}, {x1 + 44:.1f} {y1 - 72:.1f}, {x1 + 16:.1f} {y1 - node_radius + 2:.1f}" '
                'fill="none" stroke="#49607c" stroke-width="2.2" marker-end="url(#arrowhead)"></path>'
            )
            svg.append(
                f'<text x="{x1:.1f}" y="{y1 - node_radius - loop_radius - 18:.1f}" class="edge-label" text-anchor="middle">{label}</text>'
            )
            continue

        dx = x2 - x1
        dy = y2 - y1
        distance = max((dx * dx + dy * dy) ** 0.5, 1)
        ux = dx / distance
        uy = dy / distance
        start_line_x = x1 + ux * node_radius
        start_line_y = y1 + uy * node_radius
        end_line_x = x2 - ux * node_radius
        end_line_y = y2 - uy * node_radius
        mid_x = (start_line_x + end_line_x) / 2
        mid_y = (start_line_y + end_line_y) / 2
        normal_x = -uy
        normal_y = ux
        label_x = mid_x + normal_x * 16
        label_y = mid_y + normal_y * 16

        svg.append(
            f'<line x1="{start_line_x:.1f}" y1="{start_line_y:.1f}" x2="{end_line_x:.1f}" y2="{end_line_y:.1f}" '
            'stroke="#49607c" stroke-width="2.2" marker-end="url(#arrowhead)"></line>'
        )
        svg.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" class="edge-label" text-anchor="middle">{label}</text>'
        )

    for state, (x, y) in positions.items():
        svg.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{node_radius}" class="state-node"></circle>'
        )
        if state in accepting_states:
            svg.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{node_radius - 7}" class="state-node-inner"></circle>'
            )
        svg.append(
            f'<text x="{x:.1f}" y="{y + 5:.1f}" class="state-label" text-anchor="middle">{state}</text>'
        )

    svg.append("</svg>")
    return "".join(svg)


def build_visualization(state_diagram, parse_tree, string, accepted):
    if state_diagram["available"]:
        return {
            "title": "State Diagram",
            "kind": "state_diagram",
            "message": "This diagram is built from the original grammar because it matches a regular grammar pattern.",
            "svg": state_diagram["svg"],
        }

    if string and accepted and parse_tree:
        return {
            "title": "Parse Tree",
            "kind": "parse_tree",
            "message": "This parse tree is reconstructed from the accepted input string using the CNF grammar and CYK backpointers.",
            "tree": parse_tree,
        }

    if string and not accepted:
        return {
            "title": "Grammar Visualization",
            "kind": "message",
            "message": "This grammar is not regular, so a finite-state diagram does not apply. Enter a string that is accepted to see a parse tree instead.",
        }

    if not string:
        return {
            "title": "Grammar Visualization",
            "kind": "message",
            "message": "This grammar is not regular, so a finite-state diagram does not apply. Run Full Simulation or Only CYK with an accepted string to see a parse tree.",
        }

    return {
        "title": "Grammar Visualization",
        "kind": "message",
        "message": "A grammar visualization could not be built for this input.",
    }


def build_cyk_steps(string, cyk_table, accepted, start_symbol):
    if not string or not cyk_table:
        return []

    diagonal_lines = []
    diagonal_changes = []
    for index, char in enumerate(string):
        cell = cyk_table[index][index]
        diagonal_lines.append(f"Letter '{char}' at position {index + 1} -> {format_set(cell)}")
        diagonal_changes.append({
            "text": f"For the letter '{char}', we place {format_set(cell)} in the first matching cell.",
            "type": "add" if cell else "note",
        })

    span_lines = []
    span_changes = []
    n = len(string)
    for length in range(2, n + 1):
        for start in range(n - length + 1):
            end = start + length - 1
            substring = string[start:end + 1]
            cell = cyk_table[start][end]
            span_lines.append(
                f"Substring '{substring}' from position {start + 1} to {end + 1} -> {format_set(cell)}"
            )
            span_changes.append({
                "text": f"For the substring '{substring}', the table entry becomes {format_set(cell)}.",
                "type": "add" if cell else "note",
            })

    final_cell = cyk_table[0][len(string) - 1]
    decision_text = "accepted" if accepted else "rejected"

    return [
        {
            "title": "Step 4: Fill the CYK Diagonal",
            "summary": "Start with single letters. For each letter in the string, write down which variables can produce that letter directly.",
            "content": diagonal_changes,
            "grammar": "\n".join(diagonal_lines),
        },
        {
            "title": "Step 5: Build Larger Substrings",
            "summary": "Now combine smaller answers to build bigger parts of the string, until the whole string has one final table entry.",
            "content": span_changes,
            "grammar": "\n".join(span_lines) if span_lines else "No larger substrings were needed.",
        },
        {
            "title": "Step 6: Final CYK Decision",
            "summary": f"Look at the final table entry for the whole string. If it contains {start_symbol}, the string is accepted. Otherwise, it is rejected.",
            "content": [
                {
                    "text": f"The final cell for the whole string contains {format_set(final_cell)}.",
                    "type": "add" if final_cell else "note",
                },
                {
                    "text": f"{start_symbol} is {'present' if accepted else 'not present'}, so the string is {decision_text}.",
                    "type": "add" if accepted else "remove",
                },
            ],
            "grammar": f"Whole string -> {format_set(final_cell)}\nFinal result -> {decision_text.title()}",
        },
    ]


@app.route("/")
def home():
    return render_template(
        "index.html",
        grammar=request.args.get("grammar", ""),
        string=request.args.get("string", ""),
        mode=request.args.get("mode", ""),
        show_steps=request.args.get("show_steps", "") == "1",
    )


@app.route("/process", methods=["POST"])
def process():
    grammar = request.form.get("grammar", "")
    string = request.form.get("string", "")
    show_steps = bool(request.form.get("show_steps"))
    mode = request.form.get("mode")

    cfg = parse_cfg(grammar)
    start_symbol = next(iter(cfg), "S")
    state_diagram = build_state_diagram_data(cfg, start_symbol)
    if state_diagram["available"]:
        state_diagram["svg"] = render_state_diagram_svg(state_diagram)

    cfg1, epsilon_steps = remove_epsilon_productions(cfg, start_symbol)
    cfg2, unit_steps = remove_unit_productions(cfg1)
    cnf_dict, cnf_steps = convert_to_cnf(cfg2)
    cnf = format_cfg(cnf_dict)
    language_examples = build_language_examples(cnf_dict, start_symbol)

    steps = [
        {
            "title": "Step 1: Remove epsilon-Productions",
            "summary": "Nullable productions are removed and equivalent alternatives are added where possible.",
            "content": epsilon_steps,
            "grammar": format_cfg(cfg1),
        },
        {
            "title": "Step 2: Remove Unit Productions",
            "summary": "Unit productions like A -> B are replaced with the productions of the referenced variable.",
            "content": unit_steps,
            "grammar": format_cfg(cfg2),
        },
        {
            "title": "Step 3: Convert to CNF",
            "summary": "Mixed and long productions are rewritten so every rule follows Chomsky Normal Form.",
            "content": cnf_steps,
            "grammar": cnf,
        },
    ]

    cyk_table, accepted, parse_tree = [], False, None
    if mode in ["cyk", "full"]:
        if string:
            cyk_table, accepted, backpointers = cyk_with_backpointers(cnf_dict, string, start_symbol)
            if accepted:
                parse_tree = build_parse_tree(backpointers, string, start_symbol)
            steps.extend(build_cyk_steps(string, cyk_table, accepted, start_symbol))
        else:
            accepted = EPSILON in cnf_dict.get(start_symbol, [])
            if accepted:
                parse_tree = {
                    "label": start_symbol,
                    "children": [{"label": EPSILON, "children": []}],
                }

    visualization = build_visualization(state_diagram, parse_tree, string, accepted)

    return render_template(
        "result.html",
        cnf=cnf,
        language_examples=language_examples,
        steps=steps,
        show_steps=show_steps,
        cyk_table=cyk_table,
        accepted=accepted,
        string=string,
        grammar=grammar,
        mode=mode,
        start_symbol=start_symbol,
        visualization=visualization,
    )


if __name__ == "__main__":
    app.run(debug=True)
