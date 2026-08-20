# BIP-361 Phase A and Lightning's unilateral exit: an audit finding, and a measurement

*Draft for discussion, 2026-08-20, block height 963,314.
Scripts and data snapshot: see §7. Supersedes an earlier version of this document that
contained an error; see §8.*

## 0. What this is, and what it is not

This is **not** a discovery. The core observation belongs to Boris Nagaev, who made it on the
bitcoindev list on 2025-07-16, in the BIP-361 proposal thread itself:

> Note that permanently blocking sends to vulnerable addresses can also be confiscatory. For
> example, someone might have a presigned transaction, like a Lightning force-close, where the
> destination address is a vulnerable address. If that path is blocked, the funds could be lost.
> If sending is temporary, the funds can be recovered later.

That sentence is thirteen months old and is the whole mechanism.

What this document adds is narrower: an audit of what happened to that objection, an argument
that the one remedy ever proposed for it does not work for Lightning specifically, and a
measurement of the affected population over the full public channel graph.

Three other things I initially thought were contributions turned out not to be, and I list them
so nobody has to spend time discovering it: soft-fork monotonicity — that no output can be built
inert now and live after a future soft fork — was covered by conduition (2025-07), Riard and
Wuille (2026-07); that BOLT-7 gossip publishes funding pubkeys was stated by Ivezic (2026-05-12)
naming the fields; and the n-of-n rescue-proof question was asked by Nagaev and answered by
conduition in April 2026.

## 1. The mechanism

BIP-361's `Specification` table, Phase A:

> Permitted sends are from legacy scripts to PQ scripts.

with `Backward Compatibility`:

> After Phase A, they can no longer receive from any other wallets and can only send to upgraded
> wallets.

Phase A is therefore a restriction on the **outputs a transaction may create**, not on spending
legacy inputs.

For an ordinary holder this is mild: you choose your outputs when you spend, so Phase A just
changes where you send. For the holder of a pre-signed transaction it is not, because the output
set was fixed by the counterparty's signature. BOLT 3:

> A valid signature MUST sign all inputs and outputs of the relevant transaction (i.e. MUST be
> created with a SIGHASH_ALL signature hash), unless explicitly stated otherwise.

A Lightning commitment transaction spends a 2-of-2 P2WSH funding output and pays to `to_local`
(P2WSH), `to_remote` (P2WPKH or CSV-1 P2WSH), HTLC outputs (P2WSH) and anchors (330-sat P2WSH).
Every one of those is a legacy script. Broadcasting it after Phase A is a legacy-to-legacy send.

The consequence is not primarily that funds are lost — that is Nagaev's framing and it is
correct as far as it goes. It is that **unilateral exit stops working**, and unilateral exit is
the invariant Lightning is built on. BOLT 5 defines the two ways a channel closes:

> 1. The good way (mutual close): at some point the local and remote nodes agree…
> 2. The bad way (unilateral close): something goes wrong, possibly without evil intent…

The second path exists precisely for the case where agreement is unavailable. After Phase A, an
open channel becomes a construction you can only leave with your counterparty's consent.

### 1.1 The reading this depends on, and why I think it is the only coherent one

The Abstract says "Disallows sending of any funds to quantum-vulnerable addresses". If
"quantum-vulnerable" meant only scripts with an exposed public key, the channel's hash-protected
P2WSH outputs would be permitted and this whole objection collapses. I do not think that reading
survives:

- The `Specification` table draws a binary between "legacy scripts" and "PQ scripts", not
  between exposed and hashed ones.
- `Backward Compatibility` forbids a non-upgraded wallet from **receiving** at all, which a
  hash-protected P2WPKH wallet plainly is.
- The `Rationale` speaks of "disallowing new spends to quantum vulnerable script **types**".
- The BIP lists short-range attacks among the threats it addresses, and a P2WSH output exposes
  its keys when spent, so P2WSH is quantum-vulnerable on the BIP's own definition.
- conduition, reviewing PR #1895 on 2026-04-15, read it the same way — "we would permanently
  disable sending to anything but P2MR" — and was not contradicted by the authors.

This should be argued rather than assumed, which is why it is here and not in a footnote. If the
authors intend the narrow reading, saying so would dissolve most of this document.

### 1.2 What is not an escape route

- **Anchors and CPFP** do not help. They improve the fee position of a *valid* parent. A parent
  that is consensus-invalid never enters a mempool, and no child rescues it. The anchors are
  themselves P2WSH, i.e. part of the forbidden output set.
- **`SIGHASH_SINGLE|SIGHASH_ANYONECANPAY`** does not help. It applies to second-stage HTLC
  transactions under `option_anchors`, not to the commitment transaction, and even there it
  commits to an index-paired P2WSH output. `ANYONECANPAY` permits adding inputs for fee bumping,
  nothing else.
- **Re-signing with PQ outputs, splicing, dynamic commitments, `option_simple_close`** are all
  co-signed. Every escape route is cooperative, which means it is available exactly to the set of
  channels that did not need unilateral exit in the first place.

One symmetry worth conceding: both parties are frozen, not just one. That does not restore
unilateral exit. It converts it into mutual hostage-taking, and the leverage is asymmetric — a
peer holding little or none of the channel balance is nearly indifferent to being frozen.

## 2. What I believe is actually new

**(a) The only remedy ever proposed does not work for Lightning.** Nagaev proposed replacing
permanent blocking with temporary restrictions, and later two concrete mechanisms: an incremental
rollout across 256 UTXO groups keyed on the first TXID byte, and an `OP_RETURN` opt-out valid for
2016 blocks. Both are adequate for a static UTXO and neither works for a *timed* contract.
Lightning has absolute deadlines — `to_self_delay` (CSV) and HTLC `cltv_expiry` (the
HTLC-timeout locktime). During a blocking window you cannot broadcast; by the time the window
lifts, an HTLC deadline may have passed and the counterparty can claim with the preimage. The
`OP_RETURN` opt-out is worse: it must be filed *before* you know you need a force-close, and
force-closes are by definition unplanned.

**(b) The Phase B rescue story is structurally inapplicable to Phase A.** BIP-361 has a developed
(if TBD) recovery story for Phase B — BIP-32 hardened derivation, ZK-STARK proofs, commit/reveal
— and none for Phase A. More than that: those mechanisms all prove *knowledge of a key*. A
pre-signed commitment transaction has both valid signatures and is invalid anyway, because of its
**outputs**. No proof of key knowledge can fix an output-set restriction. The asymmetry between
the two phases is not an oversight of degree, it is a category difference.

**(c) It contradicts the BIP's own incentive thesis.** The BIP argues the restriction "turns
quantum security into a private incentive to upgrade". For a bilateral contract, the cost lands
on whichever party's counterparty failed to act. That is an externality, not a private incentive
— a counterexample to the document's own justification.

**(d) The audit trail.** The objection was raised once, in one sentence, by one person.
conduition quoted it verbatim on 2025-07-20 and replied only to an unrelated question later in
the same message. Lopp never responded. Nagaev's two follow-up remedy proposals drew, as their
only reply, an advertisement for an altcoin. Nine months later the BIP was merged. In the merged
text, `grep -iE 'lightning|pre-sign|presign|grandfath|exempt|unilateral|force.?close|channel|SIGHASH'`
over all 179 lines returns nothing; the 103 comments on PR #1895 contain no mention either.

I want to be careful about how much weight (d) carries. An unanswered objection can mean the
community judged it unimportant rather than missed it. But an unanswered objection that also
never made it into the document, in a specification whose entire `Specification` section is a
four-row table with no definition of "legacy script" and no `Deployment` section, is worth
raising again.

## 3. Measurement

Full public channel graph, 2026-08-20 at height 963,314: **33,700 channels**, 101% of the
API-reported count (the overcount is churn during collection). Node gossip timestamps known for
33,467 of them; the 233 without are typically Tor-only.

**Counterparty responsiveness**, by the staler of the two endpoints:

| Staler endpoint last gossiped | Channels | % | Capacity BTC | % |
|---|---|---|---|---|
| ≤ 1 day | 27,382 | 81.8% | 3,628.5 | 96.9% |
| 1–14 days | 906 | 2.7% | 46.3 | 1.2% |
| > 14 days | 5,179 | 15.5% | 69.4 | 1.9% |
| > 1 year | 3,448 | 10.3% | 52.5 | 1.4% |

**Channel age against the Phase A horizon:**

| Age | Channels | % | Capacity BTC | % |
|---|---|---|---|---|
| > 1 year | 16,550 | 49.1% | 1,061.0 | 28.2% |
| > 2 years | 10,559 | 31.3% | 515.1 | 13.7% |
| **> 3 years (Phase A window)** | **8,053** | **23.9%** | **241.4** | **6.4%** |
| > 5 years | 4,119 | 12.2% | 59.0 | 1.6% |

**The intersection is the number that matters** — channels old enough to plausibly still be open
when Phase A arrives *and* with a counterparty that appears gone:

> **3,450 channels — 10.3% of the public network — holding 49.3 BTC.**

Say the size plainly: **roughly fifty bitcoin**. This is not a systemic loss of value and I am
not going to dress it up as one. 81.8% of channels have both ends gossiping within a day and hold
96.9% of capacity; the healthy core is very healthy. The claim is about an invariant and about a
long tail, not about an aggregate.

**Funding output types.** A systematic sample of 1,500 channels ordered by funding height,
resolved through `short_channel_id` → block → transaction, found `v0_p2wsh` in **all 1,500**,
with zero resolution failures. By the rule of three that bounds taproot funding among announced
channels below 0.2% at 95% confidence. Taproot funding is therefore
rare *among announced channels*. It does **not** follow that taproot channels are rare: lnd 0.21
ships production simple taproot channels behind an explicit `--channel_type=taproot`, and eclair
0.14 ships them explicitly **without announcements**. The honest reading is that taproot channels
are largely invisible to public gossip, and that this measurement — like everything else here —
describes the announced graph only.

## 4. Limitations

- Gossip freshness is a proxy for reachability, not a measurement of it. A node may be live and
  have no reason to re-announce. Treat the >14-day figures as an **upper bound** on
  unresponsiveness. The number a reviewer will actually want — capital in channels whose
  counterparty failed to answer a cooperative close attempt — requires operating a node and
  attempting closes, which I have not done.
- Unannounced channels are entirely invisible here, and by §3 they are probably where taproot
  channels live. Their share of the network is unknown.
- Channel age is not survival. That 23.9% of channels are older than three years today is a
  proxy for how many survive such a window; a real answer needs a survival model, not a
  histogram.
- Phase A is not scheduled. BIP-361 is not activated, Phase A falls 160,000 blocks after
  activation, and Lopp put the earliest plausible enforcement at January 2030. The ecosystem has
  years of warning and most channels will close or splice long before. This concerns a residual
  class, not Lightning as a whole.
- BIP-361 is Status: Draft, Type: Informational, `Requires: TBD Post Quantum Signature BIP`. It
  is fair to say this is an underspecified document rather than a decision to break Lightning.
  That is precisely why I would rather raise it now.

## 5. What I am asking for

Not a redesign. Two honest options, either of which closes this:

1. **Write a carve-out** for spends whose inputs were signed before Phase A takes effect, or
2. **Write one sentence** saying the authors accept this cost and why.

What should not happen is that it stays unaddressed in a document that has now been merged.

A third, for the Lightning side rather than the consensus side: the escape routes in §1.2 are all
cooperative. If Phase A stands as written, the channels that need help are the ones whose
counterparty is gone, and no consensus-layer rescue protocol can reach them. Whether a
non-cooperative migration path for existing channels is constructible at all is a question for
BOLT authors, and I do not have an answer to it.

## 6. Questions

1. Is the narrow reading of "quantum-vulnerable" in §1.1 the intended one? If so, most of this
   dissolves and it would be worth saying explicitly.
2. Is there a remedy for pre-signed timed contracts that a temporary-blocking scheme misses?
3. Does anyone have measurements of unannounced channels that would let §3 cover the network
   rather than the announced graph?

## 7. Reproducibility

All measurements come from public APIs; no archival node is required. Python 3, standard library
only.

| Script | Produces |
|---|---|
| `src/harvest_ln_nodes.py` | node metadata via bulk country/ISP endpoints |
| `src/harvest_ln_graph3.py` | full channel graph, paginated, with both endpoint pubkeys |
| `src/liveness_v2.py` | §3 responsiveness and age tables, per channel |
| `src/funding_script_types.py` | §3 funding output sample |
| `src/validate_liveness.py` | the check that caught the sampling bug in §8 |
| `src/blockspace_model.py` | BIP-141 weight model (not used above; retained) |
| `src/exit_economics.py` | BOLT-3 force-close weights (not used above; retained) |

`data/raw/` holds the point-in-time snapshot, versioned rather than regenerated because the
gossip graph changes daily.

## 8. Corrections to earlier versions

Recorded rather than quietly patched, since earlier versions were public.

- **A factual error.** An earlier version claimed that BOLT-7 gossip publishing the funding
  pubkeys destroys the knowledge asymmetry BIP-361's rescue protocols rely on. It does not.
  BIP-361 grounds that asymmetry in BIP-32 hardened derivation — knowledge of a parent XPriv —
  and its threat model already assumes the public key is exposed. A quantum attacker recovers the
  private key but not the parent XPriv. The inference was mine and it was wrong.
- **A sampling bug.** The mempool.space `/channels?public_key=` endpoint returns at most 10
  results per page and paginates via `index`. An earlier harvester did not paginate and took only
  the first 10 channels of each node, capping coverage at 61% and under-sampling large nodes. The
  figures in §3 come from a corrected re-harvest at 101% coverage. The previously reported 22.7%
  stale-counterparty figure was overstated; it is 15.5%.
- **Overstated novelty.** An earlier version presented as its own several points that are prior
  art. See §0.
