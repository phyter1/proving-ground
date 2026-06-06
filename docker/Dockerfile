# The Lean-backed checker image. Built FROM the community mathlib image so mathlib is
# already compiled — no 1-2hr build, no `lake exe cache get` dance at runtime.
#
# Run untrusted proofs with isolation (a submitted "proof" is arbitrary code; native_decide
# compiles and runs native code):
#   docker run --rm --network none --memory 8g --cpus 4 --pids-limit 256 \
#     --cap-drop ALL --security-opt no-new-privileges \
#     proving-ground-checker check /work/submission.lean
#
# Pin MATHLIB_TAG to the exact tag matching the corpus snapshot for cache hits + reproducibility.
ARG MATHLIB_TAG=latest
FROM leanprovercommunity/mathlib:${MATHLIB_TAG}

USER root

# Build the JSON proof-checking REPL once, into the image.
RUN git clone --depth 1 https://github.com/leanprover-community/repl /opt/repl \
    && cd /opt/repl \
    && lake build

# SafeVerify: kernel-replay + axiom-allowlist + statement-integrity anti-cheat gates.
RUN git clone --depth 1 https://github.com/GasStationManager/SafeVerify /opt/safeverify \
    && cd /opt/safeverify \
    && (lake exe cache get || true) \
    && lake build

# Python harness layer.
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip3 install --no-cache-dir --break-system-packages -e "/app[lean]"

# Drop privileges for running untrusted submissions.
RUN useradd -m checker
USER checker
WORKDIR /work

ENTRYPOINT ["python3", "-m", "proving_ground.cli"]
CMD ["--help"]
