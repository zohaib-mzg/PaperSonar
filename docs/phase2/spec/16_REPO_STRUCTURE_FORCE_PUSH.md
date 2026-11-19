# Repository Structure and Force-Push Procedure

## Target repository layout
```text
.github/
  workflows/
    extract-load.yml
    deploy-ci.yml
config/
  sources.yml
  taxonomy.yml
  quality_rules.yml
docs/
  submissions/phase-1/       # preserve unchanged
  phase2/
    00_README_PHASE2.md
    ...
    19_IMPLEMENTATION_PLAN.md
    AGENTS.md
sql/
  00_setup/
  01_staging/
  02_bronze/
  03_silver/
  04_categorization/
  05_dimensions/
  06_facts/
  07_reporting/
  08_audit_dq/
  09_tasks/
  99_tests/
src/
  extract/
    openalex.py
    crossref.py
    arxiv.py
    datacite.py
    zenodo.py
  runner/
tests/
  unit/
  sql/
  fixtures/
```

The exact source files may vary, but responsibilities must remain separate. Python extraction modules must not implement transformations.

## Before replacing old Phase 2 code
1. Confirm clean working tree or record all local changes.
2. Fetch remote refs and inspect current branch/remote.
3. Confirm `docs/submissions/phase-1/**` and Phase 1 artifacts are preserved.
4. Create annotated tag `phase1-final` at the intended Phase 1 commit if not already present; never move an existing tag silently.
5. Create backup branch `phase2-legacy` at the old Phase 2 commit and push it.
6. Create a separate implementation branch and review the generated files.
7. Run lint, unit tests, SQL static checks, and repository diff review.
8. Confirm target branch and remote with the repository owner.
9. Use `git push --force-with-lease`, not blind `--force`, only after explicit authorization and remote review.
10. Verify remote commit and branch history after push.

Illustrative commands (review exact branch names first):
```bash
git status --short
git fetch --all --prune
git tag phase1-final <phase1-commit>
git branch phase2-legacy <old-phase2-commit>
git push origin phase1-final phase2-legacy
git push --force-with-lease origin <implementation-branch>:<target-branch>
```
Do not execute placeholder commands literally. If the tag already exists, verify its target rather than replacing it.

## Deleted/replaced inventory
Before push, generate a file-level diff and record:
- Removed obsolete Phase 2 Python transformation code.
- Removed old per-record API-to-warehouse processing.
- Replaced old surrogate-key-at-runtime logic.
- Added SQL ELT layers and task graph.
- Added source adapters, workflow files, tests, audit/DQ scripts, and reports.
- Preserved Phase 1 submissions and project history via backup refs.

## Post-push checklist
- [ ] Correct target branch and commit.
- [ ] `phase1-final` tag exists and points to intended commit.
- [ ] `phase2-legacy` backup branch exists.
- [ ] Phase 1 files are unchanged.
- [ ] CI workflows appear and run.
- [ ] No secrets or data dumps were committed.
- [ ] Required documentation files are present.
- [ ] Live Snowflake status and known blockers are documented.

## References
- Git push: https://git-scm.com/docs/git-push
- Git tags: https://git-scm.com/book/en/v2/Git-Basics-Tagging
- GitHub protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository
