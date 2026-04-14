/**
 * Program Service — CRUD + history snapshots for ops_programs.
 */

import { FastifyInstance } from 'fastify';
import { query, transaction } from '../db';

export async function programRoutes(app: FastifyInstance) {

  // List programs (with optional status filter)
  app.get('/', async (req) => {
    const { status, vessel, limit: lim } = req.query as {
      status?: string; vessel?: string; limit?: string;
    };
    let sql = 'SELECT * FROM ops_programs';
    const params: unknown[] = [];
    const conditions: string[] = [];

    if (status) {
      conditions.push(`status = $${params.length + 1}`);
      params.push(status);
    }
    if (vessel) {
      conditions.push(`mother_vessel ILIKE $${params.length + 1}`);
      params.push(`%${vessel}%`);
    }
    if (conditions.length) sql += ' WHERE ' + conditions.join(' AND ');
    sql += ` ORDER BY created_at DESC LIMIT $${params.length + 1}`;
    params.push(parseInt(lim || '50', 10));

    const { rows } = await query(sql, params);
    return rows;
  });

  // Get by ID (+ history)
  app.get<{ Params: { id: string } }>('/:id', async (req, reply) => {
    const { rows } = await query('SELECT * FROM ops_programs WHERE id = $1', [req.params.id]);
    if (rows.length === 0) return reply.code(404).send({ error: 'Program not found' });

    const histRes = await query(
      'SELECT * FROM ops_program_history WHERE program_id = $1 ORDER BY created_at DESC',
      [req.params.id]
    );
    return { ...rows[0], history: histRes.rows };
  });

  // Create program + initial history snapshot
  app.post('/', async (req, reply) => {
    const body = req.body as Record<string, unknown>;
    const {
      mother_vessel, lighter_vessel, master_mobile, destination,
      escort_name, escort_mobile, start_date, shift, status: st
    } = body;

    if (!mother_vessel) {
      return reply.code(400).send({ error: 'mother_vessel is required' });
    }

    const result = await transaction(async (client) => {
      const { rows } = await client.query(
        `INSERT INTO ops_programs
           (mother_vessel, lighter_vessel, master_mobile, destination,
            escort_name, escort_mobile, start_date, shift, status)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
         RETURNING *`,
        [mother_vessel, lighter_vessel || null, master_mobile || null,
         destination || null, escort_name || null, escort_mobile || null,
         start_date || null, shift || null, st || 'running']
      );
      const program = rows[0];

      // Save initial snapshot
      await client.query(
        `INSERT INTO ops_program_history (program_id, snapshot, created_at)
         VALUES ($1, $2, NOW())`,
        [program.id, JSON.stringify(program)]
      );
      return program;
    });

    return reply.code(201).send(result);
  });

  // Update program (NEVER overwrite — save snapshot first)
  app.put<{ Params: { id: string } }>('/:id', async (req, reply) => {
    const body = req.body as Record<string, unknown>;
    const id = parseInt(req.params.id, 10);

    const result = await transaction(async (client) => {
      // Get current state for snapshot
      const { rows: current } = await client.query(
        'SELECT * FROM ops_programs WHERE id = $1', [id]
      );
      if (current.length === 0) throw new Error('NOT_FOUND');

      // Save snapshot BEFORE update
      await client.query(
        `INSERT INTO ops_program_history (program_id, snapshot, created_at)
         VALUES ($1, $2, NOW())`,
        [id, JSON.stringify(current[0])]
      );

      // Apply update
      const fields = [
        'mother_vessel', 'lighter_vessel', 'master_mobile', 'destination',
        'escort_name', 'escort_mobile', 'start_date', 'shift', 'status'
      ];
      const sets: string[] = [];
      const params: unknown[] = [];
      for (const f of fields) {
        if (body[f] !== undefined) {
          params.push(body[f]);
          sets.push(`${f} = $${params.length}`);
        }
      }
      if (sets.length === 0) return current[0];

      params.push(id);
      const { rows } = await client.query(
        `UPDATE ops_programs SET ${sets.join(', ')} WHERE id = $${params.length} RETURNING *`,
        params
      );
      return rows[0];
    });

    if (!result) return reply.code(404).send({ error: 'Program not found' });
    return result;
  });

  // Complete program (+ complete linked payments, calculate totals)
  app.post<{ Params: { id: string } }>('/:id/complete', async (req, reply) => {
    const id = parseInt(req.params.id, 10);
    const { changed_by } = (req.body as any) || {};
    const result = await transaction(async (client) => {
      const { rows: current } = await client.query(
        'SELECT * FROM ops_programs WHERE id = $1', [id]
      );
      if (current.length === 0) throw new Error('NOT_FOUND');

      // Snapshot
      await client.query(
        `INSERT INTO ops_program_history (program_id, snapshot, changed_by, created_at) VALUES ($1, $2, $3, NOW())`,
        [id, JSON.stringify(current[0]), changed_by || 'api']
      );

      // Calculate payment totals
      const { rows: sums } = await client.query(
        `SELECT
           COALESCE(SUM(CASE WHEN category = 'food' THEN amount ELSE 0 END), 0) as food_total,
           COALESCE(SUM(CASE WHEN category = 'transport' THEN amount ELSE 0 END), 0) as transport_total,
           COALESCE(SUM(amount), 0) as grand_total
         FROM ops_payments WHERE program_id = $1`,
        [id]
      );
      const s = sums[0];

      // Complete program
      const { rows } = await client.query(
        `UPDATE ops_programs
         SET status = 'completed', end_date = CURRENT_DATE,
             food = $1, transport = $2, total_cost = $3
         WHERE id = $4 RETURNING *`,
        [s.food_total, s.transport_total, s.grand_total, id]
      );

      // Complete linked payments
      await client.query(
        `UPDATE ops_payments SET status = 'completed' WHERE program_id = $1 AND status = 'running'`,
        [id]
      );

      return rows[0];
    });
    return result;
  });

  // Get history for a program
  app.get<{ Params: { id: string } }>('/:id/history', async (req) => {
    const { rows } = await query(
      'SELECT * FROM ops_program_history WHERE program_id = $1 ORDER BY created_at DESC',
      [req.params.id]
    );
    return rows;
  });
}
