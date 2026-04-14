/**
 * Export Service — CSV export for programs and payments.
 *
 * Endpoints:
 *   GET /export/programs?from=YYYY-MM-DD&to=YYYY-MM-DD&status=completed
 *   GET /export/payments?from=YYYY-MM-DD&to=YYYY-MM-DD
 *   GET /export/salary?from=YYYY-MM-DD&to=YYYY-MM-DD
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

function escapeCsv(val: any): string {
  if (val === null || val === undefined) return '';
  const str = String(val);
  if (str.includes(',') || str.includes('"') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function toCsvRow(values: any[]): string {
  return values.map(escapeCsv).join(',');
}

export async function exportRoutes(app: FastifyInstance) {

  // ── Export Programs CSV ──
  app.get('/programs', async (req, reply) => {
    const { from, to, status } = req.query as { from?: string; to?: string; status?: string };
    const conditions: string[] = [];
    const params: any[] = [];
    let idx = 1;

    if (from) { conditions.push(`start_date >= $${idx++}::date`); params.push(from); }
    if (to) { conditions.push(`COALESCE(end_date, start_date) <= $${idx++}::date`); params.push(to); }
    if (status) { conditions.push(`status = $${idx++}`); params.push(status); }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const { rows } = await query(`
      SELECT id, mother_vessel, lighter_vessel, destination, escort_name, escort_mobile,
        start_date, end_date, shift, status, food, transport, total_cost
      FROM ops_programs ${where}
      ORDER BY start_date DESC
    `, params);

    const headers = ['ID', 'Mother Vessel', 'Lighter Vessel', 'Destination', 'Escort Name',
      'Escort Mobile', 'Start Date', 'End Date', 'Shift', 'Status', 'Food', 'Transport', 'Total Cost'];

    const csvLines = [toCsvRow(headers)];
    for (const r of rows) {
      csvLines.push(toCsvRow([
        r.id, r.mother_vessel, r.lighter_vessel, r.destination, r.escort_name,
        r.escort_mobile, r.start_date, r.end_date, r.shift, r.status,
        r.food, r.transport, r.total_cost,
      ]));
    }

    const csv = csvLines.join('\n');
    reply.header('Content-Type', 'text/csv');
    reply.header('Content-Disposition', `attachment; filename="programs_export_${new Date().toISOString().slice(0, 10)}.csv"`);
    return csv;
  });

  // ── Export Payments CSV ──
  app.get('/payments', async (req, reply) => {
    const { from, to, status } = req.query as { from?: string; to?: string; status?: string };
    const conditions: string[] = [];
    const params: any[] = [];
    let idx = 1;

    if (from) { conditions.push(`p.payment_date >= $${idx++}::date`); params.push(from); }
    if (to) { conditions.push(`p.payment_date <= $${idx++}::date`); params.push(to); }
    if (status) { conditions.push(`p.status = $${idx++}`); params.push(status); }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const { rows } = await query(`
      SELECT p.id, p.employee_id, p.name, p.amount, p.method, p.status,
        p.category, p.paid_by, p.program_id, p.payment_date, p.created_at,
        prog.mother_vessel
      FROM ops_payments p
      LEFT JOIN ops_programs prog ON prog.id = p.program_id
      ${where}
      ORDER BY p.payment_date DESC, p.created_at DESC
    `, params);

    const headers = ['ID', 'Employee ID', 'Name', 'Amount', 'Method', 'Status',
      'Category', 'Paid By', 'Program ID', 'Mother Vessel', 'Payment Date', 'Created At'];

    const csvLines = [toCsvRow(headers)];
    for (const r of rows) {
      csvLines.push(toCsvRow([
        r.id, r.employee_id, r.name, r.amount,
        r.method === 'B' ? 'bKash' : r.method === 'N' ? 'Nagad' : r.method,
        r.status, r.category, r.paid_by, r.program_id,
        r.mother_vessel, r.payment_date, r.created_at,
      ]));
    }

    const csv = csvLines.join('\n');
    reply.header('Content-Type', 'text/csv');
    reply.header('Content-Disposition', `attachment; filename="payments_export_${new Date().toISOString().slice(0, 10)}.csv"`);
    return csv;
  });

  // ── Export Salary CSV ──
  app.get('/salary', async (req, reply) => {
    const { from, to } = req.query as { from?: string; to?: string };

    const { rows: rateRows } = await query(
      `SELECT amount FROM ops_rates WHERE rate_type = 'daily' AND active = true ORDER BY effective_from DESC LIMIT 1`
    );
    const dailyRate = rateRows.length > 0 ? parseInt(rateRows[0].amount) : 150;

    const dateCondition: string[] = [];
    const params: any[] = [];
    let idx = 1;
    if (from) { dateCondition.push(`a.date >= $${idx++}::date`); params.push(from); }
    if (to) { dateCondition.push(`a.date <= $${idx++}::date`); params.push(to); }
    const attWhere = dateCondition.length > 0 ? `WHERE ${dateCondition.join(' AND ')}` : '';

    const { rows: attendance } = await query(`
      SELECT employee_id, MAX(name) AS name, COUNT(DISTINCT date) AS duty_days
      FROM ops_attendance ${attWhere}
      GROUP BY employee_id
    `, params);

    const { rows: payments } = await query(`
      SELECT employee_id,
        COALESCE(SUM(CASE WHEN category = 'food' THEN amount ELSE 0 END), 0) AS food_total,
        COALESCE(SUM(CASE WHEN category = 'transport' THEN amount ELSE 0 END), 0) AS transport_total,
        COALESCE(SUM(CASE WHEN category = 'salary' THEN amount ELSE 0 END), 0) AS salary_paid,
        COALESCE(SUM(CASE WHEN category = 'advance' THEN amount ELSE 0 END), 0) AS advance_total,
        COALESCE(SUM(amount), 0) AS total_paid
      FROM ops_payments
      GROUP BY employee_id
    `);

    const payMap = new Map(payments.map(p => [p.employee_id, p]));

    const headers = ['Employee ID', 'Name', 'Duty Days', 'Daily Rate', 'Calculated Salary',
      'Food', 'Transport', 'Salary Paid', 'Advance', 'Total Paid', 'Net Due'];
    const csvLines = [toCsvRow(headers)];

    for (const a of attendance) {
      const p = payMap.get(a.employee_id) || {
        food_total: 0, transport_total: 0, salary_paid: 0, advance_total: 0, total_paid: 0
      };
      const dutyDays = parseInt(a.duty_days);
      const salary = dutyDays * dailyRate;
      csvLines.push(toCsvRow([
        a.employee_id, a.name, dutyDays, dailyRate, salary,
        p.food_total, p.transport_total, p.salary_paid, p.advance_total,
        p.total_paid, salary - parseInt(p.salary_paid) - parseInt(p.advance_total),
      ]));
    }

    const csv = csvLines.join('\n');
    reply.header('Content-Type', 'text/csv');
    reply.header('Content-Disposition', `attachment; filename="salary_export_${new Date().toISOString().slice(0, 10)}.csv"`);
    return csv;
  });
}
