## Worfklow Orchestration

### 1. Plan Mode Default

- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy

- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop

- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing

- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo/md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Project Structure Index

> **Maintenance rule**: Always update this index when adding or removing files in `docs/`, `extractors/`, `config/`, `models/`, `tests/`, or any pipeline-related file.
>
> **Navigation strategy — use all three layers:**
> 1. **Index (this section)** — orient to file locations; use as a map/TOC to know where to look
> 2. **LSP** — navigate symbols once you know the file: definitions (`goToDefinition`), references (`findReferences`), call hierarchies (`incomingCalls`/`outgoingCalls`), workspace-wide symbol search (`workspaceSymbol`)
> 3. **Grep** — search file content for fresh, accurate answers; never assume content from the index alone

### docs/
- `docs/PIPELINE_SPEC.md` — Full pipeline specification
- `docs/PROJECT.md` — Project overview
- `docs/UNMATCHED_TALKS_ANALYSIS.md` — Analysis of 224 API URIs not matched to talk_id (sustaining, audits, stats, welfare sessions, one-offs)
- `docs/pipeline/PLAN_PHASE_3.5_SHARED_UTILITIES.md` — Shared utilities plan
- `docs/pipeline/phase-1-metadata/PHASE1_README.md`
- `docs/pipeline/phase-2-paragraph/IMPLEMENTATION_SUMMARY.md`
- `docs/pipeline/phase-2-paragraph/PHASE2_PLAN.md`
- `docs/pipeline/phase-2-paragraph/PHASE2_README.md`
- `docs/pipeline/phase-3-citation/BUGS.md` — Bug catalogue for Phase 3 audit (all known pipeline bugs)
- `docs/pipeline/phase-3-citation/PHASE3_PLAN.md`
- `docs/pipeline/phase-3-citation/REFACTOR_CITATION_PARSING.md`
- `docs/pipeline/phase-4-footnote/BUG_FIXING_SUMMARY.md`
- `docs/pipeline/phase-4-footnote/IMPLEMENTATION_SUMMARY_INTERVIEW.md`
- `docs/pipeline/phase-4-footnote/PLAN_PHASE_4.md`
- `docs/pipeline/phase-5-validation/PLAN_PHASE_5.md`
- `docs/update/Update_GC_PLAN.md`

### extractors/
- `extractors/html_parsing_utils.py` — Shared HTML parsing utilities
- `extractors/phase1_talk_metadata.py` — Phase 1: talk metadata
- `extractors/phase2_paragraph_extraction.py` — Phase 2: paragraph extraction
- `extractors/phase3_citation_extraction.py` — Phase 3: citation extraction
- `extractors/phase4_footnote_extraction.py` — Phase 4: footnote extraction
- `extractors/phase5_validation.py` — Phase 5: validation
- `extractors/phase6_chromadb_loader.py` — Phase 6: ChromaDB loader

### config/
- `config/schemas.py` — Config/validation schemas
- `config/audit_sample.json` — Talk IDs for bug audit sample (user-curated; populate before running run_audit.py)

### models/
- `models/talk_metadata.py` — Phase 1 data model
- `models/paragraph_data.py` — Phase 2 data model
- `models/citation_data.py` — Phase 3 data model
- `models/footnote_data.py` — Phase 4 data model
- `models/validation_report.py` — Phase 5 data model

### scripts/
- `scripts/db_schema_extractor.py` — Database schema inspection utility (use with specific arguments)
- `scripts/UPDATE.py` — Conference database synchronization script (gc.db to core db)
- `scripts/process_all.py` — Batch topic and talk processing script (threaded API fetcher)
- `scripts/process_topics.py` — Topic data fetcher (topics.json → Church API → entries)
- `scripts/run_audit.py` — Bug audit driver script (runs phases 1-5 per talk_id in config/audit_sample.json)
- `scripts/run_pipeline.py` — Full pipeline orchestrator (Phases 1-6, per-talk streaming, resume, --force)
- `scripts/verify_pipeline.py` — Post-pipeline verification script (VER-01 through VER-05, JSON report)

### tests/
- `tests/test_html_parsing_utils.py`
- `tests/test_phase1.py`
- `tests/test_phase2.py`
- `tests/test_phase3.py`
- `tests/test_phase4.py`
- `tests/test_phase5.py`
- `tests/test_phase6.py`
- `tests/test_phase6_orchestrator.py`

## Process

- Do not open database files directly, instead use `scripts/db_schema_extractor.py` with specific arguments.

## Environment

- This project uses **pipenv** for dependency management and virtual environment
- All Python commands must use `pipenv run py` (Python Launcher), e.g., `pipenv run py script.py`, `pipenv run py -m pytest file`
- To install dependencies: `pipenv install`
- To enter the shell: `pipenv shell`
