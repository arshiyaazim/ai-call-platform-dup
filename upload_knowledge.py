#!/usr/bin/env python3
"""
upload_knowledge.py — Bulk knowledge uploader for Fazle AI
Parses instructions.txt into structured conversation entries
and uploads via POST /knowledge/add with duplicate checking.
Safe to run multiple times (idempotent).
"""

import sys
import logging
import time
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

API_URL = "http://localhost:8100/knowledge/add"
MAX_RETRIES = 3
DELAY_BETWEEN = 0.5
RETRY_DELAY = 2

# ── Full structured dataset parsed from instructions.txt ─────

KNOWLEDGE_DATA = [

    # ══════════════════════════════════════════════════
    # PERSONAL (existing — will be skipped as duplicates)
    # ══════════════════════════════════════════════════
    {
        "category": "personal",
        "key": "full_name",
        "value": "আমার নাম শাহ্ মোহাম্মদ ফজলে আজিম। আমি চট্টগ্রামে থাকি।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "personal",
        "key": "nid_number",
        "value": "আমার জাতীয় পরিচয়পত্র নম্বর ১৫৯৫৭০৮৯১২৯২৪।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "personal",
        "key": "passport_number",
        "value": "আমার পাসপোর্ট নম্বর A02235098, মেয়াদ ২০৩১ সালের ১৩ নভেম্বর পর্যন্ত।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # BUSINESS (existing — will be skipped as duplicates)
    # ══════════════════════════════════════════════════
    {
        "category": "business",
        "key": "company_name",
        "value": "আমার কোম্পানির নাম আল-আকসা সিকিউরিটি অ্যান্ড লজিস্টিকস সার্ভিসেস লিমিটেড।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "business",
        "key": "company_intro",
        "value": "আল-আকসা সিকিউরিটি অ্যান্ড লজিস্টিকস সার্ভিসেস লিমিটেড একটি নিরাপত্তা ও লজিস্টিক সেবা প্রদানকারী প্রতিষ্ঠান। আমরা চট্টগ্রামে অবস্থিত এবং দেশজুড়ে নিরাপত্তা গার্ড, এসকর্ট ও লজিস্টিক সেবা দিয়ে থাকি।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # COMPANY PROFILE (from instructions.txt header)
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "company_profile",
        "key": "company_profile_full",
        "value": "আল-আকসা সিকিউরিটি ২০১৪ সালে প্রতিষ্ঠিত। প্রতিষ্ঠাতা দুবাইয়ে G4S-এ ৫ বছর অপারেশন্স ম্যানেজার ছিলেন। যোগাযোগ: 01958 122300, al-aqsasecurity.com",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 1: OPENING
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "opening",
        "key": "opening_greeting",
        "value": "আসসালামু আলাইকুম! আল-আকসা সিকিউরিটি অ্যান্ড লজিস্টিকস সার্ভিসেস লিমিটেড-এ কল করার জন্য ধন্যবাদ। আমি কীভাবে আপনাকে সাহায্য করতে পারি?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "opening",
        "key": "opening_intent_unclear",
        "value": "আপনি কি সিকিউরিটি সার্ভিস নিতে চাইছেন, চাকরির বিষয়ে জানতে চাইছেন, নাকি অন্য কোনো বিষয়ে সাহায্য লাগবে?",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 2: CLIENT SERVICE
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_intro",
        "value": "আমাদের কোম্পানি ২০১৪ সাল থেকে পেশাদার সিকিউরিটি সার্ভিস দিচ্ছে। কর্পোরেট অফিস, কারখানা, শপিং মল, নির্মাণ সাইট, জেটি, VIP ও ইভেন্ট সিকিউরিটি — আপনার কোন ধরনের সিকিউরিটি প্রয়োজন?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_office",
        "value": "অফিস সিকিউরিটিতে থাকে ৮/১২ ঘণ্টার শিফট ডিউটি, গেট কন্ট্রোল ও ভিজিটর ম্যানেজমেন্ট, চেক-ইন/চেক-আউট রিপোর্টিং, CCTV সাপোর্ট ও জরুরি রিপ্লেসমেন্ট। আপনার অফিসটি কোন এলাকায়? কতজন গার্ড প্রয়োজন?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_factory",
        "value": "ফ্যাক্টরি সিকিউরিটিতে মেইন ও ব্যাক গেট সিকিউরিটি, মালামাল লোডিং মনিটরিং, শ্রমিক প্রবেশ-প্রস্থান নিয়ন্ত্রণ, রাতের শিফটে বিশেষ নজরদারি ও ফায়ার রেসপন্স ট্রেনিংপ্রাপ্ত গার্ড। কত শিফটে গার্ড দরকার?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_marine",
        "value": "মেরিন সিকিউরিটিতে জেটি ও ঘাট সিকিউরিটি, ভেসেলে গার্ড ডিপ্লয়মেন্ট, কার্গো সুপারভিশন, এস্কর্ট সিকিউরিটি ও পাইরেসি প্রিভেনশন। গার্ডরা বিশেষভাবে প্রশিক্ষিত। কোন পোর্ট বা রুটে সার্ভিস দরকার?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_event",
        "value": "কর্পোরেট ইভেন্ট, বিবাহ, কনসার্ট, রাজনৈতিক সমাবেশ ও ক্রীড়া ইভেন্টে সিকিউরিটি দিই। ইভেন্টের তারিখ, স্থান ও আনুমানিক অতিথি সংখ্যা জানালে কোটেশন তৈরি করে দিতে পারব।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_vip",
        "value": "VIP প্রটেকশনে ব্যক্তিগত বডিগার্ড, এক্সিকিউটিভ প্রটেকশন, ট্রাভেল এস্কর্ট, ক্যাশ এস্কর্ট ও ২৪/৭ সিকিউরিটি কভারেজ। গার্ডরা প্রাক্তন সামরিক ও আইনশৃঙ্খলা বাহিনীর সদস্য।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_quotation",
        "value": "রেট নির্ভর করে গার্ড সংখ্যা, শিফট ডিউরেশন (৮/১২/২৪ ঘণ্টা), ডিউটির ধরন (সাধারণ/বিশেষ/মেরিন/VIP) ও লোকেশনের উপর। তথ্য জানালে কাস্টমাইজড কোটেশন পাঠানোর ব্যবস্থা করব।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 3: JOB SEEKER
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_seeker_intro",
        "value": "আল-আকসা সিকিউরিটিতে আগ্রহ দেখানোর জন্য ধন্যবাদ! আমরা নিয়মিত নতুন গার্ড নিয়োগ দিই। আপনার কি আগে কোনো সিকিউরিটি কোম্পানিতে কাজের অভিজ্ঞতা আছে?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_seeker_experienced",
        "value": "অভিজ্ঞ গার্ডদের অগ্রাধিকার দিই। যোগ্যতা: বয়স ১৮-৪৫, শারীরিকভাবে সুস্থ, NID, চারিত্রিক সনদ। প্রাক্তন সামরিক ও পুলিশ সদস্যদের বিশেষভাবে নিয়োগ দিই। অফিসে আসুন বা ফেসবুক পেজে মেসেজ দিন।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_seeker_new",
        "value": "নতুনদেরও নিয়োগ দিই! নিয়োগের পর ট্রেনিং: রিস্ক অ্যাসেসমেন্ট, সার্ভেইল্যান্স, ইমার্জেন্সি রেসপন্স, কাস্টমার সার্ভিস ও ফায়ার সেফটি। অফিসে এসে ফর্ম পূরণ করলেই আবেদন শুরু হবে।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_seeker_accommodation",
        "value": "থাকা-খাওয়া ডিউটির ধরন ও লোকেশনের উপর নির্ভর করে। কিছু পয়েন্টে থাকার ব্যবস্থা থাকে, মেরিন ডিউটিতে খাওয়া-থাকা থাকে, কিছু ক্ষেত্রে আলাদা ভাতা দেওয়া হয়।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 4: COMPLAINT
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_intro",
        "value": "আমি বুঝতে পারছি আপনি কোনো সমস্যার সম্মুখীন হচ্ছেন। আমি আপনাকে সাহায্য করতে চাই। আপনার অভিযোগটি কোন বিষয়ে?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_guard_absent",
        "value": "গার্ড ডিউটিতে না আসা গুরুত্বপূর্ণ বিষয়। আপনার কোম্পানির নাম, লোকেশন ও শিফট জানান। এখনই অপারেশন টিমকে জানাচ্ছি — ২-৪ ঘণ্টার মধ্যে রিপ্লেসমেন্ট পৌঁছাবে।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_guard_lazy",
        "value": "গার্ডের পেশাদারিত্ব নিয়ে আপোষ করি না। গার্ডের নাম/আইডি ও পয়েন্ট জানান। সুপারভাইজার পাঠিয়ে তদন্ত করব, গার্ডকে সতর্ক বা পরিবর্তন করব, ৭ দিন বিশেষ মনিটরিং করব।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_guard_rude",
        "value": "অসৌজন্যমূলক আচরণ গ্রহণযোগ্য নয়। ফর্মাল কমপ্লেইন্ট রেজিস্টার করছি। ২৪ ঘণ্টায় তদন্ত শুরু, গার্ডকে ডিউটি থেকে সরানো হবে, ৪৮ ঘণ্টায় আপডেট জানাব।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_guard_abandoned",
        "value": "গার্ড পয়েন্ট ছেড়ে যাওয়া জরুরি বিষয়। এখনই অপারেশন কন্ট্রোলে জানাচ্ছি — ব্যাকআপ গার্ড পাঠানো হচ্ছে ও সুপারভাইজার সাইটে যাচ্ছে। আপনার পয়েন্ট অরক্ষিত থাকবে না।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_theft_suspicion",
        "value": "চুরির সন্দেহ অত্যন্ত গুরুতর। গার্ডকে তাৎক্ষণিক সাসপেন্ড, ইনভেস্টিগেশন টিম তদন্ত করবে, প্রয়োজনে আইনানুগ ব্যবস্থা নেওয়া হবে। অপারেশন ম্যানেজারের সাথে সংযুক্ত করছি।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 5: REPLACEMENT
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "replacement",
        "key": "replacement_intro",
        "value": "গার্ড রিপ্লেসমেন্ট সম্পর্কে জানতে চাইছেন? বর্তমান গার্ডের পরিবর্তে নতুন গার্ড চান নাকি অনুপস্থিত গার্ডের প্রতিস্থাপন দরকার?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "replacement",
        "key": "replacement_change",
        "value": "গার্ড রিপ্লেসমেন্ট: অনুরোধ এখনই রেজিস্টার হচ্ছে, ২৪-৪৮ ঘণ্টায় নতুন গার্ড ডিপ্লয় হবে, সাইটের চাহিদা অনুযায়ী ব্রিফ করা হবে, প্রথম ৭ দিন সুপারভাইজার নজরদারি রাখবে।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "replacement",
        "key": "replacement_urgent",
        "value": "জরুরি রিপ্লেসমেন্ট: স্ট্যান্ডবাই টিমে রিকোয়েস্ট পাঠাচ্ছি, নিকটস্থ ব্যাকআপ গার্ড মোবিলাইজ হচ্ছে, ২-৪ ঘণ্টায় গার্ড পৌঁছাবে। পয়েন্টের ঠিকানা ও কন্ট্যাক্ট পারসন জানান।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "replacement",
        "key": "replacement_multiple",
        "value": "একাধিক গার্ড পরিবর্তনে একটু সময় লাগবে। অপারেশন ম্যানেজার ২৪ ঘণ্টায় যোগাযোগ করে রিপ্লেসমেন্ট প্ল্যান তৈরি করবেন। আপনার পছন্দের যোগাযোগ সময় জানান।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 6: BILLING
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "billing",
        "key": "billing_intro",
        "value": "বিলিং সম্পর্কে জানতে চান? নতুন বিলের তথ্য, পেমেন্ট স্ট্যাটাস, বকেয়া তথ্য বা বিল সংক্রান্ত অমিল — কোন বিষয়ে সাহায্য লাগবে?",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "billing",
        "key": "billing_amount",
        "value": "আপনার কোম্পানির নাম বা চুক্তি নম্বর জানান। বিলিং সিস্টেম চুক্তি অনুযায়ী পরিচালিত। বিস্তারিত জানতে অ্যাকাউন্টস বিভাগে ট্রান্সফার করব বা কলব্যাক করব।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "billing",
        "key": "billing_payment_issue",
        "value": "পেমেন্ট ভেরিফাই করতে জানান: কবে পেমেন্ট করেছেন, কোন মাধ্যমে (ব্যাংক/চেক/ক্যাশ), ট্রানজেকশন রেফারেন্স নম্বর। অ্যাকাউন্টস টিম ২৪ ঘণ্টায় ভেরিফিকেশন করে জানাবে।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SALARY
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "salary",
        "key": "salary_info",
        "value": "বেতন নির্ভর করে ডিউটির ধরন, শিফট, লোকেশন ও অভিজ্ঞতার উপর। ওভারটাইম, বিশেষ ডিউটি ভাতা, অগ্রিম/লোন সুবিধা ও ঈদ বোনাস আছে। বিস্তারিত: HR 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 7: MONITORING
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "monitoring",
        "key": "monitoring_system",
        "value": "মনিটরিং সিস্টেম: ডিজিটাল চেক-ইন/আউট, বায়োমেট্রিক অ্যাক্সেস কন্ট্রোল, প্যাট্রোল মনিটরিং, দৈনিক/সাপ্তাহিক রিপোর্ট ও ইনসিডেন্ট রিপোর্টিং। ইমেইল বা WhatsApp-এ রিপোর্ট পাঠাতে পারি।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 8: EMERGENCY
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "emergency",
        "key": "emergency_response",
        "value": "পরিস্থিতি গুরুতর বুঝতে পারছি। শান্ত থাকুন — অপারেশন কন্ট্রোলে অ্যালার্ট পাঠাচ্ছি, সুপারভাইজার সাইটে যাচ্ছে, অতিরিক্ত গার্ড মোবিলাইজ হচ্ছে। জীবনের ঝুঁকি থাকলে 999 কল করুন।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 9: FACEBOOK REPLIES
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_job_inquiry",
        "value": "আসসালামু আলাইকুম! আগ্রহের জন্য ধন্যবাদ। আমরা নিয়মিত গার্ড নিয়োগ দিই। নাম, বয়স, ঠিকানা ও অভিজ্ঞতার তথ্য পেজে ইনবক্সে পাঠান। HR টিম যোগাযোগ করবে। কল: 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_salary_query",
        "value": "বেতন ডিউটির ধরন ও অভিজ্ঞতার উপর নির্ভর করে। প্রতিযোগিতামূলক বেতন ও অতিরিক্ত সুবিধা পান। বিস্তারিত জানতে ইনবক্স করুন বা কল দিন। 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_office_location",
        "value": "যোগাযোগ: ফোন 01958 122300, ওয়েবসাইট al-aqsasecurity.com, পেজে ইনবক্সেও মেসেজ করতে পারেন। আপনাকে সাহায্য করতে পেরে খুশি হব!",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_service_inquiry",
        "value": "আমরা ফ্যাক্টরি, অফিস, কারখানা, জেটি, ভেসেল ও ইভেন্টে পেশাদার সিকিউরিটি গার্ড দিই। কাস্টমাইজড প্ল্যান তৈরি করি। প্রতিষ্ঠানের তথ্য ইনবক্সে পাঠান। কল: 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_rate_query",
        "value": "রেট গার্ড সংখ্যা, শিফট, ডিউটির ধরন ও লোকেশনের উপর নির্ভর করে। প্রতিযোগিতামূলক মূল্যে সেরা সার্ভিস দিই। ফ্রি কোটেশনের জন্য ইনবক্সে জানান বা কল করুন 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_positive_feedback",
        "value": "অসংখ্য ধন্যবাদ সুন্দর ফিডব্যাকের জন্য! আপনাদের সন্তুষ্টিই সবচেয়ে বড় অর্জন। আরও ভালো সার্ভিস দেওয়ার চেষ্টা করছি। আল-আকসা পরিবারের সাথে থাকার জন্য ধন্যবাদ!",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_negative_feedback",
        "value": "আপনার অভিজ্ঞতার জন্য দুঃখিত। সমস্যা সমাধানের জন্য বিস্তারিত তথ্যসহ ইনবক্স করুন বা কল করুন 01958 122300। আপনার সমস্যা অবশ্যই সমাধান করব।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_fraud_accusation",
        "value": "আল-আকসা সিকিউরিটি ২০১৪ সাল থেকে সরকার অনুমোদিত লাইসেন্সে কাজ করছে। অমিল থাকলে চুক্তি নম্বর ও তথ্যসহ ম্যানেজমেন্টে যোগাযোগ করুন 01958 122300। প্রতিটি অভিযোগ তদন্ত করি।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_guard_salary_complaint",
        "value": "সকল গার্ডের বেতন নির্ধারিত সময়ে দিই। লোন অনুরোধে দেওয়া হয়, চুক্তি অনুযায়ী কিস্তিতে সমন্বয়। নির্দিষ্ট সমস্যা থাকলে HR-এ যোগাযোগ করুন 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_general_emoji",
        "value": "ধন্যবাদ! আমাদের সাথে থাকুন। al-aqsasecurity.com",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "facebook_reply",
        "key": "fb_competitor_comparison",
        "value": "কাজের মানই আমাদের পরিচয়। ২০১৪ সাল থেকে আন্তর্জাতিক মানের প্রশিক্ষিত গার্ড দিচ্ছি। প্রতিষ্ঠাতার G4S Dubai-তে ৫ বছরের অভিজ্ঞতা সার্ভিস কোয়ালিটি নিশ্চিত করে।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 10: CONTRACT
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "contract",
        "key": "contract_renewal",
        "value": "চুক্তি নবায়নে ধন্যবাদ! চুক্তি নম্বর বা কোম্পানির নাম জানান। বর্তমান শর্ত পর্যালোচনা, নতুন চাহিদা যুক্ত ও মূল্য সমন্বয় করব। সেলস টিম ২৪ ঘণ্টায় যোগাযোগ করবে।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "contract",
        "key": "contract_cancellation",
        "value": "বাতিলের কারণ জানতে চাই — হয়তো সমাধান করতে পারি। বাতিল চাইলে: নোটিশ পিরিয়ড প্রযোজ্য, বকেয়া সমন্বয় হবে, ফর্মাল ক্লোজার সম্পন্ন হবে। ম্যানেজমেন্ট টিমের সাথে সংযুক্ত করি।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 11: SUPERVISOR
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "supervisor",
        "key": "supervisor_visit",
        "value": "রুটিন সুপারভাইজার ভিজিট সপ্তাহে ২-৩ বার। বিশেষ ভিজিট অনুরোধে। নির্দিষ্ট বিষয়ে ভিজিট চাইলে জানান — এলাকার সুপারভাইজারকে জানাচ্ছি, যোগাযোগ করে সময় ঠিক করবেন।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 12: TRAINING
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "training",
        "key": "training_details",
        "value": "প্রশিক্ষণ আমাদের মূল ভিত্তি। গার্ডরা শেখে: রিস্ক অ্যাসেসমেন্ট, থ্রেট ডিটেকশন, সার্ভেইল্যান্স, ইমার্জেন্সি রেসপন্স, ফার্স্ট এইড, ফায়ার সেফটি, কাস্টমার সার্ভিস ও CCTV অপারেশন।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # JOB FAQ — Detailed Q&A from instructions.txt
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_no_experience",
        "value": "অভিজ্ঞতা না থাকলেও আবেদন করা যায়। কমপক্ষে ৪৫ দিনের ট্রেনিং নিতে হবে। ট্রেনিং চলাকালীন ১২,০০০-১৫,০০০ টাকা (বেতন + ভাতা সহ) পাবেন।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_no_education",
        "value": "শিক্ষাগত সনদ বাধ্যতামূলক না। শারীরিক ফিটনেস, সততা ও দায়িত্বশীলতা বেশি গুরুত্বপূর্ণ। শিক্ষাগত যোগ্যতা বেশি থাকলে অফিসিয়াল চাকরি, বেশি বেতন ও ক্যারিয়ার উন্নতির সুযোগ।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_how_to_apply",
        "value": "সরাসরি চট্টগ্রাম অফিসে আসবেন। সাথে আনতে হবে: কাপড়-চোপড়, মোশারি, কাঁথা, NID/জন্ম নিবন্ধন, জাতীয়তার সনদ, শিক্ষাগত সনদ (না থাকলে বাবা-মায়ের আইডি), ২ কপি পাসপোর্ট ছবি, ২ কপি স্ট্যাম্প ছবি। যেদিন আসবেন সেদিন বা পরের দিন জাহাজে উঠতে পারবেন।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_joining_fee",
        "value": "কোনো ঘুষ বা জামানত লাগে না। জয়েনিং ফি ৩৫০০ টাকা — একসাথে না দিলে মাসে ৫০০ করে কাটা হবে, ৬ মাস পর ফেরত। জয়েনের সময় কমপক্ষে ১৫০০ জমা। কারণ: খাওয়া, আইডি কার্ড, ইউনিফর্ম, জাহাজে অনুমতি।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_resignation",
        "value": "চাকরি ছাড়তে ৩০ দিন আগে লিখিত রিজাইন দিতে হবে। না দিলে ১ মাসের বেতনের সমপরিমাণ টাকা জমা দিতে হবে।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_details_escort",
        "value": "জাহাজে থেকে আমদানি করা মালামাল পাহারা দেওয়া। লোড/আনলোড সময় উপস্থিত থাকা, হিসাব রাখা (Tallyman/Scaleman)। জাহাজ যায়: নারায়ণগঞ্জ, ভৈরব, আশুগঞ্জ, পাবনা, যশোর, মংলা, বরিশাল।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_duty_hours",
        "value": "২৪ ঘন্টা সিস্টেমে কাজ (শিফট অনুযায়ী)। জাহাজে অবস্থান করতে হবে — বাসা থেকে যাতায়াত করে ডিউটি করা যাবে না।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_post_duty",
        "value": "রিলিজ হলে ডিউটি স্লিপে সাইন নিয়ে WhatsApp-এ ছবি পাঠাতে হবে। বিকাশ/নগদে ২-৩ ঘন্টায় টাকা পাবেন। তারপর চট্টগ্রাম অফিসে ফিরে নতুন ডিউটি পাবেন।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_salary_payment",
        "value": "প্রতি মাসের ১০-১২ তারিখে বেতন। ২০ তারিখের পর জয়েন করলে ৩য় মাসে বেতন পাবেন। শর্ত: মাসের ১-১০ তারিখে ২ দিনের বেশি অনুপস্থিত থাকা যাবে না।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "job_leave_policy",
        "value": "প্রথম ৩ মাস কোনো ছুটি নেই। বেতন নির্ধারণ হবে জমা দেওয়া ডিউটি স্লিপ অনুযায়ী।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "job_seeker",
        "key": "office_location_chittagong",
        "value": "চট্টগ্রাম অফিস: ইস্পাহানি কন্টেইনার ডিপোর ১ নং গেইট, খোকনের বিল্ডিং (৩য় তলা), একে খান মোড়, পাহাড়তলী, চট্টগ্রাম। ফোন: 01958 122300",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # CLIENT SERVICE — Specific sub-types
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "client_service",
        "key": "client_service_construction",
        "value": "নির্মাণ সাইট ও গুদামঘরে সিকিউরিটি সার্ভিস দিই। মালামাল পাহারা, শ্রমিক প্রবেশ নিয়ন্ত্রণ ও রাতের শিফটে বিশেষ নজরদারি।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # COMPLAINT — Sub-types
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_guard_sleeping",
        "value": "গার্ড ঘুমানো বা ফোনে থাকা গ্রহণযোগ্য নয়। সুপারভাইজার পাঠিয়ে তদন্ত, গার্ড সতর্ক বা পরিবর্তন, ৭ দিন বিশেষ মনিটরিং করব।",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "complaint",
        "key": "complaint_guard_left_post",
        "value": "গার্ড পয়েন্ট ছেড়ে যাওয়া জরুরি বিষয়। ব্যাকআপ গার্ড পাঠানো হচ্ছে, গার্ডের সাথে যোগাযোগ হচ্ছে, সুপারভাইজার সাইটে যাচ্ছে। পয়েন্ট অরক্ষিত থাকবে না।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 13: CLOSING
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "closing",
        "key": "closing_farewell",
        "value": "আল-আকসা সিকিউরিটি-এ কল করার জন্য ধন্যবাদ। যেকোনো সময় কল করুন 01958 122300 বা ভিজিট করুন al-aqsasecurity.com। আল্লাহ হাফেজ, ভালো থাকবেন!",
        "language": "bn",
        "confidence": 1.0,
    },
    {
        "category": "conversation",
        "subcategory": "closing",
        "key": "closing_continue",
        "value": "জি, বলুন। আমি শুনছি।",
        "language": "bn",
        "confidence": 1.0,
    },

    # ══════════════════════════════════════════════════
    # SECTION 14: FALLBACK
    # ══════════════════════════════════════════════════
    {
        "category": "conversation",
        "subcategory": "fallback",
        "key": "fallback_unclear",
        "value": "আমি একটু পরিষ্কারভাবে বুঝতে পারিনি। আপনি কি একটু বিস্তারিত বলবেন?",
        "language": "bn",
        "confidence": 0.9,
    },
    {
        "category": "conversation",
        "subcategory": "fallback",
        "key": "fallback_transfer",
        "value": "এই বিষয়টি সংশ্লিষ্ট বিভাগ ভালো বলতে পারবে। ট্রান্সফার করছি অথবা কলব্যাক করব — পছন্দের সময় জানান?",
        "language": "bn",
        "confidence": 0.9,
    },
    {
        "category": "conversation",
        "subcategory": "fallback",
        "key": "fallback_angry_caller",
        "value": "আপনার হতাশা বুঝতে পারছি এবং আন্তরিকভাবে দুঃখিত। সমস্যা সমাধান হবে — এখনই সিনিয়র ম্যানেজারের সাথে সংযুক্ত করছি।",
        "language": "bn",
        "confidence": 0.9,
    },
    {
        "category": "conversation",
        "subcategory": "fallback",
        "key": "fallback_wrong_number",
        "value": "কোনো সমস্যা নেই! এটি আল-আকসা সিকিউরিটি — পেশাদার সিকিউরিটি সার্ভিস দিই। ভবিষ্যতে প্রয়োজন হলে মনে রাখবেন! আল্লাহ হাফেজ।",
        "language": "bn",
        "confidence": 0.9,
    },
]


def upload_all(api_url: str) -> dict:
    """Upload all knowledge entries with rate-limit handling and retries."""
    stats = {"inserted": 0, "exists": 0, "failed": 0}

    for i, entry in enumerate(KNOWLEDGE_DATA, 1):
        key = entry["key"]
        retries = 0
        success = False

        while retries < MAX_RETRIES and not success:
            try:
                resp = requests.post(api_url, json=entry, timeout=10)

                if resp.status_code == 429:
                    retries += 1
                    wait = RETRY_DELAY * retries
                    logger.warning(
                        "  429 rate limited on %s — retry %d/%d in %ds",
                        key, retries, MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                result = resp.json()
                status = result.get("status", "unknown")

                if status == "inserted":
                    stats["inserted"] += 1
                    logger.info(
                        "  ✅ INSERTED [%d/%d]: %s",
                        i, len(KNOWLEDGE_DATA), key,
                    )
                elif status == "exists":
                    stats["exists"] += 1
                    logger.info(
                        "  ⚠️  EXISTS  [%d/%d]: %s",
                        i, len(KNOWLEDGE_DATA), key,
                    )
                else:
                    stats["failed"] += 1
                    logger.warning(
                        "  ❌ UNKNOWN [%d/%d]: %s → %s",
                        i, len(KNOWLEDGE_DATA), key, result,
                    )
                success = True

            except requests.RequestException as e:
                retries += 1
                if retries >= MAX_RETRIES:
                    stats["failed"] += 1
                    logger.error(
                        "  ❌ FAILED  [%d/%d]: %s → %s",
                        i, len(KNOWLEDGE_DATA), key, e,
                    )
                else:
                    logger.warning(
                        "  Retry %d/%d for %s: %s",
                        retries, MAX_RETRIES, key, e,
                    )
                    time.sleep(RETRY_DELAY)

        time.sleep(DELAY_BETWEEN)

    return stats


def main():
    # Count categories
    cats = {}
    subcats = {}
    for e in KNOWLEDGE_DATA:
        cats[e["category"]] = cats.get(e["category"], 0) + 1
        sc = e.get("subcategory", "-")
        subcats[sc] = subcats.get(sc, 0) + 1

    logger.info("=" * 55)
    logger.info("  Fazle Knowledge Uploader — instructions.txt edition")
    logger.info("=" * 55)
    logger.info("  Target:  %s", API_URL)
    logger.info("  Total entries: %d", len(KNOWLEDGE_DATA))
    logger.info("  Categories: %s", dict(cats))
    logger.info("  Subcategories: %s", dict(subcats))
    logger.info("=" * 55)

    stats = upload_all(API_URL)

    logger.info("=" * 55)
    logger.info("  RESULTS:")
    logger.info("    ✅ Inserted: %d", stats["inserted"])
    logger.info("    ⚠️  Exists:   %d", stats["exists"])
    logger.info("    ❌ Failed:   %d", stats["failed"])
    logger.info("    Total:      %d", sum(stats.values()))
    logger.info("=" * 55)

    if stats["failed"] > 0:
        logger.error("Some entries failed! Check logs above.")
        sys.exit(1)

    logger.info("All done. System is idempotent — safe to re-run.")


if __name__ == "__main__":
    main()
