#!/usr/bin/env python3
"""
Odhad podílu LN kapacity, jejíž protistrana vypadá opuštěně.

Proč to měří: kooperativní uzavření kanálu vyžaduje ŽIVOU protistranu, která
podepíše novou (a v postkvantovém světě: PQ) closing transakci. Není-li
protistrana dostupná, zbývá jen jednostranné uzavření opřené o PŘEDPODEPSANOU
commitment transakci. Právě ta je tím, co by sunset legacy podpisů zneplatnil.

Proxy pro "živost": pole updated_at z gossipu (poslední node_announcement).
BOLT-7 doporučuje uzlům periodicky obnovovat oznámení; implementace typicky
přestanou šířit uzly, které dlouho mlčí. Stale updated_at tedy signalizuje
uzel, který je off-line nebo opuštěný, ačkoli jeho kanály v grafu přetrvávají.

Známá omezení (uvádíme explicitně):
  - Vzorek pokrývá jen uzly s geolokací; Tor-only uzly chybí (~9 % uzlů).
  - updated_at odráží gossip, ne skutečnou dosažitelnost; uzel může být živý
    a jen nemít důvod přeposílat oznámení. Jde tedy o HORNÍ odhad živosti
    u čerstvých a DOLNÍ odhad opuštěnosti u starých hodnot.
"""
import json, os, sys
from datetime import datetime, timezone

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")

def load(name):
    p = os.path.join(RAW, name)
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p):
        try: out.append(json.loads(line))
        except json.JSONDecodeError: pass
    return out

def main():
    nodes = load("ln_nodes.jsonl")
    if not nodes:
        print("[!] ln_nodes.jsonl chybi"); return
    # referencni cas je PEVNY (den sberu), ne max() - gossip pripousti clock skew
    # a jeden uzel ve vzorku hlasi cas v roce 2030.
    NOW = 1787270400  # 2026-08-20T00:00:00Z, den sberu
    now = NOW
    nodes = [n for n in nodes if n.get("updated_at") and n["updated_at"] <= now + 86400]
    print(f"=== Vzorek: {len(nodes)} uzlu, referencni cas {datetime.fromtimestamp(now, timezone.utc):%Y-%m-%d} ===\n")

    DAY = 86400
    buckets = [
        ("<= 1 den",        0,        1*DAY),
        ("1-7 dni",         1*DAY,    7*DAY),
        ("7-14 dni",        7*DAY,   14*DAY),
        ("14-30 dni",      14*DAY,   30*DAY),
        ("30-90 dni",      30*DAY,   90*DAY),
        ("90-365 dni",     90*DAY,  365*DAY),
        ("> 1 rok",       365*DAY,  10**9),
    ]
    tot_n = len(nodes)
    tot_cap = sum(n.get("capacity_sat") or 0 for n in nodes) / 2.0  # kazdy kanal ma 2 konce
    tot_ch  = sum(n.get("channels") or 0 for n in nodes) / 2.0
    print(f"{'stari gossipu':>14} {'uzlu':>7} {'% uzlu':>8} {'kapacita BTC':>14} {'% kap':>7} {'kanalu':>8} {'% kan':>7}")
    cum_stale_cap = cum_stale_ch = 0
    for label, lo, hi in buckets:
        sel = [n for n in nodes if n.get("updated_at") and lo <= (now - n["updated_at"]) < hi]
        cap = sum(n.get("capacity_sat") or 0 for n in sel) / 2.0
        ch  = sum(n.get("channels") or 0 for n in sel) / 2.0
        print(f"{label:>14} {len(sel):>7} {100.0*len(sel)/tot_n:>7.1f}% "
              f"{cap/1e8:>13,.1f} {100.0*cap/tot_cap:>6.1f}% {ch:>8,.0f} {100.0*ch/tot_ch:>6.1f}%")
        if lo >= 14*DAY:
            cum_stale_cap += cap; cum_stale_ch += ch

    print(f"\n>>> Uzly bez gossipu > 14 dni (bezna prune hranice):")
    print(f"    kapacita {cum_stale_cap/1e8:,.1f} BTC ({100.0*cum_stale_cap/tot_cap:.1f}% vzorku)")
    print(f"    kanalu   {cum_stale_ch:,.0f} ({100.0*cum_stale_ch/tot_ch:.1f}% vzorku)")

    # vek uzlu (first_seen) - jak dlouho uz kanaly potencialne existuji
    fs = sorted(n["first_seen"] for n in nodes if n.get("first_seen"))
    if fs:
        print(f"\n=== Stari uzlu (first_seen), kvantily ===")
        for q in (10, 25, 50, 75, 90):
            v = fs[int(len(fs)*q/100)]
            print(f"  p{q:<3} {(now-v)/365/DAY:>5.2f} let  ({datetime.fromtimestamp(v, timezone.utc):%Y-%m-%d})")

if __name__ == "__main__":
    main()
