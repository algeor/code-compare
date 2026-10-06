from pathlib import Path

from pr_suggestion_metrics.demo_gradio import build_app


demo = build_app(model_dir=Path("models/pr_suggestion_coverage/demo_weak_local/model"))


if __name__ == "__main__":
    demo.launch()
