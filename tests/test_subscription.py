import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class SubscriptionDownloadTests(unittest.TestCase):
    def test_download_uses_browser_like_user_agent_and_timeout(self):
        from subscription import Subscription

        subscription = Subscription.__new__(Subscription)
        response = MagicMock()
        response.text = "subscription payload"

        with patch("subscription.requests.get", return_value=response) as get:
            self.assertEqual(subscription._download("https://example.com/sub"), "subscription payload")

        get.assert_called_once_with(
            "https://example.com/sub",
            timeout=30,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
