#!/usr/bin/env python3
"""
Ověření metodiky za §6.2.

Výhrada, kterou to zavírá: liveness čísla vycházejí z pole `channels` u uzlu
(agregace mempool.space). Kdyby to pole obsahovalo historické, dnes už zavřené
kanály, byla by tvrzení o "opuštěných protistranách" nafouknutá.

Test: vezmi vzorek uzlů, které negossipovaly déle než 14 dní, a zjisti přímým
dotazem, kolik OTEVŘENÝCH kanálů skutečně mají. Porovnej s deklarovaným počtem.

Pro kontrolu totéž na vzorku čerstvých uzlů.
"""
import json, os, sys, time
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
API = "https://mempool.space/api/v1/lightning"
UA = {"User-Agent": "btc-pq-research/0.1"}
NOW = 1787270400          # 2026-08-20, den sberu
DAY = 86400
N = int(sys.argv[1]) if len(sys.argv) > 1 else 60

def get(url):
    for a in range(4):
        time.sleep(0.18)
        try:
            with urlopen(Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode())
        except HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 ** a)
        except (URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2 ** a)
    return None

def sample(nodes, lo, hi, n):
    """Deterministicky kazdy k-ty uzel z pasma, serazeno podle pubkey."""
    sel = [x for x in nodes
           if x.get("updated_at") and lo <= (NOW - x["updated_at"]) < hi
           and (x.get("channels") or 0) > 0]
    sel.sort(key=lambda x: x["public_key"])
    step = max(1, len(sel) // n)
    return sel[::step][:n], len(sel)

def probe(group, nodes):
    decl = real = zero = 0
    checked = 0
    for nd in nodes:
        ch = get(f"{API}/channels?public_key={nd['public_key']}&status=open")
        if ch is None: continue
        checked += 1
        decl += nd.get("channels") or 0
        real += len(ch)
        if len(ch) == 0: zero += 1
    print(f"\n=== {group} (overeno {checked} uzlu) ===")
    print(f"  deklarovanych kanalu celkem: {decl}")
    print(f"  skutecne otevrenych:         {real}")
    if decl:
        print(f"  pomer skutecne/deklarovane:  {100.0*real/decl:.1f}%")
    print(f"  uzlu s NULOU otevrenych:     {zero} ({100.0*zero/checked:.1f}%)" if checked else "")
    return {"group": group, "checked": checked, "declared": decl,
            "actually_open": real, "zero_open_nodes": zero}

def main():
    nodes = [json.loads(l) for l in open(os.path.join(RAW, "ln_nodes.jsonl"))]
    nodes = [n for n in nodes if n.get("updated_at") and n["updated_at"] <= NOW + DAY]

    stale, n_stale = sample(nodes, 14*DAY, 10**9, N)
    fresh, n_fresh = sample(nodes, 0, DAY, N)
    print(f"[i] populace: {n_stale} zatuchlych uzlu s kanaly, {n_fresh} cerstvych")
    print(f"[i] vzorek {len(stale)} + {len(fresh)}")

    r1 = probe("ZATUCHLE (gossip > 14 dni)", stale)
    r2 = probe("CERSTVE (gossip <= 1 den)", fresh)

    print("\n[zaver] Pokud je u zatuchlych uzlu pomer skutecne/deklarovane vysoky,")
    print("        deklarovane pocty odrazeji realne otevrene kanaly a §6.2 plati.")
    print("        Nizky pomer by znamenal, ze cislo 22,7 % je nadhodnocene.")
    json.dump({"stale": r1, "fresh": r2, "population_stale": n_stale,
               "population_fresh": n_fresh},
              open(os.path.join(RAW, "..", "..", "out", "liveness_validation.json"), "w"),
              indent=2)

if __name__ == "__main__":
    main()
