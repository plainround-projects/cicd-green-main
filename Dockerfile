# The artifact the pipeline built, as an image: installs the checksum-verified wheel from dist/ and nothing else.
# Built by `make deploy-local`, which verifies dist/SHA256SUMS first. Nothing here serves traffic; the health command is the check.
FROM python:3.12.8-slim-bookworm@sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock

COPY dist/*.whl ./
RUN pip install --no-deps ./*.whl && rm ./*.whl

RUN useradd --system --uid 10001 --no-create-home app
USER app

HEALTHCHECK --interval=30s --timeout=20s --retries=3 CMD ["small-service", "health"]
CMD ["small-service", "health"]
