/**
 * Employee Service — CRUD operations for ops_employees table.
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

export async function employeeRoutes(app: FastifyInstance) {

  // List employees
  app.get('/', async (req, reply) => {
    const { role, q } = req.query as { role?: string; q?: string };
    let sql = 'SELECT * FROM ops_employees';
    const params: unknown[] = [];
    const conditions: string[] = [];

    if (role) {
      conditions.push(`role = $${params.length + 1}`);
      params.push(role);
    }
    if (q) {
      conditions.push(`(name ILIKE $${params.length + 1} OR employee_id = $${params.length + 2})`);
      params.push(`%${q}%`, q);
    }
    if (conditions.length) sql += ' WHERE ' + conditions.join(' AND ');
    sql += ' ORDER BY created_at DESC LIMIT 100';

    const { rows } = await query(sql, params);
    return rows;
  });

  // Get by ID
  app.get<{ Params: { id: string } }>('/:id', async (req, reply) => {
    const { rows } = await query(
      'SELECT * FROM ops_employees WHERE id = $1 OR employee_id = $2',
      [req.params.id, req.params.id]
    );
    if (rows.length === 0) return reply.code(404).send({ error: 'Employee not found' });
    return rows[0];
  });

  // Create
  app.post('/', async (req, reply) => {
    const { employee_id, name, mobile, role } = req.body as {
      employee_id: string; name: string; mobile: string; role?: string;
    };
    if (!employee_id || !name || !mobile) {
      return reply.code(400).send({ error: 'employee_id, name, mobile required' });
    }
    const { rows } = await query(
      `INSERT INTO ops_employees (employee_id, name, mobile, role)
       VALUES ($1, $2, $3, $4) RETURNING *`,
      [employee_id, name, mobile, role || 'escort']
    );
    return reply.code(201).send(rows[0]);
  });

  // Update
  app.put<{ Params: { id: string } }>('/:id', async (req, reply) => {
    const { name, mobile, role } = req.body as {
      name?: string; mobile?: string; role?: string;
    };
    const { rows } = await query(
      `UPDATE ops_employees
       SET name = COALESCE($2, name),
           mobile = COALESCE($3, mobile),
           role = COALESCE($4, role)
       WHERE id = $1 OR employee_id = $1
       RETURNING *`,
      [req.params.id, name, mobile, role]
    );
    if (rows.length === 0) return reply.code(404).send({ error: 'Employee not found' });
    return rows[0];
  });

  // Find similar names (for suggestions)
  app.get('/suggest/:name', async (req, reply) => {
    const { name } = req.params as { name: string };
    const { rows } = await query(
      `SELECT id, employee_id, name, mobile, role,
              similarity(name, $1) AS score
       FROM ops_employees
       WHERE similarity(name, $1) > 0.2
       ORDER BY score DESC
       LIMIT 5`,
      [name]
    );
    return rows;
  });
}
