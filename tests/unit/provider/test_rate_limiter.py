import time
from unittest.mock import patch
from vocabgen.provider.rate_limiter import RateLimiter


def test_rate_limiter_allows_immediate_calls_when_unlimited():
    rl = RateLimiter(max_calls_per_minute=None)
    start = time.time()
    rl.acquire()
    rl.acquire()
    assert time.time() - start < 0.1


def test_rate_limiter_allows_immediate_calls_when_zero():
    """Zero or negative max_calls should disable rate limiting."""
    rl = RateLimiter(max_calls_per_minute=0)
    start = time.time()
    rl.acquire()
    rl.acquire()
    rl.acquire()
    assert time.time() - start < 0.1


def test_rate_limiter_allows_calls_within_limit():
    """Should allow calls up to the limit without sleeping."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        # Mock time to return consistent values
        mock_time.return_value = 1000.0

        rl = RateLimiter(max_calls_per_minute=5)

        # First 5 calls should not trigger sleep
        for _ in range(5):
            rl.acquire()

        mock_sleep.assert_not_called()
        assert len(rl._timestamps) == 5


def test_rate_limiter_blocks_when_limit_exceeded():
    """Should sleep when exceeding the rate limit."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        # Setup: 3 calls per minute allowed
        rl = RateLimiter(max_calls_per_minute=3)

        # Simulate 3 calls at t=0
        mock_time.return_value = 1000.0
        for _ in range(3):
            rl.acquire()

        # 4th call at t=10 should trigger sleep for ~50 seconds
        mock_time.return_value = 1010.0
        rl.acquire()

        # Should sleep for approximately 60 - 10 = 50 seconds
        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 49.5 < sleep_time < 50.5, f"Expected ~50s sleep, got {sleep_time}s"


def test_rate_limiter_calculates_correct_sleep_time():
    """Should calculate exact sleep time based on oldest timestamp."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=2)

        # First call at t=100
        mock_time.return_value = 100.0
        rl.acquire()

        # Second call at t=110
        mock_time.return_value = 110.0
        rl.acquire()

        # Third call at t=130 (30 seconds after first)
        # Should sleep for 60 - 30 = 30 seconds
        mock_time.return_value = 130.0
        rl.acquire()

        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 29.5 < sleep_time < 30.5, f"Expected ~30s sleep, got {sleep_time}s"


def test_rate_limiter_sliding_window_cleanup():
    """Old timestamps should be removed from the window."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=2)

        # First call at t=0
        mock_time.return_value = 0.0
        rl.acquire()

        # Second call at t=10
        mock_time.return_value = 10.0
        rl.acquire()

        # Third call at t=70 (after 60s window from first call)
        # First timestamp should be cleaned up, no sleep needed
        mock_time.return_value = 70.0
        rl.acquire()

        mock_sleep.assert_not_called()
        assert len(rl._timestamps) == 2  # Only the last 2 calls within window


def test_rate_limiter_multiple_cycles():
    """Should handle multiple rate limit cycles correctly."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=2)

        # First cycle: 2 calls at t=0
        mock_time.return_value = 0.0
        rl.acquire()
        rl.acquire()

        # Exceed limit at t=10 - should sleep ~50s
        mock_time.return_value = 10.0
        rl.acquire()
        assert mock_sleep.call_count == 1
        assert 49.5 < mock_sleep.call_args[0][0] < 50.5

        # After sleeping, we're now at t=60 (simulated)
        # Old timestamps are cleared, start fresh
        mock_time.return_value = 60.0
        rl.acquire()
        rl.acquire()

        # Should still only have slept once (from earlier)
        assert mock_sleep.call_count == 1


def test_rate_limiter_no_negative_sleep():
    """Should not sleep negative time if calculation goes negative."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=2)

        # First 2 calls at t=0
        mock_time.return_value = 0.0
        rl.acquire()
        rl.acquire()

        # Third call at t=70 (after window expires)
        # Should not sleep at all
        mock_time.return_value = 70.0
        rl.acquire()

        mock_sleep.assert_not_called()


def test_rate_limiter_precise_boundary_condition():
    """Test behavior exactly at the 60-second boundary."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=1)

        # First call at t=0
        mock_time.return_value = 0.0
        rl.acquire()

        # Second call exactly at t=60.0
        mock_time.return_value = 60.0
        rl.acquire()

        # Should not need to sleep (exactly at boundary)
        mock_sleep.assert_not_called()


def test_rate_limiter_high_rate_limit():
    """Test with a high rate limit to ensure deque performs well."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=100)

        mock_time.return_value = 1000.0

        # Should handle 100 calls without issue
        for _ in range(100):
            rl.acquire()

        mock_sleep.assert_not_called()
        assert len(rl._timestamps) == 100

        # 101st call should trigger sleep
        mock_time.return_value = 1001.0
        rl.acquire()

        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 58.5 < sleep_time < 59.5


def test_rate_limiter_fractional_timestamps():
    """Ensure fractional seconds are handled correctly."""
    with patch('time.sleep') as mock_sleep, patch('time.time') as mock_time:
        rl = RateLimiter(max_calls_per_minute=2)

        # Calls at fractional timestamps
        mock_time.return_value = 1000.5
        rl.acquire()

        mock_time.return_value = 1010.7
        rl.acquire()

        # Third call at t=1030.2
        # Should sleep for (1000.5 + 60) - 1030.2 = 30.3 seconds
        mock_time.return_value = 1030.2
        rl.acquire()

        mock_sleep.assert_called_once()
        sleep_time = mock_sleep.call_args[0][0]
        assert 29.8 < sleep_time < 30.8
