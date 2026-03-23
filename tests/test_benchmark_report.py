from pathlib import Path
import unittest

from benchmark.report import parse_mongostat


class ParseMongostatTests(unittest.TestCase):
    def test_sample_log_produces_rows(self) -> None:
        rows = parse_mongostat(Path('benchmark/benchmark_logs/mongostat.log'))

        self.assertGreater(len(rows), 0)
        self.assertEqual(rows[0]['insert'], 1297)
        self.assertEqual(rows[0]['query'], 1295)
        self.assertEqual(rows[0]['connections'], 65)
        self.assertEqual(rows[0]['timestamp'], 'Mar 20 16:23:10.593')


if __name__ == '__main__':
    unittest.main()
