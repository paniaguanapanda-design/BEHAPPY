# RevenueCat — integrated (2026-06)
Memory for interacting with the user's RevenueCat account via integration proxy.

## Identifiers (from /setup)
- rc_project_id: proj74d102b8
- apple_app_id: app858bb8aaf8
- play_app_id: app07e58e735a
- entitlement_lookup_key: pro
- offering_lookup_key: default
- Packages:
  - $rc_monthly -> prodab4d2d41ff (EUR 19.99 / P1M, no trial)
  - $rc_annual  -> proda3333bdabc (EUR 199.99 / P1Y, no trial)
- Dashboard: https://app.revenuecat.com/projects/proj74d102b8
- bundle/package: com.emergent.fixmyhomecam.xal70a

## Status check
curl -sS -H "$AUTH" "$INTEGRATION_PROXY_URL/internal/revenuecat/projects/f71f6978-37f2-4edf-bad0-18b235203242/status"
If project_state < project_created, re-fetch the RevenueCat playbook via integration expert.

## Updates (integration proxy ONLY — never RevenueCat REST API)
- Upsert price/package: POST $INTEGRATION_PROXY_URL/internal/revenuecat/projects/f71f6978-37f2-4edf-bad0-18b235203242/products
  body {"products":[{"package":"$rc_monthly","price":19.99,"currency":"EUR","period":"P1M","prices":[{"amount_micros":19990000,"currency":"EUR"}]}]}
- Remove: DELETE .../products/%24rc_monthly
- Re-run idempotent /setup to recover identifiers / keys.

## App notes
- Client: src/revenuecat.tsx (init at module scope in app/_layout.tsx, logIn(user_id) in SubscriptionProvider).
- Paywall: app/membership.tsx (Stripe card + in-app). Backend mirrors entitlement expiry via POST /api/membership/revenuecat-sync so the specialist is listed to clients (required by product: hidden specialists).

## Going live (user steps)
1. Upload App Store Connect API key (.p8) / in-app purchase key and Google Play service-account JSON in RevenueCat dashboard.
2. Set up payment profiles in App Store Connect & Play Console.
3. Create matching subscription products with the SAME product IDs as RevenueCat.
4. Release build → TestFlight / internal testing → submit.
All steps are also in the FAQ of the payments panel.
