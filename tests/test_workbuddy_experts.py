from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SKILL_ROOT / "scripts" / "workbuddy_experts.py"
SPEC = importlib.util.spec_from_file_location("workbuddy_experts", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class WorkBuddyExpertBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / ".workbuddy"
        self.packages = self.config / "plugins" / "marketplaces" / "experts" / "plugins"
        self.packages.mkdir(parents=True)

    def write_package(
        self,
        name: str,
        manifest: dict,
        agents: dict[str, str] | None = None,
        *,
        marketplace: str = "experts",
    ) -> Path:
        collection = self.config / "plugins" / "marketplaces" / marketplace / "plugins"
        collection.mkdir(parents=True, exist_ok=True)
        package = collection / name
        manifest_dir = package / ".codebuddy-plugin"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "plugin.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for filename, content in (agents or {}).items():
            path = package / "agents" / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return package

    def write_catalog(self, experts: list[dict], categories: list[dict] | None = None) -> Path:
        cache = self.config / "app" / "cache" / "experts"
        cache.mkdir(parents=True, exist_ok=True)
        path = cache / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "categories": categories or [],
                    "experts": experts,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    def write_recommendation_fixture(self) -> Path:
        self.write_package(
            "xiaohongshu-operations",
            {
                "name": "xiaohongshu-operations",
                "expertType": "agent",
                "agentName": "xiaohongshu-operations",
                "agents": ["./agents/xiaohongshu-operations.md"],
            },
            {"xiaohongshu-operations.md": "# Xiaohongshu\n"},
        )
        categories = [
            {
                "id": "06-ContentCreative",
                "name": {"zh": "内容创作", "en": "Content Creative"},
                "description": {"zh": "内容编辑、短视频、自媒体运营", "en": "Content operations"},
            },
            {
                "id": "04-DataAI",
                "name": {"zh": "数据智能", "en": "Data & AI"},
                "description": {"zh": "数据分析和人工智能", "en": "Data analysis and AI"},
            },
            {
                "id": "11-SecurityCompliance",
                "name": {"zh": "法务安全", "en": "Security"},
                "description": {"zh": "信息安全与合规", "en": "Security and compliance"},
            },
        ]
        experts = [
            {
                "id": "XiaohongshuOperationsExpert",
                "plugin": "xiaohongshu-operations",
                "agentName": "xiaohongshu-operations",
                "expertType": "agent",
                "displayName": {"zh": "小红书运营专家"},
                "profession": {"zh": "小红书内容增长顾问"},
                "description": {"zh": "负责账号定位、种草笔记、选题和涨粉复盘"},
                "categoryId": "06-ContentCreative",
                "tags": [{"zh": "小红书运营"}, {"zh": "种草内容"}, {"zh": "粉丝增长"}],
                "createdAt": "2026-07-01T00:00:00Z",
                "displayPosition": 1,
            },
            {
                "id": "ContentDistributionTeam",
                "plugin": "content-distribution-team",
                "expertType": "team",
                "displayName": {"zh": "全域内容分发专家团"},
                "profession": {"zh": "多平台内容运营团队"},
                "description": {"zh": "规划小红书、公众号和短视频的持续内容分发"},
                "categoryId": "06-ContentCreative",
                "tags": [{"zh": "内容排期"}, {"zh": "多平台分发"}],
                "createdAt": "2026-07-03T00:00:00Z",
            },
            {
                "id": "ViralTopicMaster",
                "plugin": "viral-topic-master",
                "expertType": "agent",
                "displayName": {"zh": "爆款选题策划师"},
                "profession": {"zh": "内容增长专家"},
                "description": {"zh": "为小红书账号策划选题并复盘内容增长"},
                "categoryId": "06-ContentCreative",
                "tags": [{"zh": "爆款选题"}, {"zh": "内容增长"}],
                "createdAt": "2026-07-02T00:00:00Z",
            },
            {
                "id": "AccountGuardian",
                "plugin": "account-guardian",
                "expertType": "agent",
                "displayName": {"zh": "账号安全管家"},
                "profession": {"zh": "账号安全专家"},
                "description": {"zh": "处理登录风险与账号保护"},
                "categoryId": "11-SecurityCompliance",
                "tags": [{"zh": "账号安全"}],
                "createdAt": "2026-07-04T00:00:00Z",
            },
            {
                "id": "DataAnalyst",
                "plugin": "data-analyst",
                "expertType": "agent",
                "displayName": {"zh": "数据分析师"},
                "profession": {"zh": "经营数据分析"},
                "description": {"zh": "制作指标看板和数据报告"},
                "categoryId": "04-DataAI",
                "tags": [{"zh": "数据分析"}],
                "createdAt": "2026-07-05T00:00:00Z",
            },
        ]
        return self.write_catalog(experts, categories)

    def test_discovers_team_and_resolves_lead(self) -> None:
        self.write_package(
            "team-alpha",
            {
                "name": "team-alpha",
                "version": "1.0.0",
                "expertType": "team",
                "agentName": "team-alpha-lead",
                "teamInfo": {"leadAgent": "team-alpha-lead", "memberAgents": ["team-alpha-dev"]},
                "agents": ["./agents/team-alpha-lead.md", "./agents/team-alpha-dev.md"],
                "displayName": {"zh": "甲团队", "en": "Team Alpha"},
            },
            {
                "team-alpha-lead.md": "# Lead\n",
                "team-alpha-dev.md": "# Developer\n",
            },
        )

        packages, warnings = bridge.discover_packages([self.config])

        self.assertEqual([], warnings)
        self.assertEqual(1, len(packages))
        self.assertEqual("declared-expert", packages[0]["package_class"])
        self.assertEqual("team", packages[0]["expert_type"])
        self.assertEqual(2, packages[0]["agent_count"])
        self.assertTrue(packages[0]["lead_path"].endswith("team-alpha-lead.md"))

    def test_legacy_manifest_falls_back_to_direct_agent_markdown(self) -> None:
        self.write_package(
            "legacy-team",
            {
                "name": "legacy-team",
                "expertType": "team",
                "agentName": "legacy-lead",
                "teamInfo": {"leadAgent": "legacy-lead"},
            },
            {"legacy-lead.md": "# Legacy Lead\n", "legacy-member.md": "# Member\n"},
        )

        packages, _ = bridge.discover_packages([self.config])

        self.assertEqual(2, packages[0]["agent_count"])
        self.assertTrue(packages[0]["lead_path"].endswith("legacy-lead.md"))

    def test_manifest_path_escape_is_rejected(self) -> None:
        self.write_package(
            "unsafe-agent",
            {
                "name": "unsafe-agent",
                "expertType": "agent",
                "agentName": "safe",
                "agents": ["./agents/safe.md", "../../outside.md"],
            },
            {"safe.md": "# Safe\n"},
        )

        packages, _ = bridge.discover_packages([self.config])

        self.assertEqual(1, packages[0]["agent_count"])
        self.assertTrue(any("escapes package root" in warning for warning in packages[0]["warnings"]))

    def test_catalog_marks_metadata_only_and_installed(self) -> None:
        self.write_package(
            "installed-agent",
            {
                "name": "installed-agent",
                "expertType": "agent",
                "agentName": "installed-agent",
                "agents": ["./agents/installed-agent.md"],
            },
            {"installed-agent.md": "# Installed\n"},
        )
        cache = self.config / "app" / "cache" / "experts"
        cache.mkdir(parents=True)
        (cache / "manifest.json").write_text(
            json.dumps(
                {
                    "experts": [
                        {"id": "Installed", "plugin": "installed-agent", "expertType": "agent"},
                        {"id": "RemoteOnly", "plugin": "remote-only", "expertType": "team"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        packages, _ = bridge.discover_packages([self.config])
        catalog, warnings = bridge.load_catalog([self.config], packages)

        self.assertEqual([], warnings)
        availability = {item["id"]: item["availability"] for item in catalog}
        self.assertEqual("installed", availability["Installed"])
        self.assertEqual("metadata-only", availability["RemoteOnly"])

    def test_discovers_agent_bearing_package_without_expert_type(self) -> None:
        self.write_package(
            "multi-agent-tools",
            {
                "name": "multi-agent-tools",
                "description": "Local multi-agent plugin",
                "agents": ["./agents/researcher.md", "./agents/reviewer.md"],
            },
            {"researcher.md": "# Researcher\n", "reviewer.md": "# Reviewer\n"},
            marketplace="cb_teams_marketplace",
        )

        packages, warnings = bridge.discover_packages([self.config])

        self.assertEqual([], warnings)
        self.assertEqual(1, len(packages))
        self.assertEqual("agent-package", packages[0]["package_class"])
        self.assertEqual("team", packages[0]["kind"])
        self.assertEqual("", packages[0]["expert_type"])

    def test_ignores_plugin_without_expert_type_or_agent_prompts(self) -> None:
        self.write_package(
            "ordinary-plugin",
            {"name": "ordinary-plugin", "description": "No agents"},
        )

        packages, warnings = bridge.discover_packages([self.config])

        self.assertEqual([], warnings)
        self.assertEqual([], packages)

    def test_resolve_reports_metadata_only_and_recovery_without_download(self) -> None:
        cache = self.config / "app" / "cache" / "experts"
        cache.mkdir(parents=True)
        (cache / "manifest.json").write_text(
            json.dumps(
                {
                    "experts": [
                        {
                            "id": "ContentCreator",
                            "plugin": "content-creator",
                            "agentName": "content-creator",
                            "expertType": "agent",
                            "promptFile": "/plugins/content-creator/agents/content-creator.md",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "resolve",
                "ContentCreator",
                "--root",
                str(self.config),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("blocked", payload["status"])
        self.assertEqual("metadata-only", payload["availability"])
        self.assertEqual("ContentCreator", payload["match"]["id"])
        self.assertFalse(payload["downloaded"])
        self.assertIn("local .codebuddy-plugin/plugin.json", payload["missing"])
        self.assertGreaterEqual(len(payload["next_steps"]), 1)
        self.assertEqual(bridge.METADATA_RECOVERY_ACTION, payload["recovery_action"])

    def test_resolve_not_found_reports_recovery(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "resolve",
                "DoesNotExist",
                "--root",
                str(self.config),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("not-found", payload["status"])
        self.assertEqual("not-found", payload["availability"])
        self.assertGreaterEqual(len(payload["next_steps"]), 1)
        self.assertEqual(bridge.NOT_FOUND_RECOVERY_ACTION, payload["recovery_action"])

    def test_skill_contract_requires_team_receipt_and_recovery_action(self) -> None:
        skill_text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")

        for marker in ("lead_loaded", "member_files_loaded", "load_order", "recovery_action"):
            with self.subTest(marker=marker):
                self.assertIn(marker, skill_text)

    def test_resolve_prefers_declared_expert_over_same_named_agent_package(self) -> None:
        for marketplace, expert_type in (
            ("experts", "agent"),
            ("cb_teams_marketplace", None),
        ):
            manifest = {
                "name": "shared-name",
                "agentName": "shared-name",
                "agents": ["./agents/shared-name.md"],
            }
            if expert_type:
                manifest["expertType"] = expert_type
            self.write_package(
                "shared-name",
                manifest,
                {"shared-name.md": "# Shared\n"},
                marketplace=marketplace,
            )

        packages, _ = bridge.discover_packages([self.config])
        selected = bridge.select_package(packages, "shared-name", None)

        self.assertEqual("declared-expert", selected["package_class"])
        self.assertEqual("experts", selected["marketplace"])

    def test_inventory_classifies_three_layers_and_bounds_metadata_examples(self) -> None:
        self.write_package(
            "formal-agent",
            {
                "name": "formal-agent",
                "expertType": "agent",
                "agentName": "formal-agent",
                "agents": ["./agents/formal-agent.md"],
            },
            {"formal-agent.md": "# Formal\n"},
        )
        for index in range(8):
            self.write_package(
                f"agent-tools-{index}",
                {
                    "name": f"agent-tools-{index}",
                    "agents": ["./agents/tool.md"],
                },
                {"tool.md": "# Tool\n"},
                marketplace="cb_teams_marketplace",
            )
        team_dir = self.config / "teams" / "saved-team"
        team_dir.mkdir(parents=True)
        (team_dir / "config.json").write_text(
            json.dumps(
                {
                    "name": "saved-team",
                    "description": "Historical state",
                    "members": [{"name": "lead"}, {"name": "worker", "prompt": "private"}],
                }
            ),
            encoding="utf-8",
        )
        cache = self.config / "app" / "cache" / "experts"
        cache.mkdir(parents=True)
        (cache / "manifest.json").write_text(
            json.dumps(
                {
                    "experts": [
                        {"id": f"Remote{index}", "plugin": f"remote-{index}", "expertType": "agent"}
                        for index in range(8)
                    ]
                }
            ),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "inventory",
                "--root",
                str(self.config),
                "--metadata-examples",
                "3",
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(1, payload["layers"]["declared_experts"]["total"])
        self.assertEqual(8, payload["layers"]["agent_packages"]["total"])
        self.assertEqual(5, payload["layers"]["agent_packages"]["returned"])
        self.assertTrue(payload["layers"]["agent_packages"]["truncated"])
        self.assertEqual(1, payload["layers"]["runtime_teams"]["total"])
        self.assertEqual(8, payload["catalog"]["metadata_only"])
        self.assertEqual(3, payload["catalog"]["examples_returned"])
        self.assertTrue(payload["catalog"]["examples_truncated"])
        self.assertNotIn("private", json.dumps(payload, ensure_ascii=False))

    def test_recommend_open_ended_need_returns_explainable_top_three(self) -> None:
        self.write_recommendation_fixture()

        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "recommend",
                "我想运营小红书账号，持续产出种草内容并实现粉丝增长",
                "--root",
                str(self.config),
                "--json",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("ok", payload["status"])
        self.assertEqual(3, payload["returned"])
        self.assertEqual("XiaohongshuOperationsExpert", payload["recommendations"][0]["id"])
        self.assertEqual("installed", payload["recommendations"][0]["availability"])
        self.assertEqual("内容创作", payload["recommendations"][0]["category"]["name"])
        self.assertGreaterEqual(len(payload["recommendations"][0]["recommendation_reasons"]), 2)
        for recommendation in payload["recommendations"]:
            self.assertIn(recommendation["expert_type"], {"agent", "team"})
            self.assertIn(recommendation["availability"], {"installed", "metadata-only"})
            self.assertIn("relevance", recommendation["ranking_evidence"])
            self.assertIn("category", recommendation["ranking_evidence"])
            self.assertIn("hot", recommendation["ranking_evidence"])
            self.assertIn("latest", recommendation["ranking_evidence"])

    def test_recommend_never_guesses_hot_from_dates_or_display_position(self) -> None:
        self.write_recommendation_fixture()
        packages, _ = bridge.discover_packages([self.config])
        catalog, _ = bridge.load_catalog([self.config], packages)

        payload = bridge.recommend_catalog(
            catalog,
            "运营小红书账号并制作种草内容",
            kind="auto",
            availability="all",
            category="",
            limit=3,
        )

        self.assertEqual("unavailable", payload["ranking_sources"]["hot"]["status"])
        self.assertEqual(0, payload["ranking_sources"]["hot"]["coverage"]["known"])
        self.assertIn("未用创建时间", payload["ranking_sources"]["hot"]["unavailable_reason"])
        self.assertEqual("available", payload["ranking_sources"]["latest"]["status"])
        self.assertEqual(1, payload["recommendations"][0]["ranking_evidence"]["hot"]["display_position"])
        self.assertIsNone(payload["recommendations"][0]["ranking_evidence"]["hot"]["use_count"])

    def test_anonymous_official_request_sends_no_credentials(self) -> None:
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def getcode(self) -> int:
                return self.status

            def read(self, _limit: int) -> bytes:
                return b'{"experts": []}'

        class FakeOpener:
            request: object | None = None

            def open(self, request: object, *, timeout: float) -> FakeResponse:
                self.request = request
                self.timeout = timeout
                return FakeResponse()

        opener = FakeOpener()
        result = bridge.anonymous_official_json(
            bridge.WORKBUDDY_PUBLIC_CATALOG_URL,
            opener=opener,
        )

        self.assertEqual("available", result["status"])
        self.assertIsNotNone(opener.request)
        headers = {key.casefold(): value for key, value in opener.request.header_items()}
        self.assertNotIn("authorization", headers)
        self.assertNotIn("cookie", headers)
        self.assertNotIn("proxy-authorization", headers)
        self.assertEqual("application/json", headers["accept"])

    def test_anonymous_official_request_rejects_nonofficial_host(self) -> None:
        with self.assertRaises(bridge.BridgeError) as caught:
            bridge.anonymous_official_json("https://example.com/expert_center.json")

        self.assertEqual("official_source_not_allowlisted", caught.exception.code)

    def test_official_online_auth_gate_keeps_live_ranking_unavailable(self) -> None:
        self.write_recommendation_fixture()
        packages, _ = bridge.discover_packages([self.config])
        catalog, _ = bridge.load_catalog([self.config], packages)
        calls: list[tuple[str, str, dict[str, object] | None]] = []

        def fake_fetch(
            url: str,
            *,
            method: str = "GET",
            body: dict[str, object] | None = None,
            timeout: float = bridge.OFFICIAL_ONLINE_TIMEOUT_SECONDS,
        ) -> dict[str, object]:
            calls.append((url, method, body))
            if url == bridge.WORKBUDDY_PUBLIC_CATALOG_URL:
                return {
                    "url": url,
                    "method": method,
                    "status": "available",
                    "http_status": 200,
                    "reason_code": "",
                    "content_type": "application/json",
                    "_payload": {
                        "version": "1.0.0",
                        "lastUpdated": "2026-08-27T10:19:53Z",
                        "categories": [],
                        "experts": [{"id": item["id"], "createdAt": item["created_at"]} for item in catalog],
                    },
                }
            return {
                "url": url,
                "method": method,
                "status": "unavailable",
                "http_status": 401,
                "reason_code": "authentication_required",
                "auth_scheme": "Bearer",
                "content_type": "text/html",
                "_payload": None,
            }

        probe = bridge.probe_official_online_ranking(catalog, fetcher=fake_fetch)
        summary = bridge.ranking_source_summary(catalog, probe)

        self.assertEqual("unavailable", probe["status"])
        self.assertTrue(probe["authentication_required"])
        self.assertFalse(probe["credential_policy"]["local_credentials_read"])
        self.assertFalse(probe["credential_policy"]["authorization_header_sent"])
        self.assertFalse(probe["credential_policy"]["cookies_sent"])
        self.assertEqual(["reco_rank", "published_at"], probe["sort_fields_not_attempted_after_common_auth_gate"])
        self.assertEqual(3, len(calls))
        self.assertEqual("unavailable", summary["hot"]["status"])
        self.assertIn("Bearer", summary["hot"]["unavailable_reason"])

    def test_official_online_merges_only_complete_explicit_live_fields(self) -> None:
        self.write_recommendation_fixture()
        packages, _ = bridge.discover_packages([self.config])
        catalog, _ = bridge.load_catalog([self.config], packages)
        live_items = [
            {
                "source_id": item["id"],
                "use_count": 1000 - index,
                "reco_rank": 500 - index,
                "published_at": f"2026-08-{20 + index:02d}T00:00:00Z",
            }
            for index, item in enumerate(catalog)
        ]

        def fake_fetch(
            url: str,
            *,
            method: str = "GET",
            body: dict[str, object] | None = None,
            timeout: float = bridge.OFFICIAL_ONLINE_TIMEOUT_SECONDS,
        ) -> dict[str, object]:
            del timeout
            if url == bridge.WORKBUDDY_PUBLIC_CATALOG_URL:
                payload: dict[str, object] = {
                    "version": "1.0.0",
                    "lastUpdated": "2026-08-27T10:19:53Z",
                    "categories": [],
                    "experts": [{"id": item["id"]} for item in catalog],
                }
            else:
                self.assertTrue(url.startswith(bridge.WORKBUDDY_OFFICIAL_API_ORIGIN))
                if method == "POST":
                    self.assertIn(body["sort_by"], bridge.OFFICIAL_SORT_FIELDS)
                payload = {"code": 0, "data": {"items": live_items, "total": len(live_items)}}
            return {
                "url": url,
                "method": method,
                "status": "available",
                "http_status": 200,
                "reason_code": "",
                "content_type": "application/json",
                "_payload": payload,
            }

        probe = bridge.probe_official_online_ranking(catalog, fetcher=fake_fetch)
        summary = bridge.ranking_source_summary(catalog, probe)

        self.assertEqual("available", probe["status"])
        self.assertEqual({"use_count", "reco_rank", "published_at"}, set(probe["complete_fields"]))
        self.assertEqual("available", summary["hot"]["status"])
        self.assertEqual("available", summary["comprehensive"]["status"])
        self.assertEqual(bridge.WORKBUDDY_MARKET_LIST_URL, catalog[0]["use_count_source"])
        self.assertEqual(bridge.WORKBUDDY_MARKET_LIST_URL, catalog[0]["reco_rank_source"])
        self.assertEqual(bridge.WORKBUDDY_MARKET_LIST_URL, catalog[0]["latest_source"])

    def test_recommend_official_online_flag_wires_probe_into_evidence(self) -> None:
        self.write_recommendation_fixture()
        fake_probe = {
            "status": "unavailable",
            "credential_policy": {
                "local_credentials_read": False,
                "authorization_header_sent": False,
                "cookies_sent": False,
            },
            "unavailable_reason": "anonymous official endpoint requires Bearer authentication",
        }
        args = bridge.build_parser().parse_args(
            [
                "recommend",
                "运营小红书并增长粉丝",
                "--root",
                str(self.config),
                "--official-online",
                "--json",
            ]
        )
        with mock.patch.object(bridge, "probe_official_online_ranking", return_value=fake_probe) as probe:
            payload = bridge.run(args)

        probe.assert_called_once()
        self.assertEqual(fake_probe, payload["ranking_sources"]["official_online"])
        self.assertEqual("unavailable", payload["ranking_sources"]["hot"]["status"])
        self.assertIn("Bearer", payload["ranking_sources"]["hot"]["unavailable_reason"])

    def test_recommend_is_offline_unless_official_online_is_explicit(self) -> None:
        self.write_recommendation_fixture()
        args = bridge.build_parser().parse_args(
            [
                "recommend",
                "运营小红书并增长粉丝",
                "--root",
                str(self.config),
                "--json",
            ]
        )
        with mock.patch.object(bridge, "probe_official_online_ranking") as probe:
            payload = bridge.run(args)

        probe.assert_not_called()
        self.assertNotIn("official_online", payload["ranking_sources"])

    def test_recommend_auto_honors_explicit_expert_team_request(self) -> None:
        self.write_recommendation_fixture()
        packages, _ = bridge.discover_packages([self.config])
        catalog, _ = bridge.load_catalog([self.config], packages)

        payload = bridge.recommend_catalog(
            catalog,
            "请推荐一个专家团，负责小红书内容排期和多平台分发",
            kind="auto",
            availability="all",
            category="内容创作",
            limit=3,
        )

        self.assertEqual("team", payload["filters"]["inferred_kind_preference"])
        self.assertEqual(["06-ContentCreative"], payload["filters"]["resolved_category_ids"])
        self.assertGreaterEqual(payload["returned"], 1)
        self.assertTrue(all(item["expert_type"] == "team" for item in payload["recommendations"]))
        self.assertEqual("ContentDistributionTeam", payload["recommendations"][0]["id"])

    def test_catalog_json_does_not_expose_internal_search_fields(self) -> None:
        self.write_recommendation_fixture()

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "catalog", "--root", str(self.config), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertNotIn("_search_fields", completed.stdout)

    def test_inspection_reports_but_does_not_execute_scripts(self) -> None:
        package = self.write_package(
            "scripted-agent",
            {
                "name": "scripted-agent",
                "expertType": "agent",
                "agentName": "scripted-agent",
                "agents": ["./agents/scripted-agent.md"],
            },
            {"scripted-agent.md": "# Scripted\n"},
        )
        marker = package / "executed.txt"
        script_dir = package / "scripts"
        script_dir.mkdir()
        (script_dir / "danger.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n",
            encoding="utf-8",
        )

        packages, _ = bridge.discover_packages([self.config])
        report = bridge.inspect_package(packages[0])

        self.assertFalse(marker.exists())
        self.assertTrue(any(path.endswith("danger.py") for path in report["executable_files"]))
        self.assertTrue(report["read_only"])

    def test_cli_doctor_emits_json(self) -> None:
        self.write_package(
            "cli-agent",
            {
                "name": "cli-agent",
                "expertType": "agent",
                "agentName": "cli-agent",
                "agents": ["./agents/cli-agent.md"],
            },
            {"cli-agent.md": "# CLI\n"},
        )

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "doctor", "--root", str(self.config), "--json"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("ok", payload["status"])
        self.assertEqual(1, payload["installed_experts"])
        self.assertEqual(1, payload["installed_packages"])
        self.assertEqual(0, payload["installed_agent_packages"])
        self.assertTrue(payload["read_only"])

    def test_cli_preserves_chinese_metadata_in_utf8_json(self) -> None:
        self.write_package(
            "chinese-agent",
            {
                "name": "chinese-agent",
                "expertType": "agent",
                "agentName": "chinese-agent",
                "agents": ["./agents/chinese-agent.md"],
                "displayName": {"zh": "中文专家", "en": "Chinese Expert"},
            },
            {"chinese-agent.md": "# 中文专家\n"},
        )

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "list", "--root", str(self.config), "--json"],
            check=False,
            capture_output=True,
        )

        self.assertEqual(0, completed.returncode, completed.stderr.decode("utf-8", errors="replace"))
        payload = json.loads(completed.stdout.decode("utf-8"))
        self.assertEqual("中文专家", payload["items"][0]["display_name"])


if __name__ == "__main__":
    unittest.main()
