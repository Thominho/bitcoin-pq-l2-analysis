#!/usr/bin/env python3
"""
Sbírá metadata uzlů LN (zejména updated_at = poslední gossip aktualizace).

Motivace: chceme odhadnout, jaká část kapacity sítě má protistranu, která
vypadá opuštěně. Uzel, který přestal vysílat node_announcement, je typicky
offline; většina implementací ho po ~14 dnech přestane šířit. Kanály takového
uzlu ale v grafu zůstávají, dokud se neuzavřou on-chain.

To je pro postkvantovou otázku klíčové: s mrtvou protistranou NELZE provést
kooperativní uzavření kanálu. Zbývá jen jednostranné uzavření, které se opírá
o PŘEDPODEPSANOU commitment transakci.

Zdroj: mempool.space /nodes/country/{iso} a /nodes/isp/{asn} — bulk endpointy,
takže ~109 + ~N dotazů místo 16k jednotlivých.

Známé zkreslení: uzly bez geolokace (typicky Tor-only) se v country listingu
neobjeví. Podíl pokrytí reportujeme explicitně.
"""
import json, os, time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

API = "https://mempool.space/api/v1/lightning"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
UA = "btc-pq-research/0.1"
DELAY = 0.22

def get(url, tries=4):
    for a in range(tries):
        time.sleep(DELAY)
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code in (429, 502, 503, 504):
                time.sleep(2 ** a * 2); continue
            if e.code == 404:
                return None
            time.sleep(2 ** a)
        except (URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2 ** a)
    return None

def main():
    os.makedirs(OUT, exist_ok=True)
    stats = get(f"{API}/statistics/latest")
    total_nodes = stats["latest"]["node_count"]
    unannounced = stats["latest"]["unannounced_nodes"]
    print(f"[i] API hlasi {total_nodes} uzlu ({unannounced} neohlasenych)", flush=True)

    nodes = {}

    countries = get(f"{API}/nodes/countries") or []
    print(f"[i] {len(countries)} zemi", flush=True)
    for i, c in enumerate(countries, 1):
        iso = (c.get("iso") or "").lower()
        if not iso:
            continue
        r = get(f"{API}/nodes/country/{iso}")
        for n in (r or {}).get("nodes", []):
            pk = n.get("public_key")
            if pk:
                nodes[pk] = {
                    "public_key": pk,
                    "alias": n.get("alias"),
                    "capacity_sat": n.get("capacity"),
                    "channels": n.get("channels"),
                    "first_seen": n.get("first_seen"),
                    "updated_at": n.get("updated_at"),
                    "iso_code": n.get("iso_code"),
                    "as_number": n.get("as_number"),
                }
        if i % 20 == 0:
            print(f"  [{i}/{len(countries)}] uzlu: {len(nodes)}", flush=True)

    isps = get(f"{API}/nodes/isp-ranking")
    isp_list = []
    if isinstance(isps, dict):
        isp_list = isps.get("ispRanking") or isps.get("clearnetCapacity") or []
    elif isinstance(isps, list):
        isp_list = isps
    print(f"[i] {len(isp_list)} ISP zaznamu", flush=True)
    for i, e in enumerate(isp_list[:400], 1):
        asn = e[0] if isinstance(e, list) and e else (e.get("asn") if isinstance(e, dict) else None)
        if asn is None:
            continue
        r = get(f"{API}/nodes/isp/{asn}")
        for n in (r or {}).get("nodes", []):
            pk = n.get("public_key")
            if pk and pk not in nodes:
                nodes[pk] = {
                    "public_key": pk, "alias": n.get("alias"),
                    "capacity_sat": n.get("capacity"), "channels": n.get("channels"),
                    "first_seen": n.get("first_seen"), "updated_at": n.get("updated_at"),
                    "iso_code": n.get("iso_code"), "as_number": asn,
                }
        if i % 50 == 0:
            print(f"  [ISP {i}] uzlu: {len(nodes)}", flush=True)

    path = os.path.join(OUT, "ln_nodes.jsonl")
    with open(path, "w") as f:
        for n in nodes.values():
            f.write(json.dumps(n) + "\n")
    meta = {
        "api_reported_node_count": total_nodes,
        "api_reported_unannounced": unannounced,
        "harvested_node_count": len(nodes),
        "coverage_pct": round(100.0 * len(nodes) / total_nodes, 1),
        "bias_note": "bulk listing pokryva jen uzly s geolokaci/ISP; Tor-only uzly chybi",
        "source": "mempool.space REST API",
    }
    json.dump(meta, open(os.path.join(OUT, "ln_nodes_meta.json"), "w"), indent=2)
    print(f"\n[OK] {len(nodes)} uzlu -> {path}", flush=True)
    print(json.dumps(meta, indent=2), flush=True)

if __name__ == "__main__":
    main()
