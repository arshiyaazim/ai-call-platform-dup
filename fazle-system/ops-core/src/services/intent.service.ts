/**
 * Intent Detection — classifies incoming WhatsApp messages.
 *
 * Categories:
 *   confirm      → "ok", "yes", "save" — confirms pending action
 *   cancel       → "no", "cancel" — cancels pending action
 *   completion   → "completed", "done", "finish"
 *   payment      → contains amount + mobile
 *   program      → contains vessel/mobile/destination
 *   employee     → add/update employee
 *   attendance   → attendance-related
 *   note         → add a note
 *   search       → contains lookup keywords
 *   conversational → fallback to Fazle AI
 */

export type IntentType =
  | 'confirm'
  | 'cancel'
  | 'completion'
  | 'payment'
  | 'program'
  | 'employee'
  | 'attendance'
  | 'note'
  | 'search'
  | 'conversational';

export interface Intent {
  type: IntentType;
  confidence: number;  // 0.0 – 1.0
}

// Re-export for backward compat
export type DetectedIntent = Intent;

// ── Patterns ──

const MOBILE_RE = /(?:\+?880|0)1[3-9]\d{8}/;
const AMOUNT_RE = /\d{2,}(?:\s*\/-|\s*tk|\s*taka)?/i;
const METHOD_RE = /\b[BN]\b|\bbkash\b|\bnagad\b/i;
const VESSEL_RE = /\b(?:mv|m\.v|mother\s*vessel|lighter|vessel)\b/i;
const DESTINATION_RE = /\b(?:destination|dest|mongla|chittagong|ctg|payra|dhaka|khulna|narayanganj)\b/i;
const SHIFT_RE = /\b[DN]\b.*(?:shift|duty)/i;
const ESCORT_RE = /\b(?:escort|guard)\b/i;
const EMPLOYEE_KW_RE = /\b(?:add\s*employee|new\s*employee|update\s*employee|employee\s*add|register)\b/i;
const ATTENDANCE_KW_RE = /\b(?:attendance|present|absent|hajira|duty\s*report)\b/i;
const NOTE_KW_RE = /\b(?:note|memo|remark|comment)\b/i;
const SEARCH_KW_RE = /\b(?:search|find|check|show|list|details|info|আছে|দেখাও|খুঁজে)\b/i;
const CONFIRM_RE = /^(ok|yes|save|হ্যাঁ|ঠিক আছে|সেভ|confirm)\s*$/i;
const CANCEL_RE = /^(no|cancel|না|বাদ)\s*$/i;
const COMPLETION_RE = /\b(completed|done|finish|finished|শেষ|সম্পন্ন|complete)\b/i;

export function detectIntent(text: string): Intent {
  const trimmed = text.trim();

  // Confirm / Cancel — highest priority (for correction flow)
  if (CONFIRM_RE.test(trimmed)) {
    return { type: 'confirm', confidence: 1.0 };
  }
  if (CANCEL_RE.test(trimmed)) {
    return { type: 'cancel', confidence: 1.0 };
  }

  // Completion — "completed", "done", "finish" + optional mobile/vessel
  if (COMPLETION_RE.test(trimmed)) {
    return { type: 'completion', confidence: 0.95 };
  }

  // Payment: amount + mobile or method marker
  const hasAmount = AMOUNT_RE.test(trimmed);
  const hasMobile = MOBILE_RE.test(trimmed);
  const hasMethod = METHOD_RE.test(trimmed);

  if (hasAmount && (hasMobile || hasMethod)) {
    return { type: 'payment', confidence: 0.95 };
  }
  if (hasAmount && trimmed.length < 80) {
    return { type: 'payment', confidence: 0.7 };
  }

  // Program: vessel keywords or structured program data
  const hasVessel = VESSEL_RE.test(trimmed);
  const hasDest = DESTINATION_RE.test(trimmed);
  const hasEscort = ESCORT_RE.test(trimmed);

  if (hasVessel && (hasDest || hasEscort || hasMobile)) {
    return { type: 'program', confidence: 0.9 };
  }
  if (hasVessel) {
    return { type: 'program', confidence: 0.7 };
  }

  // Employee
  if (EMPLOYEE_KW_RE.test(trimmed)) {
    return { type: 'employee', confidence: 0.9 };
  }

  // Attendance
  if (ATTENDANCE_KW_RE.test(trimmed)) {
    return { type: 'attendance', confidence: 0.85 };
  }

  // Note
  if (NOTE_KW_RE.test(trimmed)) {
    return { type: 'note', confidence: 0.75 };
  }

  // Search
  if (SEARCH_KW_RE.test(trimmed) || /^0?1[3-9]\d{8}$/.test(trimmed.replace(/\s/g, ''))) {
    return { type: 'search', confidence: 0.8 };
  }

  // Fallback
  return { type: 'conversational', confidence: 0.5 };
}
