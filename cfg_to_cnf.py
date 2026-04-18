import re


VARIABLE_PATTERN = re.compile(r"^[A-Z][0-9']*$")
EPSILON = "\u03b5"
ALT_EPSILON = "\u03f5"
EPSILON_VALUES = {EPSILON, ALT_EPSILON, "epsilon", "eps"}
ARROW_VALUES = ("->", "\u2192")


def _normalize_production(prod):
    cleaned = prod.strip()
    if cleaned in EPSILON_VALUES:
        return EPSILON
    return cleaned


def _tokenize_production(prod):
    prod = _normalize_production(prod)

    if prod == EPSILON:
        return [EPSILON]

    if " " in prod.strip():
        return [token for token in prod.split() if token]

    tokens = []
    i = 0

    while i < len(prod):
        ch = prod[i]

        if ch.isspace():
            i += 1
            continue

        if ch.isupper():
            token = ch
            i += 1
            while i < len(prod) and (prod[i].isdigit() or prod[i] == "'"):
                token += prod[i]
                i += 1
            tokens.append(token)
            continue

        tokens.append(ch)
        i += 1

    return tokens


def _join_tokens(tokens):
    return "".join(tokens)


def _is_variable(token):
    return bool(VARIABLE_PATTERN.fullmatch(token))


def parse_cfg(grammar_text):
    cfg = {}
    lines = grammar_text.strip().split("\n")

    for line in lines:
        arrow = next((symbol for symbol in ARROW_VALUES if symbol in line), None)
        if arrow is None:
            continue

        left, right = line.split(arrow, 1)
        left = left.strip()
        productions = [_normalize_production(p) for p in right.split("|")]
        cfg.setdefault(left, [])
        for production in productions:
            if production not in cfg[left]:
                cfg[left].append(production)

    return cfg


def remove_unit_productions(cfg):
    new_cfg = {}
    steps = []

    for var in cfg:
        new_cfg[var] = []
        closure = {var}
        stack = [var]

        while stack:
            current = stack.pop()
            for prod in cfg.get(current, []):
                tokens = _tokenize_production(prod)
                if len(tokens) == 1 and _is_variable(tokens[0]):
                    target = tokens[0]
                    if current == var:
                        steps.append({
                            "text": f"{current} -> {target} (unit) removed",
                            "type": "remove",
                        })
                    if target not in closure:
                        closure.add(target)
                        stack.append(target)

        for target in closure:
            for replacement in cfg.get(target, []):
                tokens = _tokenize_production(replacement)
                if len(tokens) == 1 and _is_variable(tokens[0]):
                    continue

                if target != var:
                    steps.append({
                        "text": f"{var} -> {replacement} added via {target}",
                        "type": "add",
                    })

                if replacement not in new_cfg[var]:
                    new_cfg[var].append(replacement)

    return new_cfg, steps


def remove_epsilon_productions(cfg, start_symbol=None):
    new_cfg = {}
    steps = []

    nullable = set()
    changed = True
    while changed:
        changed = False
        for var, productions in cfg.items():
            if var in nullable:
                continue

            for prod in productions:
                tokens = _tokenize_production(prod)
                if prod == EPSILON or all(token in nullable for token in tokens):
                    nullable.add(var)
                    changed = True
                    if prod == EPSILON:
                        steps.append({
                            "text": f"{var} -> {EPSILON} removed",
                            "type": "remove",
                        })
                    break

    for var in cfg:
        new_cfg[var] = []

        for prod in cfg[var]:
            if prod == EPSILON:
                continue

            if prod not in new_cfg[var]:
                new_cfg[var].append(prod)

            tokens = _tokenize_production(prod)
            nullable_positions = [index for index, token in enumerate(tokens) if token in nullable]

            for mask in range(1, 1 << len(nullable_positions)):
                removed_indexes = {
                    nullable_positions[bit]
                    for bit in range(len(nullable_positions))
                    if mask & (1 << bit)
                }
                new_prod_tokens = [
                    token for index, token in enumerate(tokens) if index not in removed_indexes
                ]

                if not new_prod_tokens:
                    continue

                new_prod = _join_tokens(new_prod_tokens)
                steps.append({
                    "text": f"{var} -> {new_prod} added from {prod}",
                    "type": "add",
                })
                if new_prod not in new_cfg[var]:
                    new_cfg[var].append(new_prod)

    if start_symbol and start_symbol in nullable:
        new_cfg.setdefault(start_symbol, [])
        if EPSILON not in new_cfg[start_symbol]:
            new_cfg[start_symbol].append(EPSILON)
            steps.append({
                "text": f"{start_symbol} -> {EPSILON} kept because the start symbol can derive the empty string",
                "type": "note",
            })

    return new_cfg, steps


def convert_to_cnf(cfg):
    new_cfg = {}
    terminal_map = {}
    counter = 1
    steps = []

    for var in cfg:
        new_cfg.setdefault(var, [])

        for prod in cfg[var]:
            tokens = _tokenize_production(prod)

            if len(tokens) == 1 and len(tokens[0]) == 1 and tokens[0].islower():
                new_cfg[var].append(prod)
                continue

            replaced_tokens = []
            for token in tokens:
                if len(token) == 1 and token.islower():
                    if token not in terminal_map:
                        new_var = f"T{counter}"
                        counter += 1
                        terminal_map[token] = new_var
                        new_cfg[new_var] = [token]
                        steps.append({
                            "text": f"{token} replaced with {new_var}",
                            "type": "add",
                        })
                    replaced_tokens.append(terminal_map[token])
                else:
                    replaced_tokens.append(token)

            if len(replaced_tokens) <= 2:
                new_prod = _join_tokens(replaced_tokens)
                if new_prod not in new_cfg[var]:
                    new_cfg[var].append(new_prod)
                continue

            current_var = var
            remaining_tokens = replaced_tokens[:]

            while len(remaining_tokens) > 2:
                new_var = f"X{counter}"
                counter += 1

                new_cfg.setdefault(new_var, [])
                split_prod = f"{remaining_tokens[0]}{new_var}"
                if split_prod not in new_cfg[current_var]:
                    new_cfg[current_var].append(split_prod)
                steps.append({
                    "text": f"{current_var} -> {split_prod} created while splitting {prod}",
                    "type": "add",
                })

                current_var = new_var
                remaining_tokens = remaining_tokens[1:]

            final_prod = _join_tokens(remaining_tokens)
            if final_prod not in new_cfg[current_var]:
                new_cfg[current_var].append(final_prod)
            steps.append({
                "text": f"{current_var} -> {final_prod} finalized",
                "type": "add",
            })

    return new_cfg, steps