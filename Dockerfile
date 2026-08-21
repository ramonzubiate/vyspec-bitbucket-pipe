FROM python:3.12.11-bookworm

ARG VYSPEC_VERSION=0.1.9

LABEL org.opencontainers.image.description="Run Vyspec QA in Bitbucket Pipelines"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/Vyspec/vyspec-bitbucket-pipe"
LABEL org.opencontainers.image.title="Vyspec Bitbucket Pipe"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends socat \
    && python -m pip install --no-cache-dir "vyspec==${VYSPEC_VERSION}" \
    && python -m playwright install --with-deps --only-shell chromium \
    && rm -rf /var/lib/apt/lists/*

COPY pipe.py /opt/vyspec/pipe.py

ENTRYPOINT ["python", "/opt/vyspec/pipe.py"]
