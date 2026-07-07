# Sandboxed per-test coverage capture. Build/run this in YOUR environment; it executes the
# project's tests in an isolated, non-root, network-less container. Only coverage_modes.json leaves.
FROM python:3.12-slim
WORKDIR /work
# copy the project in read-only spirit; the container is disposable
COPY . /work
RUN useradd -m runner || true
USER runner
RUN pip install --no-cache-dir coverage pytest
CMD ["bash", "run_coverage.sh"]
