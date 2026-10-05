# -*- coding: utf-8 -*-

import unittest

import pandas as pd

from strategy_beauty import calculate_beauty_score


def make_df(values):
    dates = pd.date_range("2026-01-01", periods=len(values), freq="B")
    return pd.DataFrame(
        {
            "date": dates,
            "high": values,
            "low": values,
            "close": values,
        }
    )


class StrategyBeautyTests(unittest.TestCase):
    def test_uptrend_scores_higher_than_downtrend(self):
        up = [100 + idx * 0.25 for idx in range(260)]
        down = [165 - idx * 0.25 for idx in range(260)]
        up_score = calculate_beauty_score(make_df(up))["beauty_score"]
        down_score = calculate_beauty_score(make_df(down))["beauty_score"]
        self.assertGreater(up_score, down_score)
        self.assertGreaterEqual(up_score, 65)

    def test_short_history_is_insufficient(self):
        result = calculate_beauty_score(make_df([100 + idx for idx in range(50)]))
        self.assertIsNone(result["beauty_score"])
        self.assertEqual(result["beauty_status"], "INSUFFICIENT_DATA")

    def test_score_and_components_are_bounded(self):
        values = [100 + idx * 0.2 for idx in range(260)]
        result = calculate_beauty_score(make_df(values))
        self.assertGreaterEqual(result["beauty_score"], 0)
        self.assertLessEqual(result["beauty_score"], 100)
        self.assertEqual(sum(result["beauty_components"].values()), result["beauty_score"])


if __name__ == "__main__":
    unittest.main()
