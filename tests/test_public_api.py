import pr_suggestion_metrics


def test_public_api_exports_are_explicit_and_cached() -> None:
    assert set(pr_suggestion_metrics.__all__).issubset(dir(pr_suggestion_metrics))

    for name in pr_suggestion_metrics.__all__:
        first_value = getattr(pr_suggestion_metrics, name)
        second_value = getattr(pr_suggestion_metrics, name)

        assert first_value is second_value
        assert pr_suggestion_metrics.__dict__[name] is first_value
