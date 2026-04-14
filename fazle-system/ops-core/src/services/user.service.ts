/**
 * User Service — CRUD for ops_users (role-based WhatsApp access control).
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

export async function userRoutes(app: FastifyInstance) {

  /** List all users */
  app.get('/', async () => {
    const { rows } = await query(
      `SELECT id, name, whatsapp_number, role, active, created_at
       FROM ops_users ORDER BY created_at DESC`
    );
    return rows;
  });

  /** Get user by whatsapp number */
  app.get('/by-number/:number', async (req) => {
    const { number } = req.params as { number: string };
    const { rows } = await query(
      `SELECT * FROM ops_users WHERE whatsapp_number = $1`, [number]
    );
    return rows[0] || null;
  });

  /** Create user */
  app.post('/', async (req, reply) => {
    const { name, whatsapp_number, role } = req.body as {
      name: string; whatsapp_number: string; role: string;
    };
    if (!name || !whatsapp_number) {
      return reply.code(400).send({ error: 'name and whatsapp_number required' });
    }
    const validRoles = ['admin', 'operator', 'viewer'];
    const userRole = validRoles.includes(role) ? role : 'operator';

    const { rows } = await query(
      `INSERT INTO ops_users (name, whatsapp_number, role)
       VALUES ($1, $2, $3)
       ON CONFLICT (whatsapp_number) DO UPDATE SET name = $1, role = $3
       RETURNING *`,
      [name, whatsapp_number, userRole]
    );
    return rows[0];
  });

  /** Update user role */
  app.put('/:id', async (req) => {
    const { id } = req.params as { id: string };
    const { name, role, active } = req.body as { name?: string; role?: string; active?: boolean };

    const { rows } = await query(
      `UPDATE ops_users
       SET name = COALESCE($1, name),
           role = COALESCE($2, role),
           active = COALESCE($3, active)
       WHERE id = $4 RETURNING *`,
      [name || null, role || null, active ?? null, id]
    );
    return rows[0] || null;
  });

  /** Delete user */
  app.delete('/:id', async (req) => {
    const { id } = req.params as { id: string };
    await query(`DELETE FROM ops_users WHERE id = $1`, [id]);
    return { deleted: true };
  });
}
