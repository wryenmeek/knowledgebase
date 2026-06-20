import sys
import re

with open('tests/kb/test_write_utils.py', 'r') as f:
    tc = f.read()

tc = tc.replace('from unittest.mock import patch\n\nimport pytest\n', 'from unittest.mock import patch\nimport unittest\nfrom datetime import datetime\n\nimport pytest\n')

# Find the end of test_exclusive_write_lock_contention_reports_live_holder_metadata
# and append DarwinTimezoneFallbackTests

idx = tc.find('    def test_lock_unavailable_error_reports_dead_holder(self) -> None:')

insertion = """

class DarwinTimezoneFallbackTests(unittest.TestCase):
    def test_darwin_timezone_fallback_when_tz_zero(self) -> None:
        with patch("sys.platform", "darwin"):
            with patch("os.environ", {}):
                with patch("subprocess.run") as mock_run:
                    mock_result = unittest.mock.Mock()
                    mock_result.stdout = "Thu Jan  1 00:00:00 1970\\n"
                    mock_run.return_value = mock_result
                    with patch("scripts.kb.write_utils.datetime") as mock_datetime:
                        mock_now = mock_datetime.now.return_value
                        mock_now.astimezone.return_value.tzinfo = None
                        mock_datetime.strptime = datetime.strptime
                        with patch("time.mktime") as mock_mktime:
                            mock_mktime.return_value = 0.0
                            result = write_utils._darwin_pid_start_time_unix_seconds(1234)
                            mock_mktime.assert_called_once()
                            self.assertEqual(result, 0.0)

"""

# Let's just put it at the very end of the file. No indentation problems there.
tc = tc + insertion

with open('tests/kb/test_write_utils.py', 'w') as f:
    f.write(tc)
