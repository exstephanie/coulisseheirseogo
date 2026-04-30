# TODOS

## Pre-Build Dependencies

### Publish Google OAuth App to Production
- **What:** Apply for Google OAuth verification to move the GBP API app from "testing" to "production" status.
- **Why:** In testing mode, OAuth refresh tokens expire every 7 days, causing GBP posting and review fetching to silently fail weekly. Production status = permanent tokens.
- **How:** Go to Google Cloud Console > APIs & Services > OAuth consent screen > Publish app. Requires privacy policy URL and possibly a security review.
- **Effort:** S (application takes 10 min, Google review takes 1-4 weeks)
- **Priority:** P1 (blocks reliable v3 operation)
- **Depends on:** Nothing. Start immediately.

### Verify PDPA Compliance for Review Quoting
- **What:** Confirm that quoting Google reviews (with customer first names) in blog posts complies with Singapore's Personal Data Protection Act.
- **Why:** V3's entire content strategy is built around embedding real customer reviews in blog posts. If this violates PDPA, the core approach needs rethinking.
- **How:** Check with marketing executive or do a quick legal consult. Google reviews are public, but republishing names in a different context may trigger PDPA obligations.
- **Effort:** S (1-2 hour research or one email to a lawyer)
- **Priority:** P1 (blocks v3 going live with review-quoting content)
- **Depends on:** Nothing. Can verify while building.

## Deferred Features

### Multi-Brand Vault Structure
- **What:** Restructure vault/ as vault/{brand}/ with BRAND env var so each of Daniel's 5 beauty brands gets its own data.
- **Why:** Currently single-brand. Will need restructuring when brand #2 onboards.
- **Context:** Deferred during CEO review after outside voice flagged it as premature abstraction. Every path becomes brand-aware, adding complexity for 4 brands with no timeline.
- **Effort:** S (human: ~2h / CC: ~10 min)
- **Priority:** P3 (do when brand #2 is actually ready)
- **Depends on:** V3 stable for Coulisse Heir first.

### Competitor Keyword Analysis
- **What:** Cross-reference GSC striking-distance keywords with competitor rankings.
- **Why:** Would turn topic selection from "what we're close to ranking for" into "what we're close to AND competitors are beatable."
- **Context:** Deferred because no free competitor data source exists. Requires Ahrefs or SEMrush subscription (~$100/month). GSC striking-distance data is already in the base v3 plan.
- **Effort:** M (human: ~1 day / CC: ~20 min)
- **Priority:** P3 (add if/when paid SEO tools are available)
- **Depends on:** V3 + SEO tool subscription.

### Email Nurture from Blog Content
- **What:** Auto-generate weekly email digest from the blog post the agent just wrote. Send via Resend/SendGrid to customer list.
- **Why:** Research shows salon email with styling tutorials gets 60% open rates and doubles website conversions.
- **Context:** Skipped during CEO review. Different system. Keep v3 focused on SEO.
- **Effort:** M (human: ~1 day / CC: ~20 min)
- **Priority:** P2 (high value but separate initiative)
- **Depends on:** V3 + email list + email API setup.
