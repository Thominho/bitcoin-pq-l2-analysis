# BIP-361 Phase A and Lightning's unilateral exit

An audit finding and a measurement, concerning what BIP-361's Phase A would do to
Lightning channels that are open when it takes effect.

Phase A permits only sends from legacy scripts to PQ scripts. A pre-signed commitment
transaction pays to legacy outputs fixed by the counterparty's `SIGHASH_ALL` signature,
so broadcasting it is a legacy-to-legacy send. The effect is that **unilateral exit
stops working** — the invariant Lightning is built on — and every remaining escape route
is cooperative, so it is available exactly to the channels that never needed unilateral
exit.

**This observation is not mine.** Boris Nagaev made it on the bitcoindev list on
2025-07-16, in the BIP-361 proposal thread. It was never answered and never made it into
the document. What this repository adds is an audit of that, an argument that the one
remedy ever proposed does not work for a timed contract, and a measurement.

The draft is in [`notes/draft.md`](notes/draft.md).

## The measurement

Full public channel graph, 2026-08-20 at height 963,314 — 33,700 channels, 101% of the
API-reported count:

- **15.5%** of channels have a counterparty that has not gossiped in over 14 days
- **23.9%** are already older than Phase A's three-year window
- **3,450 channels — 10.3% of the network, 49.3 BTC** — are both

Roughly fifty bitcoin. This is not a systemic loss of value and the draft does not claim
it is; 81.8% of channels have both ends gossiping within a day and hold 96.9% of
capacity. The argument is about a security invariant and a long tail.

## Reproducing it

Public APIs only. No archival node, no chain download. Python 3, standard library.

```
python3 src/harvest_ln_nodes.py     # node metadata, ~10 min
python3 src/harvest_ln_graph3.py    # full channel graph, paginated, ~45 min
python3 src/liveness_v2.py          # the tables in section 3
```

`data/raw/` holds the snapshot, versioned rather than regenerated because the gossip
graph changes daily. Each snapshot has a `*_meta.json` recording coverage and known bias.

## Status

Draft, published for criticism. Section 8 records two corrections to earlier public
versions of this document, including one outright factual error, because they were
public before they were wrong. Section 4 states the limitations; the most important is
that gossip freshness is a proxy for reachability rather than a measurement of it, so
the responsiveness figures are an upper bound.

Corrections are welcome, particularly to the reading of Phase A defended in §1.1 — if
the narrow reading is the intended one, most of this dissolves.

## License

MIT. Reuse the scripts, the measurements and the argument freely; a pointer back
is appreciated but not required.
