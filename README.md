# SafeWatch AI — working MVP starter

Human-reviewed evidence intake and multilingual harassment screening for Urdu, Punjabi, Roman Urdu, and English. **No scraping, report bots, or automatic TikTok takedowns.**

## Run

1. Install Docker Desktop and Docker Compose.
2. Copy `.env.example` to `.env` and replace both keys with **different long random secrets**.
3. Run `docker compose up --build`.
4. Visit **http://localhost:3000**. API documentation is at **http://localhost:8000/docs** (requires API key for protected actions).
5. Create a case, upload permitted evidence, analyze (use the transcript input unless ASR is enabled), and submit a reviewer decision. Enter `ADMIN_API_KEY` in the reviewer key field. Approved cases can download PDF evidence summaries.

The app talks to the API through Next.js server routes; client users never receive `APP_API_KEY`. **However, this demo allows all web visitors to access cases via that server proxy**: run on localhost/trusted network only. Real multiuser deployment requires account login, per-case access control, CSRF protections, rate limiting, session-bound reviewer permissions, and audit logging. Never expose this MVP publicly with sensitive evidence.

## Optional speech recognition

Set `ENABLE_ASR=true` in `.env`. The backend uses `faster-whisper` (CPU int8); the first run downloads the ASR model and may take time, and larger models require more memory. Audio extracted via FFmpeg. Recognition of Punjabi, code-switching, slang and accents is **not validated**. If disabled, paste a consent-based transcription in the analysis field. Text classifier is a **transparent heuristic baseline**, not trained/validated multilingual harassment AI. Urdu/Punjabi OCR, deep contextual LLM classification and in-video timestamps remain future work.

## API

- `GET /api/health` — health
- `POST /api/cases` — create a case with optional TikTok HTTPS URL
- `GET /api/cases` — cases
- `GET /api/cases/{id}` — case detail
- `POST /api/cases/{id}/evidence` — multipart media upload (100MB cap)
- `POST /api/cases/{id}/analyze` — accepts `supplied_transcript` (optional)
- `POST /api/cases/{id}/review` — admin-only; approve/reject/needs_context
- `GET /api/cases/{id}/report.pdf` — approved-case PDF

All protected endpoints require an `x-api-key` header; review requires `ADMIN_API_KEY`.

## Database

SQLAlchemy schema contains cases, evidence, analyses and reviews. Database is PostgreSQL in Docker. Auto-create tables is a development shortcut; add Alembic migrations before production.

## Tests

`cd backend && python -m pip install -r requirements.txt && PYTHONPATH=. pytest -q`

## Privacy and security caveats

The app keeps uploaded media on a private Docker volume, stores SHA-256 checksums, and masks detected phone numbers in API/report output. **Raw transcript and evidence are not encrypted at rest** and initial version stores unmasked transcript internally. Real deployment needs encryption at rest, secure redacted PDF generation with Unicode fonts, media sniffing/FFprobe and antivirus, file retention/deletion, private evidence access logs, proper identity and permissions, malware and abuse controls, review appeals, legal/policy review and third-party privacy safeguards. The regex rules can miss sensitive data and flag benign quotations. Reports are informational and must be verified by a human. 

PDF currently uses Helvetica and may substitute characters for Urdu/Punjabi: production must bundle a properly licensed Unicode font and proper Indic/Arabic shaping pipeline. No font files are shipped.
