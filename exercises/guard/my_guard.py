"""EXERCISE 2: the guard that decides 401 / 429 / allowed.

Run the tests:   uv run pytest exercises/guard -q
(You finished the rate limiter in exercise 1. Here it is given to you as a
"fake" in the tests, so this exercise does not depend on your other code.)

THE SPEC
    Guard(keys, limiter)
        keys     list of valid API keys. EMPTY list = authentication is OFF.
        limiter  an object with .allow(caller) -> float (0.0 = ok, seconds > 0 = wait)
                 or None = no rate limiting.

    .check(api_key, client_ip) -> None
        Returns normally if the request may run. Otherwise RAISES HTTPException:

        1. If keys are configured:
             - api_key missing (None) or not one of the keys -> 401, "Missing or invalid API key"
             - otherwise the caller identity for rate limiting is the api_key
           If no keys are configured:
             - the caller identity is client_ip
        2. If there is a limiter: ask limiter.allow(caller).
             - result > 0 -> 429, "Rate limit exceeded", and the header
               Retry-After set to the wait rounded UP to whole seconds.
               (Simple way to round up here: int(wait) + 1)

    IMPORTANT ORDER: authentication first. A request with a bad key must be
    rejected WITHOUT touching the limiter (otherwise an attacker without a key
    could use up a real client's budget).

HINTS (open one at a time)
    - Raising: raise HTTPException(status_code=401, detail="...")
      With a header: HTTPException(status_code=429, detail="...", headers={"Retry-After": "13"})
    - Comparing keys: do NOT use ==. Use hmac.compare_digest(a.encode(), b.encode()).
      It takes the same time wherever the strings differ, so a timing measurement
      cannot reveal how many leading characters of a guess were right.
    - To avoid stopping at the first match (which also leaks timing), loop over ALL
      keys and remember if any matched.
    - Write a small helper method `_valid(self, api_key) -> bool`.
"""

import hmac  # noqa: F401  (you will need it)

from fastapi import HTTPException  # noqa: F401  (you will need it)


class Guard:
    def __init__(self, keys: list[str], limiter):
        # TODO: store what you need
        pass

    def check(self, api_key: str | None, client_ip: str) -> None:
        # TODO: implement the spec above, authentication first
        raise NotImplementedError
