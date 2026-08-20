#!/usr/bin/env python3
"""
Liveness protistran, verze 2 — na úrovni kanálů.

Co dělá jinak než v1: v1 brala počet kanálů deklarovaný u uzlu a z něj
extrapolovala. To bylo špatně hned dvakrát — deklarované počty obsahují i dávno
zavřené kanály (ověřeno: 63 % uzlů se zatuchlým gossipem nemá otevřený ani jeden
kanál), a sběr grafu navíc kvůli chybějícímu stránkování velké uzly podvzorkoval.

v2 pracuje s konkrétními OTEVŘENÝMI kanály a s pubkeys obou koncových bodů, takže
každý kanál je posuzován sám za sebe.

Co to měří a co ne — explicitně, protože na tom stojí interpretace:
  Měří: kdy naposledy uzel poslal node_announcement do gossipu.
  Neměří: jestli je uzel dosažitelný na p2p vrstvě. Uzel může být živý a nemít
          důvod oznámení obnovovat; refresh intervaly se liší podle implementace.
  Proto: zatuchlý gossip je NUTNÁ, ne postačující podmínka opuštěnosti. Čísla
          níže jsou HORNÍ odhad počtu nespolupracujících protistran.
"""
import json, os, sys
from datetime import datetime, timezone

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
NOW = 1787270400   # 2026-08-20, den sberu
DAY = 86400

def main():
    nodes = {}
    for line in open(os.path.join(RAW, "ln_nodes.jsonl")):
        try:
            n = json.loads(line)
            if n.get("updated_at") and n["updated_at"] <= NOW + DAY:
                nodes[n["public_key"]] = n["updated_at"]
        except (json.JSONDecodeError, KeyError):
            pass

    chans = []
    for line in open(os.path.join(RAW, "ln_channels.jsonl")):
        try:
            c = json.loads(line)
            if c.get("capacity_sat") is not None:
                chans.append(c)
        except json.JSONDecodeError:
            pass

    meta = json.load(open(os.path.join(RAW, "ln_harvest_meta.json")))
    print(f"=== {len(chans)} otevrenych kanalu ({meta['coverage_pct']}% verejneho grafu), "
          f"{len(nodes)} uzlu s gossip timestampem ===\n")

    # pokryti: u kolika kanalu zname stari gossipu ASPON jednoho konce
    known, unknown = [], 0
    for c in chans:
        eps = c.get("endpoints") or []
        ages = [NOW - nodes[p] for p in eps if p in nodes]
        if ages:
            known.append((c, max(ages)))   # nejzatuchlejsi konec rozhoduje
        else:
            unknown += 1
    print(f"[i] u {len(known)} kanalu zname gossip aspon jednoho konce, "
          f"u {unknown} ne ({100.0*unknown/len(chans):.1f}% - typicky Tor-only uzly)\n")

    tot_cap = sum(c["capacity_sat"] for c, _ in known)
    print(f"{'nejzatuchlejsi konec':>24} {'kanalu':>8} {'% kan':>8} {'kapacita BTC':>14} {'% kap':>8}")
    buckets = [("<= 1 den", 0, DAY), ("1-7 dni", DAY, 7*DAY), ("7-14 dni", 7*DAY, 14*DAY),
               ("14-30 dni", 14*DAY, 30*DAY), ("30-90 dni", 30*DAY, 90*DAY),
               ("90-365 dni", 90*DAY, 365*DAY), ("> 1 rok", 365*DAY, 10**12)]
    for label, lo, hi in buckets:
        sel = [(c, a) for c, a in known if lo <= a < hi]
        cap = sum(c["capacity_sat"] for c, _ in sel)
        print(f"{label:>24} {len(sel):>8,} {100.0*len(sel)/len(known):>7.1f}% "
              f"{cap/1e8:>13,.1f} {100.0*cap/tot_cap:>7.1f}%")

    print(f"\n=== Kumulativne: kanaly, kde aspon jeden konec mlci dele nez ... ===")
    print(f"{'prah':>10} {'kanalu':>9} {'% kan':>8} {'kapacita BTC':>14} {'% kap':>8}")
    for label, thr in (("14 dni", 14*DAY), ("30 dni", 30*DAY), ("90 dni", 90*DAY),
                       ("1 rok", 365*DAY), ("2 roky", 730*DAY)):
        sel = [(c, a) for c, a in known if a >= thr]
        cap = sum(c["capacity_sat"] for c, _ in sel)
        print(f"{label:>10} {len(sel):>9,} {100.0*len(sel)/len(known):>7.1f}% "
              f"{cap/1e8:>13,.1f} {100.0*cap/tot_cap:>7.1f}%")

    # vek kanalu vs horizonty BIP-361
    tip = meta["harvested_tip_height"]
    SECS_PER_BLOCK = 594.6   # kalibrovano na 157 680 blocich, viz channel_age.py
    BPY = 365.25 * DAY / SECS_PER_BLOCK
    withh = [c for c in chans if c.get("funding_height")]
    tot_cap2 = sum(c["capacity_sat"] for c in withh)
    print(f"\n=== Vek kanalu vs horizonty BIP-361 ({len(withh)} kanalu) ===")
    print(f"{'horizont':>22} {'kanalu':>9} {'% kan':>8} {'kapacita BTC':>14} {'% kap':>8}")
    for label, yrs in (("1 rok", 1), ("2 roky", 2), ("3 roky (faze A)", 3),
                       ("5 let (faze A+B)", 5), ("7 let", 7)):
        sel = [c for c in withh if (tip - c["funding_height"]) >= yrs * BPY]
        cap = sum(c["capacity_sat"] for c in sel)
        print(f"{label:>22} {len(sel):>9,} {100.0*len(sel)/len(withh):>7.1f}% "
              f"{cap/1e8:>13,.1f} {100.0*cap/tot_cap2:>7.1f}%")

    # prusecik: stary kanal A ZAROVEN zatuchla protistrana
    print(f"\n=== Prusecik: kanal starsi nez 3 roky A ZAROVEN konec mlcici > 14 dni ===")
    thr_age = 3 * BPY
    sel = [(c, a) for c, a in known
           if c.get("funding_height") and (tip - c["funding_height"]) >= thr_age and a >= 14*DAY]
    cap = sum(c["capacity_sat"] for c, _ in sel)
    print(f"  {len(sel):,} kanalu ({100.0*len(sel)/len(known):.1f}% znamych), {cap/1e8:,.1f} BTC")
    print(f"\n[pozn.] Zatuchly gossip je NUTNA, ne postacujici podminka nespoluprace.")
    print(f"        Ber to jako HORNI odhad.")

if __name__ == "__main__":
    main()
