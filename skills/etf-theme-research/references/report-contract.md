# Theme Report Contract

Required sections:

1. Theme definition and research boundary.
2. Executive summary labelled as a research hypothesis.
3. Supporting evidence cards with an internal evidence ID and URL plus user-facing Chinese title, fact summary, implication, source tier, confidence, and limitation. The UI exposes the source button but not the internal ID or raw URL text.
4. Counter-evidence and conflicting interpretations.
5. Investability and ETF landscape, using explicit unknown states when data is absent.
6. Disconfirming conditions and missing evidence.
7. Deterministic audit result and provenance appendix.
8. Independent `latestMarketSnapshot` and deduplicated `researchSources`; neither may mutate the report body, conclusion, version, or content hash.

Reject a generated section when it cites an unknown evidence ID, introduces a number absent from the evidence package, upgrades a secondary discovery to a verified fact, or converts missing data into a positive conclusion.
Reject Chinese evidence output when its entry count differs from the input or it adds a company or URL. DeepSeek may verify candidates, translate evidence and explain gaps; it must not generate market numbers.
