#!/usr/bin/env python3
"""Read-only discovery and inspection for local WorkBuddy expert packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


MIN_PYTHON = (3, 10)
MANIFEST_RELATIVE = Path(".codebuddy-plugin") / "plugin.json"
MARKETPLACE_COLLECTIONS = ("plugins", "external_plugins")
DECLARED_EXPERT = "declared-expert"
AGENT_PACKAGE = "agent-package"
DEFAULT_LIST_LIMIT = 25
DEFAULT_CATALOG_LIMIT = 20
DEFAULT_INVENTORY_LIMIT = 25
DEFAULT_AGENT_PACKAGE_EXAMPLES = 5
DEFAULT_METADATA_EXAMPLES = 3
DEFAULT_RECOMMEND_LIMIT = 3
MAX_RECOMMEND_LIMIT = 20
WORKBUDDY_HOT_SORT_FIELD = "use_count"
WORKBUDDY_LATEST_SORT_FIELD = "published_at"
WORKBUDDY_RECOMMENDED_SORT_FIELD = "reco_rank"
WORKBUDDY_RANKING_ENDPOINT = "/console/expert/ranking"
WORKBUDDY_PUBLIC_CATALOG_URL = (
    "https://acc-1258344699.cos.accelerate.myqcloud.com/"
    "workbuddy/expert-marketplace/expert_center.json"
)
WORKBUDDY_OFFICIAL_API_ORIGIN = "https://copilot.tencent.com"
WORKBUDDY_MARKET_LIST_ENDPOINT = "/portal/operation-platform/market/expert/list"
WORKBUDDY_MARKET_LIST_URL = WORKBUDDY_OFFICIAL_API_ORIGIN + WORKBUDDY_MARKET_LIST_ENDPOINT
WORKBUDDY_RANKING_URL = WORKBUDDY_OFFICIAL_API_ORIGIN + WORKBUDDY_RANKING_ENDPOINT
WORKBUDDY_OFFICIAL_HOSTS = frozenset(
    {
        "acc-1258344699.cos.accelerate.myqcloud.com",
        "copilot.tencent.com",
    }
)
OFFICIAL_ONLINE_TIMEOUT_SECONDS = 10.0
OFFICIAL_ONLINE_MAX_BYTES = 5 * 1024 * 1024
OFFICIAL_ONLINE_USER_AGENT = "workbuddy-expert-bridge/1"
OFFICIAL_SORT_FIELDS = (
    WORKBUDDY_HOT_SORT_FIELD,
    WORKBUDDY_RECOMMENDED_SORT_FIELD,
    WORKBUDDY_LATEST_SORT_FIELD,
)
NOT_FOUND_RECOVERY_ACTION = (
    "Verify the exact expert name, or provide an existing readable package root with --root; "
    "then run resolve again."
)
METADATA_RECOVERY_ACTION = (
    "Install the package through WorkBuddy's own expert management UI, or provide an existing "
    "readable package root with --root; then run resolve again."
)
UNUSABLE_RECOVERY_ACTION = (
    "Repair or reinstall the package through WorkBuddy's own expert management UI, or provide "
    "a readable package root containing at least one agent Markdown file; then run resolve again."
)
INSTALLED = "installed"
INSTALLED_UNUSABLE = "installed-unusable"
METADATA_ONLY = "metadata-only"

TRUST_POLICY_VERSION = "2026-08-29.1"
TRUST_ELIGIBLE = "eligible"
TRUST_REVIEW_REQUIRED = "review-required"
TRUST_QUARANTINED = "quarantined"
TRUST_UNKNOWN = "unknown"
TRUST_STATUSES = (
    TRUST_ELIGIBLE,
    TRUST_REVIEW_REQUIRED,
    TRUST_QUARANTINED,
    TRUST_UNKNOWN,
)
FINDING_BLOCK = "block"
FINDING_REVIEW = "review"
FINDING_NOTICE = "notice"
FINDING_SEVERITIES = (FINDING_BLOCK, FINDING_REVIEW, FINDING_NOTICE)
DEFAULT_AUDIT_LIMIT = 25
MAX_AUDIT_FILES = 256
MAX_AUDIT_DIRECTORY_ENTRIES = 2048
MAX_AUDIT_DEPTH = 16
MAX_AUDIT_FILE_BYTES = 1024 * 1024
MAX_AUDIT_TOTAL_BYTES = 8 * 1024 * 1024
MAX_AUDIT_FINDINGS = 200
MAX_DECLARED_AUDIT_PATHS = 256
MAX_MANIFEST_JSON_BYTES = 1024 * 1024
MAX_CATALOG_JSON_BYTES = 5 * 1024 * 1024
MAX_RUNTIME_JSON_BYTES = 1024 * 1024
MAX_CROSS_LINE_SCAN_BYTES = MAX_AUDIT_FILE_BYTES
AUDIT_TEXT_SUFFIXES = frozenset(
    {
        ".bat",
        ".cfg",
        ".cjs",
        ".cmd",
        ".ini",
        ".js",
        ".json",
        ".jsonc",
        ".md",
        ".mdx",
        ".mjs",
        ".ps1",
        ".py",
        ".sh",
        ".toml",
        ".ts",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

URL_RE = re.compile(
    r"(?:https?://|weixin://|alipays://|data:image/)[^\s<>\"']+",
    re.IGNORECASE,
)
ZERO_WIDTH_AND_INVISIBLE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad\x00-\x08\x0b\x0c\x0e-\x1f]"
)
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"(?i)(?:^[a-z]:[\\/]|^\\\\)")
EMBEDDED_WINDOWS_PATH_RE = re.compile(
    r"(?i)(?:(?<![a-z0-9])[a-z]:[\\/]|\\\\[^\\\s]+[\\/])"
)
EMBEDDED_POSIX_LOCAL_PATH_RE = re.compile(
    r"(?i)(?:^|[\s:,(])/(?:home|users|tmp|var(?:/tmp)?|mnt|opt|private|root)(?:/|\b)"
)
TRUST_RULE_PATTERNS: tuple[tuple[str, str, str, re.Pattern[str]], ...] = (
    (
        "prompt_override",
        FINDING_BLOCK,
        "instruction-override",
        re.compile(
            r"(?:\b(?:ignore|disregard|override|bypass|forget)\b.{0,100}"
            r"\b(?:previous|prior|system|developer|user|all)\b.{0,60}"
            r"\b(?:instructions?|rules?|prompts?)\b|"
            r"(?:忽略|覆盖|绕过|忘记).{0,80}(?:之前|以上|系统|开发者|用户|所有).{0,50}(?:指令|规则|提示词))",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_access",
        FINDING_BLOCK,
        "credential-access",
        re.compile(
            r"(?:\b(?:read|scan|search|find|collect|dump|print|show|reveal|echo|extract|enumerate)\b"
            r".{0,100}\b(?:credentials?|passwords?|api[-_\s]*keys?|access[-_\s]*tokens?|cookies?|"
            r"secrets?|\.env|id_rsa|ssh[-_\s]*keys?)\b|"
            r"(?:读取|扫描|搜索|查找|收集|导出|打印|回显|显示|提取).{0,80}"
            r"(?:凭据|密码|口令|API\s*密钥|令牌|Cookie|\.env|SSH\s*密钥))",
            re.IGNORECASE,
        ),
    ),
    (
        "sensitive_data_upload",
        FINDING_BLOCK,
        "sensitive-upload",
        re.compile(
            r"(?:\bexfiltrate\b.{0,100}\b(?:private|sensitive|personal|credential|token|secret|files?|data|prompts?|history|code|workspace|repo)\b|"
            r"\b(?:upload|transmit)\b.{0,100}\b(?:private|sensitive|personal|credential|token|secret|customer\s+data|user\s+data|prompts?|history|code|workspace|repo|files?|context)\b|"
            r"\b(?:send|post|forward)\b.{0,100}\b(?:private|sensitive|personal|credential|token|secret|customer\s+data|user\s+data|prompts?|history|code|workspace|repo|files?|context)\b.{0,100}\b(?:external|third[- ]party|server|endpoint|url|website|cloud|service|https?://)\b|"
            r"\b(?:external|third[- ]party|server|endpoint|url|website|cloud|service|https?://)\b.{0,100}\b(?:send|post|forward)\b.{0,100}\b(?:private|sensitive|personal|credential|token|secret|customer\s+data|user\s+data|prompts?|history|code|workspace|repo|files?|context)\b|"
            r"外传.{0,80}(?:隐私|敏感|个人|凭据|令牌|密钥|文件|数据|提示词|聊天记录|代码|工作区|仓库)|"
            r"上传.{0,80}(?:隐私|敏感|个人|凭据|令牌|密钥|客户数据|用户数据|提示词|聊天记录|代码|工作区|仓库|文件|上下文).{0,80}(?:外部|第三方|服务器|接口|网址|网站|云端|服务|https?://|至|到)|"
            r"(?:发送|提交|回传|POST).{0,80}(?:隐私|敏感|个人|凭据|令牌|密钥|客户数据|用户数据|提示词|聊天记录|代码|工作区|仓库|文件|上下文).{0,80}(?:外部|第三方|服务器|接口|网址|网站|云端|服务|https?://)|"
            r"(?:外部|第三方|服务器|接口|网址|网站|云端|服务|https?://).{0,80}(?:发送|提交|回传|POST).{0,80}(?:隐私|敏感|个人|凭据|令牌|密钥|客户数据|用户数据|提示词|聊天记录|代码|工作区|仓库|文件|上下文)|"
            r"(?:(?:将|把)(?:当前)?(?:隐私|敏感|个人|凭据|令牌|密钥|客户数据|用户数据|提示词|聊天记录|代码|工作区|仓库|文件|上下文).{0,80}(?:发送|提交|回传|外传|上传|POST).{0,80}(?:外部|第三方|服务器|接口|网址|网站|云端|服务|https?://|至|到)))",
            re.IGNORECASE,
        ),
    ),
    (
        "remote_download_execute",
        FINDING_BLOCK,
        "download-and-execute",
        re.compile(
            r"(?:(?:\bcurl\b|\bwget\b|invoke-webrequest|invoke-restmethod|\birm\b|\bdownload\b|\bfetch\b|下载).{0,180}"
            r"(?:\bbash\b|\bsh\b|powershell|\biex\b|\bcmd\b|\bexecute\b|\bexec\b|\brun\b|\bsource\b|\beval\b|执行|运行)|"
            r"(?:\bbash\b|\bsh\b|powershell|\biex\b|\bcmd\b|\bexecute\b|\bexec\b|\brun\b|执行|运行).{0,180}"
            r"(?:\bcurl\b|\bwget\b|invoke-webrequest|invoke-restmethod|\birm\b|\bdownload\b|下载)|"
            r"\bpython\s+-c\s+[\"'].*?\b(?:exec|eval)\b|"
            r"\bcertutil(?:\.exe)?\s+-[a-z]*urlcache\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "qr_auth_or_payment",
        FINDING_REVIEW,
        "qr-gate",
        re.compile(
            r"(?:(?:扫码|二维码|qr\s*code).{0,100}(?:登录|授权|充值|支付|进群|加入|获取|咨询|解锁|login|auth|recharge|pay|join)|"
            r"(?:登录|授权|充值|支付|进群|加入|获取|咨询|解锁|login|auth|recharge|pay|join).{0,100}(?:扫码|二维码|qr\s*code)|"
            r"weixin://[^\s<>\"']+|alipays://[^\s<>\"']+|data:image/[a-zA-Z0-9+]+;base64,[a-zA-Z0-9+/=]+)",
            re.IGNORECASE,
        ),
    ),
    (
        "payment_or_membership_gate",
        FINDING_REVIEW,
        "payment-gate",
        re.compile(
            r"(?:充值|付费解锁|付费后|购买后|付费购买|开通会员|会员专享|VIP会员|消耗积分|积分不足|卡密|商业授权|"
            r"paywall|paid\s+plan|premium\s+required|top\s*up|credits?\s+required|membership\s+required|"
            r"subscription\s+required|commercial\s+license)",
            re.IGNORECASE,
        ),
    ),
    (
        "tracking_or_referral_link",
        FINDING_REVIEW,
        "tracked-link",
        re.compile(
            r"(?:[?&](?:ref|referral|affiliate|source|channel|from|spm|promoter|tag|cps|invite_code|invite|coupon|utm_[a-z_]+)=|"
            r"\b(?:https?://)?(?:t\.cn|bit\.ly|dwz\.cn|url\.cn|tinyurl\.com|b23\.tv|suo\.im|zws\.im)/[a-zA-Z0-9_\-]+|"
            r"\baffiliate\b|邀请码|推广码|返利链接|渠道码|"
            r"(?:(?:配套阅读|推广链接|广告链接|赞助内容|优惠活动|专属福利|"
            r"promotional?\s+(?:link|resource)|sponsored\s+(?:link|content)).{0,180}https?://|"
            r"https?://.{0,180}(?:配套阅读|推广链接|广告链接|赞助内容|优惠活动|专属福利|"
            r"promotional?\s+(?:link|resource)|sponsored\s+(?:link|content))))",
            re.IGNORECASE,
        ),
    ),
    (
        "external_account_or_api_key",
        FINDING_REVIEW,
        "external-account-gate",
        re.compile(
            r"(?:(?:\b(?:need|required|must|configure|provide|enter|supply|set)\b|需要|必须|请先|配置|设置|提供|输入|填入|填写).{0,100}"
            r"(?:注册|登录|api[-_ ]?key|access[-_ ]?token|第三方账号|secret)|"
            r"(?:注册|登录|api[-_ ]?key|access[-_ ]?token|第三方账号|secret).{0,100}"
            r"(?:\b(?:need|required|must|configure|provide|enter|supply|set)\b|需要|必须|请先|配置|设置|提供|输入|填入|填写))",
            re.IGNORECASE,
        ),
    ),
    (
        "social_diversion",
        FINDING_REVIEW,
        "social-diversion",
        re.compile(
            r"(?:(?:添加|加|加入|关注|私信|联系).{0,60}"
            r"(?:微信|微信群|公众号|QQ|QQ群|Telegram|Discord|知识星球|企微|企业微信|飞书|飞书群|社群)|"
            r"(?:join|follow|contact|dm).{0,60}(?:wechat|telegram|discord|community)|"
            r"(?:(?:官方)?(?:微信|微信群|公众号|QQ群?|Telegram|Discord|知识星球|企微|企业微信|飞书群?|交流群|社群|读者群|VIP群))[：:\s]+[a-zA-Z0-9_\-\u4e00-\u9fa5]+)",
            re.IGNORECASE,
        ),
    ),
)

ASCII_TERM_RE = re.compile(r"[a-z0-9][a-z0-9+#._/-]*", re.IGNORECASE)
CJK_SEQUENCE_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
ASCII_STOPWORDS = {
    "a",
    "an",
    "and",
    "agent",
    "expert",
    "for",
    "help",
    "i",
    "me",
    "my",
    "of",
    "please",
    "recommend",
    "the",
    "team",
    "to",
    "use",
    "want",
    "with",
}
CJK_STOPWORDS = {
    "一个",
    "一些",
    "这个",
    "那个",
    "他们",
    "以及",
    "使用",
    "可以",
    "希望",
    "想做",
    "我想",
    "我们",
    "我的",
    "帮我",
    "帮忙",
    "推荐",
    "最适合",
    "专家",
    "专家团",
    "团队",
    "单专家",
    "需要",
    "请帮",
    "请给",
}
GENERIC_RECOMMEND_TERMS = {
    "工作",
    "工作流",
    "任务",
    "项目",
    "流程",
    "需求",
    "方案",
    "内容",
    "工具",
    "系统",
    "服务",
    "专家",
    "实现",
}
GENERIC_RECOMMEND_ASCII_TERMS = {"app", "project", "task", "tool", "workflow"}
TEAM_HINTS = ("专家团", "多角色专家", "多角色团队", "expert team", "multi-agent team")
AGENT_HINTS = ("单专家", "单个专家", "一位专家", "个人专家", "single expert")
RECOMMEND_FIELD_WEIGHTS = {
    "display_name": 9.0,
    "profession": 8.0,
    "tags": 7.0,
    "category_name": 4.0,
    "category_description": 2.5,
    "description": 3.0,
    "id": 3.0,
    "plugin": 2.0,
    "agent_name": 2.0,
}
RECOMMEND_FIELD_LABELS = {
    "display_name": "名称",
    "profession": "专业定位",
    "tags": "标签",
    "category_name": "分类",
    "category_description": "分类说明",
    "description": "简介",
    "id": "标识",
    "plugin": "插件标识",
    "agent_name": "角色标识",
}


def configure_standard_streams() -> None:
    """Keep structured output readable across Windows and Unix hosts."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


class BridgeError(RuntimeError):
    """A user-actionable bridge failure."""

    def __init__(self, message: str, *, code: str = "bridge_error") -> None:
        super().__init__(message)
        self.code = code


def read_json(path: Path, *, max_bytes: int = MAX_CATALOG_JSON_BYTES) -> Any:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            raise BridgeError(
                f"JSON file exceeds the bounded read limit: {path}",
                code="json_too_large",
            )
        with path.open("rb") as handle:
            raw = handle.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise BridgeError(
                f"JSON file exceeds the bounded read limit: {path}",
                code="json_too_large",
            )
        return json.loads(raw.decode("utf-8-sig"))
    except FileNotFoundError as exc:
        raise BridgeError(f"File not found: {path}", code="file_not_found") from exc
    except PermissionError as exc:
        raise BridgeError(f"File is not readable: {path}", code="permission_denied") from exc
    except UnicodeDecodeError as exc:
        raise BridgeError(f"JSON file is not UTF-8 text: {path}", code="invalid_json") from exc
    except json.JSONDecodeError as exc:
        raise BridgeError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}",
            code="invalid_json",
        ) from exc


def localized(value: Any, fallback: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("zh", "en"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for candidate in value.values():
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return fallback


def localized_values(value: Any) -> list[str]:
    """Return all non-empty localized strings without choosing a display language."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, dict):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for candidate in value.values():
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        normalized = candidate.strip()
        key = normalized.casefold()
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def localized_list(value: Any) -> tuple[list[str], list[str]]:
    """Return display values and all-language values for a localized list."""
    if not isinstance(value, list):
        return [], []
    display_values: list[str] = []
    search_values: list[str] = []
    display_seen: set[str] = set()
    search_seen: set[str] = set()
    for item in value:
        display = localized(item)
        if display and display.casefold() not in display_seen:
            display_seen.add(display.casefold())
            display_values.append(display)
        for candidate in localized_values(item):
            if candidate.casefold() not in search_seen:
                search_seen.add(candidate.casefold())
                search_values.append(candidate)
    return display_values, search_values


def exact_number(value: Any) -> int | float | None:
    """Accept only explicit numeric evidence; booleans and guessed values are rejected."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value if math.isfinite(float(value)) else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value.strip())
        except ValueError:
            return None
        if not math.isfinite(parsed):
            return None
        return int(parsed) if parsed.is_integer() else parsed
    return None


class _RejectOfficialRedirects(urllib.request.HTTPRedirectHandler):
    """Keep the anonymous probe on the fixed first-party origin it was given."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def anonymous_official_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = OFFICIAL_ONLINE_TIMEOUT_SECONDS,
    opener: Any = None,
) -> dict[str, Any]:
    """Fetch one allowlisted WorkBuddy source without auth, cookies, or proxy credentials."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in WORKBUDDY_OFFICIAL_HOSTS:
        raise BridgeError(
            f"Official online source is not allowlisted: {url}",
            code="official_source_not_allowlisted",
        )

    request_body = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {
        "Accept": "application/json",
        "User-Agent": OFFICIAL_ONLINE_USER_AGENT,
    }
    if request_body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=request_body,
        headers=headers,
        method=method.upper(),
    )
    client = opener or urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _RejectOfficialRedirects(),
    )

    response: Any
    try:
        response = client.open(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        authenticate = str(exc.headers.get("WWW-Authenticate") or "")
        return {
            "url": url,
            "method": method.upper(),
            "status": "unavailable",
            "http_status": int(exc.code),
            "reason_code": (
                "authentication_required"
                if exc.code in {401, 403}
                else "redirect_rejected"
                if 300 <= exc.code < 400
                else "http_error"
            ),
            "auth_scheme": authenticate.split(maxsplit=1)[0] if authenticate else "",
            "content_type": str(exc.headers.get("Content-Type") or ""),
            "etag": str(exc.headers.get("ETag") or ""),
            "last_modified": str(exc.headers.get("Last-Modified") or ""),
            "_payload": None,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "url": url,
            "method": method.upper(),
            "status": "unavailable",
            "http_status": None,
            "reason_code": "network_error",
            "error_type": type(exc).__name__,
            "auth_scheme": "",
            "content_type": "",
            "etag": "",
            "last_modified": "",
            "_payload": None,
        }

    with response:
        status_code = int(getattr(response, "status", response.getcode()))
        response_headers = response.headers
        raw = response.read(OFFICIAL_ONLINE_MAX_BYTES + 1)
    if len(raw) > OFFICIAL_ONLINE_MAX_BYTES:
        return {
            "url": url,
            "method": method.upper(),
            "status": "unavailable",
            "http_status": status_code,
            "reason_code": "response_too_large",
            "auth_scheme": "",
            "content_type": str(response_headers.get("Content-Type") or ""),
            "etag": str(response_headers.get("ETag") or ""),
            "last_modified": str(response_headers.get("Last-Modified") or ""),
            "_payload": None,
        }
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    return {
        "url": url,
        "method": method.upper(),
        "status": "available" if payload is not None else "unavailable",
        "http_status": status_code,
        "reason_code": "" if payload is not None else "invalid_json",
        "auth_scheme": "",
        "content_type": str(response_headers.get("Content-Type") or ""),
        "etag": str(response_headers.get("ETag") or ""),
        "last_modified": str(response_headers.get("Last-Modified") or ""),
        "bytes": len(raw),
        "_payload": payload,
    }


def official_items(payload: Any) -> list[dict[str, Any]]:
    """Read supported first-party catalog and API envelope shapes."""
    if not isinstance(payload, dict):
        return []
    for key in ("items", "experts"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("items", "experts"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def official_api_success(result: dict[str, Any]) -> bool:
    payload = result.get("_payload")
    if result.get("status") != "available" or not isinstance(payload, dict):
        return False
    code = payload.get("code")
    return code in {None, 0}


def official_probe_view(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("_payload")
    items = official_items(payload)
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}
    return {
        key: value
        for key, value in {
            **{key: value for key, value in result.items() if not key.startswith("_")},
            "api_code": payload.get("code") if isinstance(payload, dict) else None,
            "api_message": payload.get("msg") if isinstance(payload, dict) else None,
            "returned": len(items),
            "total": data.get("total") or data.get("total_count") if isinstance(data, dict) else None,
        }.items()
        if value not in (None, "")
    }


def merge_official_ranking_records(
    catalog: list[dict[str, Any]],
    records: list[dict[str, Any]],
    source_url: str,
) -> dict[str, int]:
    """Merge only explicit official fields into unambiguous local catalog matches."""
    alias_map: dict[str, set[int]] = {}
    for index, item in enumerate(catalog):
        for value in (item.get("id"), item.get("plugin"), item.get("agent_name")):
            key = str(value or "").strip().casefold()
            if key:
                alias_map.setdefault(key, set()).add(index)

    updated_indexes: dict[str, set[int]] = {
        "use_count": set(),
        "reco_rank": set(),
        "published_at": set(),
    }
    for record in records:
        candidate_indexes: set[int] = set()
        for value in (
            record.get("source_id"),
            record.get("id"),
            record.get("expert_id"),
            record.get("plugin"),
            record.get("agentName"),
            record.get("agent_name"),
        ):
            key = str(value or "").strip().casefold()
            if key:
                candidate_indexes.update(alias_map.get(key, set()))
        if len(candidate_indexes) != 1:
            continue
        index = next(iter(candidate_indexes))
        item = catalog[index]

        use_count = exact_number(record.get("useCount"))
        if use_count is None:
            use_count = exact_number(record.get("use_count"))
        if use_count is not None:
            item["use_count"] = use_count
            item["use_count_source"] = source_url
            updated_indexes["use_count"].add(index)

        reco_rank = exact_number(record.get("recoRank"))
        if reco_rank is None:
            reco_rank = exact_number(record.get("reco_rank"))
        if reco_rank is not None:
            item["reco_rank"] = reco_rank
            item["reco_rank_source"] = source_url
            updated_indexes["reco_rank"].add(index)

        published_at = str(record.get("publishedAt") or record.get("published_at") or "").strip()
        if published_at:
            item["latest_value"] = published_at
            item["latest_field"] = "publishedAt" if record.get("publishedAt") else "published_at"
            item["latest_source"] = source_url
            updated_indexes["published_at"].add(index)

    return {field: len(indexes) for field, indexes in updated_indexes.items()}


def probe_official_online_ranking(
    catalog: list[dict[str, Any]],
    *,
    fetcher: Any = None,
) -> dict[str, Any]:
    """Probe fixed WorkBuddy public sources without touching local or browser credentials."""
    fetch = fetcher or anonymous_official_json

    public_catalog = fetch(WORKBUDDY_PUBLIC_CATALOG_URL, method="GET")
    public_items = official_items(public_catalog.get("_payload"))
    public_view = official_probe_view(public_catalog)
    public_view.update(
        {
            "catalog_version": public_catalog.get("_payload", {}).get("version")
            if isinstance(public_catalog.get("_payload"), dict)
            else None,
            "catalog_last_updated": public_catalog.get("_payload", {}).get("lastUpdated")
            if isinstance(public_catalog.get("_payload"), dict)
            else None,
            "categories": len(public_catalog.get("_payload", {}).get("categories", []))
            if isinstance(public_catalog.get("_payload"), dict)
            else 0,
            "explicit_field_coverage": {
                "use_count": sum(
                    exact_number(item.get("useCount")) is not None
                    or exact_number(item.get("use_count")) is not None
                    for item in public_items
                ),
                "reco_rank": sum(
                    exact_number(item.get("recoRank")) is not None
                    or exact_number(item.get("reco_rank")) is not None
                    for item in public_items
                ),
                "published_at": sum(bool(item.get("publishedAt") or item.get("published_at")) for item in public_items),
            },
        }
    )

    direct_ranking = fetch(f"{WORKBUDDY_RANKING_URL}?limit=500", method="GET")
    if official_api_success(direct_ranking):
        merge_official_ranking_records(
            catalog,
            official_items(direct_ranking.get("_payload")),
            WORKBUDDY_RANKING_URL,
        )

    live_list_results: dict[str, dict[str, Any]] = {}
    sort_fields_not_attempted: list[str] = []
    for index, sort_field in enumerate(OFFICIAL_SORT_FIELDS):
        result = fetch(
            WORKBUDDY_MARKET_LIST_URL,
            method="POST",
            body={
                "page": 1,
                "page_size": 500,
                "sort_by": sort_field,
                "sort_order": "desc",
            },
        )
        live_list_results[sort_field] = official_probe_view(result)
        if official_api_success(result):
            merge_official_ranking_records(
                catalog,
                official_items(result.get("_payload")),
                WORKBUDDY_MARKET_LIST_URL,
            )
            continue
        if result.get("reason_code") == "authentication_required":
            sort_fields_not_attempted = list(OFFICIAL_SORT_FIELDS[index + 1 :])
            break

    total = len(catalog)
    live_api_host = urllib.parse.urlparse(WORKBUDDY_OFFICIAL_API_ORIGIN).hostname
    online_coverage = {
        "use_count": sum(
            urllib.parse.urlparse(str(item.get("use_count_source") or "")).hostname
            == live_api_host
            for item in catalog
        ),
        "reco_rank": sum(
            urllib.parse.urlparse(str(item.get("reco_rank_source") or "")).hostname
            == live_api_host
            for item in catalog
        ),
        "published_at": sum(
            urllib.parse.urlparse(str(item.get("latest_source") or "")).hostname
            == live_api_host
            for item in catalog
        ),
    }
    complete_fields = [field for field, count in online_coverage.items() if total > 0 and count == total]
    ranking_available = bool(complete_fields)
    auth_required = any(
        view.get("reason_code") == "authentication_required"
        for view in [official_probe_view(direct_ranking), *live_list_results.values()]
    )

    return {
        "status": "available" if ranking_available else "unavailable",
        "scope": "cn-production official anonymous sources",
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "credential_policy": {
            "local_credentials_read": False,
            "authorization_header_sent": False,
            "cookies_sent": False,
            "environment_proxies_used": False,
            "redirects_followed": False,
        },
        "sources": {
            "public_catalog": public_view,
            "direct_hot_ranking": official_probe_view(direct_ranking),
            "live_market_lists": live_list_results,
        },
        "sort_fields_not_attempted_after_common_auth_gate": sort_fields_not_attempted,
        "field_updates": online_coverage,
        "online_coverage": {field: {"known": count, "total": total} for field, count in online_coverage.items()},
        "complete_fields": complete_fields,
        "authentication_required": auth_required,
        "unavailable_reason": "" if ranking_available else (
            "WorkBuddy 官方公共清单没有覆盖全部候选的显式排名字段；匿名实时接口"
            + ("要求 Bearer 登录态。" if auth_required else "未返回可验证的完整排名数据。")
            + "未读取或发送任何凭据。"
        ),
        "read_only": True,
    }


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            normalized = path.expanduser().resolve()
        except OSError:
            normalized = path.expanduser().absolute()
        key = os.path.normcase(str(normalized))
        if key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def resolved_path_within(root: Path, candidate: Path) -> Path | None:
    """Resolve a candidate and reject symlink or traversal escapes from root."""
    try:
        resolved_root = root.resolve()
        resolved = candidate.resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        return None
    return resolved


def source_candidates(explicit_root: str | None) -> list[Path]:
    if explicit_root:
        return unique_paths([Path(explicit_root)])

    candidates: list[Path] = []
    configured = os.environ.get("WORKBUDDY_CONFIG_DIR")
    if configured:
        candidates.append(Path(configured))
    candidates.append(Path.home() / ".workbuddy")
    return unique_paths(candidates)


def child_directories(path: Path) -> list[Path]:
    try:
        return sorted((item for item in path.iterdir() if item.is_dir()), key=lambda p: p.name.casefold())
    except (FileNotFoundError, PermissionError, OSError):
        return []


def package_manifests_in_collection(collection: Path) -> list[Path]:
    manifests: list[Path] = []
    for package_dir in child_directories(collection):
        manifest = package_dir / MANIFEST_RELATIVE
        if manifest.is_file():
            manifests.append(manifest)
    return manifests


def package_manifests_in_marketplace(marketplace: Path) -> list[Path]:
    manifests: list[Path] = []
    for collection_name in MARKETPLACE_COLLECTIONS:
        manifests.extend(package_manifests_in_collection(marketplace / collection_name))
    return manifests


def manifest_paths_for_root(root: Path) -> list[Path]:
    """Discover package manifests without an unbounded recursive scan."""
    manifests: list[Path] = []

    direct_manifest = root / MANIFEST_RELATIVE
    if direct_manifest.is_file():
        manifests.append(direct_manifest)

    # A direct package collection, such as .../experts/plugins.
    manifests.extend(package_manifests_in_collection(root))

    # A marketplace root, such as .../marketplaces/experts.
    manifests.extend(package_manifests_in_marketplace(root))

    marketplace_roots: list[Path] = []
    if root.name.casefold() == "marketplaces":
        marketplace_roots.append(root)
    for candidate in (root / "plugins" / "marketplaces", root / "marketplaces"):
        if candidate.is_dir():
            marketplace_roots.append(candidate)

    for marketplaces_root in unique_paths(marketplace_roots):
        for marketplace in child_directories(marketplaces_root):
            manifests.extend(package_manifests_in_marketplace(marketplace))

    return [
        resolved
        for manifest in unique_paths(manifests)
        if (resolved := resolved_path_within(root, manifest)) is not None
    ]


def marketplace_name(package_root: Path) -> str:
    parent = package_root.parent
    if parent.name in MARKETPLACE_COLLECTIONS:
        return parent.parent.name
    return "direct"


def safe_package_path(package_root: Path, raw_path: str) -> tuple[Path | None, str | None]:
    relative = Path(raw_path)
    if relative.is_absolute():
        return None, f"Absolute path is not allowed: {raw_path}"
    try:
        resolved_root = package_root.resolve()
        resolved = (package_root / relative).resolve()
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        return None, f"Path escapes package root: {raw_path}"
    return resolved, None


def safe_discovered_package_path(
    package_root: Path,
    candidate: Path,
    *,
    label: str,
) -> tuple[Path | None, str | None]:
    """Validate paths found by fallback enumeration, including symlinks."""
    try:
        raw_path = str(candidate.relative_to(package_root))
    except ValueError:
        return None, f"{label} escapes package root: {candidate}"
    path, error = safe_package_path(package_root, raw_path)
    if error:
        return None, f"{label} escapes package root: {raw_path}"
    return path, None


def declared_string_paths(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def agent_paths(package_root: Path, manifest: dict[str, Any]) -> tuple[list[Path], list[str]]:
    declared = declared_string_paths(manifest.get("agents"))
    warnings: list[str] = []
    result: list[Path] = []

    if declared:
        for raw_path in declared:
            path, error = safe_package_path(package_root, raw_path)
            if error:
                warnings.append(error)
            elif path is not None and path.is_file():
                result.append(path)
            else:
                warnings.append(f"Declared agent file is missing: {raw_path}")
    else:
        agents_dir = package_root / "agents"
        if agents_dir.is_dir():
            for candidate in sorted(agents_dir.glob("*.md"), key=lambda p: p.name.casefold()):
                path, error = safe_discovered_package_path(
                    package_root,
                    candidate,
                    label="Discovered agent file",
                )
                if error:
                    warnings.append(error)
                elif path is not None and path.is_file():
                    result.append(path)

    return unique_paths(result), warnings


def skill_paths(package_root: Path, manifest: dict[str, Any]) -> tuple[list[Path], list[str]]:
    declared = declared_string_paths(manifest.get("skills"))
    warnings: list[str] = []
    result: list[Path] = []

    if declared:
        for raw_path in declared:
            path, error = safe_package_path(package_root, raw_path)
            if error:
                warnings.append(error)
            elif path is not None and path.exists():
                result.append(path)
            else:
                warnings.append(f"Declared skill path is missing: {raw_path}")
    else:
        skills_dir = package_root / "skills"
        if skills_dir.is_dir():
            for child in child_directories(skills_dir):
                skill_file = child / "SKILL.md"
                path, error = safe_discovered_package_path(
                    package_root,
                    skill_file,
                    label="Discovered skill file",
                )
                if error:
                    warnings.append(error)
                elif path is not None and path.is_file():
                    result.append(path)

    return unique_paths(result), warnings


def _relative_audit_path(package_root: Path, path: Path) -> str:
    try:
        return path.relative_to(package_root).as_posix()
    except ValueError:
        return "[outside-package-root]"


def _safe_relative_identifier(value: Any) -> str:
    """Project an untrusted package-relative label without exposing host paths."""
    if not isinstance(value, str):
        return "[unknown-relative-file]"
    normalized = value.strip().replace("\\", "/")
    if (
        not normalized
        or WINDOWS_ABSOLUTE_PATH_RE.search(normalized)
        or normalized.startswith("/")
        or ".." in Path(normalized).parts
    ):
        return "[unsafe-relative-path]"
    return sanitize_untrusted_text(normalized, limit=260) or "[unknown-relative-file]"


def _path_has_symlink(package_root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(package_root)
    except ValueError:
        return True
    current = package_root
    for part in relative.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def _new_audit_state() -> dict[str, Any]:
    return {
        "candidates": {},
        "entries_seen": 0,
        "findings": [],
        "finding_total": 0,
        "finding_counts": {severity: 0 for severity in FINDING_SEVERITIES},
        "finding_keys": set(),
        "incomplete_reasons": [],
        "incomplete_keys": set(),
    }


def _record_finding(
    state: dict[str, Any],
    *,
    rule_id: str,
    severity: str,
    relative_file: str,
    line: int,
    match_kind: str,
) -> None:
    if severity not in FINDING_SEVERITIES:
        raise ValueError(f"Unsupported finding severity: {severity}")
    safe_relative_file = _safe_relative_identifier(relative_file)
    key = (rule_id, severity, safe_relative_file, line, match_kind)
    if key in state["finding_keys"]:
        return
    state["finding_keys"].add(key)
    state["finding_total"] += 1
    state["finding_counts"][severity] += 1
    if len(state["findings"]) < MAX_AUDIT_FINDINGS:
        state["findings"].append(
            {
                "rule_id": rule_id,
                "severity": severity,
                "evidence_count": 1,
                "relative_file": safe_relative_file,
                "line": line,
                "match_kind": match_kind,
            }
        )


def _record_incomplete(
    state: dict[str, Any],
    *,
    rule_id: str,
    relative_file: str,
    match_kind: str,
) -> None:
    safe_relative_file = _safe_relative_identifier(relative_file)
    key = (rule_id, safe_relative_file, match_kind)
    if key not in state["incomplete_keys"]:
        state["incomplete_keys"].add(key)
        state["incomplete_reasons"].append(
            {
                "rule_id": rule_id,
                "relative_file": safe_relative_file,
                "match_kind": match_kind,
            }
        )
    _record_finding(
        state,
        rule_id=rule_id,
        severity=FINDING_BLOCK,
        relative_file=safe_relative_file,
        line=0,
        match_kind=match_kind,
    )


def _bounded_directory_entries(
    package_root: Path,
    directory: Path,
    state: dict[str, Any],
) -> list[Path]:
    relative = _relative_audit_path(package_root, directory)
    if _path_has_symlink(package_root, directory):
        _record_incomplete(
            state,
            rule_id="scan_path_violation",
            relative_file=relative,
            match_kind="symlink",
        )
        return []
    try:
        entries: list[Path] = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                state["entries_seen"] += 1
                if state["entries_seen"] > MAX_AUDIT_DIRECTORY_ENTRIES:
                    _record_incomplete(
                        state,
                        rule_id="scan_budget_exceeded",
                        relative_file=relative,
                        match_kind="directory-entry-limit",
                    )
                    break
                path = Path(entry.path)
                if entry.is_symlink():
                    _record_incomplete(
                        state,
                        rule_id="scan_path_violation",
                        relative_file=_relative_audit_path(package_root, path),
                        match_kind="symlink",
                    )
                    continue
                entries.append(path)
    except (FileNotFoundError, PermissionError, OSError):
        _record_incomplete(
            state,
            rule_id="scan_read_error",
            relative_file=relative,
            match_kind="directory-read",
        )
        return []
    return sorted(entries, key=lambda item: item.name.casefold())


def _queue_audit_file(
    package_root: Path,
    path: Path,
    state: dict[str, Any],
    *,
    require_supported_text: bool = False,
) -> None:
    relative = _relative_audit_path(package_root, path)
    if relative == "[outside-package-root]" or _path_has_symlink(package_root, path):
        _record_incomplete(
            state,
            rule_id="scan_path_violation",
            relative_file=relative,
            match_kind="path-or-symlink",
        )
        return
    if path.suffix.casefold() not in AUDIT_TEXT_SUFFIXES:
        if require_supported_text:
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=relative,
                match_kind="unaudited-executable-content",
            )
        return
    candidates: dict[str, Path] = state["candidates"]
    if relative in candidates:
        return
    if len(candidates) >= MAX_AUDIT_FILES:
        _record_incomplete(
            state,
            rule_id="scan_budget_exceeded",
            relative_file=relative,
            match_kind="file-count-limit",
        )
        return
    candidates[relative] = path


def _walk_audit_path(
    package_root: Path,
    path: Path,
    state: dict[str, Any],
    *,
    depth: int = 0,
    require_supported_text: bool = False,
) -> None:
    relative = _relative_audit_path(package_root, path)
    if depth > MAX_AUDIT_DEPTH:
        _record_incomplete(
            state,
            rule_id="scan_budget_exceeded",
            relative_file=relative,
            match_kind="directory-depth-limit",
        )
        return
    if _path_has_symlink(package_root, path):
        _record_incomplete(
            state,
            rule_id="scan_path_violation",
            relative_file=relative,
            match_kind="symlink",
        )
        return
    try:
        is_file = path.is_file()
        is_dir = path.is_dir()
    except OSError:
        _record_incomplete(
            state,
            rule_id="scan_read_error",
            relative_file=relative,
            match_kind="path-stat",
        )
        return
    if is_file:
        _queue_audit_file(
            package_root,
            path,
            state,
            require_supported_text=require_supported_text,
        )
        return
    if not is_dir:
        _record_incomplete(
            state,
            rule_id="declared_content_missing",
            relative_file=relative,
            match_kind="missing-path",
        )
        return
    for child in _bounded_directory_entries(package_root, path, state):
        _walk_audit_path(
            package_root,
            child,
            state,
            depth=depth + 1,
            require_supported_text=require_supported_text,
        )


def _declared_audit_paths(
    package_root: Path,
    value: Any,
    state: dict[str, Any],
    *,
    declaration_kind: str,
    allow_directories: bool,
) -> bool:
    if not isinstance(value, list) or not value:
        return False
    if len(value) > MAX_DECLARED_AUDIT_PATHS:
        _record_incomplete(
            state,
            rule_id="scan_budget_exceeded",
            relative_file=MANIFEST_RELATIVE.as_posix(),
            match_kind=f"{declaration_kind}-declaration-limit",
        )
    for raw_value in value[:MAX_DECLARED_AUDIT_PATHS]:
        if not isinstance(raw_value, str) or not raw_value.strip():
            _record_incomplete(
                state,
                rule_id="declared_content_missing",
                relative_file=MANIFEST_RELATIVE.as_posix(),
                match_kind=f"invalid-{declaration_kind}-declaration",
            )
            continue
        relative = Path(raw_value.strip())
        display_relative = relative.as_posix()
        if relative.is_absolute() or ".." in relative.parts:
            _record_incomplete(
                state,
                rule_id="scan_path_violation",
                relative_file=display_relative,
                match_kind=f"{declaration_kind}-path-escape",
            )
            continue
        path = package_root / relative
        if _path_has_symlink(package_root, path):
            _record_incomplete(
                state,
                rule_id="scan_path_violation",
                relative_file=display_relative,
                match_kind=f"{declaration_kind}-symlink",
            )
            continue
        try:
            exists = path.exists()
            is_directory = path.is_dir()
        except OSError:
            exists = False
            is_directory = False
        if not exists:
            _record_incomplete(
                state,
                rule_id="declared_content_missing",
                relative_file=display_relative,
                match_kind=f"missing-{declaration_kind}",
            )
            continue
        if is_directory and not allow_directories:
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=display_relative,
                match_kind=f"directory-{declaration_kind}",
            )
            continue
        if not is_directory and path.suffix.casefold() not in AUDIT_TEXT_SUFFIXES:
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=display_relative,
                match_kind=f"unsupported-{declaration_kind}-text",
            )
            continue
        _walk_audit_path(package_root, path, state)
    return True


def _fallback_agent_audit_paths(
    package_root: Path,
    state: dict[str, Any],
) -> None:
    agents_dir = package_root / "agents"
    if not agents_dir.exists():
        _record_incomplete(
            state,
            rule_id="declared_content_missing",
            relative_file="agents",
            match_kind="missing-agent-directory",
        )
        return
    for candidate in _bounded_directory_entries(package_root, agents_dir, state):
        try:
            is_file = candidate.is_file()
        except OSError:
            is_file = False
        if is_file and candidate.suffix.casefold() == ".md":
            _queue_audit_file(package_root, candidate, state)


def _clean_obfuscation(text: str) -> str:
    norm = unicodedata.normalize("NFKC", text)
    cleaned = ZERO_WIDTH_AND_INVISIBLE_RE.sub("", norm)
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"(\*\*|__)", "", cleaned)
    cleaned = re.sub(r"(?<=\S)\*(?=\S)", "", cleaned)
    return cleaned


def _risk_match_details(text: str) -> list[tuple[str, str, str, int]]:
    matches: list[tuple[str, str, str, int]] = []
    clean_text = _clean_obfuscation(text)
    for rule_id, severity, match_kind, pattern in TRUST_RULE_PATTERNS:
        # Block rules are deliberately fail-closed. Natural-language negation is
        # too ambiguous to safely exempt a match (for example, double negatives
        # such as "do not hesitate to ignore"). Benign safety prose may therefore
        # require review, but attack wording cannot become eligible by phrasing.
        accepted = list(pattern.finditer(clean_text))
        if not accepted:
            continue
        matches.extend((rule_id, severity, match_kind, match.start()) for match in accepted)
    if (URL_RE.search(text) or URL_RE.search(clean_text)) and not any(
        severity != FINDING_NOTICE for _, severity, _, _ in matches
    ):
        url_match = URL_RE.search(text) or URL_RE.search(clean_text)
        if url_match is not None:
            matches.append(("external_link", FINDING_NOTICE, "external-link", url_match.start()))
    return matches


def _line_risk_matches(line: str) -> list[tuple[str, str, str]]:
    return list(
        dict.fromkeys(
            (rule_id, severity, match_kind)
            for rule_id, severity, match_kind, _ in _risk_match_details(line)
        )
    )


def _cross_line_scan_text(text: str) -> str:
    """Join wrapped lines without letting rules cross paragraph or heading boundaries."""
    scan_text = text[:MAX_CROSS_LINE_SCAN_BYTES]
    protected_newlines: set[int] = set()
    boundary_patterns = (
        re.compile(r"\r?\n[ \t]*\r?\n"),
        re.compile(r"\r?\n(?=[ \t]{0,3}#{1,6}[ \t])"),
    )
    for boundary_pattern in boundary_patterns:
        for match in boundary_pattern.finditer(scan_text):
            protected_newlines.update(
                index
                for index in range(match.start(), match.end())
                if scan_text[index] == "\n"
            )
    characters = list(scan_text)
    for index, character in enumerate(characters):
        if character == "\r":
            characters[index] = " "
        elif character == "\n" and index not in protected_newlines:
            characters[index] = " "
    return "".join(characters)


def sanitize_untrusted_text(value: Any, *, limit: int = 240) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.replace("\x1b", "").split())
    if EMBEDDED_WINDOWS_PATH_RE.search(text) or EMBEDDED_POSIX_LOCAL_PATH_RE.search(text):
        return "[redacted-local-path]"
    if any(severity in {FINDING_BLOCK, FINDING_REVIEW} for _, severity, _ in _line_risk_matches(text)):
        return "[redacted-untrusted-text]"
    text = URL_RE.sub("[external-link]", text)
    home_name = Path.home().name
    if home_name and len(home_name) >= 3:
        text = re.sub(re.escape(home_name), "[local-user]", text, flags=re.IGNORECASE)
    if len(text) > limit:
        return text[: max(limit - 1, 0)] + "…"
    return text


def safe_identifier(value: Any, *, limit: int = 120) -> str:
    return sanitize_untrusted_text(value, limit=limit)


def _trust_recovery_action(trust_status: str) -> str:
    if trust_status == TRUST_ELIGIBLE:
        return "No trust action is required before normal use; re-audit if the content digest changes."
    if trust_status == TRUST_REVIEW_REQUIRED:
        return (
            "Review the sanitized findings and obtain explicit user approval for this policy version "
            "and content digest before minimally reading package content."
        )
    if trust_status == TRUST_QUARANTINED:
        return (
            "Do not reuse package content. Repair or remove the blocking content or incomplete-scan "
            "condition, then run audit again."
        )
    return "Local package content is unavailable; install or provide a readable package before auditing."


def unknown_trust_report(identity: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "policy_version": TRUST_POLICY_VERSION,
        "trust_status": TRUST_UNKNOWN,
        "package": identity or {},
        "content_digest": None,
        "scan_complete": None,
        "scan": {
            "status": "not-applicable",
            "files_scanned": 0,
            "bytes_scanned": 0,
            "limits": {
                "max_files": MAX_AUDIT_FILES,
                "max_single_file_bytes": MAX_AUDIT_FILE_BYTES,
                "max_total_bytes": MAX_AUDIT_TOTAL_BYTES,
            },
            "incomplete_reasons": [],
        },
        "finding_counts": {severity: 0 for severity in FINDING_SEVERITIES},
        "findings": [],
        "findings_truncated": False,
        "recovery_action": _trust_recovery_action(TRUST_UNKNOWN),
        "read_only": True,
    }


def audit_package(package: dict[str, Any]) -> dict[str, Any]:
    package_root = Path(package["package_root"])
    manifest = package.get("_manifest") if isinstance(package.get("_manifest"), dict) else {}
    state = _new_audit_state()

    manifest_path = package_root / MANIFEST_RELATIVE
    if _path_has_symlink(package_root, manifest_path):
        _record_incomplete(
            state,
            rule_id="scan_path_violation",
            relative_file=MANIFEST_RELATIVE.as_posix(),
            match_kind="manifest-symlink",
        )
    elif not manifest_path.is_file():
        _record_incomplete(
            state,
            rule_id="declared_content_missing",
            relative_file=MANIFEST_RELATIVE.as_posix(),
            match_kind="missing-manifest",
        )
    else:
        _queue_audit_file(package_root, manifest_path, state)

    if not _declared_audit_paths(
        package_root,
        manifest.get("agents"),
        state,
        declaration_kind="agent",
        allow_directories=False,
    ):
        _fallback_agent_audit_paths(package_root, state)

    if not _declared_audit_paths(
        package_root,
        manifest.get("skills"),
        state,
        declaration_kind="skill",
        allow_directories=True,
    ):
        skills_root = package_root / "skills"
        if skills_root.exists():
            _walk_audit_path(package_root, skills_root, state)

    references_root = package_root / "references"
    if references_root.exists():
        _walk_audit_path(package_root, references_root, state)

    for executable_directory_name in ("scripts", "bin", "hooks"):
        executable_root = package_root / executable_directory_name
        if executable_root.exists():
            _walk_audit_path(
                package_root,
                executable_root,
                state,
                require_supported_text=True,
            )

    for candidate in _bounded_directory_entries(package_root, package_root, state):
        try:
            if candidate.is_file() and candidate.suffix.casefold() in AUDIT_TEXT_SUFFIXES:
                _queue_audit_file(package_root, candidate, state)
        except OSError:
            pass

    for docs_directory_name in ("docs", "templates"):
        docs_root = package_root / docs_directory_name
        if docs_root.exists():
            _walk_audit_path(package_root, docs_root, state)

    hasher = hashlib.sha256()
    total_bytes = 0
    files_scanned = 0
    for relative_file, path in sorted(state["candidates"].items()):
        try:
            size = path.stat().st_size
        except (FileNotFoundError, PermissionError, OSError):
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=relative_file,
                match_kind="file-stat",
            )
            continue
        if size > MAX_AUDIT_FILE_BYTES:
            _record_incomplete(
                state,
                rule_id="scan_budget_exceeded",
                relative_file=relative_file,
                match_kind="single-file-byte-limit",
            )
            continue
        if total_bytes + size > MAX_AUDIT_TOTAL_BYTES:
            _record_incomplete(
                state,
                rule_id="scan_budget_exceeded",
                relative_file=relative_file,
                match_kind="total-byte-limit",
            )
            continue
        try:
            raw = path.read_bytes()
        except (FileNotFoundError, PermissionError, OSError):
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=relative_file,
                match_kind="file-read",
            )
            continue
        if len(raw) != size:
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=relative_file,
                match_kind="file-changed-during-read",
            )
            continue
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            _record_incomplete(
                state,
                rule_id="scan_read_error",
                relative_file=relative_file,
                match_kind="unsupported-text-encoding",
            )
            continue
        hasher.update(relative_file.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(raw)
        hasher.update(b"\x00")
        total_bytes += size
        files_scanned += 1
        scan_text = _cross_line_scan_text(text)
        for rule_id, severity, match_kind, match_start in _risk_match_details(scan_text):
            line_number = text.count("\n", 0, match_start) + 1
            _record_finding(
                state,
                rule_id=rule_id,
                severity=severity,
                relative_file=relative_file,
                line=line_number,
                match_kind=match_kind,
            )

    if package.get("package_class") == AGENT_PACKAGE:
        _record_finding(
            state,
            rule_id="undeclared_agent_package",
            severity=FINDING_REVIEW,
            relative_file=MANIFEST_RELATIVE.as_posix(),
            line=1,
            match_kind="missing-expertType",
        )

    finding_counts = dict(state["finding_counts"])

    scan_complete = not state["incomplete_reasons"]
    if not scan_complete or finding_counts[FINDING_BLOCK] > 0:
        trust_status = TRUST_QUARANTINED
    elif finding_counts[FINDING_REVIEW] > 0:
        trust_status = TRUST_REVIEW_REQUIRED
    else:
        trust_status = TRUST_ELIGIBLE
    identity = {
        "name": safe_identifier(package.get("name")),
        "display_name": safe_identifier(package.get("display_name")),
        "version": safe_identifier(package.get("version")),
        "marketplace": safe_identifier(package.get("marketplace")),
        "package_class": package.get("package_class"),
        "expert_type": package.get("expert_type") or None,
        "availability": package.get("availability"),
    }
    return {
        "policy_version": TRUST_POLICY_VERSION,
        "trust_status": trust_status,
        "package": identity,
        "content_digest": f"sha256:{hasher.hexdigest()}" if scan_complete else None,
        "scan_complete": scan_complete,
        "scan": {
            "status": "complete" if scan_complete else "incomplete",
            "files_scanned": files_scanned,
            "bytes_scanned": total_bytes,
            "limits": {
                "max_files": MAX_AUDIT_FILES,
                "max_directory_entries": MAX_AUDIT_DIRECTORY_ENTRIES,
                "max_depth": MAX_AUDIT_DEPTH,
                "max_single_file_bytes": MAX_AUDIT_FILE_BYTES,
                "max_total_bytes": MAX_AUDIT_TOTAL_BYTES,
            },
            "incomplete_reasons": state["incomplete_reasons"],
        },
        "finding_counts": finding_counts,
        "findings": state["findings"],
        "findings_truncated": state["finding_total"] > len(state["findings"]),
        "recovery_action": _trust_recovery_action(trust_status),
        "read_only": True,
    }


def trust_summary(report: dict[str, Any], *, include_findings: bool = False) -> dict[str, Any]:
    keys = (
        "policy_version",
        "trust_status",
        "content_digest",
        "scan_complete",
        "finding_counts",
        "recovery_action",
    )
    summary = {key: report.get(key) for key in keys}
    if include_findings:
        summary["scan"] = report.get("scan", {})
        summary["findings"] = report.get("findings", [])
        summary["findings_truncated"] = bool(report.get("findings_truncated"))
    return summary


def package_trust(package: dict[str, Any]) -> dict[str, Any]:
    report = package.get("_trust_audit")
    if not isinstance(report, dict):
        report = audit_package(package)
        package["_trust_audit"] = report
    return report


def trust_rank(trust_status: str) -> int:
    return {
        TRUST_ELIGIBLE: 0,
        TRUST_UNKNOWN: 1,
        TRUST_REVIEW_REQUIRED: 2,
        TRUST_QUARANTINED: 3,
    }.get(trust_status, 3)


def most_restrictive_trust(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if not reports:
        return unknown_trust_report()
    return max(reports, key=lambda report: trust_rank(str(report.get("trust_status") or "")))


def oversized_manifest_package(manifest_path: Path) -> dict[str, Any]:
    """Represent an oversized manifest without reading its body into memory."""
    package_root = manifest_path.parent.parent.resolve()
    agents, path_warnings = agent_paths(package_root, {})
    path_warnings.append("manifest-json-too-large")
    package = {
        "name": package_root.name,
        "folder": package_root.name,
        "marketplace": marketplace_name(package_root),
        "package_class": AGENT_PACKAGE,
        "kind": "agent" if len(agents) <= 1 else "team",
        "kind_source": "bounded-fallback-agent-count",
        "expert_type": "",
        "version": "",
        "display_name": package_root.name,
        "profession": "",
        "description": "",
        "category_id": "",
        "agent_name": "",
        "lead_agent": "",
        "lead_path": "",
        "agent_paths": [str(path) for path in agents],
        "agent_count": len(agents),
        "availability": INSTALLED if agents else INSTALLED_UNUSABLE,
        "member_count": 0,
        "manifest_path": str(manifest_path.resolve()),
        "package_root": str(package_root),
        "warnings": path_warnings,
        "_manifest": {},
    }
    package["_trust_audit"] = audit_package(package)
    return package


def build_package(manifest_path: Path) -> dict[str, Any] | None:
    try:
        data = read_json(manifest_path, max_bytes=MAX_MANIFEST_JSON_BYTES)
    except BridgeError as exc:
        if exc.code == "json_too_large":
            return oversized_manifest_package(manifest_path)
        raise
    if not isinstance(data, dict):
        raise BridgeError(f"Manifest root must be an object: {manifest_path}", code="invalid_manifest")

    package_root = manifest_path.parent.parent.resolve()
    agents, path_warnings = agent_paths(package_root, data)
    declared_expert_type = data.get("expertType")
    if declared_expert_type in {"agent", "team"}:
        package_class = DECLARED_EXPERT
        kind = declared_expert_type
        kind_source = "manifest.expertType"
    elif agents:
        package_class = AGENT_PACKAGE
        kind = "agent" if len(agents) == 1 else "team"
        kind_source = "readable-agent-count"
        if declared_expert_type not in {None, ""}:
            path_warnings.append(
                f"Unsupported expertType {declared_expert_type!r}; classified as an agent-bearing package."
            )
    else:
        return None

    name_value = data.get("name")
    name = name_value.strip() if isinstance(name_value, str) and name_value.strip() else package_root.name
    display_name = localized(data.get("displayName"), name)
    profession = localized(data.get("profession"), display_name)
    description = localized(data.get("displayDescription")) or localized(data.get("description"))

    team_info = data.get("teamInfo") if isinstance(data.get("teamInfo"), dict) else {}
    lead_name = team_info.get("leadAgent") or data.get("agentName")
    lead_path = None
    if isinstance(lead_name, str):
        for path in agents:
            if path.stem.casefold() == lead_name.casefold():
                lead_path = path
                break

    raw_members = data.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raw_members = team_info.get("memberAgents")
    member_count = len(raw_members) if isinstance(raw_members, list) else 0

    package = {
        "name": name,
        "folder": package_root.name,
        "marketplace": marketplace_name(package_root),
        "package_class": package_class,
        "kind": kind,
        "kind_source": kind_source,
        "expert_type": declared_expert_type if declared_expert_type in {"agent", "team"} else "",
        "version": str(data.get("version") or ""),
        "display_name": display_name,
        "profession": profession,
        "description": description,
        "category_id": str(data.get("categoryId") or ""),
        "agent_name": str(data.get("agentName") or ""),
        "lead_agent": str(lead_name or ""),
        "lead_path": str(lead_path) if lead_path else "",
        "agent_paths": [str(path) for path in agents],
        "agent_count": len(agents),
        "availability": INSTALLED if agents else INSTALLED_UNUSABLE,
        "member_count": member_count,
        "manifest_path": str(manifest_path.resolve()),
        "package_root": str(package_root),
        "warnings": path_warnings,
        "_manifest": data,
    }
    package["_trust_audit"] = audit_package(package)
    return package


def discover_packages(roots: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    packages: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_manifests: set[str] = set()

    for root in roots:
        for manifest_path in manifest_paths_for_root(root):
            key = os.path.normcase(str(manifest_path))
            if key in seen_manifests:
                continue
            seen_manifests.add(key)
            try:
                package = build_package(manifest_path)
            except BridgeError as exc:
                warnings.append(str(exc))
                continue
            if package is not None:
                packages.append(package)

    packages.sort(key=lambda item: (item["name"].casefold(), item["marketplace"].casefold()))
    return packages, warnings


def existing_roots(explicit_root: str | None) -> list[Path]:
    candidates = source_candidates(explicit_root)
    existing = [path for path in candidates if path.exists()]
    if not existing:
        checked = ", ".join(str(path) for path in candidates)
        raise BridgeError(
            f"No readable WorkBuddy source was found. Checked: {checked}",
            code="source_not_found",
        )
    return existing


def cache_manifests_for_roots(roots: list[Path]) -> list[Path]:
    results: list[Path] = []
    for root in roots:
        candidates = [root]
        candidates.extend(list(root.parents)[:6])
        for candidate in candidates:
            manifest = candidate / "app" / "cache" / "experts" / "manifest.json"
            if manifest.is_file():
                resolved = resolved_path_within(candidate, manifest)
                if resolved is not None:
                    results.append(resolved)
    return unique_paths(results)


def runtime_team_roots_for_roots(roots: list[Path]) -> list[Path]:
    results: list[Path] = []
    for root in roots:
        candidates = [root]
        candidates.extend(list(root.parents)[:6])
        for candidate in candidates:
            teams_root = candidate / "teams"
            if teams_root.is_dir():
                resolved = resolved_path_within(candidate, teams_root)
                if resolved is not None:
                    results.append(resolved)
    return unique_paths(results)


def load_runtime_teams(roots: list[Path]) -> tuple[list[dict[str, Any]], list[str]]:
    """Read only non-sensitive runtime-team summary fields."""
    teams: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for teams_root in runtime_team_roots_for_roots(roots):
        for team_dir in child_directories(teams_root):
            config_path = team_dir / "config.json"
            if not config_path.is_file():
                continue
            safe_config = resolved_path_within(teams_root, config_path)
            if safe_config is None:
                warnings.append(f"Runtime team config escapes teams root: {config_path}")
                continue
            key = os.path.normcase(str(safe_config))
            if key in seen:
                continue
            seen.add(key)
            try:
                data = read_json(safe_config, max_bytes=MAX_RUNTIME_JSON_BYTES)
            except BridgeError as exc:
                warnings.append(str(exc))
                continue
            if not isinstance(data, dict):
                warnings.append(f"Runtime team config root must be an object: {config_path}")
                continue
            members = data.get("members") if isinstance(data.get("members"), list) else []
            teams.append(
                {
                    "name": str(data.get("name") or team_dir.name),
                    "description": localized(data.get("description")),
                    "member_count": len(members),
                    "classification": "runtime-team",
                    "reusable_package": False,
                    "config_path": str(safe_config),
                }
            )
    teams.sort(key=lambda item: item["name"].casefold())
    return teams, warnings


def load_catalog(roots: list[Path], installed: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    installed_keys: dict[str, list[dict[str, Any]]] = {}
    for package in installed:
        for value in (package["name"], package["folder"], package["agent_name"]):
            if value:
                bucket = installed_keys.setdefault(value.casefold(), [])
                if package not in bucket:
                    bucket.append(package)

    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    linked_manifests: set[str] = set()
    known_categories: dict[str, dict[str, Any]] = {}
    for path in cache_manifests_for_roots(roots):
        try:
            data = read_json(path, max_bytes=MAX_CATALOG_JSON_BYTES)
        except BridgeError as exc:
            warnings.append(str(exc))
            continue
        experts = data.get("experts") if isinstance(data, dict) else None
        if not isinstance(experts, list):
            warnings.append(f"Catalog does not contain an experts array: {path}")
            continue
        category_map: dict[str, dict[str, Any]] = {}
        categories = data.get("categories") if isinstance(data, dict) else None
        if isinstance(categories, list):
            for category in categories:
                if not isinstance(category, dict):
                    continue
                category_id = str(category.get("id") or "").strip()
                if not category_id:
                    continue
                category_map[category_id] = {
                    "name": localized(category.get("name"), category_id),
                    "description": localized(category.get("description")),
                    "search_name": " ".join(localized_values(category.get("name"))),
                    "search_description": " ".join(localized_values(category.get("description"))),
                }
                known_categories[category_id] = category_map[category_id]
        for entry in experts:
            if not isinstance(entry, dict):
                continue
            identifier = str(entry.get("id") or entry.get("plugin") or entry.get("agentName") or "").strip()
            if not identifier:
                continue
            dedupe_key = identifier.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            aliases = {
                identifier.casefold(),
                str(entry.get("plugin") or "").casefold(),
                str(entry.get("agentName") or "").casefold(),
            }
            local_matches: list[dict[str, Any]] = []
            local_seen: set[str] = set()
            for alias in aliases:
                for package in installed_keys.get(alias, []):
                    key = os.path.normcase(str(package["manifest_path"]))
                    if key not in local_seen:
                        local_seen.add(key)
                        local_matches.append(package)
            local_classes = sorted({package["package_class"] for package in local_matches})
            local_roots = sorted({package["package_root"] for package in local_matches})
            usable_local_matches = [package for package in local_matches if package["agent_count"] > 0]
            local_trust = most_restrictive_trust(
                [package_trust(package) for package in local_matches]
            ) if local_matches else unknown_trust_report(
                {
                    "name": safe_identifier(identifier),
                    "display_name": safe_identifier(localized(entry.get("displayName"), identifier)),
                    "version": "",
                    "marketplace": "catalog",
                    "package_class": "metadata-only",
                    "expert_type": str(entry.get("expertType") or "") or None,
                    "availability": METADATA_ONLY,
                }
            )
            linked_manifests.update(
                os.path.normcase(str(package["manifest_path"])) for package in local_matches
            )
            category_id = str(entry.get("categoryId") or "")
            category = category_map.get(category_id, {})
            tags, search_tags = localized_list(entry.get("tags"))
            display_name = localized(entry.get("displayName"), identifier)
            profession = localized(entry.get("profession"))
            description = localized(entry.get("description"))
            use_count = exact_number(entry.get("useCount"))
            if use_count is None:
                use_count = exact_number(entry.get("use_count"))
            reco_rank = exact_number(entry.get("recoRank"))
            if reco_rank is None:
                reco_rank = exact_number(entry.get("reco_rank"))
            display_position = exact_number(entry.get("displayPosition"))
            published_at = str(entry.get("publishedAt") or entry.get("published_at") or "")
            if entry.get("publishedAt"):
                latest_field = "publishedAt"
            elif entry.get("published_at"):
                latest_field = "published_at"
            else:
                latest_field = "createdAt"
            created_at = str(entry.get("createdAt") or "")
            latest_value = published_at or created_at
            items.append(
                {
                    "id": identifier,
                    "plugin": str(entry.get("plugin") or ""),
                    "agent_name": str(entry.get("agentName") or ""),
                    "expert_type": str(entry.get("expertType") or ""),
                    "display_name": display_name,
                    "profession": profession,
                    "description": description,
                    "category_id": category_id,
                    "category_name": str(category.get("name") or category_id),
                    "category_description": str(category.get("description") or ""),
                    "tags": tags,
                    "created_at": created_at,
                    "updated_at": str(entry.get("updatedAt") or ""),
                    "latest_value": latest_value,
                    "latest_field": latest_field if latest_value else "",
                    "latest_source": str(path) if latest_value else "",
                    "use_count": use_count,
                    "use_count_source": str(path) if use_count is not None else "",
                    "reco_rank": reco_rank,
                    "reco_rank_source": str(path) if reco_rank is not None else "",
                    "display_position": display_position,
                    "prompt_file": str(entry.get("promptFile") or ""),
                    "availability": (
                        INSTALLED
                        if usable_local_matches
                        else INSTALLED_UNUSABLE
                        if local_matches
                        else METADATA_ONLY
                    ),
                    "trust_status": local_trust["trust_status"],
                    "local_package_classes": local_classes,
                    "local_package_roots": local_roots,
                    "catalog_path": str(path),
                    "_trust_audit": local_trust,
                    "_search_fields": {
                        "display_name": " ".join(localized_values(entry.get("displayName"))) or display_name,
                        "profession": " ".join(localized_values(entry.get("profession"))) or profession,
                        "description": " ".join(localized_values(entry.get("description"))) or description,
                        "tags": " ".join(search_tags),
                        "category_name": str(category.get("search_name") or category_id),
                        "category_description": str(category.get("search_description") or ""),
                    },
                }
            )

    for package in installed:
        manifest_key = os.path.normcase(str(package["manifest_path"]))
        if manifest_key in linked_manifests:
            continue
        identifier = str(package.get("name") or package.get("folder") or "local-package")
        base_identifier = identifier
        suffix = 1
        while identifier.casefold() in seen:
            suffix += 1
            identifier = f"{base_identifier}@{package['marketplace']}-{suffix}"
        seen.add(identifier.casefold())
        manifest = package.get("_manifest") if isinstance(package.get("_manifest"), dict) else {}
        tags, search_tags = localized_list(manifest.get("tags"))
        category_id = str(package.get("category_id") or "")
        category = known_categories.get(category_id, {})
        expert_type = (
            str(package.get("expert_type") or "")
            if package["package_class"] == DECLARED_EXPERT
            else ""
        )
        local_trust = package_trust(package)
        items.append(
            {
                "id": identifier,
                "plugin": str(package.get("name") or ""),
                "agent_name": str(package.get("agent_name") or ""),
                "expert_type": expert_type,
                "expert_type_source": (
                    "manifest.expertType"
                    if package["package_class"] == DECLARED_EXPERT
                    else "undeclared (plugin package without manifest.expertType)"
                ),
                "object_class": package["package_class"],
                "formal_expert": package["package_class"] == DECLARED_EXPERT,
                "display_name": str(package.get("display_name") or identifier),
                "profession": str(package.get("profession") or ""),
                "description": str(package.get("description") or ""),
                "category_id": category_id,
                "category_name": str(category.get("name") or category_id),
                "category_description": str(category.get("description") or ""),
                "tags": tags,
                "created_at": "",
                "updated_at": "",
                "latest_value": "",
                "latest_field": "",
                "latest_source": "",
                "use_count": None,
                "use_count_source": "",
                "reco_rank": None,
                "reco_rank_source": "",
                "display_position": None,
                "prompt_file": "",
                "availability": package["availability"],
                "trust_status": local_trust["trust_status"],
                "local_package_classes": [package["package_class"]],
                "local_package_roots": [package["package_root"]],
                "catalog_path": "",
                "_trust_audit": local_trust,
                "_search_fields": {
                    "display_name": str(package.get("display_name") or identifier),
                    "profession": str(package.get("profession") or ""),
                    "description": str(package.get("description") or ""),
                    "tags": " ".join(search_tags),
                    "category_name": str(category.get("search_name") or category_id),
                    "category_description": str(category.get("search_description") or ""),
                },
            }
        )
    items.sort(key=lambda item: item["id"].casefold())
    return items, warnings


def package_summary(package: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "folder",
        "marketplace",
        "package_class",
        "kind",
        "kind_source",
        "expert_type",
        "version",
        "display_name",
        "profession",
        "description",
        "category_id",
        "agent_name",
        "lead_agent",
        "agent_count",
        "availability",
        "member_count",
    )
    summary = {key: package.get(key) for key in keys}
    for key in (
        "name",
        "folder",
        "marketplace",
        "version",
        "display_name",
        "profession",
        "description",
        "category_id",
        "agent_name",
        "lead_agent",
    ):
        summary[key] = sanitize_untrusted_text(summary.get(key))
    summary["trust"] = trust_summary(package_trust(package))
    summary["trust_status"] = summary["trust"]["trust_status"]
    return summary


def catalog_summary(item: dict[str, Any]) -> dict[str, Any]:
    hidden = {
        "prompt_file",
        "local_package_roots",
        "catalog_path",
        "latest_source",
        "use_count_source",
        "reco_rank_source",
    }
    summary = {
        key: value
        for key, value in item.items()
        if not key.startswith("_") and key not in hidden
    }
    for key in (
        "id",
        "plugin",
        "agent_name",
        "display_name",
        "profession",
        "description",
        "category_id",
        "category_name",
        "category_description",
        "created_at",
        "updated_at",
        "latest_value",
    ):
        summary[key] = sanitize_untrusted_text(summary.get(key))
    if summary.get("expert_type") not in {"agent", "team", ""}:
        summary["expert_type"] = "unknown"
    summary["tags"] = [
        sanitize_untrusted_text(tag)
        for tag in summary.get("tags", [])
        if isinstance(tag, str)
    ][:50]
    report = item.get("_trust_audit")
    if not isinstance(report, dict):
        report = unknown_trust_report()
    summary["trust"] = trust_summary(report)
    summary["trust_status"] = report["trust_status"]
    return summary


def compact_package_summary(package: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "name",
        "display_name",
        "package_class",
        "kind",
        "marketplace",
        "agent_count",
        "availability",
        "version",
    )
    summary = {key: package.get(key) for key in keys}
    for key in ("name", "display_name", "marketplace", "version"):
        summary[key] = sanitize_untrusted_text(summary.get(key))
    summary["trust"] = trust_summary(package_trust(package))
    summary["trust_status"] = summary["trust"]["trust_status"]
    return summary


def compact_runtime_team_summary(team: dict[str, Any]) -> dict[str, Any]:
    keys = ("name", "classification", "member_count", "reusable_package")
    summary = {key: team.get(key) for key in keys}
    summary["name"] = sanitize_untrusted_text(summary.get("name"))
    return summary


def matches_query(item: dict[str, Any], query: str) -> bool:
    needle = query.casefold()
    fields = (
        item.get("name"),
        item.get("folder"),
        item.get("display_name"),
        item.get("profession"),
        item.get("description"),
        item.get("id"),
        item.get("plugin"),
        item.get("agent_name"),
        item.get("category_id"),
        item.get("category_name"),
        item.get("category_description"),
        " ".join(item.get("tags") or []),
    )
    search_fields = item.get("_search_fields")
    extra_fields = search_fields.values() if isinstance(search_fields, dict) else ()
    return any(needle in str(value).casefold() for value in (*fields, *extra_fields) if value)


def normalize_match_text(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def extract_query_terms(query: str) -> list[str]:
    """Build deterministic English tokens and Chinese 2-6 character n-grams."""
    normalized = normalize_match_text(query)[:512]
    for phrase in sorted(CJK_STOPWORDS | {"专家或专家团", "专家和专家团", "专家/专家团"}, key=len, reverse=True):
        normalized = normalized.replace(phrase, " ")
    for particle in ("的", "并", "或", "请"):
        normalized = normalized.replace(particle, " ")
    terms: set[str] = set()
    for token in ASCII_TERM_RE.findall(normalized):
        cleaned = token.strip("._-/")
        if len(cleaned) >= 2 and cleaned not in ASCII_STOPWORDS:
            terms.add(cleaned)
    for sequence in CJK_SEQUENCE_RE.findall(normalized):
        max_size = min(6, len(sequence))
        for size in range(2, max_size + 1):
            for start in range(0, len(sequence) - size + 1):
                term = sequence[start : start + size]
                if (
                    term not in CJK_STOPWORDS
                    and "专家" not in term
                    and "家团" not in term
                    and "团队" not in term
                ):
                    terms.add(term)
    return sorted(terms, key=lambda term: (-len(term), term))


def maximal_matched_terms(terms: list[str], field_text: str, limit: int = 8) -> list[str]:
    haystack = normalize_match_text(field_text)
    if not haystack:
        return []
    selected: list[str] = []
    for term in terms:
        if term not in haystack:
            continue
        if any(term in existing for existing in selected):
            continue
        selected.append(term)
        if len(selected) >= limit:
            break
    return selected


def term_specificity_factor(term: str) -> float:
    if CJK_SEQUENCE_RE.fullmatch(term):
        return (len(term) / 2.0) ** 1.5
    return 1.0 + min(len(term), 8) / 8.0


def is_high_signal_recommend_term(term: str) -> bool:
    if CJK_SEQUENCE_RE.fullmatch(term):
        return len(term) >= 2 and term not in GENERIC_RECOMMEND_TERMS
    return len(term) >= 3 and term not in GENERIC_RECOMMEND_ASCII_TERMS


def infer_preferred_kind(query: str) -> str | None:
    normalized = normalize_match_text(query)
    if any(neutral in normalized for neutral in ("专家或专家团", "专家和专家团", "专家/专家团")):
        return None
    if any(hint in normalized for hint in TEAM_HINTS):
        return "team"
    if any(hint in normalized for hint in AGENT_HINTS):
        return "agent"
    return None


def iso_timestamp(value: Any) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return 0.0


def ranking_source_summary(
    catalog: list[dict[str, Any]],
    official_online_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    total = len(catalog)
    source_paths = ["local-cache"] if any(item.get("catalog_path") for item in catalog) else []
    hot_source_paths = sorted(
        {
            label
            for item in catalog
            if (label := public_source_label(item.get("use_count_source"))) is not None
        }
    )
    latest_source_paths = sorted(
        {
            label
            for item in catalog
            if (label := public_source_label(item.get("latest_source"))) is not None
        }
    )
    recommended_source_paths = sorted(
        {
            label
            for item in catalog
            if (label := public_source_label(item.get("reco_rank_source"))) is not None
        }
    )
    category_known = sum(bool(item.get("category_id") and item.get("category_name")) for item in catalog)
    hot_known = sum(exact_number(item.get("use_count")) is not None for item in catalog)
    latest_known = sum(bool(item.get("latest_value")) for item in catalog)
    recommended_known = sum(exact_number(item.get("reco_rank")) is not None for item in catalog)

    hot_available = total > 0 and hot_known == total
    latest_available = total > 0 and latest_known == total
    recommended_available = total > 0 and recommended_known == total
    category_available = total > 0 and category_known == total

    hot_unavailable_reason = (
        str(official_online_probe.get("unavailable_reason") or "")
        if official_online_probe
        else (
            "本地可读缓存没有完整 useCount；未调用 WorkBuddy API，也未用创建时间、"
            "displayPosition 或语义分数猜测热度。"
        )
    )
    comprehensive_unavailable_reason = (
        (
            "WorkBuddy 官方匿名在线探针没有获得覆盖全部候选的显式 reco_rank；"
            "未从名称、时间、热度或排序位置反推综合分。"
        )
        if official_online_probe
        else "本地可读缓存没有完整 reco_rank；未从名称、时间或热度反推综合排名。"
    )
    result = {
        "category": {
            "status": "available" if category_available else "unavailable",
            "local_fields": ["categories", "expert.categoryId"],
            "coverage": {"known": category_known, "total": total},
            "source_paths": source_paths,
        },
        "hot": {
            "status": "available" if hot_available else "unavailable",
            "workbuddy_sort_field": WORKBUDDY_HOT_SORT_FIELD,
            "workbuddy_metric": "useCount",
            "official_ranking_endpoint": WORKBUDDY_RANKING_ENDPOINT,
            "coverage": {"known": hot_known, "total": total},
            "source_paths": hot_source_paths,
            "display_position_semantics": "displayPosition pins operational positions but is not a popularity metric",
            "unavailable_reason": "" if hot_available else hot_unavailable_reason,
        },
        "latest": {
            "status": "available" if latest_available else "unavailable",
            "workbuddy_sort_field": WORKBUDDY_LATEST_SORT_FIELD,
            "local_fields": ["publishedAt", "createdAt"],
            "coverage": {"known": latest_known, "total": total},
            "source_paths": latest_source_paths,
            "scope": "可核验目录快照时间字段，不声称是实时服务端榜单。",
        },
        "comprehensive": {
            "status": "available" if recommended_available else "unavailable",
            "workbuddy_sort_field": WORKBUDDY_RECOMMENDED_SORT_FIELD,
            "coverage": {"known": recommended_known, "total": total},
            "source_paths": recommended_source_paths,
            "unavailable_reason": "" if recommended_available else comprehensive_unavailable_reason,
        },
    }
    if official_online_probe is not None:
        result["official_online"] = official_online_probe
    return result


def resolve_category_filter(catalog: list[dict[str, Any]], hint: str) -> set[str]:
    needle = normalize_match_text(hint)
    categories = {
        str(item.get("category_id") or ""): str(item.get("category_name") or "")
        for item in catalog
        if item.get("category_id")
    }
    exact = {
        category_id
        for category_id, name in categories.items()
        if needle in {normalize_match_text(category_id), normalize_match_text(name)}
    }
    if exact:
        return exact
    partial = {
        category_id
        for category_id, name in categories.items()
        if needle in normalize_match_text(category_id) or needle in normalize_match_text(name)
    }
    if partial:
        return partial
    raise BridgeError(f"Unknown WorkBuddy category: {hint}", code="category_not_found")


def score_catalog_item(
    item: dict[str, Any],
    request: str,
    terms: list[str],
    term_weights: dict[str, float],
    category_affinity: dict[str, float],
    preferred_kind: str | None,
) -> dict[str, Any]:
    search_fields = item.get("_search_fields") if isinstance(item.get("_search_fields"), dict) else {}
    fields = {
        "display_name": search_fields.get("display_name") or item.get("display_name"),
        "profession": search_fields.get("profession") or item.get("profession"),
        "tags": search_fields.get("tags") or " ".join(item.get("tags") or []),
        "category_name": search_fields.get("category_name") or item.get("category_name"),
        "category_description": search_fields.get("category_description") or item.get("category_description"),
        "description": search_fields.get("description") or item.get("description"),
        "id": item.get("id"),
        "plugin": item.get("plugin"),
        "agent_name": item.get("agent_name"),
    }
    field_evidence: list[dict[str, Any]] = []
    term_contributions: dict[str, list[float]] = {}
    for field, weight in RECOMMEND_FIELD_WEIGHTS.items():
        matched = maximal_matched_terms(terms, str(fields.get(field) or ""))
        if not matched:
            continue
        contribution = 0.0
        for term in matched:
            value = weight * term_specificity_factor(term) * term_weights.get(term, 1.0)
            contribution += value
            term_contributions.setdefault(term, []).append(value)
        field_evidence.append(
            {
                "field": field,
                "field_label": RECOMMEND_FIELD_LABELS[field],
                "matched_terms": matched,
                "score": round(contribution, 2),
            }
        )

    semantic_score = 0.0
    for contributions in term_contributions.values():
        ordered = sorted(contributions, reverse=True)
        semantic_score += ordered[0] + 0.2 * sum(ordered[1:])
    matched_concepts: list[str] = []
    for term in sorted(term_contributions, key=lambda value: (-len(value), value)):
        if not any(term in existing for existing in matched_concepts):
            matched_concepts.append(term)
    direct_fields = {
        "display_name",
        "profession",
        "tags",
        "description",
        "id",
        "plugin",
        "agent_name",
    }
    high_signal_terms = [term for term in matched_concepts if is_high_signal_recommend_term(term)]
    direct_high_signal_terms = sorted(
        {
            term
            for evidence in field_evidence
            if evidence["field"] in direct_fields
            for term in evidence["matched_terms"]
            if is_high_signal_recommend_term(term)
        },
        key=lambda term: (-len(term), term),
    )
    qualified = len(direct_high_signal_terms) >= 2 or (
        len(direct_high_signal_terms) == 1 and len(normalize_match_text(request)) <= 20
    )
    qualification_rule = "two direct high-signal terms, or one for a short focused request"
    coverage_factor = {0: 0.0, 1: 0.35, 2: 0.8}.get(len(matched_concepts), 1.0)
    semantic_score *= coverage_factor
    normalized_request = normalize_match_text(request)
    short_profile = normalize_match_text(f"{item.get('display_name', '')} {item.get('profession', '')}")
    scope_mismatches: list[str] = []
    for match in re.finditer(r"([\u3400-\u4dbf\u4e00-\u9fff]{2,6})行业", short_profile):
        scope = match.group(1)
        if scope not in normalized_request and scope not in scope_mismatches:
            scope_mismatches.append(scope)
    scope_factor = 0.65 if scope_mismatches else 1.0
    semantic_score *= scope_factor
    category_affinity_score = category_affinity.get(str(item.get("category_id") or ""), 0.0)
    category_bonus = min(category_affinity_score, 20.0)
    if not qualified and len(direct_high_signal_terms) == 1 and category_bonus >= 10.0:
        qualified = True
        qualification_rule = "one direct high-signal term supported by strong category affinity"
    kind_bonus = 10.0 if preferred_kind and item.get("expert_type") == preferred_kind else 0.0
    availability_bonus = 3.0 if item.get("availability") == "installed" else 0.0
    field_evidence.sort(key=lambda evidence: (-float(evidence["score"]), evidence["field"]))
    return {
        "semantic_score": round(semantic_score, 2),
        "category_affinity_bonus": round(category_bonus, 2),
        "kind_bonus": kind_bonus,
        "availability_bonus": availability_bonus,
        "total_score": round(semantic_score + category_bonus + kind_bonus + availability_bonus, 2),
        "matched_concept_count": len(matched_concepts),
        "coverage_factor": coverage_factor,
        "scope_factor": scope_factor,
        "unrequested_industry_scopes": scope_mismatches,
        "field_evidence": field_evidence,
        "matched_concepts": matched_concepts,
        "high_signal_matched_terms": high_signal_terms,
        "direct_high_signal_matched_terms": direct_high_signal_terms,
        "qualification": {
            "status": "qualified" if qualified else "weak-match",
            "rule": qualification_rule,
        },
    }


def query_term_weights(catalog: list[dict[str, Any]], terms: list[str]) -> dict[str, float]:
    """Down-weight generic request terms that occur across many catalog entries."""
    documents: list[str] = []
    for item in catalog:
        search_fields = item.get("_search_fields") if isinstance(item.get("_search_fields"), dict) else {}
        documents.append(
            normalize_match_text(
                " ".join(
                    [
                        str(item.get("id") or ""),
                        str(item.get("plugin") or ""),
                        str(item.get("agent_name") or ""),
                        *(str(value or "") for value in search_fields.values()),
                    ]
                )
            )
        )
    total = len(documents)
    if total == 0:
        return {term: 1.0 for term in terms}
    return {
        term: 1.0 + math.log((total + 1.0) / (1.0 + sum(term in document for document in documents)))
        for term in terms
    }


def category_affinity_scores(
    catalog: list[dict[str, Any]],
    terms: list[str],
    term_weights: dict[str, float],
) -> dict[str, float]:
    """Score each WorkBuddy category from its real name and description metadata."""
    categories: dict[str, tuple[str, str]] = {}
    for item in catalog:
        category_id = str(item.get("category_id") or "")
        if not category_id or category_id in categories:
            continue
        search_fields = item.get("_search_fields") if isinstance(item.get("_search_fields"), dict) else {}
        categories[category_id] = (
            str(search_fields.get("category_name") or item.get("category_name") or ""),
            str(search_fields.get("category_description") or item.get("category_description") or ""),
        )
    raw_scores: dict[str, float] = {}
    for category_id, (name, description) in categories.items():
        score = 0.0
        for field_text, weight in ((name, 6.0), (description, 3.0)):
            for term in maximal_matched_terms(terms, field_text, limit=10):
                score += weight * term_specificity_factor(term) * term_weights.get(term, 1.0)
        raw_scores[category_id] = score
    maximum = max(raw_scores.values(), default=0.0)
    if maximum <= 0:
        return {category_id: 0.0 for category_id in raw_scores}
    return {category_id: 20.0 * score / maximum for category_id, score in raw_scores.items()}


def recommendation_reasons(
    item: dict[str, Any],
    score: dict[str, Any],
    preferred_kind: str | None,
) -> list[str]:
    reasons: list[str] = []
    evidence = score["field_evidence"]
    if evidence:
        strongest = evidence[:2]
        labels = "、".join(entry["field_label"] for entry in strongest)
        terms: list[str] = []
        for entry in strongest:
            for term in entry["matched_terms"]:
                if term not in terms:
                    terms.append(term)
        reasons.append(f"需求词“{'、'.join(terms[:5])}”命中其{labels}。")
    category_name = sanitize_untrusted_text(
        str(item.get("category_name") or item.get("category_id") or "未分类")
    )
    reasons.append(f"归属 WorkBuddy“{category_name}”分类。")
    if preferred_kind and item.get("expert_type") == preferred_kind:
        label = "专家团" if preferred_kind == "team" else "单专家"
        reasons.append(f"需求体现了{label}偏好，候选类型一致。")
    return reasons


def public_source_label(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme == "https" and (parsed.hostname or "").casefold() in WORKBUDDY_OFFICIAL_HOSTS:
        return value
    return "local-cache"


def recommend_catalog(
    catalog: list[dict[str, Any]],
    request: str,
    *,
    kind: str,
    availability: str,
    category: str,
    limit: int,
    trust: str = TRUST_ELIGIBLE,
    official_online_probe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if trust != "all" and trust not in TRUST_STATUSES:
        raise BridgeError(f"Unsupported trust filter: {trust}", code="invalid_trust_filter")
    trust_pool = (
        list(catalog)
        if trust == "all"
        else [item for item in catalog if item.get("trust_status") == trust]
    )
    excluded_by_trust = len(catalog) - len(trust_pool)
    terms = extract_query_terms(request)
    term_weights = query_term_weights(trust_pool, terms)
    category_affinity = category_affinity_scores(trust_pool, terms, term_weights)
    preferred_kind = infer_preferred_kind(request) if kind in {"auto", "all"} else kind
    filtered = [item for item in trust_pool if item.get("availability") != INSTALLED_UNUSABLE]
    if kind in {"agent", "team"}:
        filtered = [item for item in filtered if item.get("expert_type") == kind]
    elif kind == "auto" and preferred_kind:
        filtered = [item for item in filtered if item.get("expert_type") == preferred_kind]
    if availability != "all":
        filtered = [item for item in filtered if item.get("availability") == availability]
    category_ids: set[str] = set()
    if category:
        category_ids = resolve_category_filter(trust_pool, category)
        filtered = [item for item in filtered if item.get("category_id") in category_ids]

    ranking_sources = ranking_source_summary(trust_pool, official_online_probe)
    scored: list[dict[str, Any]] = []
    raw_matched_count = 0
    for item in filtered:
        score = score_catalog_item(
            item,
            request,
            terms,
            term_weights,
            category_affinity,
            preferred_kind,
        )
        if score["semantic_score"] <= 0:
            continue
        raw_matched_count += 1
        if category:
            score["qualification"]["status"] = "qualified"
            score["qualification"]["rule"] = "explicit category filter plus semantic match"
        if score["qualification"]["status"] != "qualified":
            continue
        scored.append({"item": item, "score": score})

    scored.sort(key=lambda record: str(record["item"].get("id") or "").casefold())
    hot_available = ranking_sources["hot"]["status"] == "available"
    latest_available = ranking_sources["latest"]["status"] == "available"
    scored.sort(
        key=lambda record: (
            float(record["score"]["total_score"]),
            float(record["item"].get("use_count") or 0) if hot_available else 0.0,
            iso_timestamp(record["item"].get("latest_value")) if latest_available else 0.0,
        ),
        reverse=True,
    )

    safe_limit = min(max(limit, 0), MAX_RECOMMEND_LIMIT)
    recommendations: list[dict[str, Any]] = []
    for rank, record in enumerate(scored[:safe_limit], start=1):
        item = record["item"]
        score = record["score"]
        safe_score = dict(score)
        safe_score["unrequested_industry_scopes"] = [
            sanitize_untrusted_text(value, limit=40)
            for value in score.get("unrequested_industry_scopes", [])
            if isinstance(value, str)
        ][:20]
        item_trust = item.get("_trust_audit")
        if not isinstance(item_trust, dict):
            item_trust = unknown_trust_report()
        hot_status = ranking_sources["hot"]["status"]
        latest_status = "available" if item.get("latest_value") else "unavailable"
        comprehensive_status = ranking_sources["comprehensive"]["status"]
        recommendations.append(
            {
                "rank": rank,
                "id": safe_identifier(item["id"]),
                "display_name": sanitize_untrusted_text(item["display_name"]),
                "profession": sanitize_untrusted_text(item["profession"]),
                "category": {
                    "id": safe_identifier(item["category_id"]),
                    "name": sanitize_untrusted_text(item["category_name"]),
                },
                "expert_type": item["expert_type"] if item.get("expert_type") in {"agent", "team"} else ("undeclared" if item.get("object_class") == AGENT_PACKAGE else "unknown"),
                "availability": item["availability"],
                "availability_evidence": {
                    "local_package_classes": [
                        value
                        for value in item.get("local_package_classes", [])
                        if value in {DECLARED_EXPERT, AGENT_PACKAGE}
                    ],
                    "local_package_count": len(item.get("local_package_roots") or []),
                    "catalog_source": "local-cache" if item.get("catalog_path") else "local-package",
                },
                "object_class": item.get("object_class") or (
                    item["local_package_classes"][0]
                    if len(item["local_package_classes"]) == 1
                    else "catalog-expert"
                ),
                "formal_expert": item.get("formal_expert", True),
                "expert_type_source": item.get("expert_type_source") or "catalog.expertType",
                "trust": trust_summary(item_trust),
                "recommendation_reasons": recommendation_reasons(item, score, preferred_kind),
                "ranking_evidence": {
                    "relevance": safe_score,
                    "category": {
                        "status": "available" if item.get("category_id") else "unavailable",
                        "id": safe_identifier(item.get("category_id")),
                        "name": sanitize_untrusted_text(item.get("category_name")),
                        "source": (
                            "expert.categoryId joined to local cache categories"
                            if item.get("catalog_path")
                            else "local package manifest categoryId"
                            if item.get("category_id")
                            else None
                        ),
                    },
                    "hot": {
                        "status": hot_status,
                        "use_count": item.get("use_count") if hot_status == "available" else None,
                        "display_position": item.get("display_position"),
                        "source": public_source_label(item.get("use_count_source")) if hot_status == "available" else None,
                        "official_ranking_endpoint": WORKBUDDY_RANKING_ENDPOINT,
                        "unavailable_reason": ranking_sources["hot"]["unavailable_reason"],
                    },
                    "latest": {
                        "status": latest_status,
                        "value": sanitize_untrusted_text(item.get("latest_value"), limit=80) or None,
                        "local_field": item.get("latest_field") or None,
                        "workbuddy_sort_field": WORKBUDDY_LATEST_SORT_FIELD,
                        "source": public_source_label(item.get("latest_source")) if latest_status == "available" else None,
                    },
                    "comprehensive": {
                        "status": comprehensive_status,
                        "reco_rank": item.get("reco_rank") if comprehensive_status == "available" else None,
                        "source": public_source_label(item.get("reco_rank_source")) if comprehensive_status == "available" else None,
                        "unavailable_reason": ranking_sources["comprehensive"]["unavailable_reason"],
                    },
                },
                "next_action": (
                    f"resolve {safe_identifier(item['id'])} and inspect the installed package"
                    if item["availability"] == "installed" and item_trust["trust_status"] == TRUST_ELIGIBLE
                    else f"audit {safe_identifier(item['id'])} before any package-content use"
                ),
            }
        )

    matched_terms: list[str] = []
    for recommendation in recommendations:
        for evidence in recommendation["ranking_evidence"]["relevance"]["field_evidence"]:
            for term in evidence["matched_terms"]:
                if term not in matched_terms:
                    matched_terms.append(term)
    returned_terms = matched_terms[:40]
    payload = {
        "status": "ok" if recommendations else "no-match",
        "request": request,
        "filters": {
            "kind": kind,
            "inferred_kind_preference": preferred_kind,
            "availability": availability,
            "category": category,
            "trust": trust,
            "resolved_category_ids": sorted(safe_identifier(value) for value in category_ids),
        },
        "query_evidence": {
            "term_count": len(terms),
            "returned_terms": returned_terms,
            "matched_terms_returned": len(returned_terms),
            "matched_terms_truncated": len(matched_terms) > len(returned_terms),
            "strategy": "English tokens plus Chinese 2-6 character n-grams; stop words excluded",
        },
        "candidate_count": len(filtered),
        "excluded_by_trust_count": excluded_by_trust,
        "matched_candidate_count": len(scored),
        "raw_matched_candidate_count": raw_matched_count,
        "qualified_candidate_count": len(scored),
        "rejected_weak_match_count": raw_matched_count - len(scored),
        "no_match_reason": (
            "No candidate had a direct high-signal requirement match; weak generic matches were not used to fill Top 3."
            if not recommendations
            else ""
        ),
        "returned": len(recommendations),
        "requested_top": safe_limit,
        "recommendations": recommendations,
        "ranking_policy": {
            "primary": "natural-language metadata relevance",
            "bonuses": [
                "WorkBuddy category affinity",
                "explicit or inferred expert type",
                "installed local package",
            ],
            "tie_breakers": [
                "WorkBuddy useCount when complete verified evidence is available",
                "cached publishedAt/createdAt",
                "stable expert id",
            ],
            "hot_tiebreak_used": hot_available,
            "latest_tiebreak_used": latest_available,
        },
        "ranking_sources": ranking_sources,
        "read_only": True,
    }
    return project_public_payload(payload)


def select_package(
    packages: list[dict[str, Any]], query: str, marketplace: str | None
) -> dict[str, Any]:
    candidates = packages
    if marketplace:
        candidates = [item for item in candidates if item["marketplace"].casefold() == marketplace.casefold()]

    exact = [
        item
        for item in candidates
        if query.casefold()
        in {
            item["name"].casefold(),
            item["folder"].casefold(),
            item["display_name"].casefold(),
        }
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        declared = [item for item in exact if item["package_class"] == DECLARED_EXPERT]
        if len(declared) == 1:
            return declared[0]
        options = ", ".join(
            f"{safe_identifier(item.get('marketplace'), limit=40)}:"
            f"{safe_identifier(item.get('name'), limit=80)}"
            for item in exact[:20]
        )
        raise BridgeError(f"Expert name is ambiguous: {options}", code="ambiguous_expert")

    partial = [item for item in candidates if matches_query(item, query)]
    if len(partial) == 1:
        return partial[0]
    declared = [item for item in partial if item["package_class"] == DECLARED_EXPERT]
    if len(declared) == 1:
        return declared[0]
    if not partial:
        raise BridgeError(
            f"No installed expert or agent package matches: {query}",
            code="expert_not_found",
        )
    options = ", ".join(
        f"{safe_identifier(item.get('marketplace'), limit=40)}:"
        f"{safe_identifier(item.get('name'), limit=80)}"
        for item in partial[:20]
    )
    raise BridgeError(f"Expert query is ambiguous: {options}", code="ambiguous_expert")


def select_catalog_item(items: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    needle = query.casefold()
    exact = [
        item
        for item in items
        if needle
        in {
            str(item.get("id") or "").casefold(),
            str(item.get("plugin") or "").casefold(),
            str(item.get("agent_name") or "").casefold(),
            str(item.get("display_name") or "").casefold(),
        }
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        options = ", ".join(safe_identifier(item.get("id"), limit=100) for item in exact[:20])
        raise BridgeError(f"Catalog query is ambiguous: {options}", code="ambiguous_expert")

    partial = [item for item in items if matches_query(item, query)]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        return None
    options = ", ".join(safe_identifier(item.get("id"), limit=100) for item in partial[:20])
    raise BridgeError(f"Catalog query is ambiguous: {options}", code="ambiguous_expert")


def packages_for_catalog_item(
    packages: list[dict[str, Any]], catalog_item: dict[str, Any]
) -> list[dict[str, Any]]:
    aliases = {
        str(catalog_item.get("id") or "").casefold(),
        str(catalog_item.get("plugin") or "").casefold(),
        str(catalog_item.get("agent_name") or "").casefold(),
    }
    aliases.discard("")
    matches: list[dict[str, Any]] = []
    for package in packages:
        package_aliases = {
            str(package.get("name") or "").casefold(),
            str(package.get("folder") or "").casefold(),
            str(package.get("agent_name") or "").casefold(),
        }
        if aliases & package_aliases:
            matches.append(package)
    matches.sort(
        key=lambda item: (
            item["package_class"] != DECLARED_EXPERT,
            item["marketplace"].casefold(),
            item["name"].casefold(),
        )
    )
    return matches


def bounded_section(items: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    safe_limit = max(limit, 0)
    returned = items[:safe_limit]
    return {
        "total": len(items),
        "returned": len(returned),
        "truncated": len(returned) < len(items),
        "items": returned,
    }


def relative_package_path(package_root: Path, value: Any) -> str:
    if not isinstance(value, (str, Path)) or not str(value):
        return ""
    path = Path(value)
    try:
        return path.relative_to(package_root).as_posix()
    except ValueError:
        return "[outside-package-root]"


def project_members(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed_string_keys = ("id", "name", "agent", "agentName", "kind")
    allowed_boolean_keys = ("required", "optional")
    result: list[dict[str, Any]] = []
    for item in value[:100]:
        if isinstance(item, str):
            result.append({"id": safe_identifier(item)})
            continue
        if not isinstance(item, dict):
            continue
        projected: dict[str, Any] = {}
        for key in allowed_string_keys:
            if isinstance(item.get(key), str):
                projected[key] = safe_identifier(item[key])
        for key in allowed_boolean_keys:
            if isinstance(item.get(key), bool):
                projected[key] = item[key]
        if projected:
            result.append(projected)
    return result


def project_dependencies(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    result: list[dict[str, Any]] = []
    for raw_name in sorted(value, key=lambda item: str(item).casefold())[:100]:
        name = safe_identifier(str(raw_name))
        raw_value = value[raw_name]
        projected: dict[str, Any] = {"name": name}
        if isinstance(raw_value, str):
            projected["constraint"] = safe_identifier(raw_value)
        elif isinstance(raw_value, list):
            identifiers = [safe_identifier(item) for item in raw_value if isinstance(item, str)]
            projected["entry_count"] = len(raw_value)
            projected["identifiers"] = identifiers[:50]
        elif isinstance(raw_value, dict):
            projected["entry_count"] = len(raw_value)
            projected["identifiers"] = [
                safe_identifier(str(item))
                for item in sorted(raw_value, key=lambda item: str(item).casefold())[:50]
            ]
        elif isinstance(raw_value, (bool, int, float)):
            projected["value"] = raw_value
        else:
            projected["value_type"] = type(raw_value).__name__
        result.append(projected)
    return result


def project_connector_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [safe_identifier(item) for item in value if isinstance(item, str)][:100]


def inspect_package(package: dict[str, Any]) -> dict[str, Any]:
    manifest = package["_manifest"]
    package_root = Path(package["package_root"])
    skills, skill_warnings = skill_paths(package_root, manifest)
    warnings = list(package["warnings"]) + skill_warnings

    executable_suffixes = {".exe", ".dll", ".so", ".dylib", ".ps1", ".bat", ".cmd", ".sh"}
    executable_files: list[str] = []
    executable_entries_seen = 0
    for directory_name in ("scripts", "bin", "hooks"):
        directory = package_root / directory_name
        if not directory.is_dir():
            continue
        safe_directory, directory_error = safe_discovered_package_path(
            package_root,
            directory,
            label=f"Discovered {directory_name} directory",
        )
        if directory_error or safe_directory is None:
            warnings.append(directory_error or f"Unsafe directory: {directory}")
            continue
        try:
            for path in safe_directory.rglob("*"):
                executable_entries_seen += 1
                if executable_entries_seen > MAX_AUDIT_DIRECTORY_ENTRIES:
                    warnings.append("Executable inventory exceeded the bounded directory-entry budget.")
                    break
                safe_path, path_error = safe_discovered_package_path(
                    package_root,
                    path,
                    label="Discovered executable",
                )
                if path_error:
                    warnings.append(path_error)
                elif safe_path is not None and safe_path.is_file() and (
                    safe_path.suffix.casefold() in executable_suffixes
                    or directory_name in {"scripts", "hooks"}
                ):
                    executable_files.append(str(safe_path))
        except (PermissionError, OSError):
            warnings.append(f"Could not fully inspect executable directory: {directory}")

    license_value = manifest.get("license")
    license_files: list[str] = []
    for candidate in package_root.glob("LICENSE*"):
        path, error = safe_discovered_package_path(package_root, candidate, label="Discovered license file")
        if error:
            warnings.append(error)
        elif path is not None and path.is_file():
            license_files.append(str(path))
    license_files.sort()
    if not (isinstance(license_value, str) and license_value.strip()) and not license_files:
        warnings.append("No package license metadata or LICENSE file was found; do not redistribute by default.")
    if executable_files:
        warnings.append("Package contains scripts, hooks, or executable files; discovery did not run them.")

    if package["agent_count"] == 0:
        warnings.append("No readable agent Markdown files were found.")
    if package["package_class"] == AGENT_PACKAGE:
        warnings.append(
            "Manifest has no declared expertType; treat this as an agent-bearing plugin, not an Expert Center package."
        )
    if package["package_class"] == DECLARED_EXPERT and package["expert_type"] == "team" and not package["lead_path"]:
        warnings.append("Team lead file could not be resolved from teamInfo or agentName.")

    team_info = manifest.get("teamInfo") if isinstance(manifest.get("teamInfo"), dict) else {}
    raw_members = manifest.get("members")
    if not isinstance(raw_members, list) or not raw_members:
        raw_members = team_info.get("memberAgents")
    members = project_members(raw_members)
    dependencies = project_dependencies(manifest.get("dependencies"))
    connector_ids = project_connector_ids(manifest.get("connectorIds"))
    report = package_trust(package)
    safe_warnings = sorted(
        {
            sanitize_untrusted_text(str(warning).replace(str(package_root), "<package-root>"), limit=300)
            for warning in warnings
        }
    )

    return {
        "name": safe_identifier(package["name"]),
        "display_name": sanitize_untrusted_text(package["display_name"]),
        "profession": sanitize_untrusted_text(package["profession"]),
        "package_class": package["package_class"],
        "kind": package["kind"],
        "kind_source": package["kind_source"],
        "expert_type": package["expert_type"],
        "version": safe_identifier(package["version"]),
        "marketplace": safe_identifier(package["marketplace"]),
        "manifest_path": MANIFEST_RELATIVE.as_posix(),
        "lead_agent": safe_identifier(package["lead_agent"]),
        "lead_path": relative_package_path(package_root, package["lead_path"]),
        "agent_paths": [relative_package_path(package_root, path) for path in package["agent_paths"]],
        "agent_count": package["agent_count"],
        "members": members,
        "skill_paths": [relative_package_path(package_root, path) for path in skills],
        "reference_roots": [
            relative_package_path(package_root, path)
            for candidate in (package_root / "references",)
            if candidate.is_dir()
            and (path := resolved_path_within(package_root, candidate)) is not None
        ],
        "dependencies": dependencies,
        "connector_ids": connector_ids,
        "license": safe_identifier(license_value) if isinstance(license_value, str) else "",
        "license_files": [relative_package_path(package_root, path) for path in license_files],
        "executable_files": sorted(relative_package_path(package_root, path) for path in executable_files),
        "trust": trust_summary(report, include_findings=True),
        "warnings": safe_warnings,
        "read_only": True,
    }


def filter_packages(packages: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    result = packages
    if args.kind != "all":
        result = [item for item in result if item["kind"] == args.kind]
    if args.package_class != "all":
        result = [item for item in result if item["package_class"] == args.package_class]
    if args.marketplace:
        result = [item for item in result if item["marketplace"].casefold() == args.marketplace.casefold()]
    if args.query:
        result = [item for item in result if matches_query(item, args.query)]
    return result


def _warning_code(value: Any) -> str:
    text = str(value or "").casefold()
    if "json-too-large" in text or "bounded read limit" in text:
        return "json-too-large"
    if "invalid json" in text or "root must be an object" in text:
        return "invalid-json"
    if (
        "escape" in text
        or "unsafe" in text
        or "symlink" in text
        or "outside" in text
        or "absolute path" in text
    ):
        return "unsafe-path"
    if "missing" in text or "not found" in text:
        return "missing-content"
    if "not readable" in text or "could not" in text or "permission" in text:
        return "read-error"
    if "unsupported experttype" in text:
        return "unsupported-expert-type"
    if "license" in text:
        return "license-metadata-missing"
    if "script" in text or "executable" in text or "hook" in text:
        return "executable-content-present"
    if "no declared experttype" in text:
        return "undeclared-agent-package"
    return "discovery-warning"


def _project_public_warnings(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values[:200]:
        code = _warning_code(value)
        if code not in seen:
            seen.add(code)
            result.append({"code": code})
    return result


def _public_safe_string(value: str, *, key: str = "") -> str:
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme == "https"
        and (parsed.hostname or "").casefold() in WORKBUDDY_OFFICIAL_HOSTS
    ):
        return value
    path_key = (
        key.endswith("_path")
        or key.endswith("_paths")
        or key.endswith("_root")
        or key.endswith("_roots")
        or key in {"config_path", "package_root", "source_roots"}
    )
    stripped = value.strip()
    if (
        WINDOWS_ABSOLUTE_PATH_RE.search(stripped)
        or EMBEDDED_WINDOWS_PATH_RE.search(stripped)
        or EMBEDDED_POSIX_LOCAL_PATH_RE.search(stripped)
    ):
        return "[redacted-local-path]"
    if path_key and key != "official_ranking_endpoint" and stripped.startswith("/"):
        return "[redacted-local-path]"
    home_name = Path.home().name
    projected = sanitize_untrusted_text(value, limit=500)
    if home_name and len(home_name) >= 3:
        projected = re.sub(re.escape(home_name), "[local-user]", projected, flags=re.IGNORECASE)
    return projected


def project_public_payload(value: Any, *, key: str = "") -> Any:
    """Recursively enforce the no-local-path/no-untrusted-text public JSON boundary."""
    if key == "warnings":
        return _project_public_warnings(value)
    if isinstance(value, dict):
        return {
            str(item_key): project_public_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
            if not str(item_key).startswith("_")
        }
    if isinstance(value, list):
        return [project_public_payload(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [project_public_payload(item, key=key) for item in value]
    if isinstance(value, str):
        return _public_safe_string(value, key=key)
    return value


def emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return

    command = payload.get("command")
    if command == "list":
        for item in payload.get("items", []):
            print(
                "\t".join(
                    [
                        item["name"],
                        item["kind"],
                        item["package_class"],
                        item["display_name"],
                        item["marketplace"],
                    ]
                )
            )
    elif command == "catalog":
        for item in payload.get("items", []):
            print(
                "\t".join(
                    [
                        item["id"],
                        item["expert_type"],
                        item["availability"],
                        item.get("trust_status", TRUST_UNKNOWN),
                        item["display_name"],
                    ]
                )
            )
    elif command == "audit":
        if "items" in payload:
            for item in payload.get("items", []):
                identity = item.get("package", {})
                print(
                    "\t".join(
                        [
                            str(identity.get("name") or "unknown"),
                            str(item.get("trust_status") or TRUST_UNKNOWN),
                            "complete" if item.get("scan_complete") is True else "incomplete-or-unavailable",
                        ]
                    )
                )
        else:
            identity = payload.get("package", {})
            print(
                f"{identity.get('name') or 'unknown'}\t{payload.get('trust_status')}\t"
                f"policy={payload.get('policy_version')}\tdigest={payload.get('content_digest') or 'unavailable'}"
            )
    elif command == "recommend":
        if not payload.get("recommendations"):
            print("没有找到具备可解释元数据命中的 WorkBuddy 候选。")
        for item in payload.get("recommendations", []):
            hot = item["ranking_evidence"]["hot"]
            latest = item["ranking_evidence"]["latest"]
            print(
                f"{item['rank']}. {item['display_name']} ({item['id']}) "
                f"[{item['expert_type']} | {item['availability']} | {item['trust']['trust_status']}]"
            )
            print(f"   分类: {item['category']['name']} ({item['category']['id']})")
            print(f"   理由: {' '.join(item['recommendation_reasons'])}")
            print(
                "   排名证据: "
                f"relevance={item['ranking_evidence']['relevance']['total_score']}; "
                f"hot={hot['status']}; latest={latest['status']}:{latest['value']}"
            )
        hot_source = payload.get("ranking_sources", {}).get("hot", {})
        if hot_source.get("status") == "unavailable":
            print(f"热度: unavailable — {hot_source.get('unavailable_reason', '')}")
        official_online = payload.get("ranking_sources", {}).get("official_online")
        if official_online:
            print(
                "官方匿名在线探针: "
                f"{official_online.get('status')} — "
                f"{official_online.get('unavailable_reason') or '已获得完整显式排名字段。'}"
            )
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only WorkBuddy expert bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(subparser: argparse.ArgumentParser) -> None:
        subparser.add_argument("--root", help="WorkBuddy config, marketplaces, marketplace, collection, or package path")
        subparser.add_argument("--json", action="store_true", help="Emit structured JSON")

    doctor = subparsers.add_parser("doctor", help="Check source discovery and summarize availability")
    add_common(doctor)

    inventory = subparsers.add_parser(
        "inventory",
        help="Summarize declared experts, agent-bearing packages, runtime teams, and cached metadata",
    )
    add_common(inventory)
    inventory.add_argument("--limit", type=int, default=DEFAULT_INVENTORY_LIMIT)
    inventory.add_argument(
        "--agent-package-examples",
        type=int,
        default=DEFAULT_AGENT_PACKAGE_EXAMPLES,
    )
    inventory.add_argument("--metadata-examples", type=int, default=DEFAULT_METADATA_EXAMPLES)

    list_parser = subparsers.add_parser("list", help="List installed expert and agent-bearing packages")
    add_common(list_parser)
    list_parser.add_argument("--query", default="", help="Case-insensitive metadata filter")
    list_parser.add_argument("--kind", choices=("all", "agent", "team"), default="all")
    list_parser.add_argument(
        "--package-class",
        choices=("all", DECLARED_EXPERT, AGENT_PACKAGE),
        default="all",
    )
    list_parser.add_argument("--marketplace", default="", help="Filter by marketplace name")
    list_parser.add_argument("--limit", type=int, default=DEFAULT_LIST_LIMIT)

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Resolve one name across installed packages and cached catalog metadata",
    )
    resolve_parser.add_argument("name", help="Exact name, folder, display name, or unique partial query")
    add_common(resolve_parser)
    resolve_parser.add_argument("--marketplace", default="", help="Disambiguate installed packages")

    inspect_parser = subparsers.add_parser("inspect", help="Inspect one installed expert package")
    inspect_parser.add_argument("name", help="Exact name, folder, display name, or unique partial query")
    add_common(inspect_parser)
    inspect_parser.add_argument("--marketplace", default="", help="Disambiguate by marketplace name")

    audit = subparsers.add_parser(
        "audit",
        help="Audit one local package or return a bounded trust summary for discovered entries",
    )
    audit.add_argument(
        "name",
        nargs="?",
        default="",
        help="Optional exact package or catalog name for a full structured audit",
    )
    add_common(audit)
    audit.add_argument("--marketplace", default="", help="Disambiguate installed packages")
    audit.add_argument("--limit", type=int, default=DEFAULT_AUDIT_LIMIT)

    catalog = subparsers.add_parser("catalog", help="List cached expert metadata and local availability")
    add_common(catalog)
    catalog.add_argument("--query", default="", help="Case-insensitive metadata filter")
    catalog.add_argument("--kind", choices=("all", "agent", "team"), default="all")
    catalog.add_argument(
        "--availability",
        choices=("all", INSTALLED, INSTALLED_UNUSABLE, METADATA_ONLY),
        default="all",
    )
    catalog.add_argument("--limit", type=int, default=DEFAULT_CATALOG_LIMIT)
    catalog.add_argument(
        "--trust",
        choices=("all",) + TRUST_STATUSES,
        default="all",
        help="Filter by package trust status without changing it",
    )

    recommend = subparsers.add_parser(
        "recommend",
        help="Recommend WorkBuddy experts from an open-ended natural-language need",
    )
    recommend.add_argument("request", help="Open-ended task or outcome description")
    add_common(recommend)
    recommend.add_argument("--kind", choices=("auto", "all", "agent", "team"), default="auto")
    recommend.add_argument("--availability", choices=("all", INSTALLED, METADATA_ONLY), default="all")
    recommend.add_argument("--category", default="", help="Optional category id or display-name filter")
    recommend.add_argument("--top", type=int, default=DEFAULT_RECOMMEND_LIMIT)
    recommend.add_argument(
        "--trust",
        choices=("all",) + TRUST_STATUSES,
        default=TRUST_ELIGIBLE,
        help="Default eligible-only; choose another status or all only for explicit risk review",
    )
    recommend.add_argument(
        "--official-online",
        action="store_true",
        help="Probe fixed anonymous WorkBuddy first-party sources without reading or sending credentials",
    )

    return parser


def _run_internal(args: argparse.Namespace) -> dict[str, Any]:
    roots = existing_roots(args.root)
    packages, discovery_warnings = discover_packages(roots)

    if args.command == "audit":
        catalog, catalog_warnings = load_catalog(roots, packages)
        if args.name:
            package: dict[str, Any] | None
            try:
                package = select_package(packages, args.name, args.marketplace or None)
            except BridgeError as exc:
                if exc.code != "expert_not_found":
                    raise
                package = None
            if package is not None:
                report = package_trust(package)
            else:
                catalog_item = select_catalog_item(catalog, args.name)
                if catalog_item is None:
                    raise BridgeError(
                        f"No installed package or catalog entry matches: {args.name}",
                        code="expert_not_found",
                    )
                report = catalog_item.get("_trust_audit")
                if not isinstance(report, dict):
                    report = unknown_trust_report(
                        {
                            "name": safe_identifier(catalog_item.get("id")),
                            "display_name": sanitize_untrusted_text(catalog_item.get("display_name")),
                            "version": "",
                            "marketplace": "catalog",
                            "package_class": "metadata-only",
                            "expert_type": catalog_item.get("expert_type") or None,
                            "availability": catalog_item.get("availability"),
                        }
                    )
            return {
                "status": "ok",
                "command": "audit",
                "source_roots": [str(path) for path in roots],
                **report,
                "next_action": (
                    "inspect"
                    if report["trust_status"] == TRUST_ELIGIBLE
                    else "explicit-user-review"
                    if report["trust_status"] == TRUST_REVIEW_REQUIRED
                    else "repair-and-reaudit"
                    if report["trust_status"] == TRUST_QUARANTINED
                    else "provide-local-package"
                ),
                "warnings": discovery_warnings + catalog_warnings,
            }

        limit = max(args.limit, 0)
        summaries: list[dict[str, Any]] = []
        counts = {status: 0 for status in TRUST_STATUSES}
        for item in catalog:
            report = item.get("_trust_audit")
            if not isinstance(report, dict):
                report = unknown_trust_report()
            trust_status = str(report.get("trust_status") or TRUST_UNKNOWN)
            counts[trust_status] = counts.get(trust_status, 0) + 1
            summaries.append(
                {
                    "package": report.get("package", {}),
                    **trust_summary(report),
                }
            )
        return {
            "status": "ok",
            "command": "audit",
            "policy_version": TRUST_POLICY_VERSION,
            "source_roots": [str(path) for path in roots],
            "total": len(summaries),
            "returned": min(len(summaries), limit),
            "truncated": len(summaries) > limit,
            "counts": counts,
            "items": summaries[:limit],
            "read_only": True,
            "warnings": discovery_warnings + catalog_warnings,
        }

    if args.command == "doctor":
        catalog, catalog_warnings = load_catalog(roots, packages)
        runtime_teams, runtime_warnings = load_runtime_teams(roots)
        declared = [item for item in packages if item["package_class"] == DECLARED_EXPERT]
        usable_declared = [item for item in declared if item["availability"] == INSTALLED]
        agent_packages = [item for item in packages if item["package_class"] == AGENT_PACKAGE]
        usable_packages = [item for item in packages if item["availability"] == INSTALLED]
        return {
            "status": "ok",
            "command": "doctor",
            "source_roots": [str(path) for path in roots],
            "discovered_package_manifests": len(packages),
            "installed_packages": len(usable_packages),
            "installed_usable_packages": len(usable_packages),
            "installed_unusable_packages": sum(
                item["availability"] == INSTALLED_UNUSABLE for item in packages
            ),
            "declared_expert_packages": len(declared),
            "installed_experts": len(usable_declared),
            "installed_agents": sum(item["kind"] == "agent" for item in usable_declared),
            "installed_teams": sum(item["kind"] == "team" for item in usable_declared),
            "installed_agent_packages": len(agent_packages),
            "agent_package_single": sum(item["kind"] == "agent" for item in agent_packages),
            "agent_package_multi": sum(item["kind"] == "team" for item in agent_packages),
            "runtime_teams": len(runtime_teams),
            "catalog_entries": len(catalog),
            "catalog_installed": sum(item["availability"] == "installed" for item in catalog),
            "catalog_installed_unusable": sum(
                item["availability"] == INSTALLED_UNUSABLE for item in catalog
            ),
            "catalog_metadata_only": sum(item["availability"] == "metadata-only" for item in catalog),
            "python": ".".join(str(part) for part in sys.version_info[:3]),
            "read_only": True,
            "warnings": discovery_warnings + catalog_warnings + runtime_warnings,
        }

    if args.command == "inventory":
        catalog, catalog_warnings = load_catalog(roots, packages)
        runtime_teams, runtime_warnings = load_runtime_teams(roots)
        declared = [
            compact_package_summary(item)
            for item in packages
            if item["package_class"] == DECLARED_EXPERT
        ]
        agent_packages = [
            compact_package_summary(item)
            for item in packages
            if item["package_class"] == AGENT_PACKAGE
        ]
        runtime_summaries = [compact_runtime_team_summary(item) for item in runtime_teams]
        metadata_only = [item for item in catalog if item["availability"] == METADATA_ONLY]
        installed_catalog = [item for item in catalog if item["availability"] == INSTALLED]
        installed_unusable = [item for item in catalog if item["availability"] == INSTALLED_UNUSABLE]
        example_limit = max(args.metadata_examples, 0)
        examples = [catalog_summary(item) for item in metadata_only[:example_limit]]
        return {
            "status": "ok",
            "command": "inventory",
            "source_roots": [str(path) for path in roots],
            "layers": {
                "declared_experts": bounded_section(declared, args.limit),
                "agent_packages": bounded_section(agent_packages, args.agent_package_examples),
                "runtime_teams": bounded_section(runtime_summaries, args.limit),
            },
            "catalog": {
                "total": len(catalog),
                "installed": len(installed_catalog),
                "metadata_only": len(metadata_only),
                "installed_unusable": len(installed_unusable),
                "metadata_only_examples": examples,
                "examples_returned": len(examples),
                "examples_truncated": len(examples) < len(metadata_only),
            },
            "output_budget": {
                "local_items_per_layer": max(args.limit, 0),
                "agent_package_examples": max(args.agent_package_examples, 0),
                "metadata_only_examples": example_limit,
            },
            "classification_notes": [
                "declared_experts have manifest expertType=agent or team",
                "agent_packages contain readable agent prompts but do not declare expertType",
                "runtime_teams are saved execution state, not reusable expert packages",
            ],
            "read_only": True,
            "warnings": discovery_warnings + catalog_warnings + runtime_warnings,
        }

    if args.command == "list":
        filtered = filter_packages(packages, args)
        limit = max(args.limit, 0)
        items = [package_summary(item) for item in filtered[:limit]]
        return {
            "status": "ok",
            "command": "list",
            "source_roots": [str(path) for path in roots],
            "total_matches": len(filtered),
            "returned": len(items),
            "truncated": len(items) < len(filtered),
            "items": items,
            "warnings": discovery_warnings,
        }

    if args.command == "recommend":
        catalog, catalog_warnings = load_catalog(roots, packages)
        official_online_probe = (
            probe_official_online_ranking(catalog)
            if args.official_online
            else None
        )
        payload = recommend_catalog(
            catalog,
            args.request,
            kind=args.kind,
            availability=args.availability,
            category=args.category,
            limit=args.top,
            trust=args.trust,
            official_online_probe=official_online_probe,
        )
        payload.update(
            {
                "command": "recommend",
                "source_roots": [str(path) for path in roots],
                "warnings": discovery_warnings + catalog_warnings,
            }
        )
        return payload

    if args.command == "resolve":
        package: dict[str, Any] | None
        try:
            package = select_package(packages, args.name, args.marketplace or None)
        except BridgeError as exc:
            if exc.code != "expert_not_found":
                raise
            package = None

        if package is not None:
            report = package_trust(package)
            if package["availability"] == INSTALLED_UNUSABLE or report["trust_status"] == TRUST_QUARANTINED:
                return {
                    "status": "blocked",
                    "command": "resolve",
                    "source_roots": [str(path) for path in roots],
                    "availability": package["availability"],
                    "match": report["package"],
                    "trust": trust_summary(report, include_findings=True),
                    "missing": (
                        ["readable local agent prompt Markdown"]
                        if package["availability"] == INSTALLED_UNUSABLE
                        else []
                    ),
                    "recovery_action": (
                        UNUSABLE_RECOVERY_ACTION
                        if package["availability"] == INSTALLED_UNUSABLE
                        else report["recovery_action"]
                    ),
                    "next_action": "audit",
                    "read_only": True,
                    "warnings": discovery_warnings,
                }
            if report["trust_status"] == TRUST_REVIEW_REQUIRED:
                return {
                    "status": TRUST_REVIEW_REQUIRED,
                    "command": "resolve",
                    "source_roots": [str(path) for path in roots],
                    "availability": INSTALLED,
                    "match": report["package"],
                    "trust": trust_summary(report, include_findings=True),
                    "next_action": "audit",
                    "read_only": True,
                    "warnings": discovery_warnings,
                }
            return {
                "status": "ok",
                "command": "resolve",
                "source_roots": [str(path) for path in roots],
                "availability": "installed",
                "match": compact_package_summary(package),
                "trust": trust_summary(report),
                "next_action": "audit",
                "read_only": True,
                "warnings": discovery_warnings,
            }

        catalog, catalog_warnings = load_catalog(roots, packages)
        catalog_item = select_catalog_item(catalog, args.name)
        if catalog_item is None:
            runtime_teams, runtime_warnings = load_runtime_teams(roots)
            for rt in runtime_teams:
                if (rt.get("name") or "").casefold() == args.name.casefold():
                    return {
                        "status": "runtime-team-ineligible",
                        "command": "resolve",
                        "source_roots": [str(path) for path in roots],
                        "availability": "runtime-only",
                        "match": {
                            "name": safe_identifier(rt.get("name")),
                            "object_class": "runtime-team",
                            "folder": safe_identifier(rt.get("folder")),
                        },
                        "missing": ["installed package", "cached catalog metadata"],
                        "next_steps": [
                            "This identifier matches a historical runtime team session in teams/, which is not a reusable Expert Center package.",
                            "Install or select a formal declared-expert package from the Expert Center.",
                        ],
                        "recovery_action": (
                            "This identifier matches a historical runtime team session in teams/, which is not a reusable "
                            "Expert Center package. To reuse experts, install or select a formal declared-expert package."
                        ),
                        "read_only": True,
                        "warnings": discovery_warnings + catalog_warnings + runtime_warnings,
                    }
            return {
                "status": "not-found",
                "command": "resolve",
                "source_roots": [str(path) for path in roots],
                "availability": "not-found",
                "match": None,
                "missing": ["installed package", "cached catalog metadata"],
                "next_steps": [
                    "Verify the exact expert name.",
                    "Provide an existing readable package root with --root if it is stored elsewhere.",
                ],
                "recovery_action": NOT_FOUND_RECOVERY_ACTION,
                "read_only": True,
                "warnings": discovery_warnings + catalog_warnings,
            }

        local_matches = packages_for_catalog_item(packages, catalog_item)
        if local_matches:
            usable_matches = [item for item in local_matches if item["agent_count"] > 0]
            if not usable_matches:
                report = package_trust(local_matches[0])
                return {
                    "status": "blocked",
                    "command": "resolve",
                    "source_roots": [str(path) for path in roots],
                    "availability": INSTALLED_UNUSABLE,
                    "match": report["package"],
                    "catalog_match": catalog_summary(catalog_item),
                    "trust": trust_summary(report, include_findings=True),
                    "missing": ["readable local agent prompt Markdown"],
                    "recovery_action": UNUSABLE_RECOVERY_ACTION,
                    "next_action": "repair-in-workbuddy",
                    "read_only": True,
                    "warnings": discovery_warnings + catalog_warnings,
                }
            selected = usable_matches[0]
            report = package_trust(selected)
            if report["trust_status"] == TRUST_QUARANTINED:
                return {
                    "status": "blocked",
                    "command": "resolve",
                    "source_roots": [str(path) for path in roots],
                    "availability": INSTALLED,
                    "match": report["package"],
                    "catalog_match": catalog_summary(catalog_item),
                    "trust": trust_summary(report, include_findings=True),
                    "recovery_action": report["recovery_action"],
                    "next_action": "audit",
                    "read_only": True,
                    "warnings": discovery_warnings + catalog_warnings,
                }
            if report["trust_status"] == TRUST_REVIEW_REQUIRED:
                return {
                    "status": TRUST_REVIEW_REQUIRED,
                    "command": "resolve",
                    "source_roots": [str(path) for path in roots],
                    "availability": INSTALLED,
                    "match": report["package"],
                    "catalog_match": catalog_summary(catalog_item),
                    "trust": trust_summary(report, include_findings=True),
                    "next_action": "audit",
                    "read_only": True,
                    "warnings": discovery_warnings + catalog_warnings,
                }
            return {
                "status": "ok",
                "command": "resolve",
                "source_roots": [str(path) for path in roots],
                "availability": "installed",
                "match": compact_package_summary(selected),
                "catalog_match": catalog_summary(catalog_item),
                "trust": trust_summary(report),
                "next_action": "audit",
                "read_only": True,
                "warnings": discovery_warnings + catalog_warnings,
            }

        metadata_report = catalog_item.get("_trust_audit")
        if not isinstance(metadata_report, dict):
            metadata_report = unknown_trust_report()
        return {
            "status": "blocked",
            "command": "resolve",
            "source_roots": [str(path) for path in roots],
            "availability": "metadata-only",
            "match": catalog_summary(catalog_item),
            "trust": trust_summary(metadata_report),
            "missing": [
                "local .codebuddy-plugin/plugin.json",
                "readable local agent prompt Markdown",
            ],
            "next_steps": [
                "Install the package through WorkBuddy's own expert management UI, or provide an existing readable package root with --root.",
                "Run resolve again and use inspect only after availability becomes installed.",
            ],
            "recovery_action": METADATA_RECOVERY_ACTION,
            "downloaded": False,
            "read_only": True,
            "warnings": discovery_warnings + catalog_warnings,
        }

    if args.command == "inspect":
        package = select_package(packages, args.name, args.marketplace or None)
        report = package_trust(package)
        if package["availability"] == INSTALLED_UNUSABLE or report["trust_status"] == TRUST_QUARANTINED:
            return {
                "status": "blocked",
                "command": "inspect",
                "source_roots": [str(path) for path in roots],
                "availability": package["availability"],
                "package": report["package"],
                "trust": trust_summary(report, include_findings=True),
                "missing": (
                    ["readable local agent prompt Markdown"]
                    if package["availability"] == INSTALLED_UNUSABLE
                    else []
                ),
                "recovery_action": (
                    UNUSABLE_RECOVERY_ACTION
                    if package["availability"] == INSTALLED_UNUSABLE
                    else report["recovery_action"]
                ),
                "warnings": discovery_warnings,
            }
        if report["trust_status"] == TRUST_REVIEW_REQUIRED:
            return {
                "status": TRUST_REVIEW_REQUIRED,
                "command": "inspect",
                "source_roots": [str(path) for path in roots],
                "availability": INSTALLED,
                "package": report["package"],
                "trust": trust_summary(report, include_findings=True),
                "recovery_action": report["recovery_action"],
                "warnings": discovery_warnings,
            }
        return {
            "status": "ok",
            "command": "inspect",
            "source_roots": [str(path) for path in roots],
            "expert": inspect_package(package),
            "trust": trust_summary(report),
            "warnings": discovery_warnings,
        }

    if args.command == "catalog":
        catalog, catalog_warnings = load_catalog(roots, packages)
        filtered = catalog
        if args.kind != "all":
            filtered = [item for item in filtered if item["expert_type"] == args.kind]
        if args.availability != "all":
            filtered = [item for item in filtered if item["availability"] == args.availability]
        if args.trust != "all":
            filtered = [item for item in filtered if item.get("trust_status") == args.trust]
        if args.query:
            filtered = [item for item in filtered if matches_query(item, args.query)]
        limit = max(args.limit, 0)
        items = [catalog_summary(item) for item in filtered[:limit]]
        return {
            "status": "ok",
            "command": "catalog",
            "source_roots": [str(path) for path in roots],
            "total_matches": len(filtered),
            "returned": len(items),
            "truncated": len(items) < len(filtered),
            "items": items,
            "warnings": discovery_warnings + catalog_warnings,
        }

    raise BridgeError(f"Unsupported command: {args.command}", code="invalid_command")


def run(args: argparse.Namespace) -> dict[str, Any]:
    return project_public_payload(_run_internal(args))


def main(argv: list[str] | None = None) -> int:
    configure_standard_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))

    if sys.version_info < MIN_PYTHON:
        payload = {
            "status": "error",
            "error_code": "python_too_old",
            "message": f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required.",
        }
        emit(payload, as_json)
        return 5

    try:
        payload = run(args)
    except BridgeError as exc:
        payload = project_public_payload(
            {"status": "error", "error_code": exc.code, "message": str(exc)}
        )
        emit(payload, as_json)
        return 3

    emit(payload, as_json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
