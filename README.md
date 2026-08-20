# Post-quantum migration and Bitcoin's layer 2

Measurement tooling and a working draft on a question the current post-quantum
proposals leave open: what a legacy signature sunset does to contracts that were
**signed once and are spent years later**.

BIP-360 (P2MR) and BIP-361 (Post Quantum Migration and Legacy Signature Sunset)
implicitly model a UTXO as owned by one party, present at spend time, whose public
key can stay secret until then. Lightning channels, DLCs, pre-signed vaults, Ark
exit paths and statechains violate all three assumptions. The draft argues this is
structural rather than an implementation gap, because soft-fork monotonicity makes
a dormant "activate later" escape hatch impossible to build today.

The draft is in [`notes/draft.md`](notes/draft.md).

## Reproducing the numbers

Everything comes from public APIs — no archival node, no chain download.
Python 3 with only the standard library.

| Script | Produces |
| --- | --- |
| `src/blockspace_model.py` | BIP-141 weight model: cost of migrating the UTXO set, and steady-state throughput under NIST FIPS 204/205 signature sizes |
| `src/harvest_ln_nodes.py` | Lightning node metadata via bulk country/ISP endpoints |
| `src/harvest_ln_graph2.py` | Channel graph; funding heights decoded from `short_channel_id` |
| `src/counterparty_liveness.py` | Share of channels whose counterparty has stopped gossiping and so cannot close cooperatively |
| `src/exit_economics.py` | Force-close cost from BOLT-3 Appendix A weights |
| `src/funding_script_types.py` | P2WSH vs P2TR split of funding outputs |
| `src/channel_age.py` | Channel age against the BIP-361 phase horizons |

```
python3 src/blockspace_model.py        # self-contained, no network
python3 src/harvest_ln_nodes.py        # ~10 min, writes data/raw/
python3 src/harvest_ln_graph2.py       # ~45 min, writes data/raw/
python3 src/counterparty_liveness.py
```

The harvesters rate-limit themselves to stay polite to the public mempool.space
API. `data/raw/` holds point-in-time snapshots that are versioned rather than
regenerated, because the gossip graph changes daily.

## Status

Draft, published for review and criticism. Measured 2026-08-20 at block height
963,304. Known limitations and biases are recorded in the draft's own Limitations
section and in the `*_meta.json` files beside each snapshot; the liveness proxy in
particular is gossip freshness, not reachability.

Corrections are welcome, especially to the weight derivations that BOLT-3 does not
specify and to the prior art — if an argument here has already been made
elsewhere, please point me at it.
