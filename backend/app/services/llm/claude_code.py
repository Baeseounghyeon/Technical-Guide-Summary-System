"""Claude Code CLI(`claude -p`)를 통해 본인의 Claude 구독으로 요약하는 엔진.

개인 PC에서 본인 문서를 처리하는 용도 전용이다. 다른 사람에게 서비스할 때는
구독 로그인을 쓰면 안 되고 Claude API(LLM_PROVIDER=claude)로 전환해야 한다.

연결 확인: python -m app.services.llm.claude_code
"""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

from ...config import settings
from .base import CompareInput, FindingResult, LLMError, OverviewInput, SectionInput, SectionResult, TocEntry
from .prompts import (
    COMPARE_SCHEMA,
    MATCH_SCHEMA,
    OVERVIEW_SCHEMA,
    REVIEW_SYSTEM_PROMPT,
    SECTION_SCHEMA,
    SYSTEM_PROMPT,
    compare_prompt,
    glossary_text,
    match_prompt,
    overview_prompt,
    parse_matches,
    section_prompt,
)

# 지시문 파일 이름 → 내용 (CLI 에 --system-prompt-file 로 넘긴다)
_SYSTEM_PROMPTS = {"summarize": SYSTEM_PROMPT, "review": REVIEW_SYSTEM_PROMPT}

# 이 변수들이 있으면 Claude Code가 구독 대신 API 키·클라우드 계정을 쓴다.
# CLAUDECODE 등은 Claude Code 안에서 서버를 띄웠을 때 중첩 실행으로 오인되지 않도록 지운다.
_ENV_TO_REMOVE = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_PROFILE",
    "ANTHROPIC_FEDERATION_RULE_ID",
    "ANTHROPIC_ORGANIZATION_ID",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
)


def find_claude_cli() -> str | None:
    configured = settings.claude_code_path
    if configured and Path(configured).is_file():
        return configured
    if configured and (found := shutil.which(configured)):
        return found
    # 기본 설치 위치 (Windows 네이티브 설치 프로그램). 서버 프로세스의 PATH 에 없을 수 있다.
    native = Path.home() / ".local" / "bin" / ("claude.exe" if os.name == "nt" else "claude")
    return str(native) if native.is_file() else None


def cli_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _ENV_TO_REMOVE}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _work_dir() -> Path:
    """프로젝트 CLAUDE.md·설정을 읽지 않도록 빈 전용 폴더에서 실행한다."""
    path = settings.storage_dir / "claude-code"
    path.mkdir(parents=True, exist_ok=True)
    for name, text in _SYSTEM_PROMPTS.items():
        prompt_file = path / f"system-{name}.md"
        if not prompt_file.is_file() or prompt_file.read_text(encoding="utf-8") != text:
            prompt_file.write_text(text, encoding="utf-8")
    return path


class ClaudeCodeProvider:
    def __init__(self) -> None:
        cli = find_claude_cli()
        if cli is None:
            raise LLMError(
                "Claude Code CLI를 찾을 수 없습니다. 설치 후 `claude` 로 한 번 로그인하거나 "
                ".env 의 CLAUDE_CODE_PATH 에 claude.exe 경로를 지정하세요."
            )
        self._base_cmd = [cli]

    async def summarize_section(self, item: SectionInput) -> SectionResult:
        data = await self._run(section_prompt(item), SECTION_SCHEMA, item.glossary)
        return SectionResult(
            summary_markdown=data["summary_markdown"],
            key_steps=list(data.get("key_steps", [])),
            warnings=list(data.get("warnings", [])),
        )

    async def summarize_overview(self, item: OverviewInput) -> str:
        data = await self._run(overview_prompt(item), OVERVIEW_SCHEMA, [])
        return data["overview_markdown"]

    async def match_sections(self, partner: list[TocEntry], vendor: list[TocEntry]) -> dict[int, int | None]:
        data = await self._run(match_prompt(partner, vendor), MATCH_SCHEMA, [], system="review")
        return parse_matches(data, partner, vendor)

    async def compare_section(self, item: CompareInput) -> list[FindingResult]:
        data = await self._run(compare_prompt(item), COMPARE_SCHEMA, [], system="review")
        return [FindingResult(**f) for f in data["findings"]]

    async def _run(
        self, prompt: str, schema: dict, glossary: list[tuple[str, str]], *, system: str = "summarize"
    ) -> dict:
        work_dir = _work_dir()
        cmd = [
            *self._base_cmd,
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--system-prompt-file", str(work_dir / f"system-{system}.md"),
            "--model", settings.claude_code_model,
            "--tools", "",
            "--max-turns", "3",
            "--no-session-persistence",
            "--safe-mode",
        ]
        # 긴 원문은 명령줄 길이 제한을 피하려고 표준 입력으로 넘긴다.
        stdin_text = "\n\n".join(filter(None, [glossary_text(glossary), prompt]))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=work_dir,
            env=cli_env(),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(stdin_text.encode("utf-8")), timeout=settings.claude_code_timeout_seconds
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise LLMError(f"Claude Code 응답이 {settings.claude_code_timeout_seconds}초 안에 오지 않았습니다.")

        return parse_cli_output(proc.returncode, stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace"))


def parse_cli_output(returncode: int | None, stdout: str, stderr: str) -> dict:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        detail = (stderr or stdout).strip()[-1000:]
        raise LLMError(f"Claude Code 실행 실패 (종료 코드 {returncode}): {detail}") from None

    if payload.get("is_error") or payload.get("subtype", "success") != "success":
        detail = payload.get("result") or payload.get("errors") or payload.get("subtype")
        raise LLMError(f"Claude Code 오류: {detail}")
    if isinstance(payload.get("structured_output"), dict):
        return payload["structured_output"]
    try:
        return json.loads(payload.get("result") or "")
    except json.JSONDecodeError:
        raise LLMError("Claude Code 응답에서 구조화된 결과를 찾지 못했습니다.") from None


def _check() -> None:
    """설치·로그인 상태를 확인하고 짧은 요약을 한 번 실행해 본다."""
    cli = find_claude_cli()
    if cli is None:
        print("Claude Code CLI를 찾지 못했습니다. README 의 설치 방법을 따라 설치하세요.")
        return
    print(f"CLI 위치: {cli}")
    status = subprocess.run(
        [cli, "auth", "status"], capture_output=True, text=True, encoding="utf-8", env=cli_env()
    )
    print(f"로그인 상태: {status.stdout.strip() or status.stderr.strip()}")
    if '"claude.ai"' not in status.stdout:
        print("주의: 구독(claude.ai) 로그인이 아닌 것 같습니다. `claude auth login` 으로 구독 계정에 로그인하세요.")

    sample = SectionInput(
        vendor="Acme",
        document_title="연결 확인",
        section_path="Install",
        text="1. Run `setup.exe /quiet`.\n2. Open TCP port 8443.\nWarning: the device reboots after setup.",
        target_language="ko",
    )
    result = asyncio.run(ClaudeCodeProvider().summarize_section(sample))
    print("요약 테스트 성공:\n" + result.summary_markdown)


if __name__ == "__main__":
    _check()
