import csv
import tempfile
import unittest
from pathlib import Path
from chord_comparison import compare, normalize, parse_csv, save_report


class ChordComparisonTests(unittest.TestCase):
    def test_enharmonic_and_minor(self):
        self.assertEqual(normalize('Dbm7'), ('C#','min'))
        self.assertEqual(normalize('Cmaj7'), ('C','maj'))
        self.assertEqual(normalize('Am'), ('A','min'))

    def test_perfect_reference(self):
        events = [(0, 'C'), (2, 'Am'), (4, 'F'), (6, 'G')]
        result = compare(events, events, end_seconds=8)
        self.assertEqual(result['exact_percent'], 100)
        self.assertEqual(result['root_percent'], 100)
        self.assertEqual(result['intervals'], [])

    def test_mismatched_chord_reports_interval(self):
        prediction = [(0, 'C'), (2, 'D'), (4, 'G')]
        reference = [(0, 'C'), (2, 'Dm'), (4, 'G')]
        result = compare(prediction, reference, end_seconds=6, step=.25)
        self.assertEqual(result['root_percent'], 100)
        self.assertAlmostEqual(result['exact_percent'], 66.7, places=1)
        self.assertEqual(len(result['intervals']), 1)
        self.assertEqual(result['intervals'][0]['riffLab'], 'D')

    def test_csv_loading_and_export(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'reference.csv'
            source.write_text('time,chord\n00:00,C\n00:02,Am\n', encoding='utf-8')
            events = parse_csv(source)
            self.assertEqual(events, [(0.0, 'C'), (2.0, 'Am')])
            report = compare(events, events, end_seconds=4)
            target = Path(temp) / 'report.csv'
            save_report(target, report)
            with target.open(newline='', encoding='utf-8') as file:
                rows = list(csv.reader(file))
            self.assertEqual(rows[0], ['start_seconds','end_seconds','RiffLab','reference'])

if __name__ == '__main__':
    unittest.main()
