/**
 * Salary Service — employee-wise salary aggregation.
 *
 * Endpoints:
 *   GET /salary/employee-summary?from=YYYY-MM-DD&to=YYYY-MM-DD
 *   GET /salary/employee/:employeeId — detailed salary breakdown
 *   GET /salary/rates — current active rates
 *   PUT /salary/rates/:id — update a rate
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

export async function salaryRoutes(app: FastifyInstance) {

  // ── Employee-wise salary summary ──
  app.get('/employee-summary', async (req) => {
    const { from, to } = req.query as { from?: string; to?: string };

    // Get current daily rate
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

    // Payment date conditions
    const payDateCond: string[] = [];
    const payParams: any[] = [];
    let pidx = 1;
    if (from) { payDateCond.push(`pay.created_at >= $${pidx++}::date`); payParams.push(from); }
    if (to) { payDateCond.push(`pay.created_at <= ($${pidx++}::date + interval '1 day')`); payParams.push(to); }
    const payWhere = payDateCond.length > 0 ? `WHERE ${payDateCond.join(' AND ')}` : '';

    // Attendance count per employee
    const { rows: attendance } = await query(`
      SELECT employee_id, MAX(name) AS name, COUNT(DISTINCT date) AS duty_days
      FROM ops_attendance
      ${attWhere}
      GROUP BY employee_id
    `, params);

    // Payments per employee
    const { rows: payments } = await query(`
      SELECT
        employee_id,
        COALESCE(SUM(CASE WHEN category = 'food' THEN amount ELSE 0 END), 0) AS food_total,
        COALESCE(SUM(CASE WHEN category = 'transport' THEN amount ELSE 0 END), 0) AS transport_total,
        COALESCE(SUM(CASE WHEN category = 'salary' THEN amount ELSE 0 END), 0) AS salary_paid,
        COALESCE(SUM(CASE WHEN category = 'advance' THEN amount ELSE 0 END), 0) AS advance_total,
        COALESCE(SUM(amount), 0) AS total_paid
      FROM ops_payments pay
      ${payWhere}
      GROUP BY employee_id
    `, payParams);

    // Merge attendance + payment data
    const payMap = new Map(payments.map(p => [p.employee_id, p]));

    const employees = attendance.map(a => {
      const p = payMap.get(a.employee_id) || {
        food_total: 0, transport_total: 0, salary_paid: 0, advance_total: 0, total_paid: 0
      };
      const dutyDays = parseInt(a.duty_days);
      const calculatedSalary = dutyDays * dailyRate;
      return {
        employee_id: a.employee_id,
        name: a.name,
        duty_days: dutyDays,
        daily_rate: dailyRate,
        calculated_salary: calculatedSalary,
        food_total: parseInt(p.food_total),
        transport_total: parseInt(p.transport_total),
        salary_paid: parseInt(p.salary_paid),
        advance_total: parseInt(p.advance_total),
        total_paid: parseInt(p.total_paid),
        net_due: calculatedSalary - parseInt(p.salary_paid) - parseInt(p.advance_total),
      };
    });

    return {
      employees: employees.sort((a, b) => b.duty_days - a.duty_days),
      count: employees.length,
      daily_rate: dailyRate,
      period: { from: from || 'all', to: to || 'all' },
    };
  });

  // ── Detailed salary for one employee ──
  app.get('/employee/:employeeId', async (req) => {
    const { employeeId } = req.params as { employeeId: string };
    const { from, to } = req.query as { from?: string; to?: string };

    const { rows: rateRows } = await query(
      `SELECT amount FROM ops_rates WHERE rate_type = 'daily' AND active = true ORDER BY effective_from DESC LIMIT 1`
    );
    const dailyRate = rateRows.length > 0 ? parseInt(rateRows[0].amount) : 150;

    // Attendance
    const attConds: string[] = ['employee_id = $1'];
    const attParams: any[] = [employeeId];
    let aidx = 2;
    if (from) { attConds.push(`date >= $${aidx++}::date`); attParams.push(from); }
    if (to) { attConds.push(`date <= $${aidx++}::date`); attParams.push(to); }

    const { rows: attendance } = await query(
      `SELECT * FROM ops_attendance WHERE ${attConds.join(' AND ')} ORDER BY date DESC`,
      attParams
    );

    // Payments
    const payConds: string[] = ['employee_id = $1'];
    const payParams: any[] = [employeeId];
    let pidx = 2;
    if (from) { payConds.push(`created_at >= $${pidx++}::date`); payParams.push(from); }
    if (to) { payConds.push(`created_at <= ($${pidx++}::date + interval '1 day')`); payParams.push(to); }

    const { rows: payments } = await query(
      `SELECT * FROM ops_payments WHERE ${payConds.join(' AND ')} ORDER BY created_at DESC`,
      payParams
    );

    // Programs
    const { rows: programs } = await query(
      `SELECT * FROM ops_programs WHERE escort_mobile = $1 ORDER BY start_date DESC`, [employeeId]
    );

    const dutyDays = new Set(attendance.map(a => a.date?.toISOString?.().slice(0, 10) || a.date)).size;
    const foodTotal = payments.filter(p => p.category === 'food').reduce((s, p) => s + parseInt(p.amount), 0);
    const transportTotal = payments.filter(p => p.category === 'transport').reduce((s, p) => s + parseInt(p.amount), 0);
    const salaryPaid = payments.filter(p => p.category === 'salary').reduce((s, p) => s + parseInt(p.amount), 0);
    const advanceTotal = payments.filter(p => p.category === 'advance').reduce((s, p) => s + parseInt(p.amount), 0);

    return {
      employee_id: employeeId,
      duty_days: dutyDays,
      daily_rate: dailyRate,
      calculated_salary: dutyDays * dailyRate,
      food_total: foodTotal,
      transport_total: transportTotal,
      salary_paid: salaryPaid,
      advance_total: advanceTotal,
      net_due: (dutyDays * dailyRate) - salaryPaid - advanceTotal,
      attendance,
      payments,
      programs,
    };
  });

  // ── Rate management ──
  app.get('/rates', async () => {
    const { rows } = await query(
      `SELECT * FROM ops_rates WHERE active = true ORDER BY rate_type, destination`
    );
    return { rates: rows };
  });

  app.put('/rates/:id', async (req) => {
    const { id } = req.params as { id: string };
    const { amount, active } = req.body as { amount?: number; active?: boolean };

    const sets: string[] = [];
    const params: any[] = [];
    let idx = 1;

    if (amount !== undefined) { sets.push(`amount = $${idx++}`); params.push(amount); }
    if (active !== undefined) { sets.push(`active = $${idx++}`); params.push(active); }
    sets.push(`updated_at = NOW()`);
    params.push(parseInt(id));

    const { rows } = await query(
      `UPDATE ops_rates SET ${sets.join(', ')} WHERE id = $${idx} RETURNING *`,
      params
    );

    if (rows.length === 0) return { error: 'Rate not found' };
    return rows[0];
  });
}
