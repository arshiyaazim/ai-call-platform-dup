// ============================================================
// WBOM — Zod Validation Schemas
// Auto-validates API responses before rendering.
// Single source of truth aligned with backend schema endpoint.
// ============================================================
import { z } from "zod";

// ── Reusable primitives ──────────────────────────────────────
const dateStr = z.string().nullable().optional();
const optStr = z.string().nullable().optional();
const optNum = z.number().nullable().optional();

// ── Entity schemas ───────────────────────────────────────────

export const EmployeeSchema = z.object({
  id: z.number(),
  name: z.string(),
  phone: optStr,
  designation: optStr,
  status: optStr,
  salary: optNum,
  bkash: optStr,
  nagad: optStr,
  nid: optStr,
  bank: optStr,
  emergency_phone: optStr,
  address: optStr,
  joined: dateStr,
  created_at: dateStr,
  updated_at: dateStr,
}).passthrough();

export const TransactionSchema = z.object({
  id: z.number(),
  employee_name: optStr,
  employee_id: optNum,
  employee_phone: optStr,
  type: optStr,
  amount: optNum,
  method: optStr,
  status: optStr,
  date: dateStr,
  time: optStr,
  reference: optStr,
  remarks: optStr,
  payment_phone: optStr,
  wa_msg_id: optStr,
  idem_key: optStr,
  approved_by: optStr,
  approved_at: dateStr,
  created_by: optStr,
}).passthrough();

export const ClientSchema = z.object({
  id: z.number(),
  name: optStr,
  phone: optStr,
  company: optStr,
  type: optStr,
  balance: optNum,
  terms: optStr,
  is_active: z.boolean().nullable().optional(),
  created_at: dateStr,
  updated_at: dateStr,
}).passthrough();

export const ApplicationSchema = z.object({
  id: z.number(),
  name: optStr,
  phone: optStr,
  position: optStr,
  experience: optStr,
  status: optStr,
  source: optStr,
  applied_at: dateStr,
  updated_at: dateStr,
}).passthrough();

export const AuditSchema = z.object({
  id: z.number(),
  time: dateStr,
  event: optStr,
  actor: optStr,
  entity: optStr,
  entity_id: optNum,
  payload: z.any().nullable().optional(),
}).passthrough();

export const PaymentSchema = z.object({
  id: z.number(),
  employee_name: optStr,
  employee_id: optNum,
  amount: optNum,
  method: optStr,
  status: optStr,
  idem_key: optStr,
  reviewed_by: optStr,
  transaction_id: optNum,
  created_at: dateStr,
}).passthrough();

// ── Standard API envelope ────────────────────────────────────

const MetaSchema = z.object({
  total: z.number(),
  page: z.number().optional(),
  count: z.number().optional(),
}).passthrough();

export const ApiEnvelopeSchema = z.object({
  success: z.boolean(),
  data: z.array(z.record(z.any())),
  meta: MetaSchema.optional(),
  schema: z.record(z.any()).optional(),
  version: z.string().optional(),
}).passthrough();

// ── Entity lookup map ────────────────────────────────────────
// Used by validateRows() to pick the right schema per entity.

export const ENTITY_SCHEMAS = {
  employees: EmployeeSchema,
  transactions: TransactionSchema,
  clients: ClientSchema,
  applications: ApplicationSchema,
  audit: AuditSchema,
  payments: PaymentSchema,
};

// ── Validation helpers ───────────────────────────────────────

/**
 * Validate the raw API envelope. Returns parsed envelope or throws.
 */
export function validateEnvelope(json) {
  return ApiEnvelopeSchema.parse(json);
}

/**
 * Validate an array of rows against an entity schema.
 * Invalid rows are logged but not thrown — returns cleaned array.
 * @param {string} entity - entity name (employees, transactions, etc.)
 * @param {Array} rows - raw data rows
 * @returns {{ valid: Array, errors: Array }}
 */
export function validateRows(entity, rows) {
  const schema = ENTITY_SCHEMAS[entity];
  if (!schema) return { valid: rows, errors: [] };

  const valid = [];
  const errors = [];
  for (let i = 0; i < rows.length; i++) {
    const result = schema.safeParse(rows[i]);
    if (result.success) {
      valid.push(result.data);
    } else {
      errors.push({ index: i, issues: result.error.issues });
      valid.push(rows[i]); // still show the row, just log
    }
  }
  if (errors.length) {
    console.warn(`[WBOM] ${entity}: ${errors.length} row(s) failed Zod validation`, errors);
  }
  return { valid, errors };
}
