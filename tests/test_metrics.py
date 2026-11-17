import unittest

from injectscope.metrics import best_threshold, percentile, roc_auc, scores


class MetricTests(unittest.TestCase):
    def test_scores(self):
        s = scores([1, 1, 0, 0], [1, 0, 1, 0])
        self.assertEqual((s["tp"], s["fp"], s["fn"], s["tn"]), (1, 1, 1, 1))
        self.assertEqual(s["f1"], 0.5)
        self.assertEqual(s["fpr"], 0.5)

    def test_auc(self):
        self.assertEqual(roc_auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]), 1.0)
        self.assertEqual(roc_auc([1, 0], [0.5, 0.5]), 0.5)  # ties count half
        self.assertEqual(roc_auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]), 0.0)

    def test_best_threshold_is_middle_of_tied_range(self):
        t = best_threshold([1, 0], [0.9, 0.1])
        self.assertTrue(0.4 <= t <= 0.6, t)

    def test_percentile(self):
        self.assertEqual(percentile([1, 2, 3, 4, 5], 0.5), 3)
        self.assertEqual(percentile([], 0.9), 0.0)


if __name__ == "__main__":
    unittest.main()
