from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

MODULE_PATH = Path(__file__).parents[1] / "pipe.py"
SPEC = importlib.util.spec_from_file_location("vyspec_bitbucket_pipe", MODULE_PATH)
assert SPEC and SPEC.loader
pipe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pipe
SPEC.loader.exec_module(pipe)


def configure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BITBUCKET_CLONE_DIR", str(tmp_path))
    monkeypatch.setenv("VSY_PROJECT_API_KEY", "vsy_live_test")


def test_saved_profile_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("RUN_PROFILE_ID", "profile-id")

    configuration = pipe.load_configuration()

    assert pipe.runner_arguments(configuration) == [
        "vsy",
        "run",
        "--app-ready-timeout",
        "120",
        "--result-file",
        str(tmp_path / "vyspec-result.json"),
        "--profile",
        "profile-id",
    ]


def test_one_time_profile_and_notes_must_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("ONE_TIME_PROFILE_FILE", ".vyspec/profile.json")
    monkeypatch.setenv("RUN_NOTES_FILE", ".vyspec/notes.json")
    (tmp_path / ".vyspec").mkdir()
    (tmp_path / ".vyspec/profile.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".vyspec/notes.json").write_text("[]", encoding="utf-8")

    arguments = pipe.runner_arguments(pipe.load_configuration())

    assert arguments[-4:] == [
        "--one-time",
        ".vyspec/profile.json",
        "--notes",
        ".vyspec/notes.json",
    ]


@pytest.mark.parametrize(
    ("run_profile", "one_time"),
    [(None, None), ("profile-id", ".vyspec/profile.json")],
)
def test_exactly_one_profile_selector_is_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    run_profile: str | None,
    one_time: str | None,
) -> None:
    configure(monkeypatch, tmp_path)
    if run_profile:
        monkeypatch.setenv("RUN_PROFILE_ID", run_profile)
    if one_time:
        monkeypatch.setenv("ONE_TIME_PROFILE_FILE", one_time)

    with pytest.raises(pipe.PipeConfigurationError, match="exactly one"):
        pipe.load_configuration()


def test_failed_qa_comment_reports_findings() -> None:
    body = pipe.comment_body(
        {
            "qa_verdict": "failed",
            "run_url": "https://app.vyspec.com/app/runs/run-id",
            "findings": [
                {
                    "severity": "high",
                    "title": "Total is inconsistent",
                    "observed": "$24 + $3 is displayed as $24",
                }
            ],
        }
    )

    assert "❌ Vyspec QA — FAILED" in body
    assert "**Confirmed findings:** 1" in body
    assert "HIGH — Total is inconsistent" in body
    assert "https://app.vyspec.com/app/runs/run-id" in body


def test_pull_request_comment_is_updated(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    result_file = tmp_path / "vyspec-result.json"
    result_file.write_text(
        json.dumps({"qa_verdict": "passed", "findings": []}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BITBUCKET_VYSPEC_TOKEN", "token")
    monkeypatch.setenv("BITBUCKET_PR_ID", "12")
    monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "vyspec/example")
    request = Mock(
        side_effect=[
            {
                "values": [
                    {
                        "id": 41,
                        "content": {"raw": f"{pipe.COMMENT_MARKER}\nold"},
                    }
                ]
            },
            {},
        ]
    )
    monkeypatch.setattr(pipe, "api_request", request)

    pipe.update_pull_request_comment(result_file)

    assert request.call_args_list[1].args[:2] == (
        "PUT",
        "https://api.bitbucket.org/2.0/repositories/vyspec/example/pullrequests/12/comments/41",
    )


def test_runner_environment_uses_bitbucket_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BITBUCKET_BRANCH", "feature/qa")
    monkeypatch.setenv("BITBUCKET_COMMIT", "abcdef")
    monkeypatch.setenv("BITBUCKET_PR_ID", "7")
    monkeypatch.setenv("BITBUCKET_REPO_FULL_NAME", "vyspec/example")

    environment = pipe.runner_environment()

    assert environment["VSY_APP_PORT"] == "3000"
    assert environment["VSY_CI_PROVIDER"] == "bitbucket"
    assert environment["VSY_CI_BRANCH"] == "feature/qa"
    assert environment["VSY_CI_COMMIT_SHA"] == "abcdef"
    assert environment["VSY_CI_PULL_REQUEST_NUMBER"] == "7"
    assert environment["VSY_CI_REPOSITORY"] == "vyspec/example"
    assert environment["VSY_HEADLESS"] == "true"
