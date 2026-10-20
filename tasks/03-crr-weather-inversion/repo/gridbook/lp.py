"""A small dense linear-program solver: two-phase simplex with Bland's rule. Standard library only.

    x, cost = linprog(c, A_ub, b_ub, A_eq, b_eq)

minimizes c.x subject to A_ub x <= b_ub, A_eq x == b_eq and x >= 0. Raises Infeasible or Unbounded.
Sized for the shadow dispatch: tens of variables and constraints per hour.
"""
from __future__ import annotations

EPS = 1e-9


class Infeasible(ValueError):
    pass


class Unbounded(ValueError):
    pass


def linprog(c, A_ub=(), b_ub=(), A_eq=(), b_eq=()):
    n = len(c)
    rows, rhs, kinds = [], [], []
    for a, b in zip(A_ub, b_ub):
        sign = -1.0 if b < 0 else 1.0
        rows.append([sign * float(x) for x in a])
        rhs.append(sign * float(b))
        kinds.append("ge" if b < 0 else "le")
    for a, b in zip(A_eq, b_eq):
        sign = -1.0 if b < 0 else 1.0
        rows.append([sign * float(x) for x in a])
        rhs.append(sign * float(b))
        kinds.append("eq")
    m = len(rows)
    n_slack = sum(k != "eq" for k in kinds)
    n_art = sum(k != "le" for k in kinds)
    total = n + n_slack + n_art
    T, basis, art = [], [], set()
    s, a = n, n + n_slack
    for i in range(m):
        row = rows[i] + [0.0] * (n_slack + n_art) + [rhs[i]]
        if kinds[i] == "le":
            row[s] = 1.0
            basis.append(s)
            s += 1
        elif kinds[i] == "ge":
            row[s] = -1.0
            s += 1
            row[a] = 1.0
            basis.append(a)
            art.add(a)
            a += 1
        else:
            row[a] = 1.0
            basis.append(a)
            art.add(a)
            a += 1
        T.append(row)

    def pivot(r, col):
        p = T[r][col]
        T[r] = [x / p for x in T[r]]
        for i in range(m):
            if i != r and T[i][col] != 0.0:
                f = T[i][col]
                T[i] = [x - f * y for x, y in zip(T[i], T[r])]
        basis[r] = col

    def run(obj, allowed):
        for _ in range(100000):
            red = {j: obj[j] - sum(obj[basis[i]] * T[i][j] for i in range(m)) for j in allowed}
            enter = next((j for j in allowed if red[j] < -EPS), None)
            if enter is None:
                return
            ratios = [(T[i][-1] / T[i][enter], i) for i in range(m) if T[i][enter] > EPS]
            if not ratios:
                raise Unbounded("the objective is unbounded below")
            best = min(r for r, _ in ratios)
            leave = min((basis[i], i) for r, i in ratios if r <= best + EPS)[1]
            pivot(leave, enter)
        raise RuntimeError("simplex did not converge")

    if art:
        run([1.0 if j in art else 0.0 for j in range(total)], list(range(total)))
        if sum(T[i][-1] for i in range(m) if basis[i] in art) > 1e-7:
            raise Infeasible("no point satisfies the constraints")
        for i in range(m):  # drive zero-level artificials out of the basis
            if basis[i] in art:
                j = next((j for j in range(n + n_slack) if abs(T[i][j]) > EPS), None)
                if j is not None:
                    pivot(i, j)
    run(list(c) + [0.0] * (n_slack + n_art), [j for j in range(total) if j not in art])
    x = [0.0] * total
    for i in range(m):
        x[basis[i]] = T[i][-1]
    x = [0.0 if abs(v) < EPS else v for v in x[:n]]
    return x, sum(ci * xi for ci, xi in zip(c, x))
