# SkillSpector Security Report

**Skill:** unknown  
**Source:** `/Users/ronmorim/Projects/JobApply_Venture/backend`  
**Scanned:** 2026-06-15 15:46:45 UTC  

## Risk Assessment

| Metric | Value |
|--------|-------|
| Score | 100/100 |
| Severity | CRITICAL |
| Recommendation | DO NOT INSTALL |

## Components (172)

| File | Type | Lines | Executable |
|------|------|-------|------------|
| `Set` | other | 0 | No |
| `__init__.py` | python | 0 | Yes |
| `agents/__init__.py` | python | 0 | Yes |
| `agents/applier.py` | python | 133 | Yes |
| `agents/ariel_tools.py` | python | 516 | Yes |
| `agents/auto_applier.py` | python | 114 | Yes |
| `agents/copilot.py` | python | 410 | Yes |
| `agents/gatekeeper.py` | python | 222 | Yes |
| `agents/matcher.py` | python | 310 | Yes |
| `agents/matching_engine.py` | python | 397 | Yes |
| `agents/profile_analyzer.py` | python | 368 | Yes |
| `agents/profile_interviewer.py` | python | 1286 | Yes |
| `agents/researcher.py` | python | 402 | Yes |
| `agents/resume.py` | python | 902 | Yes |
| `agents/scraper.py` | python | 85 | Yes |
| `agents/tailor.py` | python | 1480 | Yes |
| `agents/truth_check.py` | python | 178 | Yes |
| `api/__init__.py` | python | 0 | Yes |
| `api/deps.py` | python | 266 | Yes |
| `api/routes/__init__.py` | python | 0 | Yes |
| `api/routes/agents.py` | python | 486 | Yes |
| `api/routes/analytics.py` | python | 223 | Yes |
| `api/routes/applications.py` | python | 175 | Yes |
| `api/routes/ariel.py` | python | 371 | Yes |
| `api/routes/auth.py` | python | 156 | Yes |
| `api/routes/chat.py` | python | 582 | Yes |
| `api/routes/crm.py` | python | 175 | Yes |
| `api/routes/emails.py` | python | 266 | Yes |
| `api/routes/jobs.py` | python | 1275 | Yes |
| `api/routes/outreach.py` | python | 102 | Yes |
| `api/routes/profile.py` | python | 1124 | Yes |
| `api/routes/resumes.py` | python | 1118 | Yes |
| `api/routes/settings.py` | python | 136 | Yes |
| `config.py` | python | 114 | Yes |
| `data/active_user.json` | json | 3 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/0998b62e8fd6b444_0` | other | 149 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/4f153da05e4ae9aa_0` | other | 147 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/7148da0102006a27_0` | other | 148 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/901c056da3c0caf9_0` | other | 147 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/a29f2189ea83cbc2_0` | other | 148 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/b5b0211c3c8768e8_0` | other | 148 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/bab28d9b761a3db2_0` | other | 146 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/d6fd2fdb1984a0c6_0` | other | 146 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Cache/Cache_Data/index-dir/the-real-index` | other | 3 | No |
| `data/linkedin_browser_profile/Default/Code Cache/js/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Code Cache/js/index-dir/the-real-index` | other | 2 | No |
| `data/linkedin_browser_profile/Default/Code Cache/wasm/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Code Cache/wasm/index-dir/the-real-index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Cookies` | other | 24 | No |
| `data/linkedin_browser_profile/Default/Cookies-journal` | other | 0 | No |
| `data/linkedin_browser_profile/Default/DawnGraphiteCache/data_0` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnGraphiteCache/data_1` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnGraphiteCache/data_2` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnGraphiteCache/data_3` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnGraphiteCache/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnWebGPUCache/data_0` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnWebGPUCache/data_1` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnWebGPUCache/data_2` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnWebGPUCache/data_3` | other | 1 | No |
| `data/linkedin_browser_profile/Default/DawnWebGPUCache/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/GPUCache/data_0` | other | 1 | No |
| `data/linkedin_browser_profile/Default/GPUCache/data_1` | other | 1 | No |
| `data/linkedin_browser_profile/Default/GPUCache/data_2` | other | 1 | No |
| `data/linkedin_browser_profile/Default/GPUCache/data_3` | other | 1 | No |
| `data/linkedin_browser_profile/Default/GPUCache/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/InterestGroups` | other | 47 | No |
| `data/linkedin_browser_profile/Default/Local Storage/leveldb/000003.log` | other | 0 | No |
| `data/linkedin_browser_profile/Default/Local Storage/leveldb/CURRENT` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Local Storage/leveldb/LOCK` | other | 0 | No |
| `data/linkedin_browser_profile/Default/Local Storage/leveldb/LOG` | other | 2 | No |
| `data/linkedin_browser_profile/Default/Local Storage/leveldb/MANIFEST-000001` | other | 1 | No |
| `data/linkedin_browser_profile/Default/PersistentOriginTrials/LOCK` | other | 0 | No |
| `data/linkedin_browser_profile/Default/PersistentOriginTrials/LOG` | other | 0 | No |
| `data/linkedin_browser_profile/Default/Session Storage/000003.log` | other | 14 | No |
| `data/linkedin_browser_profile/Default/Session Storage/CURRENT` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Session Storage/LOCK` | other | 0 | No |
| `data/linkedin_browser_profile/Default/Session Storage/LOG` | other | 2 | No |
| `data/linkedin_browser_profile/Default/Session Storage/MANIFEST-000001` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Shared Dictionary/cache/index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Shared Dictionary/cache/index-dir/the-real-index` | other | 1 | No |
| `data/linkedin_browser_profile/Default/Shared Dictionary/db` | other | 29 | No |
| `data/linkedin_browser_profile/Default/Shared Dictionary/db-journal` | other | 0 | No |
| `data/linkedin_browser_profile/Default/SharedStorage` | other | 2 | No |
| `data/linkedin_browser_profile/Default/WebStorage/QuotaManager` | other | 24 | No |
| `data/linkedin_browser_profile/Default/WebStorage/QuotaManager-journal` | other | 0 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/000003.log` | other | 0 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/CURRENT` | other | 1 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/LOCK` | other | 0 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/LOG` | other | 2 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/MANIFEST-000001` | other | 1 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/metadata/000003.log` | other | 1 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/metadata/CURRENT` | other | 1 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/metadata/LOCK` | other | 0 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/metadata/LOG` | other | 2 | No |
| `data/linkedin_browser_profile/Default/shared_proto_db/metadata/MANIFEST-000001` | other | 1 | No |
| `data/ron_entities_seed.json` | json | 642 | No |
| `engines/__init__.py` | python | 0 | Yes |
| `engines/master_profile.py` | python | 178 | Yes |
| `engines/matching_engine.py` | python | 489 | Yes |
| `engines/optimization_engine.py` | python | 403 | Yes |
| `integrations/__init__.py` | python | 0 | Yes |
| `integrations/job_scraper.py` | python | 396 | Yes |
| `integrations/oauth_integrations.py` | python | 529 | Yes |
| `jobs.db` | other | 5544 | No |
| `jobs.db-shm` | other | 17 | No |
| `jobs.db-wal` | other | 10577 | No |
| `logic/__init__.py` | python | 0 | Yes |
| `logic/outreach_engine.py` | python | 275 | Yes |
| `logic/verifier.py` | python | 619 | Yes |
| `main.py` | python | 316 | Yes |
| `migrations/001_confidence_matrix.sql` | other | 193 | No |
| `personal_overrides.json` | json | 4 | No |
| `requirements.txt` | text | 23 | No |
| `reset_jobs.py` | python | 131 | Yes |
| `scrapers/__init__.py` | python | 51 | Yes |
| `scrapers/alljobs_scraper.py` | python | 395 | Yes |
| `scrapers/base_scraper.py` | python | 120 | Yes |
| `scrapers/comeet_adapter.py` | python | 461 | Yes |
| `scrapers/dialog_scraper.py` | python | 317 | Yes |
| `scrapers/drushim_scraper.py` | python | 484 | Yes |
| `scrapers/google_dork_scraper.py` | python | 301 | Yes |
| `scrapers/gotfriends_scraper.py` | python | 320 | Yes |
| `scrapers/linkedin_scraper.py` | python | 129 | Yes |
| `scrapers/nisha_scraper.py` | python | 324 | Yes |
| `scrapers/relevancy.py` | python | 137 | Yes |
| `scrapers/scraper_manager.py` | python | 261 | Yes |
| `scrapers/url_router.py` | python | 1063 | Yes |
| `scripts/backfill_entity_scores.py` | python | 198 | Yes |
| `scripts/reset_linkedin_scraper.py` | python | 187 | Yes |
| `scripts/seed_ron_entities.py` | python | 217 | Yes |
| `services/__init__.py` | python | 0 | Yes |
| `services/active_user.py` | python | 67 | Yes |
| `services/agent_orchestrator.py` | python | 48 | Yes |
| `services/agent_store.py` | python | 230 | Yes |
| `services/app_store.py` | python | 72 | Yes |
| `services/ariel_probe_service.py` | python | 807 | Yes |
| `services/ats_keyword_service.py` | python | 215 | Yes |
| `services/confidence_math.py` | python | 522 | Yes |
| `services/confidence_matrix_service.py` | python | 428 | Yes |
| `services/cv_aggregator_service.py` | python | 430 | Yes |
| `services/cv_tailor_service.py` | python | 313 | Yes |
| `services/db.py` | python | 711 | Yes |
| `services/discovery.py` | python | 347 | Yes |
| `services/document_verifier.py` | python | 206 | Yes |
| `services/email_parser.py` | python | 170 | Yes |
| `services/feed_service.py` | python | 837 | Yes |
| `services/jd_backfill_service.py` | python | 151 | Yes |
| `services/jd_structure_service.py` | python | 392 | Yes |
| `services/job_service.py` | python | 26 | Yes |
| `services/job_store.py` | python | 694 | Yes |
| `services/master_profile_service.py` | python | 509 | Yes |
| `services/match_score_service.py` | python | 1301 | Yes |
| `services/orchestrator.py` | python | 189 | Yes |
| `services/outreach_service.py` | python | 226 | Yes |
| `services/pdf_builder.py` | python | 321 | Yes |
| `services/profile_manager.py` | python | 419 | Yes |
| `services/profile_update_service.py` | python | 1140 | Yes |
| `services/supplemental_store.py` | python | 85 | Yes |
| `services/user_profile.py` | python | 717 | Yes |
| `services/user_profile_store.py` | python | 224 | Yes |
| `services/web_search.py` | python | 123 | Yes |
| `supplemental_answers.json` | json | 98 | No |
| `templates/cv/t1_classic.html` | other | 273 | No |
| `templates/cv/t2_modern.html` | other | 291 | No |
| `templates/cv/t3_executive.html` | other | 293 | No |
| `templates/cv_template.html` | other | 449 | No |
| `test_scraper.py` | python | 61 | Yes |
| `tests/__init__.py` | python | 0 | Yes |
| `tests/conftest.py` | python | 22 | Yes |
| `tests/test_profile_trust.py` | python | 528 | Yes |
| `url_scraper.py` | python | 220 | Yes |

## Issues (60)

### 🟡 MEDIUM: AST3

**Location:** `api/routes/profile.py:381`  
**Confidence:** 75%  

**Message:** Dynamic import via __import__()

**Remediation:** Use standard import statements instead of __import__(). If dynamic loading is needed, use importlib with an allowlist of permitted modules.

---

### 🟡 MEDIUM: TT2

**Location:** `integrations/oauth_integrations.py:336–344`  
**Confidence:** 65%  

**Message:** Tainted flow: 'headers' from requests.post (line 330, network input) → requests.get (network output)

**Remediation:** Validate tainted variables before passing them to sinks. Use allowlists, type checks, or sanitization functions on data from external sources.

---

### 🟡 MEDIUM: TT2

**Location:** `integrations/oauth_integrations.py:349–354`  
**Confidence:** 65%  

**Message:** Tainted flow: 'headers' from requests.post (line 330, network input) → requests.get (network output)

**Remediation:** Validate tainted variables before passing them to sinks. Use allowlists, type checks, or sanitization functions on data from external sources.

---

### 🔴 HIGH: E2

**Location:** `agents/truth_check.py:82`  
**Confidence:** 70%  

**Message:** Env Variable Harvesting

**Remediation:** Avoid reading sensitive env vars (API keys, tokens) unless strictly required. Use secrets managers or secure config. Never log or transmit credentials.

---

### 🔴 HIGH: E2

**Location:** `api/routes/chat.py:57`  
**Confidence:** 70%  

**Message:** Env Variable Harvesting

**Remediation:** Avoid reading sensitive env vars (API keys, tokens) unless strictly required. Use secrets managers or secure config. Never log or transmit credentials.

---

### 🟡 MEDIUM: E1

**Location:** `integrations/oauth_integrations.py:337`  
**Confidence:** 60%  

**Message:** External Transmission

**Remediation:** Verify the destination URL is trusted and necessary. Remove or replace with documented APIs. Ensure no secrets, tokens, or PII are transmitted.

---

### 🟡 MEDIUM: E1

**Location:** `integrations/oauth_integrations.py:350`  
**Confidence:** 60%  

**Message:** External Transmission

**Remediation:** Verify the destination URL is trusted and necessary. Remove or replace with documented APIs. Ensure no secrets, tokens, or PII are transmitted.

---

### 🔴 HIGH: E2

**Location:** `integrations/oauth_integrations.py:188`  
**Confidence:** 80%  

**Message:** Env Variable Harvesting

**Remediation:** Avoid reading sensitive env vars (API keys, tokens) unless strictly required. Use secrets managers or secure config. Never log or transmit credentials.

---

### 🔴 HIGH: E2

**Location:** `integrations/oauth_integrations.py:301`  
**Confidence:** 80%  

**Message:** Env Variable Harvesting

**Remediation:** Avoid reading sensitive env vars (API keys, tokens) unless strictly required. Use secrets managers or secure config. Never log or transmit credentials.

---

### 🟡 MEDIUM: EA2

**Location:** `agents/profile_interviewer.py:269`  
**Confidence:** 80%  

**Message:** Autonomous Decision Making

**Remediation:** Add human-in-the-loop confirmation for destructive, irreversible, or high-impact operations. Never auto-execute commands that modify files, send data, or alter system state.

---

### 🟡 MEDIUM: EA2

**Location:** `agents/tailor.py:204`  
**Confidence:** 75%  

**Message:** Autonomous Decision Making

**Remediation:** Add human-in-the-loop confirmation for destructive, irreversible, or high-impact operations. Never auto-execute commands that modify files, send data, or alter system state.

---

### 🟡 MEDIUM: EA1

**Location:** `api/routes/chat.py:456`  
**Confidence:** 80%  

**Message:** Unrestricted Tool Access

**Remediation:** Restrict tool access to only the tools required for the skill's stated purpose. Use an explicit allowlist rather than granting blanket access.

---

### 🟡 MEDIUM: EA2

**Location:** `reset_jobs.py:21`  
**Confidence:** 85%  

**Message:** Autonomous Decision Making

**Remediation:** Add human-in-the-loop confirmation for destructive, irreversible, or high-impact operations. Never auto-execute commands that modify files, send data, or alter system state.

---

### 🟡 MEDIUM: MP2

**Location:** `jobs.db-shm:3`  
**Confidence:** 80%  

**Message:** Context Window Stuffing

**Remediation:** Implement context-window management that detects and rejects padding or stuffing attempts. Prioritize system instructions over user-injected content.

---

### 🟡 MEDIUM: MP2

**Location:** `jobs.db-shm:3`  
**Confidence:** 80%  

**Message:** Context Window Stuffing

**Remediation:** Implement context-window management that detects and rejects padding or stuffing attempts. Prioritize system instructions over user-injected content.

---

### 🟡 MEDIUM: MP2

**Location:** `jobs.db-shm:3`  
**Confidence:** 80%  

**Message:** Context Window Stuffing

**Remediation:** Implement context-window management that detects and rejects padding or stuffing attempts. Prioritize system instructions over user-injected content.

---

### 🟡 MEDIUM: OH3

**Location:** `agents/applier.py:7`  
**Confidence:** 80%  

**Message:** Unbounded Output

**Remediation:** Set explicit limits on output length, generation count, and rate. Use max_tokens and truncation to prevent unbounded output.

---

### 🟡 MEDIUM: OH3

**Location:** `agents/auto_applier.py:105`  
**Confidence:** 80%  

**Message:** Unbounded Output

**Remediation:** Set explicit limits on output length, generation count, and rate. Use max_tokens and truncation to prevent unbounded output.

---

### 🔴 HIGH: PE3

**Location:** `agents/copilot.py:31`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `agents/gatekeeper.py:36`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `agents/profile_interviewer.py:49`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `agents/researcher.py:41`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `agents/tailor.py:31`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `agents/truth_check.py:33`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `api/deps.py:25`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `api/routes/chat.py:61`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `api/routes/chat.py:72`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `main.py:10`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `main.py:12`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scrapers/url_router.py:488`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scrapers/url_router.py:644`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scrapers/url_router.py:795`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/reset_linkedin_scraper.py:19`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/reset_linkedin_scraper.py:56`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/reset_linkedin_scraper.py:112`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/reset_linkedin_scraper.py:140`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/reset_linkedin_scraper.py:154`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/seed_ron_entities.py:7`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/seed_ron_entities.py:32`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `scripts/seed_ron_entities.py:33`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/ats_keyword_service.py:47`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/cv_aggregator_service.py:52`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/cv_tailor_service.py:42`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/document_verifier.py:32`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/email_parser.py:30`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/feed_service.py:483`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/feed_service.py:555`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🔴 HIGH: PE3

**Location:** `services/outreach_service.py:38`  
**Confidence:** 60%  

**Message:** Credential Access

**Remediation:** Remove references to credential paths. Use environment variables or secrets managers. For docs, use placeholder paths (e.g., /path/to/config). Never load .env or token files in production code paths.

---

### 🟢 LOW: SC4

**Location:** `requirements.txt:13`  
**Confidence:** 60%  

**Message:** Known Vulnerable Dependency: python-dotenv==1.0.1 — 1 advisory(ies): CVE-2026-28684 (python-dotenv: Symlink following in set_key allows arbitrary file overwrite via )

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🔴 HIGH: SC4

**Location:** `requirements.txt:14`  
**Confidence:** 80%  

**Message:** Known Vulnerable Dependency: python-multipart==0.0.19 — 3 advisory(ies): CVE-2026-40347 (python-multipart affected by Denial of Service via large multipart preamble or e); CVE-2026-42561 (python-multipart has Denial of Service via unbounded multipart part headers); CVE-2026-24486 (Python-Multipart has Arbitrary File Write via Non-Default Configuration)

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🔴 CRITICAL: SC4

**Location:** `requirements.txt:15`  
**Confidence:** 90%  

**Message:** Known Vulnerable Dependency: langgraph==0.2.60 — 2 advisory(ies): CVE-2026-28277 (LangGraph checkpoint loading has unsafe msgpack deserialization); CVE-2026-28277 (LangGraph SQLite Checkpoint is an implementation of LangGraph CheckpointSaver th)

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🔴 HIGH: SC4

**Location:** `requirements.txt:17`  
**Confidence:** 80%  

**Message:** Known Vulnerable Dependency: lxml==5.3.0 — 2 advisory(ies): CVE-2026-41066 (lxml: Default configuration of iterparse() and ETCompatXMLParser() allows XXE to); CVE-2026-41066 (lxml is a library for processing XML and HTML in the Python language. Prior to 6)

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🟢 LOW: SC4

**Location:** `requirements.txt:19`  
**Confidence:** 60%  

**Message:** Known Vulnerable Dependency: requests==2.32.3 — 2 advisory(ies): CVE-2024-47081 (Requests vulnerable to .netrc credentials leak via malicious URLs); CVE-2026-25645 (Requests has Insecure Temp File Reuse in its extract_zipped_paths() utility func)

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🟢 LOW: SC4

**Location:** `requirements.txt:21`  
**Confidence:** 60%  

**Message:** Known Vulnerable Dependency: pymupdf==1.26.5 — 1 advisory(ies): CVE-2026-3029 (PyMuPDF has a path traversal in _main_.py)

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🔴 CRITICAL: SC4

**Location:** `requirements.txt:23`  
**Confidence:** 90%  

**Message:** Known Vulnerable Dependency: python-jose==3.3.0 — 5 advisory(ies): CVE-2024-33663 (python-jose algorithm confusion with OpenSSH ECDSA keys); CVE-2024-33664 (python-jose denial of service via compressed JWE content); CVE-2024-33663 (python-jose through 3.3.0 has algorithm confusion with OpenSSH ECDSA keys and ot) +2 more

**Remediation:** Update the dependency to a patched version that addresses the known CVE. Check OSV (osv.dev) or NVD for details on the vulnerability.

---

### 🔴 HIGH: SC6

**Location:** `requirements.txt:2`  
**Confidence:** 70%  

**Message:** Possible Typosquatting: 'uvicorn' resembles popular package 'gunicorn'

**Remediation:** Verify the package name is correct and not a typosquatting variant. Compare against the official package name on PyPI or npm.

---

### 🟡 MEDIUM: P7

**Location:** `agents/copilot.py:395`  
**Confidence:** 75%  

**Message:** Indirect Prompt Extraction

**Remediation:** Guard against indirect extraction by refusing to summarize, translate, or rephrase system instructions. Add explicit anti-extraction clauses.

---

### 🔴 HIGH: P6

**Location:** `services/ariel_probe_service.py:541`  
**Confidence:** 85%  

**Message:** Direct Prompt Extraction

**Remediation:** Remove any instructions that reveal, print, or output system prompts or internal rules. System instructions should never be exposed to end users.

---

### 🟡 MEDIUM: TM3

**Location:** `agents/matcher.py:27`  
**Confidence:** 60%  

**Message:** Unsafe Defaults

**Remediation:** Override unsafe defaults with secure settings (verify=True, auth required, restrictive permissions). Review and harden all tool configurations.

---

### 🟡 MEDIUM: TM3

**Location:** `main.py:160`  
**Confidence:** 60%  

**Message:** Unsafe Defaults

**Remediation:** Override unsafe defaults with secure settings (verify=True, auth required, restrictive permissions). Review and harden all tool configurations.

---

## Metadata

- **Executable Scripts:** Yes

*Generated by SkillSpector v2.1.4*