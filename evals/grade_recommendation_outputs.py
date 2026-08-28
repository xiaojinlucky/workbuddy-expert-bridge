#!/usr/bin/env python3
"""Deterministically grade recommendation and official-ranking evaluations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


RECOMMENDATION_JSON_EVAL_IDS = {"4", "5", "6", "7", "11"}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def score_recommendation_item(item: dict[str, Any]) -> dict[str, Any]:
    """Score one real recommend-command JSON item without grading prose style."""
    evidence = item.get("ranking_evidence") if isinstance(item.get("ranking_evidence"), dict) else {}
    relevance = evidence.get("relevance") if isinstance(evidence.get("relevance"), dict) else {}
    category = evidence.get("category") if isinstance(evidence.get("category"), dict) else {}
    hot = evidence.get("hot") if isinstance(evidence.get("hot"), dict) else {}
    latest = evidence.get("latest") if isinstance(evidence.get("latest"), dict) else {}
    comprehensive = evidence.get("comprehensive") if isinstance(evidence.get("comprehensive"), dict) else {}
    hot_status = hot.get("status")
    hot_honest = hot_status in {"available", "unavailable"} and (
        hot_status == "available"
        or (hot.get("use_count") is None and bool(hot.get("unavailable_reason")))
    )
    dimensions = {
        "identity": bool(item.get("id") and item.get("display_name") and item.get("expert_type") in {"agent", "team"}),
        "availability": item.get("availability") in {"installed", "metadata-only"},
        "recommendation_reasons": isinstance(item.get("recommendation_reasons"), list)
        and len(item["recommendation_reasons"]) >= 2,
        "relevance": relevance.get("qualification", {}).get("status") == "qualified"
        and float(relevance.get("semantic_score") or 0) > 0
        and bool(relevance.get("field_evidence")),
        "category": category.get("status") in {"available", "unavailable"}
        and isinstance(item.get("category"), dict),
        "hot": hot_honest,
        "latest": latest.get("status") in {"available", "unavailable"},
        "comprehensive": comprehensive.get("status") in {"available", "unavailable"},
    }
    points = sum(bool(value) for value in dimensions.values())
    return {
        "rank": item.get("rank"),
        "id": item.get("id"),
        "score": points,
        "max_score": len(dimensions),
        "passed": points == len(dimensions),
        "dimensions": dimensions,
    }


def grade_recommendation_payload(
    eval_id: str,
    payload: dict[str, Any],
    expectations: list[str],
) -> dict[str, Any]:
    """Grade the command's actual JSON and preserve an item-by-item audit trail."""
    recommendations = payload.get("recommendations")
    if not isinstance(recommendations, list):
        recommendations = []
    item_scores = [score_recommendation_item(item) for item in recommendations if isinstance(item, dict)]
    ranks = [item.get("rank") for item in recommendations if isinstance(item, dict)]
    ordered = ranks == list(range(1, len(ranks) + 1))
    top_contract = 0 < len(recommendations) <= 3 and ordered and payload.get("returned") == len(recommendations)
    all_items_pass = bool(item_scores) and all(item["passed"] for item in item_scores)
    hot_source = payload.get("ranking_sources", {}).get("hot", {})
    hot_consistent = hot_source.get("status") in {"available", "unavailable"} and all(
        item.get("ranking_evidence", {}).get("hot", {}).get("status") == hot_source.get("status")
        for item in recommendations
        if isinstance(item, dict)
    )
    rendered = json.dumps(recommendations, ensure_ascii=False).casefold()

    if eval_id == "4":
        target_match = any(term in rendered for term in ("小红书", "种草", "粉丝增长", "xiaohongshu"))
        checks = [top_contract, target_match, all_items_pass, hot_consistent, hot_source.get("status") == "unavailable"]
    elif eval_id == "5":
        target_match = any(term in rendered for term in ("mvp", "原型", "全栈", "软件开发"))
        all_team = bool(recommendations) and all(item.get("expert_type") == "team" for item in recommendations)
        checks = [top_contract and all_team, target_match, all_items_pass, hot_consistent, hot_source.get("status") == "unavailable"]
    elif eval_id == "6":
        data_hits = sum(any(term in json.dumps(item, ensure_ascii=False).casefold() for term in ("数据", "kpi", "excel", "报告")) for item in recommendations)
        checks = [top_contract and data_hits >= 2, all_items_pass, hot_consistent, payload.get("qualified_candidate_count", 0) >= len(recommendations), hot_source.get("status") == "unavailable"]
    elif eval_id == "7":
        cross_border = any(term in rendered for term in ("跨境电商", "东南亚"))
        market_or_compliance = any(term in rendered for term in ("市场进入", "海外市场", "全球发展", "合规"))
        checks = [top_contract and cross_border and market_or_compliance, all_items_pass, hot_consistent, payload.get("qualified_candidate_count", 0) >= len(recommendations), hot_source.get("status") == "unavailable"]
    elif eval_id == "11":
        checks = [
            payload.get("status") == "no-match",
            payload.get("returned") == 0 and recommendations == [],
            payload.get("qualified_candidate_count") == 0,
            int(payload.get("rejected_weak_match_count") or 0) > 0,
            bool(payload.get("no_match_reason")),
        ]
    else:
        raise ValueError(f"Unsupported recommendation JSON eval id: {eval_id}")

    if len(checks) != len(expectations):
        raise ValueError(f"Expectation/check count mismatch for eval {eval_id}")
    return {
        "expectations": [
            {"text": expectation, "passed": bool(passed), "evidence": "actual recommend JSON"}
            for expectation, passed in zip(expectations, checks, strict=True)
        ],
        "recommendation_items": item_scores,
        "payload_status": payload.get("status"),
        "payload_returned": payload.get("returned"),
        "grader_input": "outputs/recommendation.json",
    }


def ranked_lines(text: str) -> dict[int, str]:
    result: dict[int, str] = {}
    patterns = (
        re.compile(r"^\s*\|\s*([123])\s*\|"),
        re.compile(r"^\s*(?:#{1,6}\s*)?([123])[.)、]\s+"),
    )
    for line in text.splitlines():
        for pattern in patterns:
            match = pattern.search(line)
            if match:
                result.setdefault(int(match.group(1)), line.strip())
                break
    return result


def contains_all(text: str, groups: list[tuple[str, ...]]) -> bool:
    lowered = text.casefold()
    return all(any(term.casefold() in lowered for term in group) for group in groups)


def count_terms(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.casefold()
    return sum(lowered.count(term.casefold()) for term in terms)


def hot_is_unavailable(text: str) -> bool:
    lowered = text.casefold()
    has_hot = any(term in lowered for term in ("hot", "热度", "最热", "usecount"))
    has_unavailable = any(term in lowered for term in ("unavailable", "不可用", "无法获得", "无法核验", "没有真实热度")) or bool(
        re.search(r"没有.{0,60}(?:热度字段|热度数据|使用次数|调用量|评分|usecount)", lowered)
    )
    has_no_guess_boundary = any(
        term in lowered
        for term in (
            "不以时间",
            "没有用创建时间",
            "未用创建时间",
            "未用时间",
            "不能用创建时间",
            "不把创建时间",
            "不能当作市场热度",
            "不是热度榜",
            "不是“最热门榜”",
            "没有用“热门”",
            "不能把清单顺序冒充人气排名",
            "任何具体排名数字都会是臆造",
            "不是按热度",
            "不是热度",
        )
    )
    return has_hot and has_unavailable and has_no_guess_boundary


def evidence_fields_present(text: str) -> bool:
    return contains_all(
        text,
        [
            ("相关性", "relevance"),
            ("分类", "category"),
            ("最热", "热度", "hot", "usecount"),
            ("最新", "latest", "createdat", "publishedat"),
        ],
    )


def common_identity_fields(text: str) -> bool:
    type_hits = count_terms(text, ("`agent`", "`team`", "（agent）", "（team）", "单专家", "专家团"))
    availability_hits = count_terms(text, ("metadata-only", "installed", "已安装", "仅元数据"))
    return type_hits >= 3 and availability_hits >= 3 and "分类" in text and any(
        marker in text for marker in ("理由", "为什么", "推荐依据")
    )


def no_credentials_boundary(text: str) -> bool:
    lowered = text.casefold()
    has_credential_terms = contains_all(
        lowered,
        [
            ("cookie",),
            ("token", "令牌"),
            ("authorization", "凭据", "登录态"),
        ],
    )
    has_negative = any(
        term in lowered
        for term in (
            "未读取",
            "不读取",
            "没有读取",
            "未发送",
            "不发送",
            "false",
            "无需登录",
        )
    )
    return has_credential_terms and has_negative


def public_snapshot_boundary(text: str) -> bool:
    lowered = text.casefold()
    has_public_source = "expert_center.json" in lowered or contains_all(lowered, [("公共",), ("目录", "清单")])
    has_missing_fields = any(
        term in lowered
        for term in (
            "覆盖 0",
            "coverage=0",
            "没有 use_count",
            "不含完整热度",
            "排名字段覆盖均为 0",
            "排名字段为 0",
        )
    )
    not_live = any(term in lowered for term in ("不是实时", "非实时", "目录快照", "清单快照"))
    return has_public_source and has_missing_fields and not_live


def official_auth_gate(text: str) -> bool:
    lowered = text.casefold()
    has_endpoint = any(
        term in lowered
        for term in (
            "/console/expert/ranking",
            "/market/expert/list",
            "实时接口",
            "排名接口",
        )
    )
    return has_endpoint and ("401" in lowered or "403" in lowered) and "bearer" in lowered


def official_probe_boundary(text: str) -> bool:
    lowered = text.casefold()
    has_official = "workbuddy 官方" in lowered or "官方匿名" in lowered
    has_probe = "匿名探针" in lowered or "official-online" in lowered or "official_online" in lowered
    has_allowlist = any(term in lowered for term in ("允许列表", "allowlist", "固定官方", "固定来源"))
    return has_official and has_probe and has_allowlist


def grade_eval(eval_id: str, text: str, expectations: list[str]) -> list[dict[str, object]]:
    ranks = ranked_lines(text)
    top_three = set(ranks) >= {1, 2, 3}
    ranked_text = "\n".join(ranks.values())
    checks: list[tuple[bool, str]]

    if eval_id == "4":
        checks = [
            (top_three, f"rank markers found: {sorted(ranks)}"),
            (
                any(term in ranked_text for term in ("小红书", "种草", "内容增长", "TrendHunter", "Xiaohongshu")),
                "ranked candidates include Xiaohongshu/content-growth evidence",
            ),
            (common_identity_fields(text), "type, availability, category, and reasons are present for the recommendation set"),
            (evidence_fields_present(text), "relevance/category/hot/latest evidence labels are present"),
            (hot_is_unavailable(text), "hot evidence is explicitly unavailable and creation time is not substituted"),
        ]
    elif eval_id == "5":
        team_rows = sum(any(term in line.casefold() for term in ("专家团", "团队", "team")) for line in ranks.values())
        all_team_statement = any(
            marker in text.casefold()
            for marker in ("3 个正式专家团", "三个候选均为 team", "全部正式团队", "只推荐 workbuddy 专家团")
        )
        checks = [
            (
                top_three and (team_rows >= 3 or (team_rows >= 2 and all_team_statement)),
                f"rank markers={sorted(ranks)}, team rows={team_rows}, all-team statement={all_team_statement}",
            ),
            (
                any(term.casefold() in ranked_text.casefold() for term in ("mvp", "快速原型", "软件开发", "全栈", "MvpDevExpertTeam")),
                "front-ranked rows contain MVP/prototyping/software-delivery evidence",
            ),
            (
                count_terms(text, ("metadata-only", "installed", "已安装", "仅元数据")) >= 3,
                "installed versus metadata-only status is stated across candidates",
            ),
            (
                "分类" in text
                and any(marker in text for marker in ("排名依据", "排序依据", "排名与可用性"))
                and any(marker in text for marker in ("依据", "理由", "为什么")),
                "category, recommendation rationale, and ranking evidence are present",
            ),
            (hot_is_unavailable(text), "hot evidence is explicitly unavailable and not guessed"),
        ]
    elif eval_id == "6":
        data_rows = sum(any(term in line.casefold() for term in ("数据", "kpi", "excel", "报告")) for line in ranks.values())
        distinction_terms = sum(
            term.casefold() in text.casefold()
            for term in ("数据获取", "数据分析", "指标", "kpi", "报告表达", "多角色", "协作", "异常")
        )
        checks = [
            (top_three and data_rows >= 2, f"rank markers={sorted(ranks)}, data-oriented rows={data_rows}"),
            (distinction_terms >= 3, f"distinct analysis/report/team markers={distinction_terms}"),
            (common_identity_fields(text), "agent/team and installed/metadata-only fields are present"),
            (
                contains_all(text, [("manifest.json", "categoryid", "usecount", "createdat"), ("未调用", "没有调用", "未联网", "只读")]),
                "ranking evidence cites local fields/source and does not claim an unmade service call",
            ),
            (hot_is_unavailable(text), "useCount absence is reported as unavailable without substitution"),
        ]
    elif eval_id == "7":
        checks = [
            (
                top_three
                and contains_all(text, [("跨境电商",), ("市场进入", "海外市场", "全球发展", "合规", "东南亚")]),
                f"rank markers={sorted(ranks)} and cross-border plus market/compliance coverage is present",
            ),
            (
                any(term in text for term in ("互补", "组合", "覆盖", "补齐")) and any(term in text for term in ("为什么", "理由", "职责")),
                "response explicitly explains complementary coverage",
            ),
            (common_identity_fields(text), "candidate type, availability, category, and reasons are present"),
            (
                contains_all(text, [("最热", "热度", "hot"), ("最新", "latest", "createdat", "publishedat")])
                and any(term in text for term in ("证据", "字段", "无法核验", "不可用", "unavailable")),
                "hot and latest evidence are both explicitly presented",
            ),
            (hot_is_unavailable(text), "hot evidence is explicitly unavailable and not guessed"),
        ]
    elif eval_id == "8":
        checks = [
            (
                top_three and common_identity_fields(text),
                f"rank markers={sorted(ranks)} and recommendation identity fields are present",
            ),
            (official_probe_boundary(text), "official anonymous probe and fixed official source boundary are explicit"),
            (public_snapshot_boundary(text), "public expert catalog is identified as a non-live snapshot without hot coverage"),
            (
                official_auth_gate(text) and hot_is_unavailable(text),
                "live endpoint Bearer authentication gate is recorded and hot remains unavailable",
            ),
            (no_credentials_boundary(text), "response explicitly records that credentials were neither read nor sent"),
        ]
    elif eval_id == "9":
        lowered = text.casefold()
        checks = [
            (
                contains_all(lowered, [("reco_rank",), ("use_count", "usecount"), ("published_at", "publishedat")]),
                "all three WorkBuddy sort fields are named",
            ),
            (
                contains_all(lowered, [("公共",), ("本地",), ("实时",)])
                and any(term in lowered for term in ("快照", "snapshot")),
                "public catalog, local snapshot, and live service are distinguished",
            ),
            (
                official_auth_gate(text)
                and contains_all(lowered, [("综合", "comprehensive"), ("最热", "hot"), ("最新", "latest")])
                and count_terms(lowered, ("unavailable", "不可用", "无法获得", "不能匿名")) >= 2,
                "authentication gate and the availability of all three sorts are stated",
            ),
            (
                ("createdat" in lowered or "created_at" in lowered)
                and any(term in lowered for term in ("本地快照", "目录快照", "不是实时", "不代表实时")),
                "createdAt is limited to local snapshot evidence",
            ),
            (
                no_credentials_boundary(text)
                and any(term in lowered for term in ("不猜", "不能猜", "不得猜", "不以 ui", "页面顺序", "卡片顺序")),
                "credential access, guessing, and UI-order substitution are rejected",
            ),
        ]
    elif eval_id == "10":
        lowered = text.casefold()
        checks = [
            (
                contains_all(lowered, [("完整",), ("显式",), ("覆盖", "全集", "全部候选")]),
                "complete explicit candidate coverage is required before merging",
            ),
            (
                contains_all(lowered, [("公共", "清单"), ("部分", "不完整")])
                and any(term in lowered for term in ("ui", "卡片顺序", "文件顺序", "页面顺序")),
                "partial public data and display/file order are rejected as ranking evidence",
            ),
            (
                contains_all(lowered, [("https",), ("允许列表", "allowlist", "固定来源")])
                and contains_all(lowered, [("代理", "proxy"), ("重定向", "redirect")]),
                "fixed official HTTPS allowlist, proxy disablement, and redirect rejection are stated",
            ),
            (
                any(term in lowered for term in ("401", "403", "认证", "登录", "格式", "覆盖不完整"))
                and any(term in lowered for term in ("unavailable", "不可用"))
                and any(term in lowered for term in ("诊断", "证据", "状态码", "原因")),
                "failures remain unavailable with diagnostic evidence",
            ),
            (
                no_credentials_boundary(text)
                and contains_all(lowered, [("未来", "之后", "后续"), ("重试", "重新运行", "再运行"), ("匿名探针",)]),
                "recovery is limited to a future anonymous retry without credential recovery",
            ),
        ]
    else:
        raise ValueError(f"Unsupported recommendation eval id: {eval_id}")

    if len(checks) != len(expectations):
        raise ValueError(f"Expectation/check count mismatch for eval {eval_id}")
    return [
        {"text": expectation, "passed": passed, "evidence": evidence}
        for expectation, (passed, evidence) in zip(expectations, checks, strict=True)
    ]


def grade_iteration(iteration_path: Path) -> None:
    plan = load_json(iteration_path / "run_plan.json")
    for run in plan["runs"]:
        run_dir = Path(run["run_dir"])
        eval_id = str(run["eval_id"])
        if eval_id in RECOMMENDATION_JSON_EVAL_IDS:
            payload_path = run_dir / "outputs" / "recommendation.json"
            if not payload_path.is_file():
                raise FileNotFoundError(payload_path)
            grading = grade_recommendation_payload(
                eval_id,
                load_json(payload_path),
                list(run["expectations"]),
            )
        else:
            response_path = run_dir / "outputs" / "response.md"
            if not response_path.is_file():
                raise FileNotFoundError(response_path)
            text = response_path.read_text(encoding="utf-8-sig")
            grading = {
                "expectations": grade_eval(eval_id, text, list(run["expectations"])),
                "grader_input": "outputs/response.md",
            }
        grading["grader"] = "evals/grade_recommendation_outputs.py"
        (run_dir / "grading.json").write_text(
            json.dumps(grading, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        timing = {
            "total_tokens": None,
            "duration_ms": None,
            "measurement_status": "unavailable_in_collaboration_runtime",
            "note": "Unavailable measurements are null; they are not zero-valued observations.",
        }
        (run_dir / "timing.json").write_text(
            json.dumps(timing, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("iteration_path")
    args = parser.parse_args()
    grade_iteration(Path(args.iteration_path).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
