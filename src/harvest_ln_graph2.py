#!/usr/bin/env python3
"""
Sběr veřejného LN grafu, verze 2.

Oprava proti v1: v1 počítal každý kanál do "známých" pro OBA koncové body při
každém nálezu, takže odhad pokrytí uzlu nafoukl a prohledávání skončilo
předčasně na ~34 %. v2 vede u každého kanálu množinu skutečných koncových bodů
a pokrytí uzlu z ní odvozuje, takže se zastaví až při reálném vyčerpání.

Strategie: uzel je "hotový", když od něj známe >= tolik kanálů, kolik jich sám
deklaruje (pole node.channels z gossipu). Prioritizujeme uzly s nejvíc dosud
neznámými kanály - hladové vrcholové pokrytí.
"""
import json, os, time, threading
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

API = "https://mempool.space/api/v1/lightning"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
UA = "btc-pq-research/0.1"
RATE, WORKERS = 6.0, 3

_lk = threading.Lock(); _last = [0.0]
def _throttle():
    with _lk:
        w = 1.0/RATE - (time.monotonic() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.monotonic()

def get(url, tries=4):
    for a in range(tries):
        _throttle()
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=45) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code == 404: return None
            if e.code in (429,502,503,504): time.sleep(2**a*2); continue
            time.sleep(2**a)
        except (URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2**a)
    return None

def decode(sid):
    try:
        h,t,o = sid.split("x"); return int(h),int(t),int(o)
    except (ValueError, AttributeError): return None

def main():
    os.makedirs(OUT, exist_ok=True)
    tip = get("https://mempool.space/api/blocks/tip/height")
    st = get(f"{API}/statistics/latest")
    total = st["latest"]["channel_count"]
    print(f"[i] tip {tip}, API hlasi {total} kanalu", flush=True)

    declared = {}
    # 1) uzly z drivejsiho sberu metadat (pokryti ~90 %)
    npath = os.path.join(OUT, "ln_nodes.jsonl")
    if os.path.exists(npath):
        for line in open(npath):
            try:
                n = json.loads(line)
                declared[n["public_key"]] = n.get("channels") or 0
            except (json.JSONDecodeError, KeyError): pass
        print(f"[i] {len(declared)} uzlu z ln_nodes.jsonl", flush=True)
    # 2) doplnime top zebricky
    for r in ("connectivity","liquidity"):
        for n in (get(f"{API}/nodes/rankings/{r}") or []):
            pk = n.get("publicKey")
            if pk: declared[pk] = max(declared.get(pk,0), n.get("channels",0) or 0)
    print(f"[i] univerzum uzlu: {len(declared)}", flush=True)

    channels = {}      # sid -> zaznam (vc. mnoziny koncovych bodu)
    endpoints = {}     # sid -> set(pubkey)
    fetched = set()
    lock = threading.Lock(); cnt = [0]

    def known_for(pk):
        return sum(1 for eps in endpoints.values() if pk in eps)

    # inkrementalni citac misto O(n) prepoctu
    known = {}

    def worker():
        while True:
            with lock:
                best, gain = None, -1
                for pk, dc in declared.items():
                    if pk in fetched: continue
                    g = dc - known.get(pk, 0)
                    if g > gain: best, gain = pk, g
                if best is None: return
                fetched.add(best); cnt[0] += 1; n = cnt[0]
            res = get(f"{API}/channels?public_key={best}&status=open")
            if not res: continue
            with lock:
                for ch in res:
                    sid = ch.get("short_id")
                    if not sid: continue
                    peer = (ch.get("node") or {}).get("public_key")
                    if peer and peer not in declared:
                        declared[peer] = (ch.get("node") or {}).get("channels") or 0
                    eps = endpoints.setdefault(sid, set())
                    for pk in (best, peer):
                        if pk and pk not in eps:
                            eps.add(pk); known[pk] = known.get(pk, 0) + 1
                    if sid not in channels:
                        d = decode(sid)
                        channels[sid] = {
                            "short_id": sid,
                            "funding_height": d[0] if d else None,
                            "capacity_sat": ch.get("capacity"),
                        }
                if n % 250 == 0:
                    print(f"[{n:5d} fetchu] kanalu {len(channels):6d} "
                          f"({100.0*len(channels)/total:5.1f}%), "
                          f"nezpracovanych uzlu {len(declared)-len(fetched)}", flush=True)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts: t.start()
    for t in ts: t.join()

    p = os.path.join(OUT, "ln_channels.jsonl")
    with open(p, "w") as f:
        for sid, ch in channels.items():
            ch["endpoints"] = len(endpoints.get(sid, ()))
            f.write(json.dumps(ch) + "\n")
    meta = {
        "harvested_tip_height": tip, "api_reported_channel_count": total,
        "harvested_channel_count": len(channels),
        "coverage_pct": round(100.0*len(channels)/total, 2),
        "node_fetches": cnt[0], "node_universe": len(declared),
        "source": "mempool.space REST API",
    }
    json.dump(meta, open(os.path.join(OUT,"ln_harvest_meta.json"),"w"), indent=2)
    print("\n[OK] " + json.dumps(meta, indent=2), flush=True)

if __name__ == "__main__":
    main()
