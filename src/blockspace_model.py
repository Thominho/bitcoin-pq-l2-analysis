#!/usr/bin/env python3
"""
Model spotřeby blockspace při postkvantové migraci Bitcoinu.

Vše je počítáno podle BIP-141: weight = base_size*3 + total_size, ekvivalentně
"nesvědecké bajty * 4 + svědecké bajty * 1". Marker+flag (2 B) se objevují jen
v total_size, takže přispívají 2 WU.

Každá konstanta má uvedený zdroj, ať je model auditovatelný.
"""
import json

# ---------------------------------------------------------------------------
# KONSTANTY PROTOKOLU
# ---------------------------------------------------------------------------
MAX_BLOCK_WEIGHT = 4_000_000      # BIP-141
BLOCKS_PER_DAY   = 144            # 10 min cíl
WU_PER_DAY       = MAX_BLOCK_WEIGHT * BLOCKS_PER_DAY

# ---------------------------------------------------------------------------
# PODPISOVÁ SCHÉMATA  (velikosti v bajtech)
#   klasická: BIP-340 (Schnorr), DER-ECDSA
#   PQ: NIST FIPS 204 (ML-DSA), FIPS 205 (SLH-DSA), draft FIPS 206 (FN-DSA/FALCON)
#   POZN: FALCON má proměnnou délku podpisu, uvádíme typickou/max hodnotu.
# ---------------------------------------------------------------------------
SCHEMES = {
    "ecdsa-p2wpkh":     {"sig": 72,    "pk": 33,   "src": "DER, low-S, vč. sighash byte"},
    "schnorr-p2tr-key": {"sig": 64,    "pk": 0,    "src": "BIP-340; keypath neodhaluje pk ve svědkovi (je ve scriptPubKey)"},
    "falcon-512":       {"sig": 666,   "pk": 897,  "src": "draft FIPS 206 / NIST round-3 FALCON"},
    "falcon-1024":      {"sig": 1280,  "pk": 1793, "src": "draft FIPS 206"},
    "ml-dsa-44":        {"sig": 2420,  "pk": 1312, "src": "NIST FIPS 204"},
    "ml-dsa-65":        {"sig": 3309,  "pk": 1952, "src": "NIST FIPS 204"},
    "ml-dsa-87":        {"sig": 4627,  "pk": 2592, "src": "NIST FIPS 204"},
    "slh-dsa-128s":     {"sig": 7856,  "pk": 32,   "src": "NIST FIPS 205 (SHA2-128s)"},
    "slh-dsa-128f":     {"sig": 17088, "pk": 32,   "src": "NIST FIPS 205 (SHA2-128f)"},
    "slh-dsa-192s":     {"sig": 16224, "pk": 48,   "src": "NIST FIPS 205 (SHA2-192s)"},
    "slh-dsa-256s":     {"sig": 29792, "pk": 64,   "src": "NIST FIPS 205 (SHA2-256s)"},
}

# ---------------------------------------------------------------------------
# STAV SÍTĚ  (měřeno, viz data/raw/)
# ---------------------------------------------------------------------------
NETWORK = {
    "utxo_count":        167_066_337,   # api.blockchain.info/charts/utxo-count, ~2026-08-15
    "tip_height":        963_304,       # mempool.space/api/blocks/tip/height, 2026-08-20
    "ln_public_channels": 33_221,       # mempool.space LN statistics, 2026-08-20
    "ln_public_capacity_sat": 378_324_360_046,
}

def varint(n):
    if n < 0xFD: return 1
    if n <= 0xFFFF: return 3
    if n <= 0xFFFF_FFFF: return 5
    return 9

def push_size(n):
    """Bajty navíc na push n-bajtové položky do svědka (varint délky)."""
    return varint(n) + n

def tx_weight(n_in, n_out, scheme, out_script_bytes=34, extra_witness_items=0):
    """
    Váha segwit transakce v WU.
      n_in/n_out          počet vstupů/výstupů
      scheme              klíč do SCHEMES pro utrácené vstupy
      out_script_bytes    délka scriptPubKey výstupu (34 = witness program v.N s 32B)
    """
    s = SCHEMES[scheme]
    # --- nesvědecká část (×4) ---
    nonwit  = 4                       # version
    nonwit += varint(n_in)
    nonwit += n_in * (32 + 4 + 1 + 4) # outpoint + scriptSig len (0) + sequence
    nonwit += varint(n_out)
    nonwit += n_out * (8 + varint(out_script_bytes) + out_script_bytes)
    nonwit += 4                       # locktime
    # --- svědecká část (×1) ---
    wit = 2                           # marker + flag
    per_in = varint(1 + (1 if s["pk"] else 0) + extra_witness_items)
    per_in += push_size(s["sig"])
    if s["pk"]:
        per_in += push_size(s["pk"])
    wit += n_in * per_in
    return nonwit * 4 + wit

def vbytes(w):
    return w / 4.0

# ---------------------------------------------------------------------------
# FÁZE 1 — samotná migrace UTXO setu do PQ-chráněných výstupů
#   Klíčový poznatek: pokud je PQ výstup HASHOVANÝ závazek (jako P2QRH), migrační
#   transakce se stále podepisuje KLASICKÝM klíčem (proto musí proběhnout dřív,
#   než klasické podpisy padnou) a výstup je jen 34 B. Migrace je tedy LEVNÁ.
#   Drahé je až budoucí utrácení. Tento rozdíl se v debatě často stírá.
# ---------------------------------------------------------------------------
def phase1_migration(batch_in=1, batch_out=1):
    w = tx_weight(batch_in, batch_out, "ecdsa-p2wpkh", out_script_bytes=34)
    per_utxo_wu = w / batch_in
    total_wu = per_utxo_wu * NETWORK["utxo_count"]
    return {
        "batch": f"{batch_in}-in/{batch_out}-out",
        "tx_weight_wu": w,
        "wu_per_utxo": round(per_utxo_wu, 1),
        "vb_per_utxo": round(vbytes(per_utxo_wu), 1),
        "total_weight_gwu": round(total_wu / 1e9, 2),
        "days_of_100pct_blocks": round(total_wu / WU_PER_DAY, 1),
        "days_at_25pct_blockspace": round(total_wu / (WU_PER_DAY * 0.25), 1),
    }

# ---------------------------------------------------------------------------
# FÁZE 2 — ustálený stav: propustnost sítě po přechodu na PQ podpisy
# ---------------------------------------------------------------------------
def phase2_throughput():
    base = tx_weight(1, 2, "ecdsa-p2wpkh", out_script_bytes=22)
    base_tps_block = MAX_BLOCK_WEIGHT / base
    rows = []
    for name in SCHEMES:
        if name in ("ecdsa-p2wpkh", "schnorr-p2tr-key"):
            osz = 22 if "wpkh" in name else 34
        else:
            osz = 34
        w = tx_weight(1, 2, name, out_script_bytes=osz)
        per_block = MAX_BLOCK_WEIGHT / w
        rows.append({
            "scheme": name,
            "sig_bytes": SCHEMES[name]["sig"],
            "pk_bytes": SCHEMES[name]["pk"],
            "tx_weight_wu": w,
            "tx_vbytes": round(vbytes(w), 1),
            "txs_per_block": round(per_block, 1),
            "throughput_vs_p2wpkh": round(per_block / base_tps_block, 3),
            "throughput_collapse_factor": round(base_tps_block / per_block, 2),
        })
    return {"baseline_p2wpkh_txs_per_block": round(base_tps_block, 1), "schemes": rows}

# ---------------------------------------------------------------------------
# FÁZE 3 — kolik by stálo přemigrovat UTXO set, kdyby PQ výstup NESL klíč přímo
#   (tj. varianta bez hashového závazku) — pro kontrast
# ---------------------------------------------------------------------------
def phase1_raw_pubkey_variant(scheme):
    pk = SCHEMES[scheme]["pk"]
    w = tx_weight(1, 1, "ecdsa-p2wpkh", out_script_bytes=pk + 2)
    total_wu = w * NETWORK["utxo_count"]
    return {
        "scheme": scheme,
        "output_script_bytes": pk + 2,
        "wu_per_utxo": w,
        "days_of_100pct_blocks": round(total_wu / WU_PER_DAY, 1),
    }

if __name__ == "__main__":
    result = {
        "network_state": NETWORK,
        "phase1_migration_hashed_commitment": [
            phase1_migration(1, 1),
            phase1_migration(1, 2),
            phase1_migration(10, 1),
            phase1_migration(50, 1),
            phase1_migration(100, 1),
        ],
        "phase2_steady_state_throughput": phase2_throughput(),
        "phase1_raw_pubkey_variant": [
            phase1_raw_pubkey_variant(s)
            for s in ("falcon-512", "ml-dsa-44", "slh-dsa-128s")
        ],
    }
    print(json.dumps(result, indent=2))
