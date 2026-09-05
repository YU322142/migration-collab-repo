# GitHub Public Repository Duplicate Audit and Manual Identification

Audit date: 2026-09-05

## Conclusion

- **Exact repository-name duplicates: 0.** Public repositories under `YU322142`
  were grouped case-insensitively by complete name; no duplicate name exists.
- **New standalone repositories: 20.** All are public, use `main` as the default
  branch, and contain their own README and build boundary.
- **Intentional source overlap: yes.** The 20 standalone repositories were
  copied from their corresponding paths in `migration-collab-repo`. This is an
  intentional “project home + collaboration index” layout, not an accidental
  duplicate project.

## Manual identification rules

### 1. Identify the repository role first

| Repository | Role | Keep? |
| --- | --- | --- |
| `migration-collab-repo` | Index, audits, migration tools, cross-project docs | Keep; do not delete |
| The 20 new repositories | Per-project source, patch, or data snapshot | Keep as project homes |
| `MCSync`, `MineAstr`, `Chest-Colorizer-NeoForge`, `ImmersivePaintings`, `Toms-Storage` | Existing standalone maintenance projects | Keep; do not merge into the index |
| Archived `Create-Fly`, `sable`, `Veil`, `Simulated-Project`, etc. | Historical/unfinished snapshots | Leave archived; not current projects |

### 2. Confirm by project name

The mapping below is authoritative. GitHub pages, website links, and release
tooling should use the standalone repository on the right; the path on the left
is only for tracing the source in the collaboration index.

| Index source path | Standalone repository |
| --- | --- |
| `outputs/projects/cctweaked-startup-shutdown-guard-neoforge` | `CCTweaked-Startup-Shutdown-Guard` |
| `outputs/projects/create-carriage-orientation-guard-neoforge` | `Create-Carriage-Orientation-Guard` |
| `outputs/projects/create-chute-unload-guard-neoforge` | `Create-Chute-Unload-Guard` |
| `outputs/projects/create-dynamic-blocking-neoforge` | `Create-Dynamic-Blocking` |
| `outputs/projects/create-saveddata-probe` | `Create-SavedData-Probe` |
| `outputs/projects/deferred-content-protection-neoforge` | `Deferred-Content-Protection` |
| `outputs/projects/hardcore-revival-death-message-fix-neoforge` | `Hardcore-Revival-Death-Message-Fix` |
| `outputs/projects/heightmap-384-to-544-compat-neoforge` | `Heightmap-384-to-544-Compat` |
| `outputs/projects/kaleidoscope-cookery-scarecrow-compat` | `Kaleidoscope-Cookery-Scarecrow-Compat` |
| `outputs/projects/kaleidoscope-nether-backport` | `Kaleidoscope-Nether-Backport` |
| `outputs/projects/mishanguc-pale-oak-equivalence` | `MishangUC-Pale-Oak-Equivalence` |
| `outputs/projects/poi-migration-diagnostic` | `POI-Migration-Diagnostic` |
| `outputs/projects/potted-farms-1.21.1-equivalence` | `Potted-Farms-1.21.1-Equivalence` |
| `outputs/projects/recipe-set-diagnostic` | `Recipe-Set-Diagnostic` |
| `outputs/projects/resource-error-overlay-1.21.1` | `Migration-Resource-Error-Overlay` |
| `outputs/projects/waypoint-fire-equivalence` | `Waypoint-Fire-Equivalence` |
| `projects/patches/tlm-patchouli-spawn-box-balance` | `TLM-Patchouli-Spawn-Box-Balance` |
| `projects/patches/worldedit-7.3.8-direction-property-fix` | `WorldEdit-Direction-Property-Fix` |
| `projects/patches/xiyuslogin-auto-session-ota` | `XiyusLogin-Auto-Session-OTA` |
| `projects/patches/yuushya-2.3.0-patchouli-safety` | `Yuushya-2.3.0-Patchouli-Safety` |

### 3. Resolve projects that look related

- `MCSync` and `migration-collab-repo`: the first is the synchronizer; the
  second is the migration collaboration repository. They are not duplicates.
- The `MineAstr` default branch and its `astrbot-plugin` branch: mod side and
  Bot side in one repository, not duplicate repositories.
- `ImmersivePaintings` and
  `projects/patches/immersive-paintings-mineastr-compat`: the former is the full
  project; the latter is a migration-JAR overlay patch. No second standalone
  patch repository was created.
- `MishangUC-Pale-Oak-Equivalence` and
  `projects/ports/mishanguc-1.21.1-equivalence`: current pale-oak equivalence
  module versus the full port reference line. Related, but do not merge.
- `Kaleidoscope-Nether-Backport` and
  `projects/ports/kaleidoscope-nether-1.21.1-equivalence`: current buildable
  backport versus historical/reference line. Related, but do not overwrite one
  with the other.
- `Potted-Farms-1.21.1-Equivalence` and
  `projects/ports/potted-farms-1.21.1-equivalence-full`: current data snapshot
  versus full packaging reference. Use the former for small data releases.

## Manual steps (GitHub web UI)

1. Open `github.com/YU322142` and go to Repositories.
2. Check the `Public` label and then whether the repository is marked `Archived`.
3. Compare the repository name character-for-character with the table above;
   **use the standalone repository for a project, and use
   `migration-collab-repo` only as the index**.
4. Read the README to identify “mod source”, “diagnostic tool”, or “patch/script”.
   A patch repository intentionally has no upstream JAR; do not create another
   repository merely to add that JAR.
5. For a mod, open `gradle.properties` and verify `mod_id` and `mod_name`. For a
   data or patch project, verify the README boundary instead.
6. Treat it as the same project only when repository name, README role, and
   `mod_id` (when present) agree. Functional relationship or shared origin alone
   does not mean duplication.

## Optional command-line check

```powershell
# Find case-insensitive exact repository-name duplicates
$repos = gh repo list YU322142 --limit 200 --json name,url,isArchived,isPrivate | ConvertFrom-Json
$repos | Group-Object { $_.name.ToLowerInvariant() } |
  Where-Object Count -gt 1 | Select-Object -ExpandProperty Group

# Confirm a new repository is public and uses main
gh repo view YU322142/<REPO> --json name,visibility,isArchived,defaultBranchRef,url
```

No output from the first command means there is no exact name duplicate. Do not
use equal file counts as a duplicate test: the index and standalone projects
intentionally share source snapshots.

## Operating rules

- Do not delete `migration-collab-repo`; it carries cross-project audits,
  redaction rules, and migration tooling.
- Do not upload third-party JARs, worlds, player data, auth databases, or real
  credentials to any public repository.
- Do not treat an archived historical repository as the current entry point.
- New work goes to the corresponding standalone project first, then the index is
  updated with its path, version, and publication boundary.
