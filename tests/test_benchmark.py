import unittest

from injectscope.benchmark import GATES, verify_blind
from injectscope.train import ROOT, folds, load


class BenchmarkTests(unittest.TestCase):
    def test_blind_sets_unchanged(self):
        self.assertTrue(verify_blind())

    def test_no_overlap_between_train_and_eval_sets(self):
        train = {r["text"].strip().lower() for r in load(ROOT / "data" / "train.jsonl")}
        for name in ("test", "hard", "blind", "blind2"):
            evaluation = {r["text"].strip().lower() for r in load(ROOT / "data" / f"{name}.jsonl")}
            self.assertEqual(train & evaluation, set(), name)

    def test_folds_are_stratified_and_complete(self):
        rows = load(ROOT / "data" / "train.jsonl")
        parts = folds(rows, 5)
        self.assertEqual(sorted(i for p in parts for i in p), list(range(len(rows))))
        ratios = [sum(rows[i]["label"] for i in p) / len(p) for p in parts]
        self.assertLess(max(ratios) - min(ratios), 0.05)

    def test_gates_defined_for_every_eval_set(self):
        self.assertEqual(set(GATES), {"test", "hard", "blind", "blind2"})


if __name__ == "__main__":
    unittest.main()
