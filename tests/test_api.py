"""API 集成测试。"""

import copy

from fastapi.testclient import TestClient

from app.examples import DEMO_EXAMPLES, REDACT_EXAMPLES
from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root_redirects_to_docs():
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/docs"


def test_docs_page_served():
    resp = client.get("/docs")
    assert resp.status_code == 200


def test_openapi_contains_three_demo_examples():
    spec = client.get("/openapi.json").json()
    examples = spec["paths"]["/match"]["post"]["requestBody"]["content"][
        "application/json"
    ]["examples"]
    assert {"duplicate_barcodes", "crossing_candidates", "equivalent_optima"} <= set(
        examples
    )


def test_demo_duplicate_barcodes():
    payload = copy.deepcopy(DEMO_EXAMPLES["duplicate_barcodes"]["value"])
    resp = client.post("/match", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["max_pairs"] == 3
    assert body["summary"]["min_total_time_diff_seconds"] == 840.0
    assert {
        (p["sampling_id"], p["detection_id"]) for p in body["certain_pairs"]
    } == {("S-01", "D-01"), ("S-02", "D-02"), ("S-03", "D-03")}
    assert body["summary"]["sampling_status"] == {
        "certain": 3,
        "review": 0,
        "unmatched": 0,
    }


def test_demo_crossing_candidates():
    payload = copy.deepcopy(DEMO_EXAMPLES["crossing_candidates"]["value"])
    resp = client.post("/match", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["max_pairs"] == 2
    assert body["summary"]["min_total_time_diff_seconds"] == 420.0
    assert {
        (p["sampling_id"], p["detection_id"]) for p in body["certain_pairs"]
    } == {("S-11", "D-11"), ("S-12", "D-12")}
    det = {r["id"]: r for r in body["detection_records"]}
    assert det["D-13"]["status"] == "unmatched"
    assert det["D-13"]["possible_partners"] == []


def test_demo_equivalent_optima():
    payload = copy.deepcopy(DEMO_EXAMPLES["equivalent_optima"]["value"])
    resp = client.post("/match", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["max_pairs"] == 3
    assert body["summary"]["min_total_time_diff_seconds"] == 780.0
    # 等价最优区域不产生确定配对，只有 BC-500 一对确定
    assert [(p["sampling_id"], p["detection_id"]) for p in body["certain_pairs"]] == [
        ("S-23", "D-23")
    ]
    sam = {r["id"]: r for r in body["sampling_records"]}
    det = {r["id"]: r for r in body["detection_records"]}
    for rid in ("S-21", "S-22"):
        assert sam[rid]["status"] == "review"
        assert sam[rid]["matched_in_all_optimal"] is True
        assert {o["id"] for o in sam[rid]["possible_partners"]} == {"D-21", "D-22"}
    for rid in ("D-21", "D-22"):
        assert det[rid]["status"] == "review"
        assert {o["id"] for o in det[rid]["possible_partners"]} == {"S-21", "S-22"}
    assert sam["S-23"]["status"] == "certain"
    assert sam["S-23"]["certain_partner_id"] == "D-23"
    assert sam["S-24"]["status"] == "unmatched"
    assert det["D-24"]["status"] == "unmatched"


def test_response_is_deterministic():
    payload = copy.deepcopy(DEMO_EXAMPLES["equivalent_optima"]["value"])
    first = client.post("/match", json=payload).json()
    second = client.post("/match", json=payload).json()
    assert first == second


def _one_record(rid="S1"):
    return {"id": rid, "barcode": "B", "timestamp": "2026-11-14T08:00:00Z"}


def test_rejects_more_than_12_records_per_side():
    payload = {
        "sampling_records": [
            {"id": f"S{i}", "barcode": "B", "timestamp": "2026-11-14T08:00:00Z"}
            for i in range(13)
        ],
        "detection_records": [],
    }
    resp = client.post("/match", json=payload)
    assert resp.status_code == 422


def test_rejects_duplicate_ids_within_group():
    payload = {
        "sampling_records": [_one_record("S1"), _one_record("S1")],
        "detection_records": [],
    }
    resp = client.post("/match", json=payload)
    assert resp.status_code == 422


def test_rejects_naive_timestamp():
    payload = {
        "sampling_records": [
            {"id": "S1", "barcode": "B", "timestamp": "2026-11-14T08:00:00"}
        ],
        "detection_records": [],
    }
    resp = client.post("/match", json=payload)
    assert resp.status_code == 422


def test_rejects_empty_barcode_and_id():
    payload = {
        "sampling_records": [{"id": "", "barcode": "B", "timestamp": "2026-11-14T08:00:00Z"}],
        "detection_records": [],
    }
    assert client.post("/match", json=payload).status_code == 422
    payload = {
        "sampling_records": [{"id": "S1", "barcode": "", "timestamp": "2026-11-14T08:00:00Z"}],
        "detection_records": [],
    }
    assert client.post("/match", json=payload).status_code == 422


def test_rejects_unknown_fields():
    payload = {
        "sampling_records": [
            {
                "id": "S1",
                "barcode": "B",
                "timestamp": "2026-11-14T08:00:00Z",
                "operator": "someone",
            }
        ],
        "detection_records": [],
    }
    assert client.post("/match", json=payload).status_code == 422


def test_accepts_timezone_offset_and_normalizes_to_utc():
    payload = {
        "sampling_records": [
            {"id": "S1", "barcode": "B", "timestamp": "2026-11-14T16:00:00+08:00"}
        ],
        "detection_records": [
            {"id": "D1", "barcode": "B", "timestamp": "2026-11-14T08:05:00Z"}
        ],
    }
    resp = client.post("/match", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["max_pairs"] == 1
    assert body["certain_pairs"][0]["time_diff_seconds"] == 300.0
    assert body["sampling_records"][0]["timestamp"].endswith("Z") or body[
        "sampling_records"
    ][0]["timestamp"].endswith("+00:00")


def test_empty_request_is_valid():
    resp = client.post("/match", json={"sampling_records": [], "detection_records": []})
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["max_pairs"] == 0
    assert body["certain_pairs"] == []


# ---------------------------------------------------------------------------
# /redact-counts
# ---------------------------------------------------------------------------


def _redact_payload(**overrides):
    payload = {
        "row_names": ["SP-1", "SP-2"],
        "column_names": ["T-A", "T-B", "T-C"],
        "counts": [[2, 5, 4], [6, 7, 8]],
        "threshold": 3,
    }
    payload.update(overrides)
    return payload


def test_openapi_contains_redact_demo_examples():
    spec = client.get("/openapi.json").json()
    examples = spec["paths"]["/redact-counts"]["post"]["requestBody"]["content"][
        "application/json"
    ]["examples"]
    assert {
        "secondary_suppression",
        "no_sensitive_cells",
        "sensitive_rectangle",
        "infeasible_table",
    } <= set(examples)


def test_redact_secondary_suppression_demo():
    payload = copy.deepcopy(REDACT_EXAMPLES["secondary_suppression"]["value"])
    resp = client.post("/redact-counts", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["row_totals"] == [11, 21]
    assert body["column_totals"] == [8, 12, 12]
    assert body["grand_total"] == 32
    assert body["grid"] == [[None, None, 4], [None, None, 8]]
    assert {(c["row_index"], c["column_index"]) for c in body["redacted_cells"]} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    assert {(c["row_index"], c["column_index"]): c["value"] for c in body["published_cells"]} == {
        (0, 2): 4,
        (1, 2): 8,
    }
    # 遮盖格带行列名称，便于合作方直接渲染
    first = body["redacted_cells"][0]
    assert first == {"row_index": 0, "column_index": 0, "row": "SP-1", "column": "T-A"}


def test_redact_no_sensitive_cells_demo():
    payload = copy.deepcopy(REDACT_EXAMPLES["no_sensitive_cells"]["value"])
    resp = client.post("/redact-counts", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["redacted_cells"] == []
    assert body["grid"] == [[0, 5], [7, 9]]
    assert len(body["published_cells"]) == 4


def test_redact_sensitive_rectangle_demo():
    payload = copy.deepcopy(REDACT_EXAMPLES["sensitive_rectangle"]["value"])
    resp = client.post("/redact-counts", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert {(c["row_index"], c["column_index"]) for c in body["redacted_cells"]} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    assert body["row_totals"] == [7, 7, 15]
    assert body["column_totals"] == [7, 7, 15]


def test_redact_infeasible_demo_rejects_without_leaking():
    payload = copy.deepcopy(REDACT_EXAMPLES["infeasible_table"]["value"])
    resp = client.post("/redact-counts", json=payload)
    assert resp.status_code == 422
    # 拒绝时只给静态说明：无部分表、无行列合计、无任何原始计数
    body = resp.json()
    assert set(body) == {"detail"}
    detail = body["detail"]
    assert isinstance(detail, str)
    for leaked in ("3", "9", "5", "0", "row_totals", "grid", "counts"):
        assert leaked not in detail


def test_redact_response_schema_has_no_sensitive_split():
    """响应不得区分敏感格/补遮盖格（阈值 2 时'sensitive'标签等于公开真值 1）。"""
    resp = client.post("/redact-counts", json=_redact_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "row_names",
        "column_names",
        "threshold",
        "row_totals",
        "column_totals",
        "grand_total",
        "grid",
        "published_cells",
        "redacted_cells",
    }
    for cell in body["redacted_cells"]:
        assert set(cell) == {"row_index", "column_index", "row", "column"}


def test_redact_is_deterministic():
    first = client.post("/redact-counts", json=_redact_payload()).json()
    second = client.post("/redact-counts", json=_redact_payload()).json()
    assert first == second


def test_redact_rejects_bad_dimensions():
    # 行数越界
    assert client.post(
        "/redact-counts", json=_redact_payload(row_names=["SP-1"], counts=[[2, 5, 4]])
    ).status_code == 422
    assert client.post(
        "/redact-counts",
        json=_redact_payload(
            row_names=["A", "B", "C", "D"],
            counts=[[1, 2, 3], [4, 5, 6], [7, 8, 9], [0, 1, 2]],
        ),
    ).status_code == 422
    # 列数越界
    assert client.post(
        "/redact-counts",
        json=_redact_payload(column_names=["T-A"], counts=[[2], [6]]),
    ).status_code == 422
    # 矩阵形状与名称数量不符
    assert client.post(
        "/redact-counts", json=_redact_payload(counts=[[2, 5, 4]])
    ).status_code == 422
    assert client.post(
        "/redact-counts", json=_redact_payload(counts=[[2, 5], [6, 7, 8]])
    ).status_code == 422


def test_redact_rejects_out_of_range_cells_and_threshold():
    assert client.post(
        "/redact-counts", json=_redact_payload(counts=[[2, 5, 10], [6, 7, 8]])
    ).status_code == 422
    assert client.post(
        "/redact-counts", json=_redact_payload(counts=[[2, 5, -1], [6, 7, 8]])
    ).status_code == 422
    assert client.post(
        "/redact-counts", json=_redact_payload(threshold=1)
    ).status_code == 422
    assert client.post(
        "/redact-counts", json=_redact_payload(threshold=5)
    ).status_code == 422


def test_redact_rejects_non_integer_values():
    for bad in (1.5, "3", True, None):
        assert client.post(
            "/redact-counts", json=_redact_payload(counts=[[2, 5, bad], [6, 7, 8]])
        ).status_code == 422, bad
    for bad in (2.5, "3", True):
        assert client.post(
            "/redact-counts", json=_redact_payload(threshold=bad)
        ).status_code == 422, bad


def test_redact_rejects_duplicate_names_and_unknown_fields():
    assert client.post(
        "/redact-counts", json=_redact_payload(row_names=["SP-1", "SP-1"])
    ).status_code == 422
    assert client.post(
        "/redact-counts",
        json=_redact_payload(column_names=["T-A", "T-A", "T-C"]),
    ).status_code == 422
    payload = _redact_payload()
    payload["operator"] = "someone"
    assert client.post("/redact-counts", json=payload).status_code == 422


def test_redact_rejects_empty_names():
    assert client.post(
        "/redact-counts", json=_redact_payload(row_names=["", "SP-2"])
    ).status_code == 422
