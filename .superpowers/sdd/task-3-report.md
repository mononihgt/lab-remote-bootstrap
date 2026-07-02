# Task 3 Bugfix Report: Subscription download User-Agent

## What changed

- Updated `lib/subscription.py` so `Subscription._download(url)` sends a browser-like `User-Agent` header with `requests.get(...)` while keeping `timeout=30` and the existing `raise_for_status()` / `SubscriptionError` wrapping behavior.
- Added `tests/test_subscription.py` with a focused regression test for `_download(...)`.

## TDD evidence

### RED

- Ran `python3 -m unittest tests.test_subscription -v`
- Result before the code change:
  - `requests.get(...)` was called with `timeout=30`
  - it did **not** include the expected `headers={"User-Agent": ...}`
  - the test failed with an assertion that the expected call was not found

### GREEN

- After the production change, reran `python3 -m unittest tests.test_subscription -v`
- Result: passed

## Verification

- Focused test: `python3 -m unittest tests.test_subscription -v`
- Full suite: `python3 -m unittest discover -s tests -p 'test*.py' -v`

Both commands completed successfully.

## Notes

- No real subscription URL was written into any committed file.
- The remote deploy tunnel behavior and subscription storage format were left unchanged.
