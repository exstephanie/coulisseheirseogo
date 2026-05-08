# Phase 3 — Outstanding Manual Fixes

Live state verified 2026-05-08. Items below cannot be done via API; they need direct dashboard access.

---

## ✅ Already live (no action needed)
- HairSalon schema on homepage
- AggregateRating (4.9★, 306 reviews)
- FAQPage schema
- Meta descriptions on all pages + blog posts
- Privacy policy page at /privacy-policy/

---

## 🚨 1. Cloudflare — strip `x-robots-tag: noindex` from sitemap (CRITICAL)

**Why:** Sitemap currently returns `x-robots-tag: noindex`, telling Google not to use it. This is the single biggest unresolved SEO blocker.

**Verify before:** `curl -sI https://coulisseheir.com/sitemap_index.xml | grep -i x-robots` → should show `noindex`

**Steps:**
1. Cloudflare dashboard → coulisseheir.com → Rules → Configuration Rules → Create Rule
2. Name: `Strip x-robots-tag from sitemap`
3. When: `(http.request.uri.path contains "sitemap") and (http.request.uri.path.extension eq "xml")`
4. Then: Set Response Header → `X-Robots-Tag` → value `index, follow` (Operation: Set)
5. Deploy

**Verify after:** same curl — header should be gone or show `index, follow`

---

## 2. Cloudflare — enable HSTS

**Why:** Tells browsers to always use HTTPS; ranking + security signal.

**Steps:**
1. Cloudflare → SSL/TLS → Edge Certificates → HTTP Strict Transport Security (HSTS) → Enable
2. Settings:
   - Max Age: 6 months
   - Apply HSTS to subdomains: ON
   - Preload: OFF (turn on later after 6 months stable)
3. Save

**Verify:** `curl -sI https://coulisseheir.com/ | grep -i strict-transport`

---

## 3. WP Admin → Rank Math (3 changes, one session)

**Login:** https://coulisseheir.com/chsysadmin

| # | Path | Change |
|---|------|--------|
| a | Rank Math → General → Breadcrumbs | Toggle ON |
| b | Rank Math → Titles & Meta → Local SEO → Business Type | LocalBusiness → **HairSalon** |
| c | Rank Math → General → Sitemap | Confirm "Add Sitemap to robots.txt" toggle is ON |

**Verify a:** `curl -s https://coulisseheir.com/ | grep -o '"@type":"BreadcrumbList"'` — should match.

---

## 4. Elementor — fix postal code on Contact page

**Why:** Page shows `Singapore 2312345` (wrong); should be `238801`.

**Steps:**
1. WP Admin → Pages → Contact (ID 413) → Edit with Elementor
2. Find the address text widget showing `Orchard Rd, #04-02 Singapore 2312345`
3. Change `2312345` → `238801`
4. Update

**Verify:** `curl -s https://coulisseheir.com/contact-us/ | grep -oE 'Singapore [0-9]+'`

---

## 5. Google OAuth → publish app to Production

**Why:** App is in testing mode → refresh tokens expire every 7 days → GBP posting + review fetching fails silently every week.

**Steps:**
1. https://console.cloud.google.com → project `innate-gizmo-495304-m0`
2. APIs & Services → OAuth consent screen → click **Publish App**
3. Fill submission:
   - App homepage: `https://coulisseheir.com`
   - Privacy policy URL: `https://coulisseheir.com/privacy-policy/` ✅ (already exists)
   - Terms of service: leave blank or point to /terms-and-conditions/ if exists
   - Authorized domain: `coulisseheir.com`
   - Scope justification (for GBP API): *"Internal SEO automation tool used by EX Group to manage Google Business Profile posts and read review data for the Coulisse Heir salon. Tokens stored only in GitHub Secrets, used only by scheduled GitHub Actions workflow."*
4. Submit for verification

**Timeline:** Google review takes 1–4 weeks. Until approved, manually re-auth weekly if tokens expire.

---

## 6. PDPA — draft email to legal/marketing

**Subject:** PDPA check — quoting Google review snippets in Coulisse Heir blog posts

> Hi [name],
>
> Quick PDPA question on a content initiative for Coulisse Heir.
>
> Our SEO automation agent writes weekly blog posts that include short, lightly edited quotes from our public Google reviews — typically 1–2 sentences with the reviewer's first name only (e.g., *"Sarah said the Reset 45 was the most relaxing 45 minutes of her week"*). Reviews are already public on Google Maps; we're republishing them in a different context (our own blog) to add social proof and improve SEO.
>
> Two questions:
> 1. Does republishing first-name + review snippet on our own site trigger PDPA notification or consent obligations, given the data is already publicly published by the reviewer?
> 2. Should we anonymise (e.g., "one client" instead of "Sarah") to be safe, or is first-name attribution acceptable?
>
> Happy to share a sample article. The agent is built to ship one post a week — currently paused pending your input.
>
> Thanks,
> Stephanie

---

## After completion

Run from `/Users/viviankek/coulisseseoaudit/`:
```bash
bash scripts/19_verify_phase3.sh config/coulisse-heir.env
```

Then capture a fresh drift baseline:
```
/seo drift baseline https://coulisseheir.com
```
