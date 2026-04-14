/**
 * Webhook Service — full business logic for ops-core.
 *
 * Flow: social-engine → /ops/whatsapp/process → intent → correction flow → handler
 *
 * Features:
 *   - Role-based access (ops_users table)
 *   - Correction flow (preview → confirm/cancel)
 *   - Program lifecycle (one active per employee, auto-complete previous)
 *   - Payment → program linking (by escort_mobile)
 *   - Multi-lighter support (multiple programs per message)
 *   - Completion logic (complete program + payments, calculate total)
 */

import { FastifyInstance } from 'fastify';
import { query, transaction } from '../db';
import { detectIntent, Intent } from './intent.service';
import {
  parsePaymentMessage, parseProgramMessage, parseEmployeeMessage,
  parseAttendanceMessage, parseMobiles
} from './parser.service';
import {
  paymentTemplate, escortReplyTemplate, multiProgramTemplate,
  employeeTemplate, attendanceTemplate, errorTemplate,
  confirmTemplate, completionTemplate, previewTemplate, programSummaryTemplate
} from './template.service';

interface IncomingWebhook {
  sender_id: string;
  text: string;
  message_id?: string;
  contact_name?: string;
}

interface WebhookResponse {
  handled: boolean;
  reply?: string;
  intent?: string;
  confidence?: number;
}

// ── Role lookup (ops_users table) ──

async function getSenderRole(senderId: string): Promise<{ role: string; name: string } | null> {
  const mobile = senderId.replace(/\D/g, '');
  const normalized = mobile.startsWith('880') ? '0' + mobile.slice(3) : mobile;
  const variants = [mobile, normalized, '880' + normalized.slice(1)];

  const { rows } = await query(
    `SELECT name, role FROM ops_users
     WHERE whatsapp_number = ANY($1) AND active = true LIMIT 1`,
    [variants]
  );
  if (rows.length > 0) return rows[0];

  // Fallback: check ops_employees for backward compat
  const { rows: empRows } = await query(
    `SELECT name, role FROM ops_employees WHERE employee_id = ANY($1) LIMIT 1`,
    [variants]
  );
  return empRows.length > 0 ? { name: empRows[0].name, role: empRows[0].role } : null;
}

// ── Correction flow helpers ──

async function getPendingAction(senderId: string) {
  const { rows } = await query(
    `SELECT * FROM ops_pending_actions
     WHERE sender_id = $1 AND status = 'pending' AND expires_at > NOW()
     ORDER BY created_at DESC LIMIT 1`,
    [senderId]
  );
  return rows[0] || null;
}

async function confirmPendingAction(id: number) {
  await query(
    `UPDATE ops_pending_actions SET status = 'confirmed' WHERE id = $1`,
    [id]
  );
}

async function cancelPendingAction(id: number) {
  await query(
    `UPDATE ops_pending_actions SET status = 'cancelled' WHERE id = $1`,
    [id]
  );
}

async function createPendingAction(
  senderId: string, intent: string, parsedData: any, previewText: string
): Promise<void> {
  // Expire any old pending actions from this sender
  await query(
    `UPDATE ops_pending_actions SET status = 'expired'
     WHERE sender_id = $1 AND status = 'pending'`,
    [senderId]
  );
  await query(
    `INSERT INTO ops_pending_actions (sender_id, intent, parsed_data, preview_text)
     VALUES ($1, $2, $3, $4)`,
    [senderId, intent, JSON.stringify(parsedData), previewText]
  );
}

// ── Execute a confirmed pending action ──

async function executePendingAction(pending: any, senderId: string): Promise<string> {
  const data = pending.parsed_data;
  switch (pending.intent) {
    case 'payment':
      return await executePayment(data, senderId);
    case 'program':
      return await executeProgram(data, senderId);
    case 'employee':
      return await executeEmployee(data);
    case 'attendance':
      return await executeAttendance(data);
    default:
      return errorTemplate('Unknown pending action type.');
  }
}

// ── Payment handler (with program linking) ──

async function handlePayment(text: string, senderId: string): Promise<string> {
  const data = parsePaymentMessage(text);
  if (!data.mobile || !data.amount) {
    return errorTemplate('Payment requires mobile + amount.\nExample: 01711XXXXXX 5000 bkash');
  }

  const paymentData = {
    employeeId: data.mobile.normalized,
    amount: data.amount,
    method: data.method || 'B',
    name: data.name,
    category: data.category || 'general',
    paymentDate: data.date || null,
  };

  const preview = previewTemplate('payment', {
    employee: paymentData.employeeId,
    amount: `${paymentData.amount}/-`,
    method: paymentData.method === 'B' ? 'Bkash' : 'Nagad',
    category: paymentData.category,
  });

  await createPendingAction(senderId, 'payment', paymentData, preview);
  return preview;
}

async function executePayment(data: any, senderId: string): Promise<string> {
  const employeeId = data.employeeId;

  // Lookup employee
  const { rows: emp } = await query(
    `SELECT id, name, employee_id FROM ops_employees WHERE employee_id = $1`,
    [employeeId]
  );
  if (emp.length === 0) {
    return errorTemplate(`Employee ${employeeId} not found. Register first.`);
  }

  // Find running program linked to this employee (escort_mobile match)
  const { rows: progs } = await query(
    `SELECT id, food, transport FROM ops_programs
     WHERE escort_mobile = $1 AND status = 'running'
     ORDER BY start_date DESC LIMIT 1`,
    [employeeId]
  );
  const programId = progs.length > 0 ? progs[0].id : null;
  const category = data.category || 'general';

  const paymentDate = data.paymentDate || null;

  return await transaction(async (client) => {
    const { rows: payment } = await client.query(
      `INSERT INTO ops_payments (employee_id, name, amount, method, status, paid_by, program_id, category, payment_date)
       VALUES ($1, $2, $3, $4, 'running', $5, $6, $7, COALESCE($8::date, CURRENT_DATE)) RETURNING *`,
      [emp[0].employee_id, emp[0].name, data.amount, data.method, senderId, programId, category, paymentDate]
    );

    // Update program food/transport totals if linked
    if (programId && (category === 'food' || category === 'transport')) {
      await client.query(
        `UPDATE ops_programs SET ${category} = ${category} + $1 WHERE id = $2`,
        [data.amount, programId]
      );
    }

    return paymentTemplate({
      employeeId: emp[0].employee_id,
      name: emp[0].name,
      mobile: emp[0].employee_id,
      method: data.method,
      amount: data.amount,
      status: 'running',
      category,
      programId,
    });
  });
}

// ── Program handler (lifecycle + multi-lighter) ──

async function handleProgram(text: string, senderId: string): Promise<string> {
  const data = parseProgramMessage(text);
  if (!data.motherVessel) {
    return errorTemplate('Program requires vessel name.\nExample: mv ocean star lighter abc chittagong');
  }

  const lighters = data.lighters.length > 0 ? data.lighters : [data.lighterVessel || 'Unknown'];

  const programData = {
    motherVessel: data.motherVessel,
    lighters,
    destination: data.destination,
    escortName: data.escortName,
    escortMobile: data.escortMobile?.normalized || null,
    startDate: data.startDate,
    shift: data.shift || 'D',
  };

  const preview = previewTemplate('program', {
    'Mother Vessel': programData.motherVessel,
    'Lighter(s)': lighters.join(', '),
    Destination: programData.destination,
    Escort: programData.escortName,
    'Escort Mobile': programData.escortMobile,
    Shift: programData.shift,
  });

  await createPendingAction(senderId, 'program', programData, preview);
  return preview;
}

async function executeProgram(data: any, senderId: string): Promise<string> {
  const lighters: string[] = data.lighters || ['Unknown'];
  const escortMobile = data.escortMobile;

  return await transaction(async (client) => {
    // Program lifecycle: auto-complete previous running program for this escort
    if (escortMobile) {
      const { rows: running } = await client.query(
        `SELECT id FROM ops_programs
         WHERE escort_mobile = $1 AND status = 'running'`,
        [escortMobile]
      );
      for (const prog of running) {
        // Snapshot before completing
        const { rows: snap } = await client.query(
          `SELECT * FROM ops_programs WHERE id = $1`, [prog.id]
        );
        await client.query(
          `INSERT INTO ops_program_history (program_id, snapshot, changed_by)
           VALUES ($1, $2, $3)`,
          [prog.id, JSON.stringify(snap[0]), senderId]
        );
        await client.query(
          `UPDATE ops_programs SET status = 'completed', end_date = CURRENT_DATE WHERE id = $1`,
          [prog.id]
        );
        // Complete linked payments
        await client.query(
          `UPDATE ops_payments SET status = 'completed' WHERE program_id = $1 AND status = 'running'`,
          [prog.id]
        );
      }
    }

    // Create one program per lighter
    const createdIds: number[] = [];
    for (const lighter of lighters) {
      const { rows: prog } = await client.query(
        `INSERT INTO ops_programs
         (mother_vessel, lighter_vessel, destination, escort_name, escort_mobile, start_date, shift, status)
         VALUES ($1, $2, $3, $4, $5, COALESCE($6::date, CURRENT_DATE), $7, 'running')
         RETURNING *`,
        [data.motherVessel, lighter, data.destination || null,
         data.escortName || null, escortMobile || null, data.startDate || null, data.shift || 'D']
      );

      // History snapshot
      await client.query(
        `INSERT INTO ops_program_history (program_id, snapshot, changed_by)
         VALUES ($1, $2, $3)`,
        [prog[0].id, JSON.stringify(prog[0]), senderId]
      );
      createdIds.push(prog[0].id);
    }

    if (lighters.length === 1) {
      return escortReplyTemplate({
        motherVessel: data.motherVessel,
        lighterVessel: lighters[0],
        escortName: data.escortName,
        escortMobile: escortMobile,
        startDate: data.startDate,
        shift: data.shift,
      });
    }
    return multiProgramTemplate(data.motherVessel, lighters, data.shift || 'D');
  });
}

// ── Employee handler ──

async function handleEmployee(text: string, senderId: string): Promise<string> {
  const data = parseEmployeeMessage(text);
  if (!data.mobile) {
    return errorTemplate('Employee registration requires mobile number.');
  }

  const empData = {
    employeeId: data.mobile.normalized,
    name: data.name || 'Unknown',
    role: data.role || 'escort',
  };

  const preview = previewTemplate('employee', empData);
  await createPendingAction(senderId, 'employee', empData, preview);
  return preview;
}

async function executeEmployee(data: any): Promise<string> {
  const { rows: existing } = await query(
    `SELECT * FROM ops_employees WHERE employee_id = $1`, [data.employeeId]
  );

  if (existing.length > 0) {
    const { rows } = await query(
      `UPDATE ops_employees SET name = COALESCE($1, name), role = COALESCE($2, role), updated_at = NOW()
       WHERE employee_id = $3 RETURNING *`,
      [data.name, data.role, data.employeeId]
    );
    return `✏️ Updated:\n` + employeeTemplate(rows[0]);
  }

  const { rows } = await query(
    `INSERT INTO ops_employees (employee_id, name, mobile, role)
     VALUES ($1, $2, $3, $4) RETURNING *`,
    [data.employeeId, data.name, data.employeeId, data.role]
  );
  return employeeTemplate(rows[0]);
}

// ── Attendance handler ──

async function handleAttendance(text: string, senderId: string): Promise<string> {
  const data = parseAttendanceMessage(text);
  if (!data.employeeId) {
    return errorTemplate('Attendance requires mobile number.');
  }

  const attData = {
    employeeId: data.employeeId,
    name: data.name,
    location: data.location,
    clientName: data.clientName,
    date: data.date,
    shift: data.shift,
  };

  // No correction flow for attendance — execute directly
  return await executeAttendance(attData);
}

async function executeAttendance(data: any): Promise<string> {
  let name = data.name || '';
  if (!name) {
    const { rows: emp } = await query(
      'SELECT name FROM ops_employees WHERE employee_id = $1', [data.employeeId]
    );
    if (emp.length > 0) name = emp[0].name;
  }

  const { rows } = await query(
    `INSERT INTO ops_attendance (employee_id, name, location, client_name, date, shift)
     VALUES ($1, $2, $3, $4, COALESCE($5::date, CURRENT_DATE), $6) RETURNING *`,
    [data.employeeId, name, data.location || null, data.clientName || null,
     data.date || null, data.shift || null]
  );
  return attendanceTemplate({
    employeeId: rows[0].employee_id,
    name: rows[0].name,
    location: rows[0].location || 'N/A',
    clientName: rows[0].client_name || 'N/A',
    date: rows[0].date,
    shift: rows[0].shift,
  });
}

// ── Note handler ──

async function handleNote(text: string, senderId: string): Promise<string> {
  const { rows } = await query(
    `INSERT INTO ops_notes (entity_type, entity_id, note, created_by)
     VALUES ('general', $1, $2, $3) RETURNING *`,
    [senderId, text, senderId]
  );
  return `📝 Note saved (ID: ${rows[0].id})`;
}

// ── Completion handler ──

async function handleCompletion(text: string, senderId: string): Promise<string> {
  // Find the sender's running program (by escort_mobile or sender's employee record)
  const mobile = senderId.replace(/\D/g, '');
  const normalized = mobile.startsWith('880') ? '0' + mobile.slice(3) : mobile;
  const variants = [mobile, normalized];

  // Also try to find program from a mobile in the message
  const mentioned = parseMobiles(text);
  if (mentioned.length > 0) {
    variants.push(mentioned[0].normalized);
  }

  const { rows: programs } = await query(
    `SELECT p.*, COALESCE(
       (SELECT SUM(amount) FROM ops_payments WHERE program_id = p.id), 0
     ) as total_paid
     FROM ops_programs p
     WHERE p.escort_mobile = ANY($1) AND p.status = 'running'
     ORDER BY p.start_date DESC`,
    [variants]
  );

  if (programs.length === 0) {
    return errorTemplate('No running program found for you. Nothing to complete.');
  }

  // Complete all running programs for this escort
  return await transaction(async (client) => {
    const results: string[] = [];

    for (const prog of programs) {
      // Snapshot
      await client.query(
        `INSERT INTO ops_program_history (program_id, snapshot, changed_by)
         VALUES ($1, $2, $3)`,
        [prog.id, JSON.stringify(prog), senderId]
      );

      // Calculate total cost from linked payments
      const { rows: paymentSums } = await client.query(
        `SELECT
           COALESCE(SUM(CASE WHEN category = 'food' THEN amount ELSE 0 END), 0) as food_total,
           COALESCE(SUM(CASE WHEN category = 'transport' THEN amount ELSE 0 END), 0) as transport_total,
           COALESCE(SUM(amount), 0) as grand_total,
           COUNT(*) as payment_count
         FROM ops_payments WHERE program_id = $1`,
        [prog.id]
      );
      const sums = paymentSums[0];

      // Auto rate calculation — duty days * daily rate + destination transport
      const dutyDays = Math.max(1,
        Math.ceil((Date.now() - new Date(prog.start_date).getTime()) / (1000 * 60 * 60 * 24))
      );
      const { rows: dailyRateRow } = await client.query(
        `SELECT amount FROM ops_rates WHERE rate_type = 'daily' AND active = true ORDER BY effective_from DESC LIMIT 1`
      );
      const dailyRate = dailyRateRow.length > 0 ? parseInt(dailyRateRow[0].amount) : 150;
      const calculatedSalary = dutyDays * dailyRate;

      let transportRate = 0;
      if (prog.destination) {
        const { rows: trRow } = await client.query(
          `SELECT amount FROM ops_rates WHERE rate_type = 'transport' AND active = true
           AND LOWER(destination) = LOWER($1) LIMIT 1`,
          [prog.destination]
        );
        if (trRow.length > 0) transportRate = parseInt(trRow[0].amount);
      }

      const autoTotalCost = parseInt(sums.grand_total) + calculatedSalary + transportRate;

      // Complete program
      await client.query(
        `UPDATE ops_programs
         SET status = 'completed', end_date = CURRENT_DATE,
             food = $1, transport = $2, total_cost = $3, salary_calculated = true
         WHERE id = $4`,
        [sums.food_total, parseInt(sums.transport_total) + transportRate, autoTotalCost, prog.id]
      );

      // Complete linked payments
      await client.query(
        `UPDATE ops_payments SET status = 'completed'
         WHERE program_id = $1 AND status = 'running'`,
        [prog.id]
      );

      results.push(completionTemplate({
        programId: prog.id,
        motherVessel: prog.mother_vessel,
        lighterVessel: prog.lighter_vessel || 'N/A',
        escortName: prog.escort_name || 'N/A',
        startDate: prog.start_date,
        endDate: new Date().toISOString().slice(0, 10),
        totalPayments: parseInt(sums.payment_count),
        food: parseInt(sums.food_total),
        transport: parseInt(sums.transport_total) + transportRate,
        totalCost: autoTotalCost,
        dutyDays,
        dailyRate,
        calculatedSalary,
        transportRate,
      }));
    }

    return results.join('\n\n---\n\n');
  });
}

// ── Search handler (improved ranking) ──

async function handleSearch(text: string): Promise<string> {
  const searchTerm = text.replace(/^(search|find|khojo|check|show|list|details|info)\s*/i, '').trim();
  if (!searchTerm) return errorTemplate('Search what? Send: search <name/id/vessel>');

  // Employees — exact first, then fuzzy
  const { rows: employees } = await query(
    `SELECT name, employee_id, role,
       CASE
         WHEN employee_id = $2 THEN 0
         WHEN name ILIKE $2 THEN 1
         WHEN name ILIKE $1 OR employee_id ILIKE $1 THEN 2
         ELSE 3
       END as rank
     FROM ops_employees
     WHERE name ILIKE $1 OR employee_id ILIKE $1 OR similarity(name, $2) > 0.25
     ORDER BY rank, similarity(name, $2) DESC
     LIMIT 5`,
    [`%${searchTerm}%`, searchTerm]
  );

  // Programs — exact first, then fuzzy
  const { rows: programs } = await query(
    `SELECT id, mother_vessel, lighter_vessel, destination, escort_name, status, start_date, end_date,
       food, transport, total_cost,
       CASE
         WHEN mother_vessel ILIKE $2 THEN 0
         WHEN mother_vessel ILIKE $1 OR destination ILIKE $1 THEN 1
         ELSE 2
       END as rank
     FROM ops_programs
     WHERE mother_vessel ILIKE $1 OR destination ILIKE $1 OR escort_name ILIKE $1
       OR lighter_vessel ILIKE $1
       OR similarity(mother_vessel, $2) > 0.25
     ORDER BY rank, start_date DESC
     LIMIT 5`,
    [`%${searchTerm}%`, searchTerm]
  );

  // Payments
  const { rows: payments } = await query(
    `SELECT employee_id, name, amount, method, status, category, program_id
     FROM ops_payments
     WHERE name ILIKE $1 OR employee_id ILIKE $1
     ORDER BY created_at DESC LIMIT 5`,
    [`%${searchTerm}%`]
  );

  const lines: string[] = [];
  if (employees.length > 0) {
    lines.push('👤 *Employees:*');
    employees.forEach(e => lines.push(`  ${e.name} | ${e.employee_id} | ${e.role}`));
  }
  if (programs.length > 0) {
    lines.push('🚢 *Programs:*');
    programs.forEach(p => {
      const date = p.start_date?.toISOString?.().slice(0, 10) || '';
      const cost = p.total_cost ? ` | Cost: ${p.total_cost}/-` : '';
      lines.push(`  #${p.id} ${p.mother_vessel} → ${p.destination || 'N/A'} | ${p.status}${cost} | ${date}`);
    });
  }
  if (payments.length > 0) {
    lines.push('💰 *Payments:*');
    payments.forEach(p => {
      const cat = p.category && p.category !== 'general' ? ` [${p.category}]` : '';
      lines.push(`  ${p.name} | ${p.amount}/- (${p.method || '-'})${cat} | ${p.status}`);
    });
  }

  if (lines.length === 0) {
    return `🔍 No results for "${searchTerm}"`;
  }
  return lines.join('\n');
}

// ── Main webhook route ──

export async function webhookRoutes(app: FastifyInstance) {

  app.post('/process', async (req, reply) => {
    const body = req.body as IncomingWebhook;
    if (!body?.text || !body?.sender_id) {
      return reply.code(400).send({ handled: false, error: 'text and sender_id required' });
    }

    const { text, sender_id } = body;

    try {
      const intent: Intent = detectIntent(text);

      // ── Step 1: Check for pending correction flow ──
      if (intent.type === 'confirm' || intent.type === 'cancel') {
        const pending = await getPendingAction(sender_id);
        if (!pending) {
          return { handled: true, reply: 'No pending action to confirm.', intent: intent.type };
        }

        if (intent.type === 'confirm') {
          await confirmPendingAction(pending.id);
          const result = await executePendingAction(pending, sender_id);
          return { handled: true, reply: result, intent: pending.intent, confidence: 1.0 };
        } else {
          await cancelPendingAction(pending.id);
          return { handled: true, reply: '❌ Action cancelled.', intent: 'cancel', confidence: 1.0 };
        }
      }

      // ── Step 2: If conversational, let brain handle ──
      if (intent.type === 'conversational') {
        return { handled: false, intent: intent.type, confidence: intent.confidence };
      }

      // ── Step 3: Role-based access ──
      const user = await getSenderRole(sender_id);
      const role = user?.role || null;

      // viewer: search only
      if (role === 'viewer' && intent.type !== 'search') {
        return {
          handled: true,
          reply: '⛔ You have viewer access only. You can search but not modify data.',
          intent: intent.type
        };
      }

      // ── Step 4: Route to handler ──
      let replyText: string;

      switch (intent.type) {
        case 'payment':
          replyText = await handlePayment(text, sender_id);
          break;
        case 'program':
          replyText = await handleProgram(text, sender_id);
          break;
        case 'employee':
          replyText = await handleEmployee(text, sender_id);
          break;
        case 'attendance':
          replyText = await handleAttendance(text, sender_id);
          break;
        case 'completion':
          replyText = await handleCompletion(text, sender_id);
          break;
        case 'note':
          replyText = await handleNote(text, sender_id);
          break;
        case 'search':
          replyText = await handleSearch(text);
          break;
        default:
          return { handled: false, intent: intent.type, confidence: intent.confidence };
      }

      return {
        handled: true,
        reply: replyText,
        intent: intent.type,
        confidence: intent.confidence
      } as WebhookResponse;

    } catch (err: any) {
      app.log.error({ err, sender_id, text: text.slice(0, 100) }, 'ops webhook error');
      return {
        handled: true,
        reply: errorTemplate('Something went wrong. Please try again.'),
        intent: 'error'
      };
    }
  });
}
