# Task 04 — Candidate Baseline, Role Profiles and Career Intelligence

## 1. Purpose

Extend Go Vacancy Agent from a vacancy-search utility into the first usable version of a **personal career assistant**. The product must help a candidate understand:

1. which vacancies are worth considering now;
2. which skills are actually requested by the market for a selected role;
3. what skills the candidate already has, and how well each claim is supported;
4. which important skill gaps remain;
5. what to learn and how to prepare for interviews.

The long-term product must support different professions. **The first supported role profile is Junior Go Developer.** Do not try to implement every profession in this task. Build a reusable core and prove it with the Go Junior profile.

This task must follow the engineering principles of the course:
https://github.com/ertaipit-web/python-agent-workflow-course

Use a simple deterministic workflow as the baseline. Use LLM calls only where interpreting unstructured text or generating a tailored explanation genuinely helps. Do not add agents merely to increase the agent count.

## 2. Confirmed product decisions

These are requirements, not questions for the user:

- Target role for the first usable version: **Junior Go Developer**.
- Long-term goal: a universal personal career assistant for different professions.
- Candidate profile/baseline: parse a resume or explicitly supplied public profile URL, ask targeted follow-up questions for missing information, and optionally assess selected skills through practical questions/tasks.
- Candidate's minimum compensation: **119,000 RUB net per month**.
- Geography/work format: remote, or hybrid in Saint Petersburg.
- DMS: a desirable advantage, not a mandatory condition.
- Interesting technical work and professional development are important preferences.
- LLM: local Ollama by default. Do not enable paid/cloud LLM fallback automatically.
- Candidate resume and profile: stored locally by default. Do not upload resume/profile contents to job sites or external LLM providers.
- Routine operation: daily run on the user's local computer while it is powered on. A Windows Task Scheduler setup is acceptable. Do not require a server or continuously running daemon.
- Reports: local Markdown and JSON files.
- Email notifications: future feature, out of scope for implementation in Task 04. Document the extension point only if it fits the existing design without premature abstraction.
- Keep existing HH.ru functionality. Do not remove it. Make the source's priority/configuration explicit. Any public-page scraper must be opt-in, disabled by default, and must not bypass anti-bot controls or terms of service.
- Do not perform any job applications, send messages to employers, or publish the candidate's personal data.

## 3. Mandatory preflight: verify the actual branch before building new features

The Task 03 report on GitHub contains completion claims and also lists working-tree modifications. Do not treat the report as proof that those changes are present in the current branch. Inspect actual files and Git state first.

1. Inspect `git status`, branch, current commit SHA, remote tracking status, recent commits, and all relevant files.
2. Preserve all user changes. Do not use destructive Git commands, reset, force-push, delete branches, or overwrite unknown modifications.
3. Work only in branch `dev`, or safely create/check it in accordance with the repository's current state.
4. Compare the code currently checked out with the claims in `tasks/task03_report.md`, `task03_report.md`, `task02_report.md`, and relevant task files. Avoid duplicate reports with conflicting contents.
5. Run the project test suite and identify which tests actually ran, skipped, or failed. Do not repeat results quoted in old reports as though they were just verified.

### Blocking foundation checks

Before enabling the new career-analysis flow, check and fix any remaining blockers from the previous task. At minimum, verify these cases against current code; fix them if still defective:

- `VacancyNormalizer.normalize_period()` must not silently interpret an absent/unrecognized salary period as monthly. Unknown stays unknown; salary conversion must return an unknown/needs-clarification result when reliable conversion is impossible.
- Vacancy verification must not claim that a vacancy is active or that its terms are confirmed merely because a source URL exists. Use source-specific details/status checks when available. Otherwise record the status as unknown and provide evidence/limitations.
- HH.ru's existing functionality must remain available, but scraping must not be an implicit fallback when the official API fails or credentials are missing. Scraping, if retained, must be explicitly enabled by configuration and must not evade anti-bot protection.
- The QA loop must re-create the report from corrected data, rerun QA, and never mark a failed/unknown QA run as successful.
- Required salary and work-format criteria must be evaluated independently of the weighted preference score.
- Configuration and CLI described in the documentation must match the actual implementation.

If one of these blockers remains, resolve the minimum changes required to make the foundation safe for this task, add regression tests, and report the changes. Do not spend the task on unrelated refactoring.

If an external credential/API is unavailable, implement the adapter contract and mock/fixture tests, mark real integration as `blocked_by_credentials` or `not_verified`, and continue with other work. Never fake a live integration result.

## 4. Product/domain documentation

Inspect the existing documentation before creating new files. Update existing documents rather than creating competing copies. The repository must have a clear, current statement of the product and architecture.

Document:

- product problem, target user, initial Go Junior use case, constraints and out-of-scope features;
- the separate concepts of (a) vacancies eligible for this candidate and (b) the broader market sample used to learn what skills a role requires;
- the candidate baseline flow;
- the data flow from sources to normalized vacancies, evidence, skill aggregation, candidate gap analysis and reports;
- what is deterministic code versus an LLM task;
- local data storage, network boundaries, source credentials, failure handling and daily execution;
- explicit limitations and the meaning of statuses such as `confirmed`, `self_reported`, `inferred`, `unknown`, `needs_clarification`, `blocked`, and `failed`.

Do not represent the system as a fully autonomous career advisor or claim that skill levels are objectively proven unless a defined assessment supports that claim.

## 5. Candidate baseline/profile

Implement a reusable, versioned candidate profile. Use the existing model/config conventions where possible instead of creating a duplicate domain model.

### 5.1 Intake inputs

Support at least:

- a local resume file (TXT/Markdown and, using suitable local parser libraries, PDF/DOCX where possible);
- manually entered or edited candidate profile data;
- an explicitly supplied public resume/profile URL, only when the user requests URL import; fetch it in a bounded, safe way and save/process locally;
- an interactive intake/interview mode to ask targeted questions when the resume/profile is incomplete.

If one file format cannot be parsed, report this clearly and offer text/manual entry. Do not silently ignore the resume or invent extracted facts.

### 5.2 Privacy defaults

- Candidate resume and profile data remain in a local data directory by default.
- Do not put personal resume text into vacancy-source queries.
- Do not send candidate resume/profile contents to HH.ru, SuperJob, Habr Career, Rabota.ru, or any other vacancy site.
- Use local Ollama only for LLM operations by default. No cloud fallback unless separately configured and explicitly approved in a future change.
- Secrets/API keys are stored in environment variables or the project's existing secret mechanism; never commit live secrets.
- Do not include resume text, contact details, or other personal data in ordinary run logs or public reports.
- URL imports must validate scheme/host, apply response-size and timeout limits, reject local/private network targets to avoid SSRF, and treat fetched content as untrusted input.

### 5.3 Skill evidence model

Each candidate skill entry must retain at least:

- canonical skill identifier/name;
- aliases/normalized form;
- claimed or assessed proficiency level, where known;
- evidence type: `resume`, `self_report`, `interview_answer`, `practical_assessment`, `inferred`, or `unknown`;
- evidence note/reference, with sensitive content minimized;
- confidence/status, distinct from proficiency;
- source/assessment date and model/schema version when relevant;
- optional notes and next suggested action.

Do not treat a skill mentioned in the resume as a verified practical skill. Do not translate absence from the resume into `no skill`. Keep proficiency, evidence strength and uncertainty as separate fields.

### 5.4 Adaptive follow-up interview

Ask only questions that resolve important missing or contradictory profile data. Prioritize:

- experience and projects;
- the skills most important for the chosen role and level;
- what the candidate has used in practice versus only studied;
- preferred tasks and areas of interest;
- desired exclusions/preferences that are not already known.

The question loop must have a configurable maximum number of questions/rounds, persist progress, allow the user to skip questions, and never block vacancy search when optional profile facts are missing. Do not claim psychological diagnosis or infer personality traits as facts.

### 5.5 Optional practical diagnostics

Provide a basic extensible interface for short skill checks. For the first Go Junior role, implement a small, transparent set of sample questions/tasks for selected foundational skills. Answers must not be treated as proof of production experience. Store the task, rubric, candidate response/result, date and confidence. Keep practical diagnostics optional and outside the critical path for daily vacancy search.

## 6. Universal role profiles (Role Packs)

Build a generic role-profile abstraction, validated and stored separately from core workflow logic. The first profile must be `go_junior`.

A Role Pack should support:

- canonical role name, role family and seniority;
- title/search aliases in Russian and English;
- source search phrases/query strategy;
- a versioned skill taxonomy for that role, including skill IDs, names, aliases and categories;
- criteria for mandatory skills versus common/desirable skills where source evidence supports the distinction;
- interview topic/question templates and practical-assessment definitions;
- normalization rules specific to the role, without hardcoding them in general vacancy processing;
- learning resource mappings, if materials recommendations are enabled.

Core models, vacancy processing, deduplication, market aggregation, candidate gap analysis and report generation must not depend on Go-specific fields/classes. Go-specific prompts/rules should live in the Go role pack or a role-specific module invoked through a clear interface.

Do not claim another profession is fully supported merely because a generic schema accepts a different title. Document what is generic and what is currently validated only for Go Junior.

## 7. Extend vacancy source integrations safely

Introduce or improve the source registry/adapter interface so each source can be independently configured, enabled/disabled, queried, normalized, status-checked and diagnosed.

### Source priorities

1. Preserve HH.ru support; do not delete the existing API or scraper code.
2. Investigate and, where feasible without paid API access, implement an official SuperJob vacancy-search adapter first. Official documentation to start from: https://api.superjob.ru/ . Search can expose public vacancy data, but an application key is required by the documented API contract; verify current terms and configuration requirements.
3. Investigate Habr Career, Rabota.ru, Работа России/Trudvsem and other credible sources. Check current official documentation, authentication, rate limits, reuse/storage rules and whether automated daily vacancy research is allowed.
4. Implement only sources for which an official or otherwise permitted integration is available. Do not label research-only/mock adapters as live integrations.

For every source, provide a source capability/status record:

- source name and integration type (`official_api`, `permitted_public_feed`, `permitted_web_source`, `fixture_only`);
- enabled/disabled state;
- credentials/configuration required (names only, never values);
- latest attempt time and status;
- result count;
- failure class and short sanitized explanation;
- terms/limitations and whether live operation was actually verified.

A failed source must not be represented as having zero vacancies. The report must distinguish `no_results` from `unavailable`, `unauthorized`, `rate_limited`, `blocked_by_credentials`, and `not_verified`.

### HH.ru policy

- Keep existing HH integration.
- Make the source priority explicitly configurable rather than silently privileging it.
- Official API should be the preferred HH path when configured and accessible.
- Keep the existing scraper code only as a separately configured, explicitly opt-in method; disabled by default. No browser fingerprint spoofing, anti-bot bypass, or automatic switch to scraping after API errors.
- If a source is disabled or access fails, report the reason and continue with other enabled sources.

### Source credentials and cost

- Do not require a paid LLM/API for the baseline workflow.
- API keys for vacancy sources may be configured locally by the user; document how to configure them, but do not request their secret values in chat or commit them.
- No source adapter may submit applications, contact recruiters, or modify external records.

## 8. Cross-source normalization and deduplication

The system must distinguish:

1. **Employer** — canonical company identity and known aliases/domains/source IDs.
2. **Canonical vacancy** — the logical hiring position as best as the data supports.
3. **Publication** — a source-specific listing, URL and source ID attached to the canonical vacancy.

Implement a conservative staged deduplication algorithm:

1. exact source ID/source URL;
2. canonicalized URL and known alternate IDs;
3. normalized employer identity, title/seniority and location/work format;
4. similarity of role description, responsibilities and requirements when needed;
5. optional LLM-assisted decision only for ambiguous cases, with the decision/evidence recorded.

Do not merge merely because employer and title match. One employer can have distinct roles with the same title. If the match is uncertain, keep separate records or mark the possible duplicate for review.

When listings are merged, preserve every source publication and provenance for each field. Re-publications must not automatically erase history; record whether the listing is new, changed, unchanged, potentially re-opened, closed, or unknown as supported by evidence.

**Market skill statistics must be computed on unique canonical vacancies, not raw source listings.** Also display distinct-employer counts when practical. This prevents the same job copied to three sites from being counted three times.

## 9. Market skill intelligence

Build a deterministic market-analysis module fed by the deduplicated vacancy corpus. LLM can help interpret descriptions or normalize ambiguous phrases, but every extracted skill must retain traceable evidence.

### 9.1 Two separate datasets

Maintain separate, clearly labelled cohorts:

- `candidate_eligible_vacancies`: vacancies that meet the candidate's confirmed mandatory conditions or are explicitly marked as needing clarification;
- `role_market_sample`: relevant vacancies used to infer role skill requirements, including postings whose compensation or other candidate-specific conditions are undisclosed or fail the candidate's filter.

Never present vacancies from the broader skill-research cohort as eligible recommendations. Do not discard useful market evidence solely because salary is undisclosed; instead label it correctly.

### 9.2 Skill extraction and normalization

For each unique vacancy, extract:

- canonical skill ID/name and original phrase;
- category (language, framework, database, infrastructure, testing, method, domain, soft skill, etc.);
- whether it was explicit in the source or inferred;
- requirement strength (`explicit_required`, `explicit_preferred`, `mentioned`, `inferred`, `unknown`);
- evidence source URL and, where feasible, text span/field;
- vacancy/employer identifiers and extractor version.

Merge aliases only when justified by the role taxonomy; do not collapse distinct skills. Count a skill at most once per canonical vacancy for frequency statistics, even if repeated many times in the same description.

### 9.3 Market report

For the Junior Go Developer profile, produce:

- unique relevant vacancies and distinct employers analyzed;
- skills sorted by number and percentage of unique vacancies that mention them;
- separate counts for explicit required/preferred mentions where the source supports this distinction;
- emerging/less common extras separately from core skills;
- coverage limitations, missing fields, sources that failed and potential selection bias;
- evidence links to representative original vacancies for each high-priority skill.

Every percentage must expose its denominator. Do not use raw mention count or duplicated source listings as the market frequency.

## 10. Ideal candidate portrait and personal skill-gap analysis

Build the ideal/target profile from actual market evidence for the chosen role pack, not from model-generated generic lists alone.

Classify target skills into configurable groups such as:

- core foundations;
- frequently required for the target level;
- commonly preferred;
- role-specific/occasional extras;
- unknown/insufficient evidence.

Do not inflate the Junior profile with senior-level expectations simply because a few listings include them. Keep the number/percentage of postings and source evidence visible.

Compare the target profile with the candidate baseline and create a gap matrix:

- skill;
- target importance;
- candidate current status/level;
- evidence status and confidence;
- gap type (`confirmed_gap`, `needs_assessment`, `matches_target`, `not_relevant`, `unknown`);
- rationale and supporting sources;
- recommended next action.

Unknown candidate skill level must result in `needs_assessment` or `unknown`, not an invented low proficiency. Self-report and practical assessment must remain distinguishable.

## 11. Learning and interview preparation

Provide an actionable, prioritized development plan based on the gap matrix.

Each learning-plan item should include:

- linked skill/gap;
- priority and reason;
- estimated effort range, clearly labelled as an estimate;
- a measurable learning outcome;
- practical exercise/project or self-check;
- suggested interview questions/topics;
- optional learning materials with title, source, URL, access date if checked, and skill coverage.

### Learning materials

- Materials selection is optional and configurable.
- Start with a small curated, versioned resource catalog for Go Junior (and relevant foundational topics) if useful, plus a provider interface for future discovery.
- Never invent a course, book, article or URL. A recommended link must originate from the catalog or a real, checked source.
- Prefer official documentation and high-quality free resources. Mark paid resources if included and do not purchase anything.
- If no verified resource is available, say so and provide a study objective/exercise rather than a fabricated link.
- Do not let resource retrieval failure break the vacancy report.

### Interview preparation

Generate a manageable set of questions/tasks prioritized by market importance and the candidate's gaps. Include question type (theory, practical, project discussion), target skill and a transparent rubric or expected elements. A local LLM may customize explanations, but the rubric and source evidence must be testable and not solely generated ad hoc.

Do not promise that these questions will be asked by a specific employer. They are preparation exercises based on observed requirements.

## 12. Daily workflow and local reports

Keep the app local-first. Do not implement server deployment or email sending in this task.

A daily run should, within configured time/request/LLM budgets:

1. load the active candidate profile and role pack;
2. search all enabled sources using bounded queries;
3. persist source statuses and raw/normalized metadata needed for audit;
4. normalize and deduplicate vacancy publications;
5. verify facts/status where source capabilities permit;
6. separate candidate-eligible vacancies from the broader role-market sample;
7. refresh market skill statistics;
8. update candidate-skill evidence only from explicit intake/assessment actions (never silently change the candidate profile merely because a daily job ran);
9. calculate the gap and learning/interview plan;
10. create validated Markdown and JSON reports;
11. run QA on the data and final report;
12. save successful and failed run history, including errors and partial-source limitations.

The daily report must include:

- run date and status;
- sources attempted, successful, unavailable, and not verified;
- new/changed/unchanged/closed/uncertain vacancy counts;
- best eligible vacancies and reasons;
- vacancies needing clarification;
- unique vacancy/employer counts used for market statistics;
- top market skills with denominators and evidence links;
- target/ideal candidate skill portrait;
- candidate baseline summary without unnecessary sensitive information;
- key gaps and prioritized next learning/interview actions;
- report limitations and failed stages.

Write `reports/latest.md`, `reports/latest.json`, and timestamped run files using the project's established layout. Never overwrite the latest *successful* report with a falsely successful report after a failed source/QA run; preserve a clear last-run status separately.

### Local scheduling

- Provide a reliable daily CLI command and document Windows Task Scheduler setup.
- Explain how to run it manually, configure the working directory/virtual environment/config paths, and enable “run as soon as possible after a missed start” if supported by the user's Windows version.
- The run must not require an always-on server. If the computer is off, the report is not generated until the task can run; document this plainly.
- Avoid installing persistent background services without explicit need.

### Future email

Email notifications are out of scope. Do not add a non-working email feature or request SMTP credentials. Keep report creation separate from delivery so an email notifier can be added in a later task.

## 13. Architecture aligned with the course

Follow the course selectively and explain choices:

- `Problem Definition`: measurable user outcomes and limits;
- `Baseline`: deterministic search/filter/dedup/report path;
- `Typed handoffs`: validated input/output models for stages;
- `State vs context`: persistent run/candidate/vacancy state separated from the reduced context passed to each LLM call;
- `Evidence`: source, timestamp, field/claim and provenance for material facts;
- `ModelClient`: local Ollama is the default provider behind an interface; mock model for tests;
- `Runtime policy`: explicit request limits, timeouts, bounded retries, maximum interview questions, maximum QA cycles and LLM-call budgets;
- `Tool permissions`: read-only source access, no job applications/email/browser side effects; local file writes limited to configured data/report directories;
- `Evaluation`: fixed fixtures with expected skills, eligibility, dedup outcomes and gap classifications; compare baseline and LLM-assisted results;
- `Trace`: record stage, model/provider identifier (not secret), prompt/schema version, inputs by reference/hash, outputs/status, duration, retries and error class without leaking resume content.

Use deterministic code for salary parsing, hard filters, dedup rules, counters and percentage calculations. Use LLM selectively for extraction/classification of unstructured text, ambiguous skill normalization and concise explanations. Any LLM-generated factual claim must be backed by evidence or labelled as an interpretation.

Do not implement a full web API, multi-user SaaS, hosted database or autonomous application-submission agent in Task 04. Avoid introducing a large framework unless repository inspection proves it necessary.

## 14. Evaluation and tests

Add automated tests for at least:

### Candidate baseline
- TXT/Markdown import and the supported resume formats;
- malformed/unreadable file handling;
- public URL validation, timeout, size limit and private-network rejection;
- extraction of skills with evidence/status;
- missing data prompts targeted questions rather than inventing facts;
- self-report vs resume mention vs practical assessment remains distinct;
- local-only processing defaults and no cloud fallback.

### Role profile and skill taxonomy
- valid/invalid Role Pack schema;
- Go/Golang alias normalization;
- different skill aliases map only when explicitly configured;
- generic core can load the Go Junior profile without Go-specific conditional logic in generic services.

### Sources and deduplication
- one failed source does not block other enabled sources;
- unavailable/unauthorized is not reported as zero results;
- credentials never appear in logs/reports;
- source IDs, URL variants and cross-source duplicates are resolved correctly;
- similar but distinct roles are not merged;
- unique-vacancy frequency does not count the same publication multiple times;
- tests work with fixtures and require no live API keys.

### Market analysis and career plan
- required/preferred/mentioned/inferred labels remain distinct;
- counts and percentages use unique canonical vacancy denominators;
- each significant skill result has evidence or an explicit unknown/unsupported status;
- separate eligible-vacancy and broader role-market cohorts do not leak into each other;
- an unknown candidate skill becomes `needs_assessment`, not a false gap or false match;
- learning resources have a real catalog/provider provenance; broken/unavailable resource sources do not break the report;
- interview questions link to skills and rubrics.

### Runtime and reports
- bounded retries/timeouts and QA iteration limits;
- partial run/failed QA cannot be shown as successful;
- Markdown/JSON are schema-valid and consistent;
- report includes source status and evaluation denominators;
- history correctly detects new/changed/closed/uncertain vacancies;
- report generation is deterministic for fixtures where expected;
- prompt-injection attempts inside vacancy text and imported resume content cannot change system/tool policy.

Create a small versioned evaluation fixture set with expected outcomes. At minimum include multiple unique Go Junior vacancy fixtures, cross-source duplicates, unknown/gross/net salary cases, unknown work format, multiple employer aliases and candidate profiles with known/unknown skill levels. Record baseline metrics for extraction/classification and compare LLM-disabled behavior with local-LLM-assisted behavior where Ollama is available. Tests must still pass without Ollama.

Do not invent target accuracy numbers. Measure the baseline, report current metrics and identify concrete failure cases. Keep evaluation data sanitized and separate from personal resume data.

## 15. Required artifacts and report

Adapt paths to existing repository conventions without creating duplicate sources of truth. At minimum, update or add:

- product/problem-definition documentation;
- workflow and domain-model documentation;
- the Go Junior Role Pack;
- candidate profile schema/example and local storage policy;
- source registry/config example and source availability documentation;
- skill taxonomy/normalization rules;
- learning resources catalog/example (if resource selection is implemented);
- operations guide for daily local execution;
- tests and versioned evaluation fixtures;
- README describing current real capabilities, not aspirational features.

**Mandatory:** create or update `task04_report.md` in the repository root. If the repository already stores task reports in `tasks/`, do not silently choose one path and contradict the task: document the convention, create the required root report, and avoid inconsistent duplicate contents.

The report must include:

1. current branch and exact commit SHA used as the base;
2. initial/final Git status and whether changes are committed (do not commit or push without user authorization if repository policy requires approval);
3. inspected previous-task reports and a comparison of claimed vs actual implementation;
4. exact features implemented, partially implemented, blocked, and not implemented;
5. changed/added files;
6. commands run and actual test counts, including skipped/failed tests;
7. source integrations tested with mocks versus tested live, and credentials missing;
8. evaluation dataset size, metrics and notable errors;
9. local setup and daily-run instructions;
10. known limitations and next steps.

Do not claim a live source works if only mock tests were run. Do not claim all criteria are complete if code changes are uncommitted or tests are missing. Do not fabricate URLs, vacancies, skill statistics, metrics or test results.

## 16. Git and execution rules

- Keep work isolated in `dev`.
- Inspect and preserve pre-existing changes. Do not discard them or silently include unrelated edits.
- Do not use `git reset --hard`, force-push, rewrite history, delete branches, or overwrite user data.
- Do not push to GitHub unless explicitly authorized.
- Do not send job applications or contact employers.
- Work autonomously on reversible technical decisions. If an integration requires unavailable credentials, finish its interface, configuration, mocks, documentation and mark live verification as blocked; continue on independent work.
- Keep commits small and coherent if commits are part of the established workflow; do not create a commit if doing so would capture unrelated user changes.

## 17. Acceptance criteria

Task 04 is complete only when all applicable items below are verified:

- [ ] The actual `dev` code was inspected; previous reports were not treated as proof.
- [ ] Remaining foundation blockers were fixed or explicitly block completion.
- [ ] A reusable candidate baseline can be built from local resume/profile inputs and targeted questions.
- [ ] Candidate skills preserve evidence type, confidence and unknown status; no inferred skill is misrepresented as verified.
- [ ] The universal Role Pack abstraction is implemented and demonstrated with `go_junior`.
- [ ] HH.ru functionality is preserved with explicit source configuration and no implicit scraper fallback.
- [ ] SuperJob and other portal APIs were researched against current official docs; implemented, permitted sources are accurately distinguished from mocks/research-only adapters.
- [ ] Cross-source deduplication preserves publication provenance and avoids counting duplicates in skill frequency.
- [ ] Market analysis reports skill frequency by unique vacancies, distinct employers where available, denominators and evidence.
- [ ] Candidate-eligible vacancies are separate from the broader market skill sample.
- [ ] The report contains the target skill profile, candidate gap matrix and an actionable learning/interview plan.
- [ ] Optional learning materials are sourced from a real catalog/provider and can be disabled.
- [ ] Daily local execution and Windows Task Scheduler instructions are valid; no server is required.
- [ ] Resume/profile stay local by default; there is no automatic cloud LLM fallback or sharing of personal profile text with vacancy sites.
- [ ] Tests cover the acceptance-critical cases and pass in the environment used for the report; any unavailable live integration is stated accurately.
- [ ] Evaluation results compare the deterministic baseline with LLM-assisted behavior where possible.
- [ ] README and operating documentation match the actual code.
- [ ] Root `task04_report.md` exists and truthfully reports implementation, tests, limitations, and Git state.

## 18. Execution order

1. Audit the actual branch and previous-task reports.
2. Resolve only the previous-task defects that block safe extension.
3. Document the current product definition and workflow.
4. Implement the reusable candidate baseline and local privacy rules.
5. Introduce/validate the Role Pack abstraction and implement `go_junior`.
6. Research source access and implement/verify source adapters within permitted access.
7. Implement cross-source canonicalization and deduplication.
8. Implement market skill aggregation, candidate gap analysis, interview preparation and optional learning resources.
9. Integrate into the local daily workflow and reports.
10. Run tests/evaluation, fix regressions, update docs and generate root `task04_report.md`.

Do not stop after writing a plan. Implement the working path end to end, use deterministic fixtures where credentials or external access are unavailable, and clearly separate verified capabilities from limitations.
