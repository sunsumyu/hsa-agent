# =============================================================================
# Purge audit_checkpoints.db (and its -shm/-wal siblings) from the entire Git history.
#
# DANGER: This rewrites every commit SHA on `main`. After running this script:
#   * You MUST force-push.
#   * All collaborators MUST re-clone (or perform a hard reset to the new history).
#
# Preconditions checklist (do these BEFORE running):
#   [ ] You are on a clean working tree   (git status == nothing to commit)
#   [ ] You have tagged the current tip on GitHub as a safety net,
#       e.g. `git tag backup/pre-filter-repo-2026-05-11 && git push origin --tags`
#   [ ] All collaborators have been notified.
#   [ ] You are running this from the repo root.
#
# Reference:
#   https://github.com/newren/git-filter-repo
#   https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
# =============================================================================

$ErrorActionPreference = "Stop"

# --- 1. Sanity checks ---------------------------------------------------------
Write-Host "[1/6] Checking preconditions..." -ForegroundColor Cyan

if ((git status --porcelain | Measure-Object -Line).Lines -ne 0) {
    Write-Error "Working tree is not clean. Commit or stash first."
}

$currentBranch = git rev-parse --abbrev-ref HEAD
if ($currentBranch -ne "main") {
    Write-Warning "You are on branch '$currentBranch' (expected 'main'). Continue? (Ctrl+C to abort)"
    Read-Host "Press Enter to continue"
}

# --- 2. Ensure git-filter-repo is installed -----------------------------------
Write-Host "[2/6] Checking git-filter-repo..." -ForegroundColor Cyan
$filterRepo = Get-Command git-filter-repo -ErrorAction SilentlyContinue
if (-not $filterRepo) {
    Write-Host "  git-filter-repo not found. Install with: pip install git-filter-repo" -ForegroundColor Yellow
    Write-Error "Aborting. Install git-filter-repo first."
}

# --- 3. Create a local safety tag --------------------------------------------
$backupTag = "backup/pre-purge-" + (Get-Date -Format "yyyyMMdd-HHmmss")
Write-Host "[3/6] Creating local safety tag: $backupTag" -ForegroundColor Cyan
git tag $backupTag

# --- 4. Show what will be purged ---------------------------------------------
Write-Host "[4/6] Showing blobs that will be removed from history:" -ForegroundColor Cyan
git rev-list --objects --all | Select-String "audit_checkpoints\.db" | Select-Object -First 10
Write-Host ""
Write-Host "About to remove these paths from the ENTIRE history:" -ForegroundColor Yellow
Write-Host "  - audit_checkpoints.db"
Write-Host "  - audit_checkpoints.db-shm"
Write-Host "  - audit_checkpoints.db-wal"
Write-Host ""
$confirm = Read-Host "Type 'YES' (uppercase) to proceed"
if ($confirm -ne "YES") { Write-Error "Aborted by user." }

# --- 5. Run git-filter-repo ---------------------------------------------------
Write-Host "[5/6] Running git-filter-repo..." -ForegroundColor Cyan
git filter-repo --invert-paths `
    --path audit_checkpoints.db `
    --path audit_checkpoints.db-shm `
    --path audit_checkpoints.db-wal `
    --force

# --- 6. Report & next steps ---------------------------------------------------
Write-Host "[6/6] Done. Post-run status:" -ForegroundColor Green
git count-objects -vH
Write-Host ""
Write-Host "NEXT STEPS (manual):" -ForegroundColor Yellow
Write-Host "  1. Re-add the remote (filter-repo strips it by design):"
Write-Host "     git remote add origin https://github.com/sunsumyu/hsa-agent.git"
Write-Host ""
Write-Host "  2. Inspect the rewritten history to verify:"
Write-Host "     git log --all --oneline -- audit_checkpoints.db    # should show NOTHING"
Write-Host ""
Write-Host "  3. Force-push (DESTRUCTIVE â€?all collaborators must re-clone):"
Write-Host "     git push origin --force --all"
Write-Host "     git push origin --force --tags"
Write-Host ""
Write-Host "  4. On GitHub, ask GitHub Support to run garbage collection on the remote"
Write-Host "     if you also need to reduce the remote's storage (usually GitHub handles it"
Write-Host "     automatically after 30 days)."
Write-Host ""
Write-Host "Safety net: if something went wrong, your old history is at tag '$backupTag'" -ForegroundColor Green

