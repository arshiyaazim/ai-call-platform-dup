/**
 * Template Generator — formats structured replies for WhatsApp.
 * Clean, standardized formatting for all response types.
 */

function fmtDate(dateStr?: string | null): string {
  if (!dateStr) {
    const now = new Date();
    const dd = String(now.getDate()).padStart(2, '0');
    const mm = String(now.getMonth() + 1).padStart(2, '0');
    const yyyy = now.getFullYear();
    return `${dd}.${mm}.${yyyy}`;
  }
  // Convert YYYY-MM-DD → DD.MM.YYYY
  const [y, m, d] = dateStr.split('-');
  return `${d}.${m}.${y}`;
}

function fmtAmount(n: number): string {
  return n.toLocaleString('en-BD') + '/-';
}

// ── Program / Escort templates ──

export interface EscortTemplateData {
  motherVessel: string;
  lighterVessel?: string;
  masterMobile?: string;
  escortName?: string;
  escortMobile?: string;
  startDate?: string;
  shift?: 'D' | 'N';
}

export function escortReplyTemplate(data: EscortTemplateData): string {
  const lines: string[] = [];
  lines.push(`Mv.${data.motherVessel}`);
  if (data.lighterVessel) lines.push(`Lighter: ${data.lighterVessel}`);
  if (data.masterMobile) lines.push(data.masterMobile);
  lines.push(`Escort Name: ${data.escortName || '___'}`);
  lines.push(`Escort Mobile: ${data.escortMobile || '___'}`);
  lines.push(`${fmtDate(data.startDate)}(${data.shift || 'D'})`);
  lines.push('Al-Aqsa Security Service');
  return lines.join('\n');
}

/** Multi-lighter: one message per lighter created */
export function multiProgramTemplate(mother: string, lighters: string[], shift: string): string {
  const lines = [`✅ ${lighters.length} programs created for Mv.${mother}`];
  for (let i = 0; i < lighters.length; i++) {
    lines.push(`  ${i + 1}. Lighter: ${lighters[i]}`);
  }
  lines.push(`Shift: ${shift || 'D'}`);
  return lines.join('\n');
}

// ── Payment templates ──

export interface PaymentTemplateData {
  employeeId: string;
  name: string;
  mobile: string;
  method?: 'B' | 'N';
  amount: number;
  status?: string;
  remarks?: string;
  category?: string;
  programId?: number;
}

export function paymentTemplate(data: PaymentTemplateData): string {
  const methodLabel = data.method || '_';
  const lines: string[] = [];
  lines.push(`✅ Payment Recorded`);
  lines.push(`${data.name} ${data.mobile}(${methodLabel}) ${fmtAmount(data.amount)}`);
  if (data.category && data.category !== 'general') lines.push(`Category: ${data.category}`);
  if (data.programId) lines.push(`Linked to Program #${data.programId}`);
  lines.push(`Status: ${data.status || 'running'}`);
  return lines.join('\n');
}

// ── Employee template ──

export interface EmployeeTemplateData {
  employeeId: string;
  name: string;
  mobile: string;
  role: string;
}

export function employeeTemplate(data: EmployeeTemplateData): string {
  return [
    `✅ Employee Registered`,
    `ID: ${data.employeeId}`,
    `Name: ${data.name}`,
    `Mobile: ${data.mobile}`,
    `Role: ${data.role}`,
  ].join('\n');
}

// ── Attendance template ──

export interface AttendanceTemplateData {
  employeeId: string;
  name: string;
  location: string;
  clientName: string;
  date: string;
  shift?: 'D' | 'N';
}

export function attendanceTemplate(data: AttendanceTemplateData): string {
  const lines = [
    `✅ Attendance Recorded`,
    `${data.name} (${data.employeeId})`,
    `Location: ${data.location}`,
    `Client: ${data.clientName}`,
    `Date: ${fmtDate(data.date)}`,
  ];
  if (data.shift) lines.push(`Shift: ${data.shift}`);
  return lines.join('\n');
}

// ── Search / Suggestions ──

export function suggestionsTemplate(query: string, matches: Array<{ name: string; id: string; score?: number }>): string {
  if (matches.length === 0) return `No results found for "${query}"`;
  const lines = [`🔍 ${matches.length} result(s) for "${query}":`];
  for (const m of matches.slice(0, 5)) {
    lines.push(`• ${m.id} — ${m.name}`);
  }
  if (matches.length > 5) lines.push(`... and ${matches.length - 5} more`);
  return lines.join('\n');
}

// ── Error / Confirm ──

export function errorTemplate(message: string): string {
  return `⚠️ ${message}`;
}

export function confirmTemplate(action: string, preview: string): string {
  return `${preview}\n\n✅ Reply "ok" to confirm ${action}, or "cancel" to cancel.`;
}

// ── Completion template ──

export interface CompletionTemplateData {
  programId: number;
  motherVessel: string;
  lighterVessel: string;
  escortName: string;
  startDate: string;
  endDate: string;
  totalPayments: number;
  food: number;
  transport: number;
  totalCost: number;
  dutyDays?: number;
  dailyRate?: number;
  calculatedSalary?: number;
  transportRate?: number;
}

export function completionTemplate(data: CompletionTemplateData): string {
  const lines = [
    `✅ Program #${data.programId} Completed`,
    `Mv.${data.motherVessel} / Lighter: ${data.lighterVessel}`,
    `Escort: ${data.escortName}`,
    `Period: ${fmtDate(data.startDate)} → ${fmtDate(data.endDate)}`,
    ``,
    `Payments: ${data.totalPayments}`,
    `  Food: ${fmtAmount(data.food)}`,
    `  Transport: ${fmtAmount(data.transport)}`,
    `  Total Cost: ${fmtAmount(data.totalCost)}`,
  ];
  if (data.dutyDays !== undefined) {
    lines.push('');
    lines.push(`📊 Auto Calculation:`);
    lines.push(`  Duty Days: ${data.dutyDays}`);
    lines.push(`  Daily Rate: ${fmtAmount(data.dailyRate || 0)}`);
    lines.push(`  Salary: ${fmtAmount(data.calculatedSalary || 0)}`);
    if (data.transportRate) lines.push(`  Transport Rate: ${fmtAmount(data.transportRate)}`);
  }
  return lines.join('\n');
}

// ── Preview template for correction flow ──

export function previewTemplate(intent: string, data: Record<string, any>): string {
  const lines: string[] = [`📋 Preview (${intent}):`];
  for (const [key, value] of Object.entries(data)) {
    if (value != null && value !== '' && key !== 'raw') {
      const label = key.replace(/([A-Z])/g, ' $1').replace(/^./, s => s.toUpperCase());
      lines.push(`  ${label}: ${value}`);
    }
  }
  lines.push('');
  lines.push(`Reply "ok" to save, "cancel" to discard.`);
  return lines.join('\n');
}

// ── Program summary (with linked payments) ──

export interface ProgramSummaryData {
  programId: number;
  motherVessel: string;
  lighterVessel: string;
  escortName: string;
  status: string;
  startDate: string;
  endDate?: string;
  payments: Array<{ amount: number; method: string; category: string }>;
  food: number;
  transport: number;
  totalCost: number;
}

export function programSummaryTemplate(data: ProgramSummaryData): string {
  const lines = [
    `📊 Program #${data.programId} [${data.status.toUpperCase()}]`,
    `Mv.${data.motherVessel} / ${data.lighterVessel}`,
    `Escort: ${data.escortName}`,
    `Started: ${fmtDate(data.startDate)}`,
  ];
  if (data.endDate) lines.push(`Ended: ${fmtDate(data.endDate)}`);
  lines.push(`Food: ${fmtAmount(data.food)} | Transport: ${fmtAmount(data.transport)}`);
  lines.push(`Total Cost: ${fmtAmount(data.totalCost)}`);
  if (data.payments.length > 0) {
    lines.push(`Payments (${data.payments.length}):`);
    for (const p of data.payments.slice(0, 5)) {
      lines.push(`  • ${fmtAmount(p.amount)} (${p.method || '-'}) [${p.category || 'general'}]`);
    }
    if (data.payments.length > 5) lines.push(`  ... +${data.payments.length - 5} more`);
  }
  return lines.join('\n');
}
