$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
python (Join-Path $root 'tools/repository/normalize_source_map.py')
python (Join-Path $root 'tools/repository/refresh_repository_manifest.py')
python (Join-Path $root 'tools/repository/check_repository.py')
python -m py_compile `
    (Join-Path $root 'tools/repository/check_repository.py') `
    (Join-Path $root 'tools/repository/normalize_source_map.py') `
    (Join-Path $root 'tools/repository/refresh_repository_manifest.py') `
    (Join-Path $root 'tools/repository/sanitize_snapshot.py') `
    (Join-Path $root 'tools/repository/stage_manifest_files.py') `
    (Join-Path $root 'tools/repository/sync_allowlisted_docs.py') `
    (Join-Path $root 'tools/repository/sync_allowlisted_sources.py')
python (Join-Path $root 'tools/repository/stage_manifest_files.py') --verify-only
# Imported upstream snapshots intentionally retain their original formatting
# (including Markdown hard-break spaces). Keep whitespace gates focused on
# repository-owned control files and documentation.
$ownedPaths = @(
    '.editorconfig', '.gitattributes', '.gitignore', 'README.md',
    'CONTRIBUTING.md', 'SECURITY.md', 'THIRD_PARTY.md', 'check.ps1',
    'docs', 'tools/repository', 'artifacts/README.md',
    'artifacts/EXTERNAL-ARTIFACTS.md', 'artifacts/EXTERNAL-ARTIFACTS.json'
)
git -C $root diff --check -- $ownedPaths
git -C $root diff --cached --check -- $ownedPaths
