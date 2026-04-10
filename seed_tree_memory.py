"""
Seed script for Tree Memory System.
Run inside fazle-brain container to populate initial tree knowledge.
"""
import httpx
import asyncio
import time

MEMORY_URL = "http://fazle-memory:8300"
KG_URL = "http://fazle-knowledge-graph:9300"

# ── Step 1: Verify services are up ──────────────────────────
async def check_health():
    async with httpx.AsyncClient(timeout=10.0) as client:
        for name, url in [("Memory", MEMORY_URL), ("KnowledgeGraph", KG_URL)]:
            try:
                r = await client.get(f"{url}/health")
                print(f"  {name}: {r.json().get('status', '?')}")
            except Exception as e:
                print(f"  {name}: FAILED — {e}")
                return False
    return True

# ── Step 2: Seed tree knowledge ─────────────────────────────
SEED_DATA = [
    # ── Core Identity ──
    {"tree_path": "azim", "text": "Azim — Owner and operator of Al-Aqsa Security & Logistics Services Ltd. Ex-G4S Operations Manager with 5 years international experience in Dubai. Sister concerns: Al-Aqsa Security Service & Trading Centre, Al-Aqsa Surveillance Force.", "source": "persona"},
    {"tree_path": "azim", "text": "Azim's owner phone is configured via SOCIAL_OWNER_PHONE env. Always recognize that number as the boss.", "source": "persona"},

    # ── Business / Al-Aqsa Security ──
    {"tree_path": "azim/business/al-aqsa-security", "text": "Al-Aqsa Security & Logistics Services Ltd. Established 2014, journey started 2013. Premier security provider in Bangladesh. Website: al-aqsasecurity.com. Contact: 01958 122300, 01958 122301, 01958 122302. Email: admin@al-aqsasecurity.com", "source": "persona"},
    {"tree_path": "azim/business/al-aqsa-security/services", "text": "Al-Aqsa provides: Corporate Security (BDT 14,500/month), Residential Security (BDT 12,500/month), Hotel & Hospitality Security (BDT 12,500/month), Healthcare Facility Security (BDT 14,500/month), Logistics & Transport Security (BDT 14,500/month), Construction & Industrial Security (BDT 14,500/month), Event Security, VIP & Personal Security. All include food, accommodation, dress. 8hr shift-based duty, 3 shifts for 3 persons.", "source": "persona"},
    {"tree_path": "azim/business/al-aqsa-security/pricing", "text": "Corporate: BDT 14,500/month. Residential: BDT 12,500/month. Hotel: BDT 12,500/month. Healthcare: BDT 14,500/month. Logistics: BDT 14,500/month. Construction: BDT 14,500/month. All rates include food, accommodation, and uniform. 8-hour shift-based duty.", "source": "persona"},
    {"tree_path": "azim/business/al-aqsa-security/employees", "text": "Guard requirements: Age 22-45, minimum education Grade 8+, must complete 45-90 days training. Team includes ex-military and ex-police officers. Guards are well-trained professionals.", "source": "persona"},
    {"tree_path": "azim/business/al-aqsa-security/operations", "text": "Al-Aqsa uses technology: CCTV surveillance, biometric access control, patrol monitoring systems. The company provides container depot security, route escort, and armed security for logistics.", "source": "persona"},

    # ── Business / Other companies ──
    {"tree_path": "azim/business", "text": "Azim owns multiple companies: Al-Aqsa Security & Logistics Services Ltd (mother company), Al-Aqsa Security Service & Trading Centre (sister concern), Al-Aqsa Surveillance Force (sister concern), Magnus Marine (magnusmarine.online).", "source": "persona"},
    {"tree_path": "azim/business/logistics", "text": "Al-Aqsa also provides logistics services: container depot guarding, route escort, armed security for transport. Part of Al-Aqsa Security & Logistics Services Ltd.", "source": "persona"},

    # ── Social Media ──
    {"tree_path": "azim/social/networks", "text": "Facebook pages: prothomnews.kilagee (News/Media), aslsl2022 (Al-Aqsa official), visantravels (Visan Travels), ashiq.pol.cu (associated), taziz2022. Websites: al-aqsasecurity.com, magnusmarine.online", "source": "persona"},

    # ── Knowledge / General ──
    {"tree_path": "azim/knowledge/general", "text": "Fazle Azim has background in security industry operations, international experience from G4S Dubai. Expert in guard deployment, client management, security technology.", "source": "persona"},
]


async def seed_tree_memories():
    print("\n[1/3] Checking services...")
    if not await check_health():
        print("Services not ready. Aborting.")
        return

    print(f"\n[2/3] Seeding {len(SEED_DATA)} tree memories...")
    success = 0
    async with httpx.AsyncClient(timeout=60.0) as client:
        for item in SEED_DATA:
            try:
                r = await client.post(f"{MEMORY_URL}/tree/store", json=item)
                if r.status_code == 200:
                    data = r.json()
                    print(f"  OK {item['tree_path']} — id={data.get('id', '?')[:8]}")
                    success += 1
                else:
                    print(f"  FAIL {item['tree_path']} — {r.status_code}: {r.text[:100]}")
            except Exception as e:
                print(f"  FAIL {item['tree_path']} — {e}")
            await asyncio.sleep(0.5)  # Don't hammer Ollama embeddings

    print(f"\n[3/3] Verifying tree...")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{MEMORY_URL}/tree/browse")
            data = r.json()
            print(f"  Total paths: {data.get('total_paths', 0)}")
            print(f"  Total memories: {data.get('total_memories', 0)}")
            for p in data.get("paths", []):
                print(f"    {p['path']} ({p['count']} items)")
        except Exception as e:
            print(f"  Browse failed: {e}")

        # Also check KG tree structure
        try:
            r = await client.get(f"{KG_URL}/tree/structure")
            data = r.json()
            print(f"  KG tree branches: {data.get('total_branches', 0)}")
        except Exception as e:
            print(f"  KG tree check failed: {e}")

    print(f"\nDone! {success}/{len(SEED_DATA)} memories stored.")


if __name__ == "__main__":
    asyncio.run(seed_tree_memories())
