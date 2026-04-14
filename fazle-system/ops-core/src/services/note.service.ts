/**
 * Note Service — CRUD for ops_notes (linked to employee/program/payment).
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

export async function noteRoutes(app: FastifyInstance) {

  // List notes for an entity
  app.get('/', async (req) => {
    const { entity_type, entity_id } = req.query as {
      entity_type: string; entity_id: string;
    };
    if (!entity_type || !entity_id) {
      return { error: 'entity_type and entity_id required' };
    }
    const { rows } = await query(
      'SELECT * FROM ops_notes WHERE entity_type = $1 AND entity_id = $2 ORDER BY created_at DESC',
      [entity_type, parseInt(entity_id, 10)]
    );
    return rows;
  });

  // Add note
  app.post('/', async (req, reply) => {
    const { entity_type, entity_id, note } = req.body as {
      entity_type: string; entity_id: number; note: string;
    };
    if (!entity_type || !entity_id || !note) {
      return reply.code(400).send({ error: 'entity_type, entity_id, note required' });
    }
    const allowed = ['employee', 'program', 'payment'];
    if (!allowed.includes(entity_type)) {
      return reply.code(400).send({ error: `entity_type must be one of: ${allowed.join(', ')}` });
    }
    const { rows } = await query(
      `INSERT INTO ops_notes (entity_type, entity_id, note, created_at)
       VALUES ($1, $2, $3, NOW()) RETURNING *`,
      [entity_type, entity_id, note]
    );
    return reply.code(201).send(rows[0]);
  });
}
