# What was tried, and why it is not here

Notes on paths investigated and abandoned, so they are not rediscovered from
scratch.

## Schedule 13D / 13G

**`date5PercentOwnership` is the only dated termination signal in the SEC
corpus.** Emanuel's TKO Amendment No. 6, filed 24 March 2025, says: "As of
March 24, 2025, the Reporting Person ceased to be a 5% owner." Nothing in
Form 4 can say that, because ceasing to be an insider's attributed holder is
not a transaction — the rows simply stop appearing.

Since 18 December 2024 these are XML, and the cover page carries
`aggregateAmountOwned` and `percentOfClass` as fields. `SC 13D` became
`SCHEDULE 13D` on that date; a filter matching only the old string hides
everything since.

It was abandoned because four conditions must coincide:

    above 5%                                     20 of 500
    an XML schedule naming the CEO                3 of 20
    that schedule newer than one of our groups    2 of 3
    the other classes convert into the scheduled one

And both cases where it fired were rows we get right. EchoStar's schedule is
two days newer than our groups — the rule measures RECENCY, not error, and
active filers amend schedules by default. It would have deleted Murdoch's
real Fox holding, which the schedule itself confirms to within 1,952 shares.

**Revisit only if two or three more companies show TKO's shape.** For one, the
exclusion list is the right tool.

## The proxy statement as an anchor

DEF 14A states beneficial ownership directly, after the filers' lawyers have
applied the disclaimers, and is what S&P Global reads — which is why Simply
Wall St separates Musk's trust from Emanuel's Endeavor block.

Rejected as a primary source: anchoring on it and rolling forward with Form 4
makes every figure depend on one parse of one HTML table, and a
misread poisons everything after. Today's design has no such dependency — a
bad group is one bad group.

Still worth having as a per-row CHECK, which cannot corrupt anything.

## Reading the disclaimer footnote

"Disclaims beneficial ownership except to the extent of his pecuniary
interest" is near-identical boilerplate and only ever removes shares, so it is
narrower than the free-text rules already removed. Not pursued, because the
whole day's direction was away from prose.
