"""구독용 요약 엔진(Claude Code CLI)을 가짜 CLI 로 검증한다. 실제 구독 사용량은 쓰지 않는다."""

import asyncio
import json
import sys

import pytest

from app.config import settings
from app.services.llm import claude_code, get_provider
from app.services.llm.base import LLMError, SectionInput
from app.services.llm.claude_code import ClaudeCodeProvider, parse_cli_output

FAKE_CLI = r'''
import json, os, sys
args = sys.argv[1:]
prompt = sys.stdin.buffer.read().decode("utf-8")
if os.environ.get("FAKE_MODE") == "error":
    print(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                      "result": "usage limit reached"}))
    sys.exit(1)
checks = {
    "print_mode": "-p" in args,
    "tools_disabled": args[args.index("--tools") + 1] == "",
    "schema_passed": "summary_markdown" in args[args.index("--json-schema") + 1],
    "api_key_removed": "ANTHROPIC_API_KEY" not in os.environ,
    "source_on_stdin": "setup.exe" in prompt,
    "glossary_on_stdin": "Glossary:" in prompt,
}
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "",
                  "structured_output": {"summary_markdown": json.dumps(checks) + "\n\n1. 설치 프로그램 실행\n> ⚠ 재부팅됨"}},
                 ensure_ascii=False))
'''

SAMPLE = SectionInput(
    vendor="Acme",
    document_title="Guide",
    section_path="Install",
    text="Run setup.exe /quiet",
    target_language="ko",
    glossary=[("switch", "스위치")],
)


@pytest.fixture
def provider(tmp_path, monkeypatch):
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE_CLI, encoding="utf-8")
    monkeypatch.setattr(claude_code, "find_claude_cli", lambda: "claude")
    p = ClaudeCodeProvider()
    p._base_cmd = [sys.executable, str(fake)]
    return p


def test_runs_cli_with_subscription_env(provider, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-be-used")
    result = asyncio.run(provider.summarize_section(SAMPLE))
    checks = json.loads(result.summary_markdown.splitlines()[0])
    assert all(checks.values()), checks
    # 절차·주의사항은 본문에서 뽑는다 (한글이 깨지지 않는다)
    assert result.key_steps == ["설치 프로그램 실행"] and result.warnings == ["재부팅됨"]


def test_cli_error_is_reported(provider, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "error")
    with pytest.raises(LLMError, match="usage limit reached"):
        asyncio.run(provider.summarize_section(SAMPLE))


def test_non_json_output_shows_stderr():
    with pytest.raises(LLMError, match="unknown option"):
        parse_cli_output(1, "", "error: unknown option '--safe-mode'")


def test_missing_cli_gives_install_hint(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "claude_code")
    monkeypatch.setattr(claude_code, "find_claude_cli", lambda: None)
    with pytest.raises(LLMError, match="Claude Code CLI를 찾을 수 없습니다"):
        get_provider()
