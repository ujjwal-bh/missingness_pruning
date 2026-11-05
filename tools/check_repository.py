"""Check a code-only research release without opening any external research data."""
from pathlib import Path
import ast
import hashlib
import json
import re
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[1]
DATA_SUFFIXES = {'.csv', '.tsv', '.parquet', '.feather', '.arrow', '.npy', '.npz', '.pt', '.pth',
                 '.pkl', '.pickle', '.joblib', '.ckpt', '.gz', '.zip', '.dump', '.backup', '.db',
                 '.h5', '.hdf5', '.docx', '.pdf'}
IGNORED_DIRS = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    files = [p for p in REPO.rglob('*') if p.is_file()
             and not any(part in IGNORED_DIRS for part in p.relative_to(REPO).parts)]
    errors = []
    for path in files:
        rel = path.relative_to(REPO).as_posix()
        if path.suffix.lower() in DATA_SUFFIXES:
            errors.append('Unexpected data/document artifact: ' + rel)
        if path.name.startswith('.env') or path.name in {'.pgpass', 'pgpass.conf'}:
            errors.append('Credential/config secret file: ' + rel)
        if path.stat().st_size > 2 * 1024 * 1024:
            errors.append('Unexpected file larger than 2 MiB: ' + rel)
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=rel)
        if path.suffix in {'.py', '.ps1', '.json', '.yml', '.yaml', '.md', '.sql'}:
            text = path.read_text(encoding='utf-8-sig')
            if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text):
                errors.append('Private key material: ' + rel)
            if re.search(r'(?i)postgres(?:ql)?://[^\s:/]+:[^\s@]+@', text):
                errors.append('Password-bearing connection URL: ' + rel)
            if re.search(r'(?i)(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})', text):
                errors.append('Possible GitHub credential: ' + rel)
    record = json.loads((REPO / 'provenance/code_cleaning.json').read_text())
    for entry in record['files']:
        path = REPO / entry['path']
        tree = ast.dump(ast.parse(path.read_text(encoding='utf-8-sig')), include_attributes=False)
        if hashlib.sha256(tree.encode()).hexdigest() != entry['original_AST_sha256']:
            errors.append('Historical Python behavior changed: ' + entry['path'])
        if sha(path) != entry['release_sha256']:
            errors.append('Release source hash changed: ' + entry['path'])
    layout = json.loads((REPO / 'provenance/workspace_layout.json').read_text())
    for dest, src in layout.items():
        if Path(dest).is_absolute() or '..' in Path(dest).parts or not (REPO / src).is_file():
            errors.append('Invalid private workspace mapping: ' + dest)
    receipt = json.loads((REPO / 'config/reference_source_audit.json').read_text())
    for rel, digest in receipt['source_sha256'].items():
        if sha(REPO / layout[rel]) != digest:
            errors.append('Hash-bound reference source changed: ' + rel)
    manifest = REPO / 'provenance/release_manifest.json'
    if manifest.exists():
        for rel, digest in json.loads(manifest.read_text())['sha256'].items():
            if sha(REPO / rel) != digest:
                errors.append('Release file changed since organization: ' + rel)
    git = shutil.which('git')
    if git and (REPO / '.git').exists():
        examples = ['data/example.csv', 'model_results/weights.pt', 'predictions_local.csv',
                    '.env', 'pgpass.conf', 'records.jsonl', 'database.dump', 'cache.npy']
        for example in examples:
            result = subprocess.run([git, 'check-ignore', '--no-index', '-q', example], cwd=REPO)
            if result.returncode != 0:
                errors.append('Git exclusion missing: ' + example)
        names = subprocess.check_output([git, 'ls-files', '--cached', '-z'], cwd=REPO).decode().split('\0')
        for name in filter(None, names):
            if Path(name).suffix.lower() in DATA_SUFFIXES or Path(name).name.startswith('.env'):
                errors.append('Restricted artifact already tracked: ' + name)
        ignored = subprocess.run([git, 'check-ignore', '--no-index', '--stdin'], cwd=REPO,
                                 input='\n'.join(p.relative_to(REPO).as_posix() for p in files) + '\n',
                                 text=True, capture_output=True)
        if ignored.returncode not in {0, 1}:
            errors.append('Could not inspect Git exclusions: ' + ignored.stderr)
        if ignored.stdout.strip():
            errors.append('Intended release files unexpectedly ignored: ' + ignored.stdout.strip())
        attr = subprocess.check_output([git, 'check-attr', 'text', '--',
                                        'source_preparation/07_build_mimic_core_candidate_features.sql'],
                                       cwd=REPO, text=True)
        if not attr.strip().endswith('text: unset'):
            errors.append('Automatic line-ending conversion could break reference source hashes.')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(json.dumps({'status': 'passed', 'release_files_checked': len(files),
                      'historical_Python_AST_checks': len(record['files']),
                      'reference_source_hashes': len(receipt['source_sha256']),
                      'data_files_in_repository': 0, 'git_checks_run': bool(git and (REPO / '.git').exists()),
                      'secret_scan': 'pattern checks passed; no network access'}, indent=2))


if __name__ == '__main__':
    main()
