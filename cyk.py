def _tokenize_production(prod):
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


def cyk_algorithm(cfg, string, start_symbol="S"):
    n = len(string)
    table = [[set() for _ in range(n)] for _ in range(n)]

    for i, char in enumerate(string):
        for var, productions in cfg.items():
            if char in productions:
                table[i][i].add(var)

    for length in range(2, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1

            for k in range(i, j):
                left = table[i][k]
                right = table[k + 1][j]

                for var, productions in cfg.items():
                    for prod in productions:
                        tokens = _tokenize_production(prod)
                        if len(tokens) == 2 and tokens[0] in left and tokens[1] in right:
                            table[i][j].add(var)

    accepted = n > 0 and start_symbol in table[0][n - 1]
    return table, accepted


def cyk_with_backpointers(cfg, string, start_symbol="S"):
    n = len(string)
    table = [[set() for _ in range(n)] for _ in range(n)]
    back = [[{} for _ in range(n)] for _ in range(n)]

    for i, char in enumerate(string):
        for var, productions in cfg.items():
            if char in productions:
                table[i][i].add(var)
                back[i][i].setdefault(var, {
                    "type": "terminal",
                    "symbol": char,
                })

    for length in range(2, n + 1):
        for i in range(n - length + 1):
            j = i + length - 1

            for k in range(i, j):
                left = table[i][k]
                right = table[k + 1][j]

                for var, productions in cfg.items():
                    for prod in productions:
                        tokens = _tokenize_production(prod)
                        if len(tokens) == 2 and tokens[0] in left and tokens[1] in right:
                            table[i][j].add(var)
                            back[i][j].setdefault(var, {
                                "type": "split",
                                "left_var": tokens[0],
                                "right_var": tokens[1],
                                "split": k,
                            })

    accepted = n > 0 and start_symbol in table[0][n - 1]
    return table, accepted, back


def build_parse_tree(backpointers, string, start_symbol="S"):
    if not string:
        return None

    if not backpointers or start_symbol not in backpointers[0][len(string) - 1]:
        return None

    def _build(i, j, variable):
        node = backpointers[i][j].get(variable)
        if not node:
            return None

        if node["type"] == "terminal":
            return {
                "label": variable,
                "children": [{
                    "label": node["symbol"],
                    "children": [],
                }],
            }

        left_child = _build(i, node["split"], node["left_var"])
        right_child = _build(node["split"] + 1, j, node["right_var"])
        if left_child is None or right_child is None:
            return None

        return {
            "label": variable,
            "children": [left_child, right_child],
        }

    return _build(0, len(string) - 1, start_symbol)
