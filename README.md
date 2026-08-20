# Bitbucket Pipelines Pipe: Vyspec QA

Run a saved Vyspec Profile or direct QA instructions against an application started in the same
Bitbucket Pipeline step.

## YAML Definition

Start the application on `0.0.0.0:3000`, then add the Pipe to the same step:

```yaml
pipelines:
  pull-requests:
    "**":
      - step:
          name: Vyspec QA
          script:
            - ./ci/start-app-for-vyspec.sh
            - pipe: docker://ghcr.io/vyspec/vyspec-bitbucket-pipe:1.3.1
              variables:
                VSY_PROJECT_API_KEY: $VSY_PROJECT_API_KEY
                RUN_PROFILE_ID: "<run-profile-id>"
          artifacts:
            - vyspec-result.json
```

The application is not exposed to the public internet. Bitbucket runs the Pipe in a separate
container, so it uses Bitbucket's internal build-host bridge and proxies the application back to
`127.0.0.1:3000` inside the Vyspec runner.

## Variables

| Variable | Required | Description |
| --- | --- | --- |
| `VSY_PROJECT_API_KEY` | Yes | Revocable Project API key stored as a secured repository variable. |
| `RUN_PROFILE_ID` | One execution source | UUID of a saved Run Profile. |
| `INSTRUCTIONS` | One execution source | Direct QA instructions. |
| `INSTRUCTIONS_FILE` | One execution source | Repository-relative plain-text QA instructions file. |
| `SESSION_PROFILE_ID` | No | Session Profile UUID for a direct authenticated Run. |
| `START_PATH` | No | Origin-relative start path for a direct Run. |
| `APP_READY_TIMEOUT` | No | Seconds to wait for the app; defaults to `120`. |
| `VSY_API_URL` | No | Vyspec API origin; defaults to `https://www.vyspec.com`. |

Set exactly one of `RUN_PROFILE_ID`, `INSTRUCTIONS`, or `INSTRUCTIONS_FILE`. Session Profile and
start-path values apply only to direct instructions; a saved Run Profile already owns that setup.

## Details

The Pipe contains the released Vyspec CLI and Chromium runtime. It preserves the canonical result
as `vyspec-result.json`, reports operational failures through the Pipeline exit status, and treats a
completed QA verdict of `failed` as a successful execution with confirmed defects. For a connected
repository, the Pipe sends its result to Vyspec and Vyspec updates one pull-request report through the
authorized Bitbucket account.

## Prerequisites

- A Vyspec Project connected to the Bitbucket repository. Vyspec creates the Project API key and
  secured repository variable automatically.
- An application started by the repository on `0.0.0.0:3000` in the same Pipeline step.

## Examples

Run a saved Profile:

```yaml
- pipe: docker://ghcr.io/vyspec/vyspec-bitbucket-pipe:1.3.1
  variables:
    VSY_PROJECT_API_KEY: $VSY_PROJECT_API_KEY
    RUN_PROFILE_ID: "20734cd8-afa8-4dcb-a71c-d64b15a7e850"
```

Run repository-owned direct instructions with an authenticated Session Profile:

```yaml
- pipe: docker://ghcr.io/vyspec/vyspec-bitbucket-pipe:1.3.1
  variables:
    VSY_PROJECT_API_KEY: $VSY_PROJECT_API_KEY
    INSTRUCTIONS_FILE: ".vyspec/verify-fix.md"
    SESSION_PROFILE_ID: "423e4567-e89b-42d3-a456-426614174000"
    START_PATH: "/account"
```

To support `@vyspec run` pull-request comments, also define a custom pipeline named
`vyspec-command`. Vyspec starts that pipeline with short-lived runtime variables after verifying
the webhook signature, commenter permission, open pull request, and exact head commit.
Pass `VYSPEC_COMMENT_COMMAND`, `VYSPEC_INSTRUCTIONS`, `VYSPEC_CHANGE_REQUEST_NUMBER`,
`VYSPEC_EXPECTED_SHA`, and `VYSPEC_BRANCH` through the Pipe's `variables` map in that custom step.

## Support

Open an issue at <https://github.com/Vyspec/vyspec-bitbucket-pipe/issues> with the Pipe version,
Pipeline logs, and reproduction details.

## License

MIT
