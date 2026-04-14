/**
 * Payment Service — create/list payments with employee lookup + suggestions.
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';
import { paymentTemplate } from './template.service';

export async function paymentRoutes(app: FastifyInstance) {

  // List payments (with optional date filtering)
  app.get('/', async (req) => {
    const { employee_id, status, from, to, limit: lim } = req.query as {
      employee_id?: string; status?: string; from?: string; to?: string; limit?: string;
    };
    let sql = 'SELECT * FROM ops_payments';
    const params: unknown[] = [];
    const conditions: string[] = [];

    if (employee_id) {
      conditions.push(`employee_id = $${params.length + 1}`);
      params.push(employee_id);
    }
    if (status) {
      conditions.push(`status = $${params.length + 1}`);
      params.push(status);
    }
    if (from) {
      conditions.push(`payment_date >= $${params.length + 1}::date`);
      params.push(from);
    }
    if (to) {
      conditions.push(`payment_date <= $${params.length + 1}::date`);
      params.push(to);
    }
    if (conditions.length) sql += ' WHERE ' + conditions.join(' AND ');
    sql += ` ORDER BY payment_date DESC, created_at DESC LIMIT $${params.length + 1}`;
    params.push(parseInt(lim || '50', 10));

    const { rows } = await query(sql, params);
    return rows;
  });

  // Create payment (with employee auto-lookup + program linking)
  app.post('/', async (req, reply) => {
    const body = req.body as {
      employee_id: string; amount: number;
      method?: string; payment_number?: string; remarks?: string;
      category?: string; program_id?: number;
    };

    if (!body.employee_id || !body.amount) {
      return reply.code(400).send({ error: 'employee_id and amount required' });
    }

    // Lookup employee name
    const { rows: empRows } = await query(
      'SELECT name, mobile FROM ops_employees WHERE employee_id = $1',
      [body.employee_id]
    );

    let empName = '';
    let empMobile = body.employee_id;

    if (empRows.length > 0) {
      empName = empRows[0].name;
      empMobile = empRows[0].mobile;
    } else {
      const { rows: suggestions } = await query(
        `SELECT employee_id, name, mobile, similarity(employee_id, $1) AS score
         FROM ops_employees
         WHERE similarity(employee_id, $1) > 0.3
         ORDER BY score DESC LIMIT 3`,
        [body.employee_id]
      );
      if (suggestions.length > 0) {
        return reply.code(404).send({
          error: 'Employee not found',
          suggestions: suggestions.map(s => ({
            employee_id: s.employee_id,
            name: s.name,
            mobile: s.mobile,
          })),
        });
      }
      return reply.code(404).send({ error: 'Employee not found, no similar matches' });
    }

    // Auto-link to running program if not specified
    let programId = body.program_id || null;
    if (!programId) {
      const { rows: progs } = await query(
        `SELECT id FROM ops_programs WHERE escort_mobile = $1 AND status = 'running'
         ORDER BY start_date DESC LIMIT 1`,
        [body.employee_id]
      );
      if (progs.length > 0) programId = progs[0].id;
    }

    const category = body.category || 'general';

    const paymentDate = (req.body as any).payment_date || null;

    const { rows } = await query(
      `INSERT INTO ops_payments (employee_id, name, payment_number, method, amount, status, remarks, program_id, category, payment_date)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, COALESCE($10::date, CURRENT_DATE)) RETURNING *`,
      [body.employee_id, empName, body.payment_number || null,
       body.method || null, body.amount, 'running', body.remarks || null,
       programId, category, paymentDate]
    );

    const payment = rows[0];
    const template = paymentTemplate({
      employeeId: payment.employee_id,
      name: payment.name,
      mobile: empMobile,
      method: payment.method,
      amount: payment.amount,
      status: payment.status,
      category: payment.category,
      programId: payment.program_id,
    });

    return reply.code(201).send({ ...payment, template });
  });

  // Complete payment
  app.post<{ Params: { id: string } }>('/:id/complete', async (req, reply) => {
    const { remarks } = (req.body || {}) as { remarks?: string };
    const { rows } = await query(
      `UPDATE ops_payments
       SET status = 'completed', remarks = COALESCE($2, remarks)
       WHERE id = $1 RETURNING *`,
      [req.params.id, remarks]
    );
    if (rows.length === 0) return reply.code(404).send({ error: 'Payment not found' });
    return rows[0];
  });

  // Summary stats
  app.get('/summary', async () => {
    const { rows } = await query(`
      SELECT
        COUNT(*) FILTER (WHERE status = 'running') AS running_count,
        COALESCE(SUM(amount) FILTER (WHERE status = 'running'), 0) AS running_total,
        COUNT(*) FILTER (WHERE status = 'completed') AS completed_count,
        COALESCE(SUM(amount) FILTER (WHERE status = 'completed'), 0) AS completed_total,
        COUNT(*) AS total_count,
        COALESCE(SUM(amount), 0) AS overall_total
      FROM ops_payments
    `);
    return rows[0];
  });

  // ── Employee Payment History (date-wise with totals) ──
  app.get<{ Params: { employeeId: string } }>('/employee/:employeeId', async (req) => {
    const { employeeId } = req.params;
    const { from, to, status } = req.query as { from?: string; to?: string; status?: string };

    const conditions = ['p.employee_id = $1'];
    const params: unknown[] = [employeeId];

    if (from) {
      conditions.push(`p.payment_date >= $${params.length + 1}::date`);
      params.push(from);
    }
    if (to) {
      conditions.push(`p.payment_date <= $${params.length + 1}::date`);
      params.push(to);
    }
    if (status) {
      conditions.push(`p.status = $${params.length + 1}`);
      params.push(status);
    }

    const where = conditions.join(' AND ');

    // Get totals
    const { rows: totals } = await query(
      `SELECT
         COUNT(*) AS total_transactions,
         COALESCE(SUM(p.amount), 0) AS grand_total,
         COALESCE(SUM(p.amount) FILTER (WHERE p.category = 'food'), 0) AS food_total,
         COALESCE(SUM(p.amount) FILTER (WHERE p.category = 'transport'), 0) AS transport_total,
         COALESCE(SUM(p.amount) FILTER (WHERE p.category = 'general'), 0) AS general_total,
         COALESCE(SUM(p.amount) FILTER (WHERE p.category = 'salary'), 0) AS salary_total,
         COALESCE(SUM(p.amount) FILTER (WHERE p.category = 'advance'), 0) AS advance_total,
         MIN(p.payment_date) AS earliest_date,
         MAX(p.payment_date) AS latest_date
       FROM ops_payments p WHERE ${where}`,
      params
    );

    // Get employee info
    const { rows: empRows } = await query(
      'SELECT name, mobile, role FROM ops_employees WHERE employee_id = $1',
      [employeeId]
    );

    // Get date-wise transactions
    const { rows: transactions } = await query(
      `SELECT p.id, p.payment_date, p.amount, p.method, p.category,
              p.status, p.remarks, p.program_id, p.paid_by,
              prog.mother_vessel
       FROM ops_payments p
       LEFT JOIN ops_programs prog ON prog.id = p.program_id
       WHERE ${where}
       ORDER BY p.payment_date DESC, p.created_at DESC`,
      params
    );

    return {
      employee: {
        employee_id: employeeId,
        name: empRows[0]?.name || null,
        mobile: empRows[0]?.mobile || null,
        role: empRows[0]?.role || null,
      },
      summary: totals[0],
      transactions,
    };
  });
}
