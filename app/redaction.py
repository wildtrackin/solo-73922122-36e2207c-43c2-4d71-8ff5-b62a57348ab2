"""阳性计数表遮盖（cell suppression）核心算法。

背景：数据管理员要把"采样点 × 检测项目"的阳性计数表交给合作方，
同时公布行合计与列合计。小计数格（0 < 计数 < 阈值）是敏感格，必须遮盖；
但只遮敏感格往往不够——合作方可以用行/列合计把被遮格反推出来，
因此需要补遮盖（secondary suppression）尽量少的非敏感格。

安全判定（与需求逐字对应）：
  对每个被遮格 c，公开数字（可公开格 + 行列合计）必须容许另一张
  "各格仍在 0~9、但 c 格计数不同"的整数矩阵。
  即：把未遮格固定为公开值、行列合计固定后，c 在 0~9 内至少存在
  一个不同于真值的可行取值。

  实现对**每一个**遮盖格（含补遮盖格）都做此检查，而非只查敏感格。
  这不改变最优解：若某补遮盖格在方案 R 下被唯一确定，则 R 去掉它
  信息完全等价、补遮盖更少，与"补遮盖数最少"矛盾。因此最优解处
  两种检查等价，而统一检查让实现与推理都更简单。

优化目标：
  1. 补遮盖格数最少；
  2. 并列时取"行优先、列次之"字典序最小的遮盖坐标集合
     （坐标按 (行, 列) 升序排列后做字典序比较）。
  注：敏感格集合固定，往两个等长有序坐标列表中合并同一集合
  保持字典序，故对全遮盖集排序与只对补遮盖集排序结果一致。

规模：2~3 行、2~3 列，格子 ≤ 9，候选子集 ≤ 2^8 = 256，
每个候选集对 ≤ 9 个格子各做一次微型可行性回溯，开销可忽略。
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

CELL_MIN = 0
CELL_MAX = 9


@dataclass(frozen=True)
class RedactionPlan:
    """一份最优遮盖方案。"""

    row_totals: tuple[int, ...]
    column_totals: tuple[int, ...]
    redacted: frozenset[tuple[int, int]]  # 全部遮盖格坐标（含敏感格与补遮盖格）


def _has_alternative_completion(
    row_remaining: list[int],
    col_remaining: list[int],
    cells: tuple[tuple[int, int], ...],
    target: tuple[int, int],
    forbidden: int,
) -> bool:
    """是否存在可行补全使 target 格取值 != forbidden。

    row_remaining[i] / col_remaining[j]：扣除已公开格后，第 i 行 / 第 j 列
    尚待分配的合计；cells 为全部待填格（含 target），按 (行, 列) 升序。
    每格取值 0~9。回溯 + 行列剩余量界剪枝，规模 ≤ 9 格，开销可忽略。
    """
    n = len(cells)
    # 每个位置之后，同行/同列还剩多少待填格（用于剩余量界剪枝；n ≤ 9，O(n^2) 足够）
    row_left = [0] * n
    col_left = [0] * n
    for k in range(n):
        i, j = cells[k]
        row_left[k] = sum(1 for p in range(k + 1, n) if cells[p][0] == i)
        col_left[k] = sum(1 for p in range(k + 1, n) if cells[p][1] == j)

    def backtrack(k: int) -> bool:
        if k == n:
            return True
        i, j = cells[k]
        ri, cj = row_remaining[i], col_remaining[j]
        hi = min(CELL_MAX, ri, cj)
        for v in range(CELL_MIN, hi + 1):
            if (i, j) == target and v == forbidden:
                continue
            # 剩余行/列合计必须能由同行/列其余待填格（每格 0~9）承担
            if ri - v > CELL_MAX * row_left[k]:
                continue
            if cj - v > CELL_MAX * col_left[k]:
                continue
            row_remaining[i] = ri - v
            col_remaining[j] = cj - v
            if backtrack(k + 1):
                return True
            row_remaining[i] = ri
            col_remaining[j] = cj
        return False

    return backtrack(0)


def _redaction_feasible(
    counts: list[list[int]],
    redacted: frozenset[tuple[int, int]],
    row_totals: tuple[int, ...],
    col_totals: tuple[int, ...],
) -> bool:
    """遮盖集合是否安全：每个遮盖格都存在"取值不同"的可行补全。"""
    n_rows = len(counts)
    n_cols = len(counts[0])
    cells = tuple(sorted(redacted))
    # 扣除公开格后，每行/列剩余待分配的合计
    row_remaining = [
        row_totals[i] - sum(counts[i][j] for j in range(n_cols) if (i, j) not in redacted)
        for i in range(n_rows)
    ]
    col_remaining = [
        col_totals[j] - sum(counts[i][j] for i in range(n_rows) if (i, j) not in redacted)
        for j in range(n_cols)
    ]
    for target in cells:
        if not _has_alternative_completion(
            list(row_remaining),
            list(col_remaining),
            cells,
            target,
            counts[target[0]][target[1]],
        ):
            return False
    return True


def plan_redaction(counts: list[list[int]], threshold: int) -> RedactionPlan | None:
    """求最优遮盖方案；无可行方案时返回 None（调用方不得给出部分表）。"""
    n_rows = len(counts)
    n_cols = len(counts[0])
    row_totals = tuple(sum(row) for row in counts)
    col_totals = tuple(
        sum(counts[i][j] for i in range(n_rows)) for j in range(n_cols)
    )
    all_cells = {(i, j) for i in range(n_rows) for j in range(n_cols)}
    sensitive = frozenset(
        (i, j) for i, j in all_cells if 0 < counts[i][j] < threshold
    )
    others = sorted(all_cells - sensitive)  # 行优先、列次之

    for extra in range(len(others) + 1):
        best: tuple[tuple[tuple[int, int], ...], frozenset[tuple[int, int]]] | None = None
        for picked in combinations(others, extra):
            redacted = sensitive | frozenset(picked)
            key = tuple(sorted(redacted))
            if best is not None and key >= best[0]:
                continue
            if _redaction_feasible(counts, redacted, row_totals, col_totals):
                best = (key, redacted)
        if best is not None:
            return RedactionPlan(
                row_totals=row_totals,
                column_totals=col_totals,
                redacted=best[1],
            )
    return None
