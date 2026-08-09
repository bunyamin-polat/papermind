# One image, two entrypoints. The API and the UI share every dependency except
# Streamlit, and maintaining two Dockerfiles to save ~50 MB is a worse trade than
# shipping Streamlit into the API image. Compose runs the same image twice with
# different commands.

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, in their own layer: they change far less often than the code,
# so editing a source file does not reinstall torch.
#
# `uv.lock` resolves torch from the CPU index on Linux (see pyproject.toml). The
# default PyPI wheel bundles CUDA — 2.9 GB of `nvidia` packages plus 652 MB of
# triton — none of which a container without a GPU can use. That alone was 4.5 GB
# of the first build.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev


FROM python:3.12-slim AS runtime

# libgomp is required by torch; curl is for the container's own healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf

# The user is created *before* anything is copied, so every COPY can set ownership
# as it writes. A `chown -R` afterwards would rewrite the metadata of every file and
# make Docker duplicate the whole tree into a new layer — in the first build of this
# file that one instruction added 6.16 GB.
RUN useradd --create-home --uid 1000 papermind \
 && mkdir -p /app /opt/hf \
 && chown papermind:papermind /app /opt/hf

WORKDIR /app
USER papermind

COPY --from=builder --chown=papermind:papermind /app/.venv /app/.venv

# Bake the embedding model into the image — 419 MB, and worth it.
#
# Downloading it at startup keeps the image small and makes every cold start depend
# on HuggingFace being reachable and fast. At step 10 on scale-to-zero compute that
# is every request after an idle period.
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('BAAI/bge-base-en-v1.5')"

# Only *after* the model is in the image. Set before it, this flag blocks the very
# download it is meant to make unnecessary — which is how the first build of this
# file failed. Now the running container never reaches for the network: a missing
# model becomes a build failure rather than a production one.
ENV HF_HUB_OFFLINE=1

COPY --chown=papermind:papermind core/ ./core/
COPY --chown=papermind:papermind storage/ ./storage/
COPY --chown=papermind:papermind ingestion/ ./ingestion/
COPY --chown=papermind:papermind retrieval/ ./retrieval/
COPY --chown=papermind:papermind evaluation/ ./evaluation/
COPY --chown=papermind:papermind scripts/ ./scripts/
COPY --chown=papermind:papermind app/ ./app/
COPY --chown=papermind:papermind ui/ ./ui/

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
