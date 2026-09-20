# -*- coding: utf-8 -*-
"""계정이 준비되지 않았을 때 네트워크를 두드리지 않고 멈추는지."""

import unittest

from korail_monitor.cli import looks_like_placeholder, main


class PlaceholderCredentialTest(unittest.TestCase):
    def test_example_values_are_rejected(self):
        self.assertTrue(looks_like_placeholder("010-1234-5678", "비밀번호"))
        self.assertTrue(looks_like_placeholder("01012345678", "실제비밀번호"))
        self.assertTrue(looks_like_placeholder("", ""))

    def test_real_looking_values_pass(self):
        self.assertFalse(looks_like_placeholder("010-9876-5432", "s3cret!"))

    def test_main_exits_without_touching_the_network(self, ):
        import os

        saved = {k: os.environ.get(k) for k in ("KORAIL_ID", "KORAIL_PW")}
        os.environ["KORAIL_ID"] = "010-1234-5678"
        os.environ["KORAIL_PW"] = "비밀번호"
        try:
            self.assertEqual(main(["--once", "--log", "none"]), 2)
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
