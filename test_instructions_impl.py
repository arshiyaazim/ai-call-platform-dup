#!/usr/bin/env python3
"""
Comprehensive test for instructions.txt implementation.
Tests all ~35 intents from the expanded intent engine.
"""

import httpx, asyncio, json, sys, os, uuid

_host = os.environ.get("BRAIN_HOST", "localhost")
BASE = f"http://{_host}:8200"
EP   = f"{BASE}/chat"
_RUN = uuid.uuid4().hex[:8]  # unique per test run

TESTS = [
    # ── Greeting / Farewell / Thanks ──
    ("greeting",           "আসসালামু আলাইকুম",                    "আল-আকসা"),
    ("farewell",           "বিদায়, ধন্যবাদ",                      "01958 122300"),
    ("thanks",             "অনেক ধন্যবাদ ভাই",                    "আল-আকসা"),

    # ── Client Service Sub-types ──
    ("service_office",     "অফিসে সিকিউরিটি গার্ড দরকার",          "অফিস"),
    ("service_factory",    "আমাদের গার্মেন্টসে গার্ড লাগবে",        "ফ্যাক্টরি|গার্মেন্টস|কারখানা"),
    ("service_marine",     "জাহাজে এসকর্ট গার্ড চাই",               "ভেসেল|এসকর্ট|জাহাজ|মেরিন"),
    ("service_event",      "আমাদের ইভেন্টে সিকিউরিটি দরকার",       "ইভেন্ট"),
    ("service_vip",        "ভিআইপি বডিগার্ড দরকার",                "ভিআইপি|বডিগার্ড|VIP"),

    # ── General service / rate ──
    ("guard_request",      "গার্ড দরকার",                           "গার্ড|সিকিউরিটি"),
    ("security_service",   "সিকিউরিটি সার্ভিস নিতে চাই",           "সিকিউরিটি|সার্ভিস"),
    ("rate_inquiry",       "গার্ডের রেট কত?",                       "খরচ|রেট|নির্ভর"),

    # ── Job Seeker general ──
    ("job_inquiry",        "চাকরি আছে?",                           "নিয়োগ|গার্ড|আগ্রহ"),

    # ── Job FAQ (11 from instructions.txt) ──
    ("job_no_experience",  "আমার কোনো অভিজ্ঞতা নেই, চাকরি পাবো?",  "অভিজ্ঞতা|ট্রেনিং|৪৫"),
    ("job_no_education",   "পড়াশোনা করি নাই, চাকরি হবে?",          "শিক্ষাগত|ফিটনেস|সততা"),
    ("job_how_to_apply",   "আবেদন করবো কিভাবে?",                   "অফিসে|NID|ছবি|ডকুমেন্ট"),
    ("job_joining_fee",    "জয়েনিং ফি কত?",                        "৩৫০০|জয়েনিং"),
    ("job_resignation",    "চাকরি ছাড়তে চাই, কি করতে হবে?",        "৩০ দিন|রিজাইন|লিখিত"),
    ("job_details",        "কাজটা কি? কি করতে হবে?",                "জাহাজ|মালামাল|পাহারা|এসকর্ট"),
    ("job_duty_hours",     "ডিউটি কত ঘণ্টা?",                      "২৪|শিফট"),
    ("job_post_duty",      "ডিউটি শেষে কি করতে হবে?",               "স্লিপ|বিকাশ|নগদ|WhatsApp"),
    ("job_salary_payment", "বেতন কবে পাবো?",                        "১০|১২|তারিখ"),
    ("job_leave",          "ছুটি কবে পাবো?",                        "৩ মাস|ছুটি"),

    # ── Salary / Accommodation ──
    ("salary_query",       "বেতন কত?",                              "বেতন|টাকা"),
    ("job_accommodation",  "থাকার ব্যবস্থা আছে?",                   "ডিউটি|লোকেশন|নির্ভর"),

    # ── Complaints (5 sub-types) ──
    ("complaint_absent",   "গার্ড আসে নাই আজ",                      "দুঃখিত|গুরুত্ব"),
    ("complaint_lazy",     "গার্ড ঘুমাচ্ছে ডিউটিতে",                "ফিডব্যাক|পেশাদারিত্ব|গুরুত্ব"),
    ("complaint_rude",     "গার্ড খুব রুড ব্যবহার করেছে",            "গুরুতর|আচরণ|গ্রহণযোগ্য"),
    ("complaint_abandoned","গার্ড পয়েন্ট ছেড়ে চলে গেছে",           "জরুরি|অপারেশন|কন্ট্রোল"),
    ("complaint_theft",    "চুরি হয়েছে, গার্ডকে সন্দেহ",            "গুরুতর|অভিযোগ|গুরুত্ব"),
    ("complaint",          "আমার একটা অভিযোগ আছে",                  "অভিযোগ|সমস্যা"),

    # ── Replacement / Billing / Monitoring / Emergency ──
    ("replacement",        "গার্ড চেঞ্জ করতে চাই",                   "পরিবর্তন|রিপ্লেসমেন্ট"),
    ("billing",            "বিল নিয়ে কথা বলতে চাই",                  "বিল|পেমেন্ট"),
    ("monitoring",         "মনিটরিং কিভাবে করেন?",                  "মনিটরিং|GPS|CCTV|সুপারভিশন"),
    ("emergency",          "জরুরি সমস্যা! গার্ড লাগবে এখনই",         "গুরুতর|অপারেশন|গার্ড মোবাইলাইজ"),

    # ── Contract ──
    ("contract_renewal",   "চুক্তি নবায়ন করতে চাই",                 "নবায়ন|রিনিউ"),
    ("contract_cancel",    "চুক্তি বাতিল করবো",                      "বাতিল|ক্যান্সেল|৩০ দিন"),

    # ── Supervisor / Training ──
    ("supervisor",         "সুপারভাইজার পাঠান",                      "সুপারভাইজার"),
    ("training",           "গার্ডদের ট্রেনিং কেমন?",                 "ট্রেনিং|প্রশিক্ষণ"),

    # ── Office / Company / Contact ──
    ("office_location",    "আপনাদের অফিস কোথায়?",                   "চট্টগ্রাম|পাহাড়তলী|ইস্পাহানি"),
    ("company_info",       "আল-আকসা কোম্পানি সম্পর্কে বলুন",        "আল-আকসা|২০১৪|G4S"),
    ("contact_info",       "যোগাযোগের নম্বর কি?",                    "01958|122300|যোগাযোগ"),
]

import re

async def run():
    passed = failed = 0
    async with httpx.AsyncClient(timeout=30) as c:
        for intent_name, msg, expect_pattern in TESTS:
            try:
                r = await c.post(EP, json={
                    "user_id": "test_instructions",
                    "message": msg,
                    "platform": "whatsapp",
                    "relationship": "social",
                    "conversation_id": f"test_{_RUN}_{intent_name}",
                })
                data = r.json()
                reply = data.get("reply", "")
                detected = data.get("intent", "")

                # Check if expected pattern matches in reply
                if re.search(expect_pattern, reply):
                    passed += 1
                    tag = "✅ PASS"
                else:
                    failed += 1
                    tag = "❌ FAIL"

                print(f"  {tag}  [{intent_name:20s}] intent={detected:20s} | reply={reply[:80]}...")
            except Exception as e:
                failed += 1
                print(f"  ❌ ERR  [{intent_name:20s}] {e}")

    print(f"\n{'='*60}")
    print(f"  Results: {passed} passed / {failed} failed / {passed+failed} total")
    print(f"{'='*60}")
    return failed

if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
