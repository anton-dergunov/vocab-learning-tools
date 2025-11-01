import pytest
from unittest.mock import Mock, patch
from vocabgen.provider.retry import retry


def test_retry_success_first_try():
    func = Mock(return_value="ok")

    decorated = retry(max_retries=3)(func)
    result = decorated()

    assert result == "ok"
    func.assert_called_once()


def test_retry_eventual_success(monkeypatch):
    func = Mock(side_effect=[Exception("fail1"), Exception("fail2"), "success"])

    sleep_calls = []
    with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        decorated = retry(max_retries=3)(func)
        result = decorated()

    assert result == "success"
    assert func.call_count == 3
    assert sum(sleep_calls) >= 1  # should have slept between retries


def test_retry_failure_after_max_retries():
    func = Mock(side_effect=Exception("always fails"))
    decorated = retry(max_retries=3)(func)

    with pytest.raises(Exception) as excinfo:
        decorated()

    assert "always fails" in str(excinfo.value)
    assert func.call_count == 3


def test_retry_as_decoration():
    @retry(max_retries=3)
    def func():
        return "ok"

    result = func()

    assert result == "ok"


def test_retry_max_backoff():
    func = Mock(side_effect=Exception("always fails"))
    MAX_BACKOFF_SECONDS = 1.0

    sleep_calls = []
    with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        decorated = retry(max_retries=5, max_backoff_seconds=MAX_BACKOFF_SECONDS)(func)
        with pytest.raises(Exception):
            decorated()

    assert all(sleep <= MAX_BACKOFF_SECONDS for sleep in sleep_calls)
