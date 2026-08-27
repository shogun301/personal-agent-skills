---
name: amazon-product-search
description: Search, verify, deduplicate, compare, and recommend products sold on Amazon while preserving an explicit Amazon retailer constraint. Use when the user says "search Amazon," "find this on Amazon," "best Amazon option," "compare Amazon listings," asks which Amazon listing to buy, or otherwise makes Amazon the requested retailer. Support general products and evidence-heavy compatibility research, especially automotive parts. Do not invoke merely because a product might be available on Amazon when the user did not express an Amazon preference.
---

# Amazon Product Search

## Preserve the retailer constraint

- Recommend Amazon listings only when the user requests Amazon products.
- Search outside Amazon only to verify specifications, identity, safety, authenticity, or compatibility.
- Never silently substitute Walmart, eBay, Home Depot, AutoZone, or another retailer because Amazon is difficult to parse.
- State the limitation if no Amazon listing can be verified.

## Discover Amazon listings

1. Normalize the user''s requirements before searching: product type, must-haves, exclusions, compatibility, budget, geography, and value criteria.
2. Construct `https://www.amazon.com/s?k=<form-URL-encoded search terms>`. Use `+` or `%20` for spaces and percent-encode reserved characters.
3. Attempt the Amazon search page when available.
4. If a browser-control surface is available and direct URL retrieval returns 503 or incomplete content, describe the focused Amazon UI attempt, ask for explicit permission, and wait. Only after permission is granted, submit the same query through Amazon's visible search box; the site UI may work even when direct navigation does not.
5. If Amazon results remain blocked, incomplete, or dynamically unparseable, continue automatically with web searches such as:
   - `site:amazon.com/dp <search terms>`
   - `site:amazon.com <exact model or part number> <search terms>`
   - `site:amazon.com <brand> <distinctive title phrase>`
6. Prefer individual `/dp/<ASIN>` pages and canonicalize verified links as `https://www.amazon.com/dp/<ASIN>`.
7. Search multiple phrasings and identifiers. Find several plausible competing listings rather than accepting the first hit.
8. Open candidate pages or cached/search-result evidence when possible. Treat snippets as weaker and potentially stale evidence.

Failure to parse Amazon''s search page is not failure to search Amazon.

## Build an evidence record

For each candidate, capture when available:

- title, brand, seller/manufacturer, ASIN, canonical Amazon URL
- current price and capture date/time, Prime status, rating, and review count
- model/part number, specifications, dimensions, material, construction, included accessories, and listing claims
- stated compatibility, fitment qualifiers, and explicit exclusions
- customer-review observations relevant to the request; verify that each review describes the selected variant because Amazon may pool ratings and reviews across unrelated style options
- variant, pack size, condition, or configuration that the price and facts describe

Do not invent unavailable fields. Mark material decision fields as `Unknown` or `Not verified`. Treat price, stock, Prime, ratings, review counts, sellers, and fulfillment as volatile.

## Label evidence precisely

Keep these categories distinct in notes and conclusions:

- **Listing claim**: stated by the Amazon seller or manufacturer listing.
- **Independent fact**: supported by OEM documentation, the manufacturer''s catalog, a regulator, a standards body, or another authoritative source independent of the Amazon listing.
- **Review observation**: reported by customers; summarize patterns and identify sparse or conflicting evidence.
- **Inference**: a reasoned conclusion from available evidence; explain the basis briefly.
- **Unknown**: evidence is missing, stale, ambiguous, or contradictory.

Never turn a listing claim or customer comment into an independently established fact.

## Normalize products

1. Deduplicate identical ASINs regardless of title or seller presentation.
2. Compare model numbers, specifications, photos, packaging, distinctive wording, dimensions, and included parts to detect likely private-label duplicates.
3. Keep separate variants separate when size, quantity, construction, accessories, warranty, fitment, or another meaningful property differs.
4. If products appear identical under different brands but proof is incomplete, label them `likely same underlying product` as an inference, not a fact.

## Verify compatibility and claims

- Do not trust Amazon''s automated compatibility selector by itself.
- Cross-check important compatibility with manufacturer fitment guides, OEM catalogs/part numbers, manuals, authoritative databases, and physical specifications whenever practical.
- Search exact model and part numbers, including superseded or interchangeable numbers.
- Resolve contradictions explicitly. Prefer primary authoritative documentation over reseller copy and title keywords.
- For automotive products, read [references/automotive-fitment.md](references/automotive-fitment.md) and follow it.

## Compare for the user''s actual decision

1. Define decision criteria from the request: verified fit, construction, quality, functionality, durability, completeness, return risk, price, and other relevant factors.
2. Eliminate or clearly flag candidates that fail must-haves or have unresolved safety/fitment questions.
3. Compare total value, not merely lowest price or highest Amazon rating.
4. Explain whether a premium option offers a meaningful, evidence-supported advantage.
5. Keep recommendations proportional to evidence. If a key property cannot be determined, say so rather than guessing.

## Report concisely

Return a compact comparison table of the strongest candidates, normally including:

| Amazon product | ASIN | Current price* | Key evidence | Important concern | Verdict |
|---|---|---:|---|---|---|

Follow it with:

- the recommended listing and why it best matches the user''s criteria
- a budget or premium alternative only when genuinely useful
- key unknowns or checks the buyer should complete before ordering
- direct canonical Amazon links whenever verified
- a note that volatile Amazon details can change, with the date checked

For compatibility-heavy requests, include explicit `Compatible`, `Incompatible`, or `Questionable / not verified` status and the evidence basis. Cite live and independent sources close to the claims they support.


