# Layer 2 and the Post-Quantum Sunset: three ownership assumptions that do not hold

*Draft for discussion. All measurements are reproducible with the scripts linked in §8.
Measured 2026-08-20 at block height 963,304.*

## Summary

BIP-360 (P2MR) and BIP-361 (Post Quantum Migration and Legacy Signature Sunset) are both
merged as Drafts, and the live discussion has moved to the choice of PQC output type. Both
proposals, and the rescue-protocol family BIP-361 describes, implicitly model a Bitcoin
UTXO as owned by **one party, present at spend time, whose public key may be kept secret
until then**.

Every deployed layer-2 construction violates all three parts of that model:

| Assumption | Held by | Violated by |
|---|---|---|
| **A1 — Secrecy.** The pubkey can be withheld until spend, so a rescue predicate can rest on knowledge asymmetry. | Unspent P2PKH / P2WPKH / P2MR | Public LN channels: BOLT-7 `channel_announcement` **mandates** publishing both funding pubkeys |
| **A2 — Presence.** The owner can sign a *new* transaction during the migration window. | Ordinary wallets | Pre-signed contracts: LN commitment/HTLC txs, DLC CETs, pre-signed vaults, Ark exit paths |
| **A3 — Unilateral knowledge.** One party holds all key material needed for a rescue proof. | Single-sig | n-of-n funding outputs: LN is 2-of-2 by construction |

I argue these are not implementation gaps but structural ones, because **soft-fork
monotonicity forbids the obvious fix**: it is impossible today to create an output that is
unspendable now and becomes spendable under a future soft fork. Therefore the stock of
un-rescuable long-lived contracts grows monotonically until a PQ opcode ships.

The sharpest consequence is earlier than it first appears. **Phase A, not Phase B, is what
breaks these contracts** — three years after activation rather than five. Phase A permits only
sends from legacy scripts *to PQ scripts*, and a pre-signed commitment transaction pays to
legacy outputs that were fixed when it was signed. It is a legacy-to-legacy spend by
construction, and Phase A has no rescue protocol to satisfy, because rescue protocols are a
Phase B concept.

Measured today: 24.3% of open public Lightning channels have already been open longer than
Phase A's entire window, and 22.7% have a counterparty that has not gossiped in over two weeks
and so cannot cooperate in a close. The value concentrated there is small — roughly 150 BTC in
the over-three-years bucket of a 61%-coverage sample — and the argument below does not depend
on it being large.

I then quantify the blockspace envelope of migration, which bounds any feasible schedule
independently of the above.

---

## 1. What is actually on the table

- **BIP-360 (P2MR)**, merged 2026-02-11, Draft. A new output type — SegWit v2, `bc1z`,
  `OP_2 OP_PUSHBYTES_32 <merkle root>` — i.e. taproot with the key path removed. It
  deliberately specifies **no** PQ signature scheme, and its own text limits its claim:
  P2MR outputs are "only resistant to long exposure attacks".
- **BIP-361**, merged 2026-04-14, Informational/Draft, header `Requires: TBD Post Quantum
  Signature BIP`. Two phases: Phase A (legacy → PQ sends only) at ~160,000 blocks
  (~3 years) after activation; Phase B two years later, which "[r]estricts ECDSA/Schnorr
  spends by encumbering them with a quantum-safe rescue protocol". It cites BIP-32
  hardened-derivation proofs, ZK-STARK rescue protocols, and commit/reveal as candidate
  rescue mechanisms, and reports that "over 34% of all bitcoin have revealed a public key
  on-chain" as of 2026-03-01.
- The output-type question is unsettled: Wuille's "PQC output type discussion" thread
  compares P2MR, P2TRv2, P2TRH, P2MR+PKR and P2QR, with a preference expressed for P2TRv2
  plus a "tripwire" that disables EC paths on observation of a successful NUMS-key
  signature.
- Bitcoin Core has **no** open PR implementing any of this.

The rescue-protocol family is the load-bearing part for what follows, because it is what
makes Phase B non-confiscatory. Every rescue mechanism described rests on the spender
proving knowledge of something a quantum attacker would not have derived — a parent xpriv,
a script preimage, a commit/reveal secret.

It is worth noting how thin the specification currently is. BIP-361's entire `Specification`
section is a four-row table. There are no consensus rules in pseudocode, no definition of
"legacy script", no reference implementation, and no `Security Considerations` section. Its
`Backward Compatibility` section discusses non-upgraded nodes and wallets only.

## 1a. Prior art, and why I believe this is a gap

I went looking for this argument before making it, and report what I found so it can be
checked:

- **Neither BIP mentions the problem.** `grep -i -E 'pre-signed|presigned|lightning|vault|
  channel|htlc|timelock|DLC|layer.2|L2'` over bip-0360.mediawiki and bip-0361.mediawiki
  returns zero hits in each. I also read BIP-361's 179 lines in full to check for
  paraphrase; the topic is not addressed indirectly either.
- **The active output-type thread does not raise it.** Delving 2749, "PQC output type
  discussion" (2026-07-27 to 2026-08-19), contains no mention of pre-signed transactions,
  Lightning, HTLCs, vaults, channels, DLCs, Ark or statechains.
- **The most relevant Lightning work stops short of it.** roasbeef's "Post Quantum
  Lightning: Layer by Layer" (Delving 2479, 2026-05-05) covers BOLT 11/12 invoice
  signatures, BOLT 8 transport, BOLT 7 gossip size, BOLT 4 onion size and payment hashes.
  On channels it says only that "[a] new channel type can mechanically replace OP_CHECKSIG
  with OP_CHECKPQSIG". Migration of *existing* pre-signed commitment and HTLC transactions,
  and the interaction with a deadline, are not treated.
- **The closest existing framing runs the other way.** Delving 2715 (Hal_03, 2026-07-14)
  asks what post-quantum means for an L2 when settlement happens on a non-PQ L1 — i.e. PQ
  off-chain against a classical L1. The direction here is the inverse: L1 restricts
  classical signatures and thereby invalidates off-chain transactions that were *already
  signed*.
- **The mailing list archive is empty on it.** A body-only full-text search of the
  bitcoindev archive for messages containing both "presigned"/"pre-signed" and "quantum"
  returns exactly one message, and there the two words co-occur by accident — it concerns a
  scriptPubKey size limit.

What is *not* new is the category of objection. "Pre-signed but unpublished transactions"
is already an established consideration in Bitcoin consensus review. Andrew Poelstra, on a
proposal to limit scriptPubKey length:

> There is a risk of confiscation of coins which have pre-signed but unpublished
> transactions spending them to new outputs with large scriptPubKeys. Due to long-standing
> standardness rules, and the presence of P2SH (and now P2WSH) for well over a decade, I'm
> skeptical that any such transactions exist.

Note the shape of the reasoning: the objection is accepted as valid in principle and
dismissed on the empirical claim that no such transactions exist. Gregory Maxwell's
"Non-confiscatory Transaction Weight Limit" (Delving 1732) and the scriptPubKey-length
proposal's deliberate exception (Delving 2150) show the same care being taken elsewhere.

The contribution here is therefore narrow and empirical rather than conceptual: for a
legacy signature sunset, the empirical claim that saved those earlier proposals is false.
Pre-signed, unpublished, un-re-signable transactions demonstrably exist, in the millions,
and they are the sole unilateral exit path for every channel that holds one.

## 2. A1 — Lightning publishes its funding keys, by mandate

BOLT-7 `channel_announcement` carries the fields `bitcoin_key_1` and `bitcoin_key_2`, and
the spec requires (lines 192–193):

> MUST set `bitcoin_key_1` and `bitcoin_key_2` to `node_id_1` and `node_id_2`'s respective
> `funding_pubkey`s.

This is not incidental — the announcement exists to prove the channel is backed by a real
UTXO, and verifiers need the keys to reconstruct the funding `scriptPubKey`.

The consequence is that **for a publicly announced channel, quantum exposure is total
regardless of output type**:

- **Legacy P2WSH funding output.** On-chain the output is a hash and would be
  hash-protected. Gossip publishes both funding pubkeys anyway. Gossip is strictly worse
  than the chain here.
- **Simple taproot channel (P2TR funding output).** The tweaked aggregate key is the
  `scriptPubKey`; it is exposed on-chain at rest, gossip or not.

So no output-type migration — P2MR, P2TRv2, or otherwise — removes the exposure of an
announced channel, and any rescue predicate resting on pubkey secrecy is unavailable to it.
This directly limits the layered hashed-address recovery proposals whose stated security
assumption is "keep your public key/internal script paths secret".

Unannounced ("private") channels do not publish gossip and are not subject to A1, though
they remain subject to A2 and A3.

## 3. A2 — Pre-signed transactions cannot be re-signed

A large class of Bitcoin contracts is signed once and broadcast much later, by a party who
cannot produce a new signature because the signature is not theirs alone to make:

| Construction | Pre-signed artifact | Re-signable unilaterally? |
|---|---|---|
| LN channel | commitment tx, HTLC-timeout/success txs | No — 2-of-2 funding |
| LN (any state) | every revoked and current commitment | No |
| DLC | all Contract Execution Transactions | No — oracle + counterparty |
| Pre-signed vault | unvault / recovery txs | No — signing key deliberately deleted |
| Ark / timeout trees | exit path branches | No — pre-signed by the operator set |
| Statechain | chain of transfer txs | No |

A sunset that invalidates classical signatures invalidates these artifacts. This is not an
expense — it is a liveness failure. The funds do not become costly to move; they become
immovable except by cooperation with a counterparty who may be gone.

### 3.1 Phase A breaks them, not Phase B

I initially assumed the damage happens at Phase B, when classical signatures stop verifying.
It happens two years earlier, at Phase A, and for a different reason.

Phase A's rule is: *"Permitted sends are from legacy scripts to PQ scripts."* Consider what a
Lightning commitment transaction actually is at that moment. It spends a legacy P2WSH funding
output, and it pays to `to_local`, `to_remote` and HTLC outputs that are themselves legacy
scripts. Those outputs were fixed when the transaction was signed and, per §3 above, cannot be
changed without a fresh signature from the counterparty. Broadcasting it is therefore a send
from a legacy script **to a legacy script** — exactly what Phase A forbids.

The same holds for DLC contract execution transactions and for pre-signed vault transactions,
whose destinations were likewise fixed at signing time, and in the vault case by a key that was
deliberately destroyed.

This matters for three reasons:

1. **It is earlier.** ~160,000 blocks (~3 years) after activation, not five.
2. **There is no rescue protocol at Phase A.** Rescue protocols are a Phase B construct. Phase A
   is a plain standardness/validity restriction on where funds may be sent, so there is nothing
   to satisfy.
3. **It is invisible in the text.** Neither BIP mentions any of these constructions, so it is
   genuinely unclear whether this consequence is intended, overlooked, or meant to be handled by
   an exception that has not been written.

I want to be careful about how strongly to put this. BIP-361's entire `Specification` is a
four-row table with no consensus rules, no pseudocode and no definition of "legacy script". The
reading above is the natural one, but the document is not precise enough to make it certain.
That imprecision is itself the finding: a rule with this consequence should not be ambiguous.

### 3.2 What the Lightning specification says

For Lightning this is spelled out in the specification rather than inferred. BOLT 5 on
unilateral close:

> MUST broadcast the *last commitment transaction*, for which it has a signature, to perform
> a *unilateral close*.

"for which it has a signature" is the whole problem: the node cannot construct a new
commitment transaction, only rebroadcast the one it was given. BOLT 3 says the same about
the HTLC transactions — HTLC-timeout "is the only way that the local node can timeout the
HTLC, and this branch requires `<remotehtlcsig>`", and HTLC-success likewise "requires
`<remotehtlcsig>`".

Nor can the destination be quietly redirected to a PQ output. Per BOLT 5, HTLC transactions
on anchor channels use `SIGHASH_SINGLE|SIGHASH_ANYONECANPAY` for the remote signature — which
still covers the output — and the commitment transaction is always `SIGHASH_ALL`. The
`ANYONECANPAY` flag permits adding inputs for fee bumping and nothing more. Changing an
output's `scriptPubKey` to a post-quantum type therefore requires a fresh signature from the
counterparty in every case.

**Deleted-key vaults are the sharpest case.** Their entire security model is that the
signing key was destroyed after pre-signing. There is nobody who *can* re-sign, by design.

**Ark is the mildest.** VTXOs created by boards and refreshes have a 28-day lifetime, and
those from Lightning receives 1–3 days, both operator-configurable. Short horizons mean the
pre-signed population turns over quickly, so Ark is far less exposed on this axis than
Lightning — an honest point against over-generalising the argument.

## 4. A3 — Nobody can produce the rescue proof alone

BIP-361's rescue predicates are stated per-key: prove knowledge of the parent xpriv behind
a pubkey. An LN funding output is 2-of-2. Party A knows their own derivation path and
nothing about B's. If the predicate must be satisfied for every key in the script, then
unilateral force-close — the one path that is supposed to work when the counterparty is
gone — requires precisely the counterparty who is gone.

There is a second problem specific to pre-signed artifacts. A rescue proof must distinguish
a legitimate owner from a quantum attacker. But the pre-signed transaction is not itself a
secret: an attacker who has derived the private keys can construct the same transaction. So
possession of the pre-signed artifact proves nothing, and the asymmetry has to come from
somewhere else — for Lightning, plausibly knowledge of the per-commitment seed or the
revocation basepoint preimages. **That predicate would have to be committed to in the
funding output's script**, which existing channels did not do, and could not have done —
see §5.

## 5. The structural obstacle: soft-fork monotonicity

The natural fix is to give long-lived contracts a dormant PQ escape hatch: a spend path
that is inert today and becomes live when a PQ opcode activates. **Under soft-fork-only
evolution this is impossible**, and taproot's upgrade hooks illustrate why.

BIP-341, script path spending:

> This implies that for the future leaf versions (non-`0xC0`) the execution must succeed.

with the rationale footnote "Why we need to success on future leaf version validation —
this is required to enable future leaf versions as soft forks". The same holds for
`OP_SUCCESSx` in BIP-342 and for unknown witness versions.

Every upgrade hook in Bitcoin works by being **permissive now and restricted later**. A
dormant escape hatch requires the opposite — **invalid now, valid later** — which is by
definition a hard fork. Concretely, committing today to a tapleaf with an
as-yet-undefined leaf version does not create a dormant PQ path; it creates a leaf that
succeeds unconditionally, handing anyone who knows the tree — starting with your channel
counterparty — an immediate unilateral sweep.

**Claim.** No output created under current consensus rules can carry a spend path that is
unspendable now and spendable after a future soft fork. Hence any contract's exit paths
must be valid under *today's* rules, and a contract created before a PQ opcode exists
cannot have a PQ exit path.

**Corollary.** The set of un-rescuable pre-signed contracts grows monotonically until a PQ
signature opcode is active. The cost of delay is not the delay itself; it is the accumulating
stock. This is an argument for shipping a PQ *spending* primitive early and independently of
the sunset schedule — the reverse of BIP-361's dependency order, which starts a 3-year Phase
A clock on activation of a document whose header still reads `Requires: TBD Post Quantum
Signature BIP`.

## 6. Measurements

### 6.1 The blockspace envelope

Weights computed per BIP-141 (`src/blockspace_model.py`). UTXO count 167,066,337
(blockchain.info charts API, 2026-08-15).

Migration into a *hashed* PQ commitment is signed classically and produces a 34-byte output,
so it is cheap per UTXO — the expensive part is deferred to later spends. This distinction
is often blurred in discussion.

| Batching | vB per UTXO | Total | Days at 100% of blocks | Days at 25% |
|---|---|---|---|---|
| 1-in/1-out | 121.5 | 81.2 GWU | 141.0 | 563.8 |
| 10-in/1-out | 73.3 | 49.0 GWU | 85.1 | 340.4 |
| 100-in/1-out | 68.5 | 45.8 GWU | 79.5 | 318.1 |

So a *complete* migration of the UTXO set costs on the order of **80–140 days of entirely
dedicated blockspace**, or **1–1.5 years at a sustained 25% share**. BIP-361's 3-year Phase A
is not obviously too short — but it has no slack for a fee market that also has ordinary
demand in it, and the tail of small-value UTXOs will never be economic to move at all.

Steady-state throughput after migration, 1-in/2-out:

| Scheme | sig / pk bytes | tx vB | tx per block | Throughput vs P2WPKH |
|---|---|---|---|---|
| ECDSA P2WPKH (baseline) | 72 / 33 | 140.5 | 7,117 | 1.0× |
| FALCON-512 | 666 / 897 | 530.0 | 1,887 | 0.27× |
| ML-DSA-44 | 2420 / 1312 | 1,072.2 | 933 | 0.13× |
| SLH-DSA-128s | 7856 / 32 | 2,110.8 | 474 | 0.067× |
| SLH-DSA-256s | 29792 / 64 | 7,602.8 | 132 | 0.018× |

A 7.6×–15× throughput collapse is the backdrop against which every forced on-chain exit in
§6.2 has to compete for space. It is also why the compact hash-based work (SHRINCS, ~324 B;
OP_CHECKSHRINCS, ~580 B) matters far more than its current visibility suggests.

### 6.2 Lightning exposure and counterparty liveness

Public network, 2026-08-20: 33,221 channels, 16,427 nodes, 3,783.2 BTC public capacity,
median channel 2,006,756 sat. Note the trend — public channel count has fallen from 67,698
(2023-08) to 33,221, and capacity from 4,714 to 3,783 BTC; a shrinking public graph is a
genuine counterargument to urgency and I flag it rather than bury it.

Counterparty liveness, from `node_announcement` freshness over a 14,898-node sample
(90.9% of nodes; Tor-only nodes are absent — stated bias):

| Gossip age | Nodes | % nodes | Capacity BTC | % cap | Channels | % chan |
|---|---|---|---|---|---|---|
| ≤ 1 day | 2,294 | 15.4% | 3,216.3 | 88.6% | 22,420 | 75.1% |
| 1–14 days | 511 | 3.4% | 36.0 | 1.0% | 639 | 2.1% |
| > 14 days | 12,093 | 81.2% | 377.1 | 10.4% | 6,790 | 22.7% |

**About 22.7% of public channels have at least one endpoint that has not gossiped in over
two weeks** — beyond the pruning horizon most implementations use. Those channels cannot be
closed cooperatively. They are exactly the population that depends on the pre-signed
commitment transaction, and exactly the population a sunset strands.

The concentration cuts the other way too: 15.4% of nodes hold 88.6% of capacity, so most
*value* sits behind live, responsive counterparties. The stranding risk is heavily weighted
toward the long tail of small channels — which is also the population least able to afford
an on-chain exit.

**How long do pre-signed commitments sit unused?** This matters directly, because a three-year
Phase A only strands channels that survive it. Antonelli et al. (arXiv 2605.12759, not peer
reviewed; 36,170 nodes, 2022-06 to 2024-10) report a median lifetime of 73 days among
channels that eventually close, with roughly 76% closing inside 180 days. That figure alone
would suggest the problem is small. The tail is what matters, and the same work finds the
probability of remaining open "increases sharply with age, reaching 0.93 for channels older
than a year".

So channel lifetime is strongly bimodal: most channels churn within months, and the ones that
survive a year largely stop closing at all. It is precisely that surviving population — the
long-lived, often forgotten channels, disproportionately the ones whose counterparty has
stopped gossiping — that a multi-year sunset horizon would find still open and still
depending on a pre-signed commitment transaction.

That population is directly measurable today. Decoding the funding block height from every
`short_channel_id` in a 20,302-channel sample (61.1% of the public graph, block time calibrated
at 9.91 min/block over the preceding 157,680 blocks):

| Channel age | Channels | % of channels | Capacity BTC | % of capacity |
|---|---|---|---|---|
| Older than 1 year | 10,217 | 50.3% | 656.7 | 27.4% |
| Older than 2 years | 6,567 | 32.3% | 344.5 | 14.4% |
| **Older than 3 years (Phase A)** | **4,941** | **24.3%** | **152.4** | **6.4%** |
| Older than 5 years (Phase A+B) | 2,674 | 13.2% | 33.9 | 1.4% |
| Older than 7 years | 1,371 | 6.8% | 9.7 | 0.4% |

Median age is 1.01 years. **Roughly a quarter of channels open right now have already been open
longer than Phase A's entire window**, and one in eight longer than Phase A and B combined.
These are channels that exist today, not a projection.

Note the inversion between the two columns, because it decides how alarming this is. Channels
older than three years are 24.3% of the count but only 6.4% of capacity; older than five years,
13.2% of count and 1.4% of capacity. The long-lived population is the small-channel tail. So the
honest characterisation is **many stranded channels holding little aggregate value** — on the
order of 150 BTC in the over-three-years bucket in this sample — rather than a systemic loss.
That is consistent with the liveness finding: the same tail of small, forgotten channels shows
up in both measurements.

The value at stake is thus modest and the design defect is not. A rule that silently makes some
users' only exit path invalid is a problem regardless of the aggregate, and the population it
hits is the one least equipped to notice a flag day and act on it.

### 6.3 Force-close economics

Weights from BOLT-3 Appendix A (`1124 + 172·n_htlc` for anchor channels, HTLC-timeout 666);
sweep and CPFP weights derived in `src/exit_economics.py` and marked as estimates.
One force close with 0 HTLCs = 2,327 WU = 581.8 vB.

| Fee rate | Exit cost | % of median channel |
|---|---|---|
| 10 sat/vB | 5,818 sat | 0.3% |
| 100 sat/vB | 58,180 sat | 2.9% |
| 500 sat/vB | 290,900 sat | 14.5% |
| 1000 sat/vB | 581,800 sat | 29.0% |
| 2000 sat/vB | 1,163,600 sat | 58.0% |

This is the *pre*-sunset failure mode — an exit rush ahead of a deadline, competing with the
migration wave of §6.1, at reduced throughput. It is a bad outcome but a recoverable one.
The *post*-sunset failure mode is not a fee problem at all: the pre-signed transaction simply
cannot be broadcast, at any price.

## 7. Design requirements

Stated as requirements on BIP-361 and on the PQC output type, not as a competing proposal.

- **R0 — Phase A needs an explicit answer for legacy-to-legacy spends of pre-signed
  transactions.** This is the one I would most like a response to. Either the restriction
  carries an exception for spends whose inputs were signed before some height, or the
  specification should say plainly that pre-signed contracts must be closed out before Phase A
  and give the ecosystem a stated deadline to work to. What it should not do is leave the
  question unanswered in a document whose `Specification` section is four rows long.

- **R1 — A rescue proof must be attachable to an already-signed input, and there is
  currently nowhere to put it.** A Phase-B encumbrance has to be satisfiable by data added
  to a transaction signed years earlier, without invalidating the existing signatures. Two
  obvious locations both fail:

  - *The annex is unusable.* BIP-341's `SigMsg` commits to `spend_type = (ext_flag * 2) +
    annex_present`, and to `sha_annex` when one is present. `spend_type` is always covered.
    So attaching an annex to a pre-signed taproot input flips a committed bit and
    invalidates the signature — **even an empty annex**.
  - *The witness stack is unusable.* Neither BIP-143 nor BIP-341 commits to other witness
    stack items, so appending is not a *signature* problem. But for tapscript the initial
    stack is the witness minus script and control block, so extra elements change script
    execution; and for the P2WSH 2-of-2 that legacy LN channels use, extra elements break
    `OP_CHECKMULTISIG` evaluation outright.

  Therefore the rescue proof needs a **new per-input field that is outside the script's
  initial stack and outside every legacy sighash preimage, whose presence flips no bit that
  legacy sighashes already commit to**. That is a stronger constraint than "put it in the
  witness", and it is exactly the property the per-input "witness style" / `pqdata` design
  in the segwit-PQ-commitment discussion would need to guarantee. I have not seen it stated
  as a requirement.
- **R2 — Rescue proofs must be satisfiable by a proper subset of the original signers.**
  A predicate requiring every key's owner to participate reproduces the liveness failure it
  is meant to prevent. For n-of-n contracts, any single party able to satisfy the original
  script should be able to produce the rescue proof.
- **R3 — A tripwire needs a grace window.** An adversarially-triggered EC shutdown fires at
  a time the attacker chooses, with no notice. Pre-signed artifacts have horizons ranging
  from LN's `cltv_expiry_delta` (up to 2016 blocks) to multi-year inheritance timelocks. Any
  tripwire should be paired with a grace period sized to the longest legitimate pre-signed
  horizon, or it becomes a tool for stranding L2 funds on demand.
- **R4 — Sequence the PQ spending primitive before the sunset clock.** By §5, contracts
  created before a PQ opcode exists cannot be built rescuable. Starting Phase A on
  activation of a document that still requires an unwritten signature BIP means the clock
  may run while the ecosystem is structurally unable to comply.
- **R5 — Anchor Phase B on measured readiness, not only on a block height.** Publish the
  exposure and L2-readiness metrics that gate the transition, so the flag day is a function
  of observed migration progress rather than a date fixed years earlier.
- **R6 — BOLT-level work is needed in parallel.** Rescuable channel constructions, and
  reconsidering whether `channel_announcement` must carry raw funding pubkeys, are Lightning
  spec questions that cannot be solved at the consensus layer alone.

## 8. Reproducibility

All numbers regenerate from public APIs; no archival node required.

| Script | Produces |
|---|---|
| `src/blockspace_model.py` | §6.1, BIP-141 weight model |
| `src/harvest_ln_nodes.py` | node metadata, 90.9% coverage |
| `src/harvest_ln_graph2.py` | channel graph, funding heights via `short_channel_id` |
| `src/counterparty_liveness.py` | §6.2 liveness table |
| `src/exit_economics.py` | §6.3, BOLT-3 weights |

## 9. Limitations

- The liveness proxy is gossip freshness, not reachability. A node may be live and simply
  have no reason to re-announce. Treat the >14-day figure as an upper bound on abandonment.
- Node channel counts come from the mempool.space aggregation; §6.2 percentages should be
  cross-checked against the harvested channel graph.
- Unannounced channels are invisible to this measurement. Their share is unknown and their
  omission biases the LN capacity figures downward.
- Sweep and CPFP weights in §6.3 are derived, not spec-mandated.
- PQ signature sizes are the NIST FIPS 204/205 parameters; the compact hash-based schemes
  under active development would change §6.1 materially. SHRINCS at ~324 bytes and
  OP_CHECKSHRINCS at ~580 bytes would move the throughput collapse from roughly 8–15× to
  under 2×, which is a different argument entirely.
- The channel sample covers 61.1% of the public graph, reached by greedy vertex cover over
  nodes ordered by declared channel count. Coverage is therefore biased toward hub-adjacent
  channels, which if anything *understates* the long tail that §6.2 is about.
- My measured public capacity (3,783 BTC) is below figures reported for May 2026 (~4,900–5,600
  BTC). The direction is consistent with the decline measured over the same period, but I have
  not reconciled the two methodologies.
- **Prior art I have not yet closed out**, stated so nobody has to discover it for me: I have
  not verified a secondary-source article titled "Fixing the Lightning Network's Quantum
  Problem: Why Layer 2 Is Harder Than Layer 1", which may cover related ground; I have not
  searched the lightning-dev archive or GitHub discussions in `lightning/bolts`,
  `lightningnetwork/lnd` or `ldk`, which are the most likely places this was raised if it was;
  and I have not swept conference proceedings (FC, AFT, CCS 2026). If any of these already
  make the argument, I would rather be told than credited.

## 10. Questions I would like answered

1. Is there a rescue predicate satisfiable by one party of an n-of-n whose asymmetry is not
   destroyed by public gossip?
2. Should Phase B distinguish outputs *created before* a PQ opcode existed from those created
   after? The former had no way to be built rescuable.
3. Is anyone modelling the interaction between the migration wave, the L2 exit rush, and
   post-migration throughput as a single fee-market event?
