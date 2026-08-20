#!/usr/bin/env python3
"""
Ekonomika jednostranného uzavření Lightning kanálu (force close).

Váhy commitment/HTLC transakcí jsou převzaty PŘÍMO z BOLT-3, Appendix A:
    Commitment weight (no option_anchors):   724 + 172 * num-untrimmed-htlc-outputs
    Commitment weight (option_anchors):     1124 + 172 * num-untrimmed-htlc-outputs
    HTLC-timeout weight (option_anchors): 666
    HTLC-success weight (option_anchors): 706
zdroj: https://github.com/lightning/bolts/blob/master/03-transactions.md

Váhy sweep a CPFP transakcí BOLT nespecifikuje (jsou na implementaci), takže je
odvozujeme z konstrukce skriptů níže a označujeme jako ODHAD.
"""
import json, os, sys
from collections import Counter

# --- BOLT-3, Appendix A (ověřeno proti specifikaci) ---
COMMITMENT_BASE_ANCHORS  = 1124
COMMITMENT_BASE_LEGACY   = 724
COMMITMENT_PER_HTLC      = 172
HTLC_TIMEOUT_ANCHORS     = 666
HTLC_SUCCESS_ANCHORS     = 706

# --- odvozené odhady (viz komentáře k výpočtu) ---
# to_local sweep po uplynutí CSV: P2WSH vstup, witness [sig, <>, witnessScript(77B)]
#   nesvědecky 82 B -> 328 WU; svědecky 2 + 154 = 156 WU
TO_LOCAL_SWEEP_WU = 484
# anchor CPFP: anchor vstup + peněženkový vstup, jeden výstup
ANCHOR_CPFP_WU    = 719
# to_remote sweep (option_anchors dělá i to_remote 1-blokově zpožděný P2WSH)
TO_REMOTE_SWEEP_WU = 440

MAX_BLOCK_WEIGHT = 4_000_000
BLOCKS_PER_DAY   = 144

def force_close_wu(n_htlcs=0, anchors=True, include_remote_sweep=False):
    """Celková váha blockspace spotřebovaná jedním jednostranným uzavřením."""
    base = COMMITMENT_BASE_ANCHORS if anchors else COMMITMENT_BASE_LEGACY
    commitment = base + COMMITMENT_PER_HTLC * n_htlcs
    htlc_txs = n_htlcs * (HTLC_TIMEOUT_ANCHORS if anchors else 663)
    total = commitment + htlc_txs + TO_LOCAL_SWEEP_WU
    if anchors:
        total += ANCHOR_CPFP_WU
    if include_remote_sweep:
        total += TO_REMOTE_SWEEP_WU
    return {
        "commitment_wu": commitment,
        "htlc_txs_wu": htlc_txs,
        "to_local_sweep_wu": TO_LOCAL_SWEEP_WU,
        "anchor_cpfp_wu": ANCHOR_CPFP_WU if anchors else 0,
        "to_remote_sweep_wu": TO_REMOTE_SWEEP_WU if include_remote_sweep else 0,
        "total_wu": total,
        "total_vb": round(total / 4.0, 1),
    }

def exit_cost_sat(feerate_sat_vb, n_htlcs=0):
    fc = force_close_wu(n_htlcs=n_htlcs)
    return round(fc["total_vb"] * feerate_sat_vb)

FEERATES = [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2000]

def load_channels():
    p = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "ln_channels.jsonl")
    if not os.path.exists(p):
        return []
    out = []
    with open(p) as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out

def main():
    chans = load_channels()
    print("=== Blockspace jednoho force-close (BOLT-3 vahy) ===")
    for n in (0, 1, 5, 10):
        fc = force_close_wu(n_htlcs=n)
        print(f"  {n:>2} HTLC: {fc['total_wu']:>6} WU = {fc['total_vb']:>7} vB "
              f"(commitment {fc['commitment_wu']}, htlc {fc['htlc_txs_wu']}, "
              f"sweep {fc['to_local_sweep_wu']}, cpfp {fc['anchor_cpfp_wu']})")

    print("\n=== Naklad exitu podle poplatkove sazby (0 HTLC) ===")
    print(f"  {'sat/vB':>8} {'naklad (sat)':>14} {'% medianoveho kanalu':>22}")
    MEDIAN_CAP = 2_006_756   # mempool.space LN statistics, 2026-08-20
    for fr in FEERATES:
        c = exit_cost_sat(fr)
        print(f"  {fr:>8} {c:>14,} {100.0*c/MEDIAN_CAP:>21.1f}%")

    if not chans:
        print("\n[!] data/raw/ln_channels.jsonl zatim neexistuje - sber jeste bezi")
        return

    caps = sorted(c["capacity_sat"] for c in chans if c.get("capacity_sat"))
    total_cap = sum(caps)
    print(f"\n=== Namerena distribuce kapacit ({len(caps)} kanalu) ===")
    for q in (1, 5, 10, 25, 50, 75, 90, 99):
        idx = int(len(caps) * q / 100)
        print(f"  p{q:<3} {caps[min(idx, len(caps)-1)]:>14,} sat")

    print(f"\n=== Podil kanalu, kde naklad exitu pohlti >X% kapacity ===")
    print(f"  {'sat/vB':>8} {'>10% kap.':>12} {'>50% kap.':>12} {'>100% kap.':>12}")
    for fr in FEERATES:
        c = exit_cost_sat(fr)
        n10 = sum(1 for x in caps if c > 0.10 * x)
        n50 = sum(1 for x in caps if c > 0.50 * x)
        n100 = sum(1 for x in caps if c > x)
        print(f"  {fr:>8} {100.0*n10/len(caps):>11.1f}% {100.0*n50/len(caps):>11.1f}% "
              f"{100.0*n100/len(caps):>11.1f}%")

    print(f"\n=== Agregatni blockspace hromadneho exitu ===")
    for n_htlc in (0, 2):
        wu = force_close_wu(n_htlcs=n_htlc)["total_wu"] * len(caps)
        scale = 33_221 / len(caps)     # extrapolace na vsechny verejne kanaly
        wu_all = wu * scale
        print(f"  {n_htlc} HTLC/kanal: {wu_all/1e6:>8.1f} MWU = "
              f"{wu_all/MAX_BLOCK_WEIGHT:>7.1f} bloku = "
              f"{wu_all/MAX_BLOCK_WEIGHT/BLOCKS_PER_DAY:>6.2f} dne plnych bloku")

if __name__ == "__main__":
    main()
