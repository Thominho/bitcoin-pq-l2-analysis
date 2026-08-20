#!/usr/bin/env python3
"""
Věková distribuce otevřených LN kanálů.

Motivace: BIP-361 navrhuje fázi A dlouhou 160 000 bloků (~3 roky) a fázi B o dva
roky později. Otázka zní, jak velká populace kanálů takový horizont přežije
otevřená — tedy kolik kanálů by sunset zastihl závislých na předpodepsané
commitment transakci.

Věk odvozujeme z short_channel_id, které kóduje výšku bloku funding transakce.
Převod bloků na čas kalibrujeme na skutečných timestampech, ne na nominálních
10 minutách.
"""
import json, os, sys
from urllib.request import urlopen, Request
from datetime import datetime, timezone

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
UA = {"User-Agent": "btc-pq-research/0.1"}

def blocktime(h):
    try:
        with urlopen(Request(f"https://mempool.space/api/block-height/{h}", headers=UA), timeout=30) as r:
            bh = r.read().decode().strip()
        with urlopen(Request(f"https://mempool.space/api/block/{bh}", headers=UA), timeout=30) as r:
            return json.loads(r.read().decode())["timestamp"]
    except Exception as e:
        print(f"[!] blocktime({h}): {e}", file=sys.stderr)
        return None

def main():
    p = os.path.join(RAW, "ln_channels.jsonl")
    if not os.path.exists(p):
        print("[!] ln_channels.jsonl chybi"); return
    chans = []
    for line in open(p):
        try:
            c = json.loads(line)
            if c.get("funding_height"): chans.append(c)
        except json.JSONDecodeError: pass
    meta = json.load(open(os.path.join(RAW, "ln_harvest_meta.json")))
    tip = meta["harvested_tip_height"]
    print(f"=== {len(chans)} kanalu s funding height, pokryti "
          f"{meta['coverage_pct']}% verejneho grafu ===\n")

    # kalibrace bloky -> cas
    t_tip = blocktime(tip)
    t_ref = blocktime(tip - 157_680)      # nominalne 3 roky pri 144 blocich/den
    if t_tip and t_ref:
        secs_per_block = (t_tip - t_ref) / 157_680
        print(f"[i] kalibrace: {secs_per_block/60:.2f} min/blok "
              f"(nominal 10.00) mereno pres 157 680 bloku\n")
    else:
        secs_per_block = 600.0
        print("[i] kalibrace selhala, pouzivam nominalnich 10 min/blok\n")

    BLOCKS_PER_YEAR = 365.25 * 86400 / secs_per_block
    ages = sorted((tip - c["funding_height"]) for c in chans)
    caps = {c["short_id"]: c.get("capacity_sat") or 0 for c in chans}
    total_cap = sum(caps.values())

    print("=== Vek otevrenych kanalu ===")
    print(f"  {'kvantil':>8} {'bloku':>9} {'let':>7}")
    for q in (10, 25, 50, 75, 90, 99):
        v = ages[int(len(ages)*q/100)]
        print(f"  {'p'+str(q):>8} {v:>9,} {v/BLOCKS_PER_YEAR:>7.2f}")

    print("\n=== Podil kanalu starsich nez horizont ===")
    print(f"  {'horizont':>22} {'kanalu':>9} {'% kanalu':>10} {'kapacita BTC':>14} {'% kap':>8}")
    for label, years in (("1 rok", 1), ("2 roky", 2),
                         ("3 roky (faze A)", 3), ("5 let (faze A+B)", 5),
                         ("7 let", 7)):
        thr = years * BLOCKS_PER_YEAR
        sel = [c for c in chans if (tip - c["funding_height"]) >= thr]
        cap = sum((c.get("capacity_sat") or 0) for c in sel)
        print(f"  {label:>22} {len(sel):>9,} {100.0*len(sel)/len(chans):>9.1f}% "
              f"{cap/1e8:>13,.1f} {100.0*cap/total_cap:>7.1f}%")

    print("\n[pozn.] Jde o vek JIZ OTEVRENYCH kanalu, ne o dobu doziti. Pokud je proces")
    print("        otevirani/zavirani zhruba stacionarni, je podil kanalu starsich nez")
    print("        T rozumnym odhadem toho, jak velka populace takovy horizont prezije.")

if __name__ == "__main__":
    main()
