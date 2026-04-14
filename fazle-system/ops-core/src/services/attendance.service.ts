/**
 * Attendance Service — record and query daily attendance.
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

export async function attendanceRoutes(app: FastifyInstance) {

  // List attendance records (with client_name and shift filter)
  app.get('/', async (req) => {
    const { employee_id, date, location, client_name, shift, limit: lim } = req.query as {
      employee_id?: string; date?: string; location?: string;
      client_name?: string; shift?: string; limit?: string;
    };
    let sql = 'SELECT * FROM ops_attendance';
    const params: unknown[] = [];
    const conditions: string[] = [];

    if (employee_id) {
      conditions.push(`employee_id = $${params.length + 1}`);
      params.push(employee_id);
    }
    if (date) {
      conditions.push(`date = $${params.length + 1}`);
      params.push(date);
    }
    if (location) {
      conditions.push(`location ILIKE $${params.length + 1}`);
      params.push(`%${location}%`);
    }
    if (client_name) {
      conditions.push(`client_name ILIKE $${params.length + 1}`);
      params.push(`%${client_name}%`);
    }
    if (shift) {
      conditions.push(`shift = $${params.length + 1}`);
      params.push(shift);
    }
    if (conditions.length) sql += ' WHERE ' + conditions.join(' AND ');
    sql += ` ORDER BY date DESC, created_at DESC LIMIT $${params.length + 1}`;
    params.push(parseInt(lim || '50', 10));

    const { rows } = await query(sql, params);
    return rows;
  });

  // Record attendance (with shift support)
  app.post('/', async (req, reply) => {
    const { employee_id, name, location, client_name, date, shift } = req.body as {
      employee_id: string; name?: string; location?: string;
      client_name?: string; date?: string; shift?: string;
    };

    if (!employee_id) {
      return reply.code(400).send({ error: 'employee_id required' });
    }

    let empName = name || '';
    if (!empName) {
      const { rows: emp } = await query(
        'SELECT name FROM ops_employees WHERE employee_id = $1',
        [employee_id]
      );
      if (emp.length > 0) empName = emp[0].name;
    }

    const { rows } = await query(
      `INSERT INTO ops_attendance (employee_id, name, location, client_name, date, shift, created_at)
       VALUES ($1, $2, $3, $4, COALESCE($5::date, CURRENT_DATE), $6, NOW()) RETURNING *`,
      [employee_id, empName, location || null, client_name || null, date || null, shift || null]
    );
    return reply.code(201).send(rows[0]);
  });

  // Daily summary
  app.get('/summary', async (req) => {
    const { date } = req.query as { date?: string };
    const targetDate = date || new Date().toISOString().slice(0, 10);
    const { rows } = await query(
      `SELECT COUNT(*) AS total,
              COUNT(DISTINCT employee_id) AS unique_employees,
              COUNT(DISTINCT location) AS locations,
              COUNT(*) FILTER (WHERE shift = 'D') AS day_shift,
              COUNT(*) FILTER (WHERE shift = 'N') AS night_shift
       FROM ops_attendance WHERE date = $1`,
      [targetDate]
    );
    return { date: targetDate, ...rows[0] };
  });

  // Daily report grouped by client/location
  app.get('/report', async (req) => {
    const { date } = req.query as { date?: string };
    const targetDate = date || new Date().toISOString().slice(0, 10);
    const { rows } = await query(
      `SELECT client_name, location, shift,
              COUNT(*) AS employee_count,
              array_agg(json_build_object('name', name, 'employee_id', employee_id)) AS employees
       FROM ops_attendance
       WHERE date = $1
       GROUP BY client_name, location, shift
       ORDER BY client_name, location`,
      [targetDate]
    );
    return { date: targetDate, groups: rows };
  });
}
