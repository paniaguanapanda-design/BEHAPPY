# FixAI — PRD

## Original problem statement
Mobile app: user uses phone camera to identify home problems; AI gives solution, steps, materials; depending on difficulty, user picks DIY or a subscribed specialist. Specialists section works like a social network: profile with work photos, profile verification, client satisfaction level and recommendations.

## User choices
Gemini 3 Flash (Emergent key) · specialists register in-app · Google + email/password (JWT) login · in-app service request + call/WhatsApp + in-app chat · Spanish + Italian.

## Architecture
- Backend: FastAPI + MongoDB (single server.py), Emergent Object Storage for images, emergentintegrations Gemini `gemini-3-flash-preview`.
- Frontend: Expo Router, tabs (Scan, Specialists, Messages, Profile; NativeTabs on iOS 26+), screens: login, scan (expo-camera), diagnosis/[id], specialist/[id], chat/[id], specialist-form, requests. i18n ES/IT.

## Implemented (2026-06)
- JWT + Google auth, root auth gate
- Camera/gallery → AI diagnosis (title, category, difficulty, safety, materials, tools, steps, time, cost) with history
- DIY mode with step checklist / "hire specialist" filtered by category
- Specialists directory (chips, search), social profile (portfolio, verified badge, rating, satisfaction %, recommends, jobs, reviews)
- Specialist registration form, avatar/portfolio upload, ID verification (auto-approve MVP)
- Reviews with recommend flag + aggregation
- Service requests (accept/reject/complete/cancel) linked to chat; polling chat; call/WhatsApp
- Seeded 4 specialists

## Backlog
- P1: manual admin verification review; push-free in-app notification badges; location/distance sorting
- P2: specialist subscription plans (monetization), quotes/pricing in requests, photo attachments in chat

## Iteration 2 (2026-06)
- Specialist membership: monthly 19,99 € / yearly 199,99 € — Stripe Checkout (one-time per period, status polling + webhook) and RevenueCat in-app subscriptions (Test Store in preview; entitlement mirrored to backend via /api/membership/revenuecat-sync)
- Gating: specialists without active membership hidden from directory, can't receive requests/new chats, can't accept or send quotes
- Quotes (ofertas): specialist sends price/description/time from requests or chat; client accepts/rejects → request accepted with agreed price
- Login/Home hero image changed to a well-kept house
- Backlog: Stripe auto-renew subscriptions, expiry reminder banner, invoices history

## Iteration 3 (2026-06)
- Rebrand to BE HAPPY: app name, icon/adaptive icon/favicon from user logo, native splash (behappy-splash.png, bg #F8F5EE) + in-app animated splash (src/AppSplash.tsx, 1.6s)
- Login: centered logo + title, language toggle moved to bottom

## Iteration 4 (2026-06)
- Camera permission prompt (bottom sheet) shown every time the user enters the app (launch + return from background) while camera not granted; "Abrir ajustes" when permanently denied (src/CameraPermissionPrompt.tsx)

## Iteration 5 (2026-06)
- AI diagnosis now uses the user's own Gemini API key (GEMINI_API_KEY in backend/.env), falls back to EMERGENT_LLM_KEY if absent. Model: gemini-3-flash-preview

## Iteration 6 (2026-06)
- Removed all seed/demo data and seed code; DB keeps only real user paniaguanapan.d.a@gmail.com
- Diagnosis speed: client compresses to max 1024px JPEG 0.6 (expo-image-manipulator); server re-shrinks (Pillow), Gemini reasoning_effort=low (~25s -> ~4-5s), image storage moved to background task
- Pending: testing_agent verification of compression flow (user paused to save to GitHub)

## Iteration 7 (2026-06)
- Diagnosis 3 outcomes: easy (steps only, no experts button), medium (steps + "Ver especialistas"), expert (no steps/materials/tools + button). Difficulty normalized backend-side.
- 5 trades only (plumbing, electrical, carpentry, hvac, appliances); specialists can have several (categories[]); filter chips = trades (toggle), active chip auto-scrolled
- Full i18n per viewer: diagnosis translated on demand (?lang=, cached in i18n.<lang>), titles in both langs, portfolio captions + review comments translated at creation, Turín/Torino, dates in es-ES/it-IT
- Experts = showcase: only members with >=1 work photo, cover = work photo, no avatar/years/rate/jobs/satisfaction, search by name only, no distance
- Ratings 1-5 once per client, only after the client wrote in chat; average shown from 3 ratings
- Service requests & quotes UI removed (deal/payment outside app); membership benefits text updated
- Gemini: own key first, falls back to Emergent universal key on failure (e.g. free-tier quota 429); errors 503

## Iteration 8 (2026-06)
- 5 groups: plumbing, electrical, hvac, masonry (Obra/Muratura: muratura, piastrellista, pintura, suelos, tejados), carpentry (puertas, ventanas, parquet, cerrajería, cristales). Appliances removed: appliance photos -> "en Turín normalmente se sustituye" (category "appliance", no specialists)
- Stripe removed (UI + backend); membership only via RevenueCat (EUR 19.99 / 199.99)
- ID document -> verification_status "in_review" (no auto badge, no admin screen)
- Scan tab: real damage photo (Wikimedia "Ceiling water damage"), only scan + gallery buttons
- Result: scanned phone photo shown instantly (localPhotos), result cached from POST (no extra fetch/translation), image stored in background, no double compression
- Profile: Cuenta / Historial segmented tabs; history rows photo/title/trade/date
