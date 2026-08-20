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


def test_direct_instructions_file_can_select_a_session_and_start_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("INSTRUCTIONS_FILE", ".vyspec/qa.md")
    monkeypatch.setenv("SESSION_PROFILE_ID", "session-id")
    monkeypatch.setenv("START_PATH", "/checkout")
    (tmp_path / ".vyspec").mkdir()
    (tmp_path / ".vyspec/qa.md").write_text("Verify checkout.", encoding="utf-8")

    arguments = pipe.runner_arguments(pipe.load_configuration())

    assert arguments[-6:] == [
        "--instructions-file",
        ".vyspec/qa.md",
        "--session-profile",
        "session-id",
        "--start-path",
        "/checkout",
    ]


@pytest.mark.parametrize(
    ("run_profile", "instructions", "instructions_file"),
    [
        (None, None, None),
        ("profile-id", "Verify checkout", None),
        (None, "Verify checkout", ".vyspec/qa.md"),
    ],
)
def test_exactly_one_execution_source_is_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    run_profile: str | None,
    instructions: str | None,
    instructions_file: str | None,
) -> None:
    configure(monkeypatch, tmp_path)
    if run_profile:
        monkeypatch.setenv("RUN_PROFILE_ID", run_profile)
    if instructions:
        monkeypatch.setenv("INSTRUCTIONS", instructions)
    if instructions_file:
        monkeypatch.setenv("INSTRUCTIONS_FILE", instructions_file)

    with pytest.raises(pipe.PipeConfigurationError, match="exactly one"):
        pipe.load_configuration()


def test_saved_profile_rejects_direct_run_options(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("RUN_PROFILE_ID", "profile-id")
    monkeypatch.setenv("START_PATH", "/checkout")

    with pytest.raises(pipe.PipeConfigurationError, match="direct instructions"):
        pipe.load_configuration()


def test_pull_request_report_is_sent_through_vyspec(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    run_id = "00000000-0000-4000-8000-000000000001"
    result_file = tmp_path / "vyspec-result.json"
    result_file.write_text(
        json.dumps({
            "qa_verdict": "passed",
            "findings": [],
            "run_id": run_id,
            "run_url": f"https://www.vyspec.com/app/runs/{run_id}",
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("BITBUCKET_PR_ID", "12")
    monkeypatch.setenv("BITBUCKET_REPO_UUID", "{repository}")
    request = Mock(return_value={"reported": True})
    monkeypatch.setattr(pipe, "api_request", request)

    pipe.report_pull_request(result_file)

    assert request.call_args.args == (
        "https://www.vyspec.com/api/v1/integrations/bitbucket/report",
        "vsy_live_test",
        {
            "change_request_number": 12,
            "provider_repository_id": "{repository}",
            "result": {
                "qa_verdict": "passed",
                "findings": [],
                "run_id": run_id,
                "run_url": f"https://www.vyspec.com/app/runs/{run_id}",
            },
        },
    )


def test_pull_request_report_never_sends_the_project_key_to_the_run_url_origin(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    result_file = tmp_path / "vyspec-result.json"
    result_file.write_text(
        json.dumps({"run_url": "https://attacker.example/runs/1"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BITBUCKET_PR_ID", "12")
    monkeypatch.setenv("BITBUCKET_REPO_UUID", "{repository}")
    monkeypatch.setenv("VSY_API_URL", "https://app.vyspec.test")
    request = Mock(return_value={"reported": True})
    monkeypatch.setattr(pipe, "api_request", request)

    pipe.report_pull_request(result_file)

    assert request.call_args.args[0] == (
        "https://app.vyspec.test/api/v1/integrations/bitbucket/report"
    )


def test_vyspec_api_origin_rejects_insecure_remote_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VSY_API_URL", "http://attacker.example")

    with pytest.raises(ValueError, match="HTTPS origin"):
        pipe.vyspec_api_origin()


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
    assert environment["VSY_API_URL"] == "https://www.vyspec.com"


def test_runner_environment_honors_a_configured_api_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VSY_API_URL", "https://staging.vyspec.test/")

    environment = pipe.runner_environment()

    assert environment["VSY_API_URL"] == "https://staging.vyspec.test"


def test_comment_command_overrides_saved_profile_and_pins_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("RUN_PROFILE_ID", "automatic-regression-profile")
    monkeypatch.setenv("VYSPEC_COMMENT_COMMAND", "true")
    monkeypatch.setenv("VYSPEC_INSTRUCTIONS", "Verify the new checkout behavior.")
    monkeypatch.setenv("VYSPEC_EXPECTED_SHA", "a" * 40)
    monkeypatch.setenv("BITBUCKET_COMMIT", "a" * 40)
    monkeypatch.setenv("VYSPEC_BRANCH", "feature/checkout")
    monkeypatch.setenv("VYSPEC_CHANGE_REQUEST_NUMBER", "19")

    configuration = pipe.load_configuration()
    environment = pipe.runner_environment()

    assert configuration.run_profile_id is None
    assert configuration.instructions == "Verify the new checkout behavior."
    assert environment["VSY_CI_BRANCH"] == "feature/checkout"
    assert environment["VSY_CI_COMMIT_SHA"] == "a" * 40
    assert environment["VSY_CI_PULL_REQUEST_NUMBER"] == "19"


def test_comment_command_rejects_a_moved_pull_request(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configure(monkeypatch, tmp_path)
    monkeypatch.setenv("VYSPEC_COMMENT_COMMAND", "true")
    monkeypatch.setenv("VYSPEC_INSTRUCTIONS", "Verify checkout.")
    monkeypatch.setenv("VYSPEC_EXPECTED_SHA", "a" * 40)
    monkeypatch.setenv("BITBUCKET_COMMIT", "b" * 40)

    with pytest.raises(pipe.PipeConfigurationError, match="changed"):
        pipe.load_configuration()
