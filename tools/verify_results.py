"""Verify saved summaries from an explicitly supplied external aggregate evidence folder."""
from pathlib import Path
import argparse
import runpy

REPO = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', required=True, type=Path,
                        help='External folder containing aggregate_results and optional SHA256SUMS.json')
    args = parser.parse_args()
    evidence = args.evidence_root.resolve()
    if evidence == REPO or evidence.is_relative_to(REPO):
        raise ValueError('Keep aggregate evidence outside this code repository.')
    if not (evidence / 'aggregate_results').is_dir():
        raise FileNotFoundError('Expected aggregate_results under --evidence-root.')
    for name in ['verify_aggregate_package.py', 'verify_focused_aggregate_evidence.py']:
        namespace = runpy.run_path(str(REPO / 'tools/verification' / name))
        function = namespace['main']
        function.__globals__['P'] = evidence
        function.__globals__['A'] = evidence / 'aggregate_results/focused_amendment'
        function()


if __name__ == '__main__':
    main()
