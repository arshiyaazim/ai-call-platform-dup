/**
 * Billing Service — mother-vessel-wise billing aggregation.
 *
 * Endpoints:
 *   GET /billing/vessel-summary?from=YYYY-MM-DD&to=YYYY-MM-DD
 *   GET /billing/vessel/:vessel — detailed breakdown for one vessel
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

export async function billingRoutes(app: FastifyInstance) {

  // ── Vessel-wise billing summary ──
  app.get('/vessel-summary', async (req) => {
    const { from, to } = req.query as { from?: string; to?: string };
    const conditions: string[] = [];
    const params: any[] = [];
    let idx = 1;

    if (from) { conditions.push(`p.start_date >= $${idx++}::date`); params.push(from); }
    if (to) { conditions.push(`COALESCE(p.end_date, p.start_date) <= $${idx++}::date`); params.push(to); }

    const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

    const { rows } = await query(`
      SELECT
        p.mother_vessel,
        COUNT(DISTINCT p.id) AS total_trips,
        COUNT(DISTINCT p.escort_mobile) AS total_escorts,
        SUM(COALESCE(p.food, 0)) AS total_food,
        SUM(COALESCE(p.transport, 0)) AS total_transport,
        SUM(COALESCE(p.total_cost, 0)) AS total_cost,
        MIN(p.start_date) AS first_trip,
        MAX(COALESCE(p.end_date, p.start_date)) AS last_trip,
        COUNT(CASE WHEN p.status = 'running' THEN 1 END) AS running_count,
        COUNT(CASE WHEN p.status = 'completed' THEN 1 END) AS completed_count
      FROM ops_programs p
      ${where}
      GROUP BY p.mother_vessel
      ORDER BY total_cost DESC
    `, params);

    return { vessels: rows, count: rows.length };
  });

  // ── Detailed breakdown for one vessel ──
  app.get('/vessel/:vessel', async (req) => {
    const { vessel } = req.params as { vessel: string };
    const { from, to } = req.query as { from?: string; to?: string };
    const conditions: string[] = ['p.mother_vessel ILIKE $1'];
    const params: any[] = [`%${vessel}%`];
    let idx = 2;

    if (from) { conditions.push(`p.start_date >= $${idx++}::date`); params.push(from); }
    if (to) { conditions.push(`COALESCE(p.end_date, p.start_date) <= $${idx++}::date`); params.push(to); }

    const where = conditions.join(' AND ');

    const { rows: programs } = await query(`
      SELECT p.*,
        (SELECT COALESCE(SUM(amount), 0) FROM ops_payments WHERE program_id = p.id) AS payment_total,
        (SELECT COUNT(*) FROM ops_payments WHERE program_id = p.id) AS payment_count
      FROM ops_programs p
      WHERE ${where}
      ORDER BY p.start_date DESC
    `, params);

    const { rows: payments } = await query(`
      SELECT pay.*
      FROM ops_payments pay
      JOIN ops_programs p ON pay.program_id = p.id
      WHERE ${where}
      ORDER BY pay.payment_date DESC, pay.created_at DESC
    `, params);

    return { vessel, programs, payments };
  });
}
