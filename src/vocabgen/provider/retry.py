import time
import random
import logging
from typing import Callable, Optional, TypeVar
from functools import wraps

T = TypeVar("T")
CallableReturningT = Callable[..., T]

logger = logging.getLogger("provider.retry")


def retry(
    max_retries: int = 3,
    max_backoff_seconds: float = 5.0,
) -> Callable[[CallableReturningT], CallableReturningT]:
    """
    Decorator to retry a function on failure with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts before giving up.
        max_backoff_seconds: Maximum time (in seconds) to sleep between retries.

    Usage:
        @retry(max_retries=3)
        def my_function(...):
            ...
    """

    def decorator(func: CallableReturningT) -> CallableReturningT:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    last_exception = e

                    func_name = getattr(func, "__name__", repr(func))
                    logger.warning(
                        "%s failed (attempt %d/%d): %s",
                        func_name,
                        attempt,
                        max_retries,
                        e,
                    )

                    if attempt == max_retries:
                        # Ensure we raise a valid exception object.
                        raise last_exception or RuntimeError("Unknown error in retry loop")

                    # Exponential backoff with jitter.
                    sleep_time = min(
                        max_backoff_seconds,
                        (2 ** (attempt - 1)) + random.random(),
                    )
                    time.sleep(sleep_time)

            # Should not reach here, but just in case.
            raise last_exception or RuntimeError("Retry loop ended unexpectedly")

        return wrapper

    return decorator
