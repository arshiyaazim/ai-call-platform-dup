/**
 * Parser — extracts structured data from messy WhatsApp text.
 *
 * Handles:
 *   - Mobile numbers (normalize +880 → 0)
 *   - Amounts (e.g. "1000/-", "500 tk")
 *   - Payment method (B = Bkash, N = Nagad)
 *   - Vessel names
 *   - Destinations
 *   - Names
 *   - Dates
 *   - Shift (D/N)
 */

export interface ParsedMobile {
  raw: string;
  normalized: string;  // leading zero form: 01XXXXXXXXX
}

export interface ParsedPayment {
  mobile: ParsedMobile | null;
  amount: number | null;
  method: 'B' | 'N' | null;
  name: string | null;
  category: 'food' | 'transport' | 'general' | 'salary' | 'advance' | null;
  date: string | null; // YYYY-MM-DD
}

export interface ParsedProgram {
  motherVessel: string | null;
  lighters: string[];        // multi-lighter support
  lighterVessel: string | null; // backward-compat: first lighter
  masterMobile: ParsedMobile | null;
  destination: string | null;
  escortName: string | null;
  escortMobile: ParsedMobile | null;
  startDate: string | null; // YYYY-MM-DD
  shift: 'D' | 'N' | null;
}

export interface ParsedEmployee {
  name: string | null;
  mobile: ParsedMobile | null;
  role: 'escort' | 'guard' | 'admin' | null;
}

export interface ParsedAttendance {
  employeeId: string | null;
  name: string | null;
  location: string | null;
  clientName: string | null;
  date: string | null;
  shift: 'D' | 'N' | null;
}

// ── Mobile parser ──

const MOBILE_RE = /(?:\+?880|0)(1[3-9]\d{8})/g;
const BARE_MOBILE_RE = /\b(01[3-9]\d{8})\b/g;

export function parseMobiles(text: string): ParsedMobile[] {
  const results: ParsedMobile[] = [];
  const seen = new Set<string>();

  // Match +880... or 880... or 01...
  let m: RegExpExecArray | null;
  const re1 = new RegExp(MOBILE_RE.source, 'g');
  while ((m = re1.exec(text)) !== null) {
    const normalized = '0' + m[1];
    if (!seen.has(normalized)) {
      seen.add(normalized);
      results.push({ raw: m[0], normalized });
    }
  }
  // Also match bare 01XXXXXXXXX
  const re2 = new RegExp(BARE_MOBILE_RE.source, 'g');
  while ((m = re2.exec(text)) !== null) {
    if (!seen.has(m[1])) {
      seen.add(m[1]);
      results.push({ raw: m[0], normalized: m[1] });
    }
  }
  return results;
}

// ── Amount parser ──

const AMOUNT_RE = /(\d[\d,]*)\s*(?:\/-|tk|taka)?/gi;

export function parseAmount(text: string): number | null {
  // Strip phone numbers before extracting amounts so phone digits
  // aren't mistaken for currency values
  const cleaned_text = text.replace(/(?:\+?880|0)1[3-9]\d{8}/g, ' ');
  const re = new RegExp(AMOUNT_RE.source, 'gi');
  const m = re.exec(cleaned_text);
  if (!m) return null;
  const cleaned = m[1].replace(/,/g, '');
  const num = parseInt(cleaned, 10);
  return isNaN(num) || num <= 0 ? null : num;
}

// ── Method parser ──

export function parseMethod(text: string): 'B' | 'N' | null {
  const lower = text.toLowerCase();
  if (/\bbkash\b/i.test(text) || /\bB\b/.test(text)) return 'B';
  if (/\bnagad\b/i.test(text) || /\bN\b/.test(text)) return 'N';
  return null;
}

// ── Vessel parser (multi-lighter support) ──

const MV_RE = /(?:mv\.?|m\.v\.?|mother\s*vessel)\s*[:\-]?\s*(.+?)(?:\n|$|,|lighter)/i;
const LIGHTER_RE = /(?:lighter)\s*[:\-]?\s*(.+?)(?:\n|$)/i;
const LIGHTER_MULTI_RE = /(?:lighter)\s*[:\-]?\s*(.+?)(?:\n|$)/gi;

export function parseVessels(text: string): { mother: string | null; lighters: string[] } {
  const mvMatch = MV_RE.exec(text);
  const lighters: string[] = [];
  const seen = new Set<string>();

  let m: RegExpExecArray | null;
  const re = new RegExp(LIGHTER_MULTI_RE.source, 'gi');
  while ((m = re.exec(text)) !== null) {
    // Each match may contain comma-separated lighter names
    const raw = m[1].trim();
    const parts = raw.split(/\s*,\s*/);
    for (const p of parts) {
      const name = p.trim();
      if (name && !seen.has(name.toLowerCase())) {
        seen.add(name.toLowerCase());
        lighters.push(name);
      }
    }
  }
  return {
    mother: mvMatch ? mvMatch[1].trim() : null,
    lighters,
  };
}

/** Backward-compat: return first lighter as single value */
export function parseVesselsSingle(text: string): { mother: string | null; lighter: string | null } {
  const v = parseVessels(text);
  return { mother: v.mother, lighter: v.lighters[0] || null };
}

// ── Destination parser ──

const DEST_RE = /(?:destination|dest)\s*[:\-]?\s*(.+?)(?:\n|$)/i;
const KNOWN_DESTINATIONS = ['mongla', 'chittagong', 'ctg', 'payra', 'dhaka', 'khulna', 'narayanganj'];

export function parseDestination(text: string): string | null {
  const dMatch = DEST_RE.exec(text);
  if (dMatch) return dMatch[1].trim();

  const lower = text.toLowerCase();
  for (const dest of KNOWN_DESTINATIONS) {
    if (lower.includes(dest)) {
      return dest.charAt(0).toUpperCase() + dest.slice(1);
    }
  }
  return null;
}

// ── Name parser ──

const NAME_RE = /(?:name|escort\s*name|guard\s*name)\s*[:\-]?\s*(.+?)(?:\n|$|,)/i;

export function parseName(text: string): string | null {
  const m = NAME_RE.exec(text);
  return m ? m[1].trim() : null;
}

// ── Date parser ──

const DATE_DD_MM_YYYY = /(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})/;
const DATE_YYYY_MM_DD = /(\d{4})[./-](\d{1,2})[./-](\d{1,2})/;

export function parseDate(text: string): string | null {
  let m = DATE_YYYY_MM_DD.exec(text);
  if (m) {
    return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`;
  }
  m = DATE_DD_MM_YYYY.exec(text);
  if (m) {
    const year = m[3].length === 2 ? '20' + m[3] : m[3];
    return `${year}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`;
  }
  return null;
}

// ── Shift parser ──

export function parseShift(text: string): 'D' | 'N' | null {
  if (/\bday\b|\bD\b|\b\(D\)/.test(text)) return 'D';
  if (/\bnight\b|\bN\b|\b\(N\)/.test(text)) return 'N';
  return null;
}

// ── Role parser ──

export function parseRole(text: string): 'escort' | 'guard' | 'admin' | null {
  const lower = text.toLowerCase();
  if (lower.includes('admin')) return 'admin';
  if (lower.includes('guard')) return 'guard';
  if (lower.includes('escort')) return 'escort';
  return null;
}

// ── Payment category parser ──

export function parseCategory(text: string): 'food' | 'transport' | 'general' | 'salary' | 'advance' | null {
  const lower = text.toLowerCase();
  if (/\b(food|meal|khana|খাবার)\b/.test(lower)) return 'food';
  if (/\b(transport|travel|fare|ভাড়া)\b/.test(lower)) return 'transport';
  if (/\b(salary|বেতন)\b/.test(lower)) return 'salary';
  if (/\b(advance|অগ্রিম)\b/.test(lower)) return 'advance';
  return null; // null means "general" — assigned in webhook
}

// ── Composite parsers ──

export function parsePaymentMessage(text: string): ParsedPayment {
  const mobiles = parseMobiles(text);
  return {
    mobile: mobiles[0] || null,
    amount: parseAmount(text),
    method: parseMethod(text),
    name: parseName(text),
    category: parseCategory(text),
    date: parseDate(text),
  };
}

export function parseProgramMessage(text: string): ParsedProgram {
  const mobiles = parseMobiles(text);
  const vessels = parseVessels(text);
  return {
    motherVessel: vessels.mother,
    lighters: vessels.lighters,
    lighterVessel: vessels.lighters[0] || null,
    masterMobile: mobiles[0] || null,
    destination: parseDestination(text),
    escortName: parseName(text),
    escortMobile: mobiles[1] || mobiles[0] || null,
    startDate: parseDate(text),
    shift: parseShift(text),
  };
}

export function parseEmployeeMessage(text: string): ParsedEmployee {
  const mobiles = parseMobiles(text);
  return {
    name: parseName(text),
    mobile: mobiles[0] || null,
    role: parseRole(text),
  };
}

export function parseAttendanceMessage(text: string): ParsedAttendance {
  const mobiles = parseMobiles(text);
  const LOC_RE = /(?:location|loc)\s*[:\-]?\s*(.+?)(?:\n|$)/i;
  const CLIENT_RE = /(?:client)\s*[:\-]?\s*(.+?)(?:\n|$)/i;
  const locMatch = LOC_RE.exec(text);
  const clientMatch = CLIENT_RE.exec(text);

  return {
    employeeId: mobiles[0]?.normalized || null,
    name: parseName(text),
    location: locMatch ? locMatch[1].trim() : null,
    clientName: clientMatch ? clientMatch[1].trim() : null,
    date: parseDate(text),
    shift: parseShift(text),
  };
}
