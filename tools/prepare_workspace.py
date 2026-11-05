"""Stage a new external private workspace; never train models or change a database."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

REPO = Path(__file__).resolve().parents[1]


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare(work, research_root=None, code_only=False):
    work = Path(work).resolve()
    if work == REPO or work.is_relative_to(REPO) or REPO.is_relative_to(work):
        raise ValueError('Choose a private work directory outside the repository and its ancestors.')
    if work.exists():
        raise FileExistsError('Use a new directory; existing runs are never overwritten.')
    layout = json.loads((REPO / 'provenance/workspace_layout.json').read_text())
    receipt = json.loads((REPO / 'config/export_verification_confirmed_2026_10_15.json').read_text())
    source = Path(research_root).resolve() if research_root is not None else None
    if not code_only:
        if source is None:
            raise ValueError('Supply --research-root, or use --code-only for synthetic tests.')
        if source == REPO or source.is_relative_to(REPO):
            raise ValueError('Patient exports must be stored outside the Git repository.')
        if source == work or source.is_relative_to(work):
            raise ValueError('Use a new private run directory separate from the source data tree.')
        for name, expected in receipt['inputs'].items():
            path = source / 'model_preparation' / name
            if sha(path) != expected['sha256']:
                raise ValueError('Validated export hash mismatch: ' + name)
    for dest, rel in layout.items():
        target = work / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)
    if not code_only:
        for name in receipt['inputs']:
            shutil.copyfile(source / 'model_preparation' / name, work / 'model_preparation' / name)
    (work / 'PRIVATE_WORKSPACE_DO_NOT_PUBLISH.txt').write_text(
        'Keep this run outside Git. Training creates restricted patient data, partitions, predictions and weights.\n',
        encoding='utf-8',
    )
    print('Prepared external workspace: ' + str(work))
    print('No training, scoring or database changes performed.')
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--research-root', type=Path)
    parser.add_argument('--code-only', action='store_true')
    args = parser.parse_args()
    prepare(args.work_dir, args.research_root, args.code_only)


if __name__ == '__main__':
    main()
