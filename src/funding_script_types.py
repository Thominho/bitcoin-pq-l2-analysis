#!/usr/bin/env python3
"""
Typ scriptu funding výstupů veřejných LN kanálů.

Proč: argument v §2 tvrdí, že veřejný kanál je kvantově exponovaný tak či tak —
P2WSH funding je on-chain hashovaný, ale gossip stejně zveřejní oba funding
pubkeys; P2TR funding (simple taproot channels) má klíč rovnou ve scriptPubKey.
Toto měří, jak je populace rozdělená.

Metoda: short_channel_id = (výška bloku, index tx v bloku, vout). Přes
mempool.space rozlousknem výšku na hash bloku, hash na seznam txid, index na
konkrétní txid a z transakce přečteme scriptpubkey_type daného vout.

Vzorkujeme deterministicky (každý k-tý kanál po seřazení podle short_id), ať je
běh reprodukovatelný bez závislosti na generátoru náhody.
"""
import json, os, sys, time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
UA = {"User-Agent": "btc-pq-research/0.1"}
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 400
DELAY = 0.17

_blockhash_cache = {}

def get(url, raw=False):
    for a in range(4):
        time.sleep(DELAY)
        try:
            with urlopen(Request(url, headers=UA), timeout=40) as r:
                d = r.read().decode()
                return d if raw else json.loads(d)
        except HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 ** a)
        except (URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2 ** a)
    return None

def block_hash(h):
    if h not in _blockhash_cache:
        _blockhash_cache[h] = get(f"https://mempool.space/api/block-height/{h}", raw=True)
        if _blockhash_cache[h]: _blockhash_cache[h] = _blockhash_cache[h].strip()
    return _blockhash_cache[h]

def main():
    p = os.path.join(RAW, "ln_channels.jsonl")
    chans = []
    for line in open(p):
        try:
            c = json.loads(line)
            if c.get("funding_height"): chans.append(c)
        except json.JSONDecodeError: pass
    chans.sort(key=lambda c: c["short_id"])
    step = max(1, len(chans) // SAMPLE)
    sample = chans[::step][:SAMPLE]
    print(f"[i] {len(chans)} kanalu, vzorek {len(sample)} (kazdy {step}. po serazeni)\n", flush=True)

    from collections import Counter
    types = Counter(); caps = Counter(); fails = 0
    for i, c in enumerate(sample, 1):
        h, _, vout = c["short_id"].split("x")
        bh = block_hash(int(h))
        if not bh: fails += 1; continue
        txids = get(f"https://mempool.space/api/block/{bh}/txids")
        if not txids: fails += 1; continue
        try:
            txid = txids[int(c["short_id"].split("x")[1])]
        except (IndexError, ValueError):
            fails += 1; continue
        tx = get(f"https://mempool.space/api/tx/{txid}")
        if not tx: fails += 1; continue
        try:
            t = tx["vout"][int(vout)]["scriptpubkey_type"]
        except (IndexError, KeyError):
            fails += 1; continue
        types[t] += 1; caps[t] += c.get("capacity_sat") or 0
        if i % 50 == 0:
            print(f"  [{i}/{len(sample)}] {dict(types)}", flush=True)

    ok = sum(types.values())
    tot_cap = sum(caps.values())
    print(f"\n=== Typ funding vystupu ({ok} rozlustenych, {fails} selhani) ===")
    for t, n in types.most_common():
        print(f"  {t:<14} {n:>5} kanalu ({100.0*n/ok:>5.1f}%)  "
              f"{caps[t]/1e8:>10,.1f} BTC ({100.0*caps[t]/tot_cap:>5.1f}%)")
    out = {"sample_size": len(sample), "resolved": ok, "failures": fails,
           "by_type_count": dict(types), "by_type_capacity_sat": dict(caps)}
    json.dump(out, open(os.path.join(RAW, "..", "..", "out", "funding_types.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
