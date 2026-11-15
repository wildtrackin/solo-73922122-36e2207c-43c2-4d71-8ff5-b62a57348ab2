"""挂载到 /docs 的演示请求。

/match：重复条码、交叉候选、等价最优。
/redact-counts：补遮盖、无敏感格、敏感格自成矩形、不可行拒绝。
"""

DEMO_EXAMPLES = {
    "duplicate_barcodes": {
        "summary": "重复条码：同条码多条记录，按时间窗区分",
        "description": (
            "条码 BC-100 在两侧各出现两次，仅靠条码无法确定配对；"
            "10 分钟时间窗把配对唯一锁定，三对全部成为确定配对。"
        ),
        "value": {
            "sampling_records": [
                {"id": "S-01", "barcode": "BC-100", "timestamp": "2026-11-14T08:00:00Z"},
                {"id": "S-02", "barcode": "BC-100", "timestamp": "2026-11-14T08:30:00Z"},
                {"id": "S-03", "barcode": "BC-200", "timestamp": "2026-11-14T09:00:00Z"},
            ],
            "detection_records": [
                {"id": "D-01", "barcode": "BC-100", "timestamp": "2026-11-14T08:04:00Z"},
                {"id": "D-02", "barcode": "BC-100", "timestamp": "2026-11-14T08:26:00Z"},
                {"id": "D-03", "barcode": "BC-200", "timestamp": "2026-11-14T09:06:00Z"},
            ],
        },
    },
    "crossing_candidates": {
        "summary": "交叉候选：时间窗交叉，贪心最近邻反而更差",
        "description": (
            "S-12 与 D-11 仅差 60 秒，若贪心占用，S-11 只能配 D-12（480 秒），"
            "总差 540 秒；全局最优为 S-11↔D-11 + S-12↔D-12，共 420 秒，两对均为确定配对。"
            "D-13 超出所有时间窗，始终未配对。"
        ),
        "value": {
            "sampling_records": [
                {"id": "S-11", "barcode": "BC-300", "timestamp": "2026-11-14T10:00:00Z"},
                {"id": "S-12", "barcode": "BC-300", "timestamp": "2026-11-14T10:04:00Z"},
            ],
            "detection_records": [
                {"id": "D-11", "barcode": "BC-300", "timestamp": "2026-11-14T10:03:00Z"},
                {"id": "D-12", "barcode": "BC-300", "timestamp": "2026-11-14T10:08:00Z"},
                {"id": "D-13", "barcode": "BC-300", "timestamp": "2026-11-14T10:30:00Z"},
            ],
        },
    },
    "equivalent_optima": {
        "summary": "等价最优：多套同等最优方案，只输出确定配对",
        "description": (
            "BC-400 下 S-21/S-22 与 D-21/D-22 形成两套成本相同（各 600 秒）的最优方案，"
            "四条记录全部待核查（始终被配对但对象不定），接口不替质控员任选一套；"
            "BC-500 是唯一确定配对；S-24、D-24 无任何候选，始终未配对。"
        ),
        "value": {
            "sampling_records": [
                {"id": "S-21", "barcode": "BC-400", "timestamp": "2026-11-14T12:00:00Z"},
                {"id": "S-22", "barcode": "BC-400", "timestamp": "2026-11-14T12:10:00Z"},
                {"id": "S-23", "barcode": "BC-500", "timestamp": "2026-11-14T13:00:00Z"},
                {"id": "S-24", "barcode": "BC-600", "timestamp": "2026-11-14T15:00:00Z"},
            ],
            "detection_records": [
                {"id": "D-21", "barcode": "BC-400", "timestamp": "2026-11-14T12:05:00Z"},
                {"id": "D-22", "barcode": "BC-400", "timestamp": "2026-11-14T12:05:00Z"},
                {"id": "D-23", "barcode": "BC-500", "timestamp": "2026-11-14T13:03:00Z"},
                {"id": "D-24", "barcode": "BC-700", "timestamp": "2026-11-14T15:00:00Z"},
            ],
        },
    },
}

REDACT_EXAMPLES = {
    "secondary_suppression": {
        "summary": "补遮盖：只遮敏感格会被行/列合计反推，需补遮 3 格",
        "description": (
            "阈值 3 下只有 (SP-1, T-A)=2 是敏感格；但 2×3 表中任何被遮格只要"
            "同行或同列其余格全公开就会被合计唯一锁定，因此最少补遮 3 格，"
            "使 (SP-1,T-A)、(SP-1,T-B)、(SP-2,T-A)、(SP-2,T-B) 形成遮盖矩形，"
            "此时敏感格在 0~4 内均有可行补全。"
        ),
        "value": {
            "row_names": ["SP-1", "SP-2"],
            "column_names": ["T-A", "T-B", "T-C"],
            "counts": [[2, 5, 4], [6, 7, 8]],
            "threshold": 3,
        },
    },
    "no_sensitive_cells": {
        "summary": "无敏感格：没有任何格子落在 (0, 阈值) 区间，全表可公开",
        "description": (
            "阈值 3 下，0 与 ≥3 的格子都不是敏感格；本表不含 1 或 2，"
            "因此无需任何遮盖，行列合计与全部格子都可发布。"
        ),
        "value": {
            "row_names": ["SP-1", "SP-2"],
            "column_names": ["T-A", "T-B"],
            "counts": [[0, 5], [7, 9]],
            "threshold": 3,
        },
    },
    "sensitive_rectangle": {
        "summary": "敏感格自成矩形：只遮敏感格即安全，无需补遮盖",
        "description": (
            "阈值 2 下四个 1 都是敏感格，且恰好构成 2×2 矩形：每个敏感格"
            "在同行、同列都有另一个被遮格分担自由度，公开数字容许它取 0 或 2，"
            "因此补遮盖数为 0。"
        ),
        "value": {
            "row_names": ["SP-1", "SP-2", "SP-3"],
            "column_names": ["T-A", "T-B", "T-C"],
            "counts": [[1, 1, 5], [1, 1, 5], [5, 5, 5]],
            "threshold": 2,
        },
    },
    "infeasible_table": {
        "summary": "不可行：行列合计把敏感格锁死，接口拒绝并返回 422",
        "description": (
            "阈值 4 下 (SP-1, T-A)=3 是敏感格；但行合计 12、列合计 3 与单格上限 9 "
            "共同把它锁定为 3（即使全表遮盖也无法容许其他取值），"
            "接口返回 422 且不给出任何部分表格或原始计数。"
        ),
        "value": {
            "row_names": ["SP-1", "SP-2"],
            "column_names": ["T-A", "T-B"],
            "counts": [[3, 9], [0, 5]],
            "threshold": 4,
        },
    },
}
