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
