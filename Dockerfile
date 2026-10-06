FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY space ./space
COPY models/pr_suggestion_coverage/demo_weak_local/model ./models/pr_suggestion_coverage/demo_weak_local/model

RUN uv sync --locked --extra demo --no-dev

EXPOSE 7860

CMD ["uv", "run", "--locked", "--extra", "demo", "pr-suggestion-demo", "--server-name", "0.0.0.0", "--server-port", "7860"]
