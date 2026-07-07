# Sandboxed per-test coverage capture. Build/run this in YOUR environment; it executes the
# project's tests in an isolated, non-root, network-less container. Only coverage_modes.json leaves.
FROM rust:1
WORKDIR /work
# copy the project in read-only spirit; the container is disposable
COPY . /work
RUN useradd -m runner || true
USER runner
RUN cargo install cargo-llvm-cov 2>/dev/null || true
CMD ["bash", "run_coverage.sh"]
