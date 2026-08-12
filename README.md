# Bitbucket Pipelines Pipe: Vyspec QA

Run saved or one-time Vyspec QA against an application started in the same Bitbucket Pipeline step.

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
            - pipe: docker://ghcr.io/ramonzubiate/vyspec-bitbucket-pipe:1.0.0
              variables:
                VSY_PROJECT_API_KEY: $VSY_PROJECT_API_KEY
                RUN_PROFILE_ID: "<run-profile-id>"
                BITBUCKET_VYSPEC_TOKEN: $BITBUCKET_VYSPEC_TOKEN
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
| `RUN_PROFILE_ID` | One profile selector is required | UUID of a saved Run Profile. |
| `ONE_TIME_PROFILE_FILE` | One profile selector is required | Repository-relative one-time Run Profile JSON file. |
| `RUN_NOTES_FILE` | No | Repository-relative JSON array of customer-supplied Run notes. |
| `APP_READY_TIMEOUT` | No | Seconds to wait for the app; defaults to `120`. |
| `BITBUCKET_VYSPEC_TOKEN` | No | Repository access token with pull-request write permission for one maintained PR comment. |
| `VSY_API_URL` | No | Vyspec API origin; defaults to `https://app.vyspec.com`. |

Set either `RUN_PROFILE_ID` or `ONE_TIME_PROFILE_FILE`, never both.

## Details

The Pipe contains the released Vyspec CLI and Chromium runtime. It preserves the canonical result
as `vyspec-result.json`, reports operational failures through the Pipeline exit status, and treats a
completed QA verdict of `failed` as a successful execution with confirmed defects. When a Bitbucket
token is supplied, each rerun updates one existing pull-request comment instead of creating duplicates.

## Prerequisites

- A Vyspec Project and Project API key.
- An application started by the repository on `0.0.0.0:3000` in the same Pipeline step.
- `VSY_PROJECT_API_KEY` stored as a secured Bitbucket repository variable.
- Optionally, a repository access token with pull-request write permission stored as
  `BITBUCKET_VYSPEC_TOKEN`.

## Examples

Run a saved Profile:

```yaml
- pipe: docker://ghcr.io/ramonzubiate/vyspec-bitbucket-pipe:1.0.0
  variables:
    VSY_PROJECT_API_KEY: $VSY_PROJECT_API_KEY
    RUN_PROFILE_ID: "20734cd8-afa8-4dcb-a71c-d64b15a7e850"
```

Run a repository-owned one-time Profile and attach notes:

```yaml
- pipe: docker://ghcr.io/ramonzubiate/vyspec-bitbucket-pipe:1.0.0
  variables:
    VSY_PROJECT_API_KEY: $VSY_PROJECT_API_KEY
    ONE_TIME_PROFILE_FILE: ".vyspec/verify-fix.json"
    RUN_NOTES_FILE: ".vyspec/run-notes.json"
    BITBUCKET_VYSPEC_TOKEN: $BITBUCKET_VYSPEC_TOKEN
```

## Support

Open an issue at <https://github.com/ramonzubiate/vyspec-bitbucket-pipe/issues> with the Pipe version,
Pipeline logs, and reproduction details.

## License

MIT
