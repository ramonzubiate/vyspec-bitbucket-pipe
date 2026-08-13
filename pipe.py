from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

COMMENT_MARKER = "<!-- vyspec-qa-result -->"
RESULT_FILENAME = "vyspec-result.json"
VYSPEC_APP_PORT = 3000


class PipeConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PipeConfiguration:
    app_ready_timeout: int
    instructions: str | None
    instructions_file: str | None
    result_file: Path
    run_profile_id: str | None
    session_profile_id: str | None
    start_path: str | None


def optional_environment(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def load_configuration() -> PipeConfiguration:
    if not optional_environment("VSY_PROJECT_API_KEY"):
        raise PipeConfigurationError("VSY_PROJECT_API_KEY is required")

    comment_command = optional_environment("VYSPEC_COMMENT_COMMAND") == "true"
    run_profile_id = None if comment_command else optional_environment("RUN_PROFILE_ID")
    instructions = (
        optional_environment("VYSPEC_INSTRUCTIONS")
        if comment_command
        else optional_environment("INSTRUCTIONS")
    )
    instructions_file = None if comment_command else optional_environment("INSTRUCTIONS_FILE")
    if sum(bool(value) for value in (run_profile_id, instructions, instructions_file)) != 1:
        raise PipeConfigurationError(
            "set exactly one of RUN_PROFILE_ID, INSTRUCTIONS, or INSTRUCTIONS_FILE"
        )

    session_profile_id = None if comment_command else optional_environment("SESSION_PROFILE_ID")
    start_path = None if comment_command else optional_environment("START_PATH")
    if run_profile_id and (session_profile_id or start_path):
        raise PipeConfigurationError(
            "SESSION_PROFILE_ID and START_PATH are available only for direct instructions"
        )

    clone_directory = Path(
        optional_environment("BITBUCKET_CLONE_DIR") or Path.cwd()
    ).resolve()
    result_file = clone_directory / RESULT_FILENAME

    if instructions_file and not (clone_directory / instructions_file).is_file():
        raise PipeConfigurationError(
            f"INSTRUCTIONS_FILE does not exist: {instructions_file}"
        )

    raw_timeout = optional_environment("APP_READY_TIMEOUT") or "120"
    try:
        app_ready_timeout = int(raw_timeout)
    except ValueError as error:
        raise PipeConfigurationError("APP_READY_TIMEOUT must be an integer") from error
    if not 1 <= app_ready_timeout <= 600:
        raise PipeConfigurationError("APP_READY_TIMEOUT must be between 1 and 600")

    expected_sha = optional_environment("VYSPEC_EXPECTED_SHA")
    current_sha = optional_environment("BITBUCKET_COMMIT")
    if comment_command and (not expected_sha or expected_sha != current_sha):
        raise PipeConfigurationError(
            "the pull request changed before this pipeline started"
        )

    return PipeConfiguration(
        app_ready_timeout=app_ready_timeout,
        instructions=instructions,
        instructions_file=instructions_file,
        result_file=result_file,
        run_profile_id=run_profile_id,
        session_profile_id=session_profile_id,
        start_path=start_path,
    )


def runner_arguments(configuration: PipeConfiguration) -> list[str]:
    arguments = [
        "vsy",
        "run",
        "--app-ready-timeout",
        str(configuration.app_ready_timeout),
        "--result-file",
        str(configuration.result_file),
    ]
    if configuration.run_profile_id:
        arguments.extend(("--profile", configuration.run_profile_id))
    elif configuration.instructions:
        arguments.extend(("--instructions", configuration.instructions))
    else:
        arguments.extend(("--instructions-file", configuration.instructions_file or ""))
    if configuration.session_profile_id:
        arguments.extend(("--session-profile", configuration.session_profile_id))
    if configuration.start_path:
        arguments.extend(("--start-path", configuration.start_path))
    return arguments


def runner_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "CI": "true",
            "VSY_APP_PORT": str(VYSPEC_APP_PORT),
            "VSY_CI_BRANCH": os.getenv("VYSPEC_BRANCH") or os.getenv("BITBUCKET_BRANCH", ""),
            "VSY_CI_COMMIT_SHA": os.getenv("VYSPEC_EXPECTED_SHA") or os.getenv("BITBUCKET_COMMIT", ""),
            "VSY_CI_PROVIDER": "bitbucket",
            "VSY_CI_PULL_REQUEST_NUMBER": os.getenv("VYSPEC_CHANGE_REQUEST_NUMBER") or os.getenv("BITBUCKET_PR_ID", ""),
            "VSY_CI_REPOSITORY": os.getenv("BITBUCKET_REPO_FULL_NAME", ""),
            "VSY_HEADLESS": "true",
        }
    )
    return environment


def start_loopback_bridge() -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [
            "socat",
            f"TCP-LISTEN:{VYSPEC_APP_PORT},bind=127.0.0.1,reuseaddr,fork",
            f"TCP:host.docker.internal:{VYSPEC_APP_PORT}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def api_request(
    method: str,
    url: str,
    token: str,
    body: dict[str, object] | None = None,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def markdown_text(value: object) -> str:
    text = " ".join(str(value or "").split()).replace("@", "@\u200b")
    return re.sub(r"([`*_\[\]<>])", r"\\\1", text)


def comment_body(result: dict[str, object] | None) -> str:
    if result is None:
        return (
            f"{COMMENT_MARKER}\n## ⚠️ Vyspec QA — EXECUTION INCOMPLETE\n\n"
            "Vyspec could not produce a QA verdict. Review the Pipeline logs for the "
            "operational error."
        )

    verdict = result.get("qa_verdict")
    raw_findings = result.get("findings")
    findings = raw_findings if isinstance(raw_findings, list) else []
    if verdict == "failed":
        heading = "❌ Vyspec QA — FAILED"
        summary = "Vyspec confirmed defects in this pull request."
    elif verdict == "passed":
        heading = "✅ Vyspec QA — PASSED"
        summary = "Vyspec did not confirm any defects in this pull request."
    else:
        heading = "⚠️ Vyspec QA — EXECUTION INCOMPLETE"
        summary = "Vyspec could not produce a definitive QA verdict."

    execution = "✅ Completed" if verdict in {"passed", "failed"} else "⚠️ Incomplete"
    qa_verdict = (
        "❌ FAILED"
        if verdict == "failed"
        else "✅ PASSED"
        if verdict == "passed"
        else "Unavailable"
    )
    lines = [
        COMMENT_MARKER,
        f"## {heading}",
        "",
        summary,
        "",
        f"**Execution:** {execution}",
        f"**QA verdict:** {qa_verdict}",
        f"**Confirmed findings:** {len(findings)}",
    ]
    for index, finding in enumerate(findings[:10], start=1):
        if not isinstance(finding, dict):
            continue
        severity = markdown_text(finding.get("severity")).upper()
        title = markdown_text(finding.get("title"))
        observed = markdown_text(finding.get("observed"))[:300]
        lines.extend(("", f"{index}. **{severity} — {title}**"))
        if observed:
            lines.append(f"   {observed}")
    if len(findings) > 10:
        lines.extend(("", f"_{len(findings) - 10} more findings are available in Vyspec._"))
    run_url = markdown_text(result.get("run_url"))
    if run_url:
        lines.extend(("", f"[View findings, evidence, and execution trace →]({run_url})"))
    return "\n".join(lines)


def load_result(result_file: Path) -> dict[str, object] | None:
    if not result_file.is_file():
        return None
    raw_result = json.loads(result_file.read_text(encoding="utf-8"))
    return raw_result if isinstance(raw_result, dict) else None


def update_pull_request_comment(result_file: Path) -> None:
    token = optional_environment("BITBUCKET_VYSPEC_TOKEN")
    pull_request = optional_environment("BITBUCKET_PR_ID") or optional_environment(
        "VYSPEC_CHANGE_REQUEST_NUMBER"
    )
    repository = optional_environment("BITBUCKET_REPO_FULL_NAME")
    if not token or not pull_request or not repository:
        return

    encoded_repository = quote(repository, safe="/")
    base_url = (
        f"https://api.bitbucket.org/2.0/repositories/{encoded_repository}"
        f"/pullrequests/{quote(pull_request, safe='')}/comments"
    )
    response = api_request("GET", f"{base_url}?pagelen=100", token)
    raw_comments = response.get("values") if isinstance(response, dict) else None
    comments = raw_comments if isinstance(raw_comments, list) else []
    existing = next(
        (
            comment
            for comment in comments
            if isinstance(comment, dict)
            and isinstance(comment.get("content"), dict)
            and COMMENT_MARKER in str(comment["content"].get("raw", ""))
        ),
        None,
    )
    body: dict[str, object] = {"content": {"raw": comment_body(load_result(result_file))}}
    if existing is None:
        api_request("POST", base_url, token, body)
    else:
        api_request("PUT", f"{base_url}/{existing['id']}", token, body)


def main() -> int:
    os.umask(0)
    bridge: subprocess.Popen[bytes] | None = None
    result_file = Path(optional_environment("BITBUCKET_CLONE_DIR") or Path.cwd()) / RESULT_FILENAME
    exit_code = 2
    try:
        configuration = load_configuration()
        result_file = configuration.result_file
        result_file.unlink(missing_ok=True)
        bridge = start_loopback_bridge()
        completed = subprocess.run(
            runner_arguments(configuration),
            env=runner_environment(),
            check=False,
        )
        exit_code = completed.returncode
    except PipeConfigurationError as error:
        print(f"Vyspec error: {error}.", file=sys.stderr)
    except OSError as error:
        print(f"Vyspec error: could not start the runner: {error}.", file=sys.stderr)
    finally:
        if bridge is not None:
            bridge.terminate()
            try:
                bridge.wait(timeout=5)
            except subprocess.TimeoutExpired:
                bridge.kill()
        try:
            update_pull_request_comment(result_file)
        except Exception as error:
            print(
                f"Vyspec error: could not update the pull-request report: {error}.",
                file=sys.stderr,
            )
            if exit_code == 0:
                exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
