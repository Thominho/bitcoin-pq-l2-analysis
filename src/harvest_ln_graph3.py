#!/usr/bin/env python3
"""
Sběr veřejného LN grafu, verze 3.

OPRAVA PROTI v2: endpoint /channels?public_key=X vrací maximálně 10 záznamů na
stránku a stránkuje se parametrem `index`. v2 to nevěděla a brala od každého uzlu
jen prvních 10 kanálů. Důsledky: strop pokrytí na ~61 % a systematické
PODVZORKOVÁNÍ velkých uzlů (hub s 1866 kanály přispěl deseti stejně jako uzel se
dvěma). Věková distribuce z v2 je proto vychýlená a nelze ji použít.

v3 stránkuje do vyčerpání a ukládá i pubkeys obou koncových bodů, aby šlo
liveness ověřit přímo proti otevřeným kanálům místo agregovaných počtů.
"""
import json, os, time, threading
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

API = "https://mempool.space/api/v1/lightning"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
UA = {"User-Agent": "btc-pq-research/0.1"}
RATE, WORKERS, PAGE = 7.0, 3, 10

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
            with urlopen(Request(url, headers=UA), timeout=45) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code == 404: return None
            if e.code in (429,502,503,504): time.sleep(2**a*2); continue
            time.sleep(2**a)
        except (URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2**a)
    return None

def all_channels(pk, declared):
    """Stránkuje přes index, dokud stránka není neúplná nebo nemáme vše."""
    out, idx, guard = [], 0, 0
    while guard < 400:                       # pojistka proti nekonecne smycce
        page = get(f"{API}/channels?public_key={pk}&status=open&index={idx}")
        if not page: break
        out.extend(page)
        if len(page) < PAGE: break
        idx += PAGE; guard += 1
        if declared and len(out) >= declared: break
    return out

def decode(sid):
    try:
        h,t,o = sid.split("x"); return int(h)
    except (ValueError, AttributeError): return None

def main():
    tip = get("https://mempool.space/api/blocks/tip/height")
    st = get(f"{API}/statistics/latest")
    total = st["latest"]["channel_count"]
    print(f"[i] tip {tip}, API hlasi {total} kanalu", flush=True)

    declared = {}
    for line in open(os.path.join(OUT, "ln_nodes.jsonl")):
        try:
            n = json.loads(line); declared[n["public_key"]] = n.get("channels") or 0
        except (json.JSONDecodeError, KeyError): pass
    for r in ("connectivity","liquidity"):
        for n in (get(f"{API}/nodes/rankings/{r}") or []):
            if n.get("publicKey"): declared[n["publicKey"]] = max(declared.get(n["publicKey"],0), n.get("channels",0) or 0)
    print(f"[i] univerzum uzlu: {len(declared)}", flush=True)

    channels, fetched = {}, set()
    lock = threading.Lock(); cnt = [0]
    order = sorted(declared, key=lambda k: -declared[k])   # velke uzly nejdriv

    def worker():
        while True:
            with lock:
                pk = None
                while order:
                    cand = order.pop(0)
                    if cand not in fetched: pk = cand; break
                if pk is None: return
                fetched.add(pk); cnt[0] += 1; n = cnt[0]
            res = all_channels(pk, declared.get(pk, 0))
            with lock:
                for ch in res:
                    sid = ch.get("short_id")
                    if not sid: continue
                    peer = (ch.get("node") or {}).get("public_key")
                    if sid not in channels:
                        channels[sid] = {
                            "short_id": sid,
                            "funding_height": decode(sid),
                            "capacity_sat": ch.get("capacity"),
                            "endpoints": [pk, peer] if peer else [pk],
                        }
                    else:
                        eps = channels[sid]["endpoints"]
                        for x in (pk, peer):
                            if x and x not in eps: eps.append(x)
                if n % 500 == 0:
                    print(f"[{n:5d} uzlu] kanalu {len(channels):6d} ({100.0*len(channels)/total:5.1f}%)", flush=True)

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
    for t in ts: t.start()
    for t in ts: t.join()

    p = os.path.join(OUT, "ln_channels.jsonl")
    with open(p, "w") as f:
        for ch in channels.values(): f.write(json.dumps(ch) + "\n")
    meta = {"harvested_tip_height": tip, "api_reported_channel_count": total,
            "harvested_channel_count": len(channels),
            "coverage_pct": round(100.0*len(channels)/total, 2),
            "node_fetches": cnt[0], "node_universe": len(declared),
            "pagination": f"index, {PAGE} per page (v2 chybela -> podvzorkovala velke uzly)",
            "source": "mempool.space REST API"}
    json.dump(meta, open(os.path.join(OUT,"ln_harvest_meta.json"),"w"), indent=2)
    print("\n[OK] " + json.dumps(meta, indent=2), flush=True)

if __name__ == "__main__":
    main()
