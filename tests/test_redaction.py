"""计数表遮盖核心算法的单元测试与暴力枚举交叉验证。"""

from itertools import combinations, product

from app.redaction import plan_redaction

# ---------------------------------------------------------------------------
# 独立暴力枚举：与 app.redaction 完全不同的实现，用于交叉验证
# ---------------------------------------------------------------------------


def brute_value_sets(counts, redacted):
    """枚举全部可行补全，返回每个被遮格的可行取值集合。

    按行递归：非末行枚举该行被遮格的所有 0~9 赋值（行合计剪枝 +
    列合计界剪枝）；末行由列剩余唯一确定并校验。真值本身总是一个
    可行补全，因此取值集合 ≥ 2 当且仅当存在"取值不同"的另一张矩阵。
    """
    n_rows = len(counts)
    n_cols = len(counts[0])
    row_totals = [sum(r) for r in counts]
    col_totals = [sum(counts[i][j] for i in range(n_rows)) for j in range(n_cols)]
    cells = sorted(redacted)
    values = {c: set() for c in cells}
    row_cells = [[c for c in cells if c[0] == i] for i in range(n_rows)]
    row_rem = [
        row_totals[i]
        - sum(counts[i][j] for j in range(n_cols) if (i, j) not in redacted)
        for i in range(n_rows)
    ]
    # 每列还有多少被遮格（含当前行之后的），用于列合计界剪枝
    assignment = {}

    def column_ok(up_to_row):
        for j in range(n_cols):
            used = 0
            open_slots = 0
            for i in range(n_rows):
                if (i, j) in assignment and i <= up_to_row:
                    used += assignment[(i, j)]
                elif (i, j) in redacted:
                    open_slots += 1
                else:
                    used += counts[i][j]
            if used > col_totals[j] or used + 9 * open_slots < col_totals[j]:
                return False
        return True

    def rec(i):
        if i == n_rows:
            for c, v in assignment.items():
                values[c].add(v)
            return
        if i == n_rows - 1:
            vals = {}
            for ri, j in row_cells[i]:
                col_used = sum(
                    assignment[(r, j)] if (r, j) in assignment else counts[r][j]
                    for r in range(n_rows)
                    if r != ri
                )
                v = col_totals[j] - col_used
                if not 0 <= v <= 9:
                    return
                vals[(ri, j)] = v
            if sum(vals.values()) != row_rem[i]:
                return
            assignment.update(vals)
            if column_ok(i):
                rec(i + 1)
            for c in vals:
                del assignment[c]
            return
        cells_i = row_cells[i]
        for combo in product(range(10), repeat=len(cells_i)):
            if sum(combo) != row_rem[i]:
                continue
            for c, v in zip(cells_i, combo):
                assignment[c] = v
            if column_ok(i):
                rec(i + 1)
            for c in cells_i:
                del assignment[c]

    rec(0)
    return values


def brute_plan(counts, threshold):
    """纯暴力求最优遮盖集：逐补遮盖数、逐集合枚举可行性，取字典序最小。"""
    n_rows = len(counts)
    n_cols = len(counts[0])
    all_cells = [(i, j) for i in range(n_rows) for j in range(n_cols)]
    sensitive = {c for c in all_cells if 0 < counts[c[0]][c[1]] < threshold}
    others = sorted(set(all_cells) - sensitive)
    for extra in range(len(others) + 1):
        best = None
        for picked in combinations(others, extra):
            redacted = sensitive | set(picked)
            values = brute_value_sets(counts, redacted)
            if all(len(values[c]) >= 2 for c in redacted):
                key = tuple(sorted(redacted))
                if best is None or key < best:
                    best = key
        if best is not None:
            return best
    return None


def solver_key(counts, threshold):
    plan = plan_redaction(counts, threshold)
    return None if plan is None else tuple(sorted(plan.redacted))


# ---------------------------------------------------------------------------
# 手工构造用例
# ---------------------------------------------------------------------------


def test_no_sensitive_cells_redacts_nothing():
    plan = plan_redaction([[0, 5], [7, 9]], 3)
    assert plan is not None
    assert plan.redacted == frozenset()
    assert plan.row_totals == (5, 16)
    assert plan.column_totals == (7, 14)


def test_zero_is_not_sensitive():
    """0 不属于'大于零且小于阈值'，但可作为补遮盖格被选中。"""
    plan = plan_redaction([[0, 1], [5, 5]], 2)
    assert plan is not None
    # 2x2 中一个敏感格会级联为全表遮盖
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_threshold_boundary():
    """等于阈值的格子不是敏感格；阈值 - 1 是敏感格。"""
    # t=3：1、2 敏感；3、4 不敏感
    plan = plan_redaction([[1, 2], [3, 4]], 3)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_sensitive_rectangle_needs_no_extra():
    """四个敏感格自成 2x2 矩形：互相提供行列自由度，补遮盖数为 0。"""
    plan = plan_redaction([[1, 1, 5], [1, 1, 5], [5, 5, 5]], 2)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_single_sensitive_cell_forces_rectangle_in_3x3():
    """3x3 中单个敏感格最少需要 3 个补遮盖格构成矩形，取字典序最小者。"""
    plan = plan_redaction([[2, 5, 5], [5, 5, 5], [5, 5, 5]], 3)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_two_sensitive_cells_share_row_cover():
    """同行两个敏感格互为行伙伴，各需一个列伙伴；取字典序最小集合。"""
    plan = plan_redaction([[1, 5, 1], [5, 5, 5], [5, 5, 5]], 2)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 2), (1, 0), (1, 2)})


def test_2x3_lexicographic_tie_break():
    """两组可行补遮盖 {(0,1),(1,0),(1,1)} 与 {(0,2),(1,0),(1,2)} 并列，
    按行优先、列次之取字典序最小。"""
    plan = plan_redaction([[2, 5, 4], [6, 7, 8]], 3)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})
    assert plan.row_totals == (11, 21)
    assert plan.column_totals == (8, 12, 12)


def test_2x2_cascades_to_full_redaction():
    plan = plan_redaction([[1, 1], [1, 5]], 2)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


def test_infeasible_when_totals_lock_sensitive_cell():
    """行合计 12、列合计 3 与单格上限 9 把敏感格锁死为 3。"""
    assert plan_redaction([[3, 9], [0, 5]], 4) is None


def test_infeasible_when_digit_bound_locks_cell():
    """真值 1 的唯一'替代'需要格子取 10，超出 0~9 => 不可行。"""
    assert plan_redaction([[1, 9], [9, 9]], 2) is None


def test_alternative_must_stay_within_0_to_9():
    """全遮后敏感格 1 的替代值 0 需要邻格取 10（非法），但 2 可行。"""
    plan = plan_redaction([[1, 9], [9, 0]], 2)
    assert plan is not None
    assert plan.redacted == frozenset({(0, 0), (0, 1), (1, 0), (1, 1)})


# ---------------------------------------------------------------------------
# 与独立暴力枚举交叉验证
# ---------------------------------------------------------------------------


def test_cross_check_all_2x2_up_to_2():
    """2x2、格子 0~2、阈值 2~4 全部 243 个实例与暴力枚举一致。"""
    for values in product(range(3), repeat=4):
        counts = [list(values[:2]), list(values[2:])]
        for threshold in (2, 3, 4):
            assert solver_key(counts, threshold) == brute_plan(counts, threshold), (
                counts,
                threshold,
            )


def test_cross_check_random_2x3():
    """2x3 随机实例（种子固定）与暴力枚举一致。"""
    import random

    rng = random.Random(20261115)
    for _ in range(60):
        counts = [[rng.randint(0, 4) for _ in range(3)] for _ in range(2)]
        threshold = rng.choice((2, 3, 4))
        assert solver_key(counts, threshold) == brute_plan(counts, threshold), (
            counts,
            threshold,
        )


def test_cross_check_random_3x3():
    """3x3 随机实例（种子固定）与暴力枚举一致。"""
    import random

    rng = random.Random(20261116)
    for _ in range(12):
        counts = [[rng.randint(0, 3) for _ in range(3)] for _ in range(3)]
        threshold = rng.choice((2, 3, 4))
        assert solver_key(counts, threshold) == brute_plan(counts, threshold), (
            counts,
            threshold,
        )
