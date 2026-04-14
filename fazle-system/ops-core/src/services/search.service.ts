/**
 * Search Service — unified search across employees, programs, payments, attendance.
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

interface SearchQuery {
  q?: string;           // free text
  id?: string;          // employee_id or entity id
  name?: string;        // name search
  vessel?: string;      // vessel search
  date?: string;        // YYYY-MM-DD
  location?: string;    // attendance location
  client?: string;      // client_name
  entity?: string;      // employee | program | payment | attendance | all
}

export async function searchRoutes(app: FastifyInstance) {

  app.get('/', async (req) => {
    const params = req.query as SearchQuery;
    const entity = params.entity || 'all';
    const results: Record<string, unknown[]> = {};

    // ── Employee search ──
    if (entity === 'all' || entity === 'employee') {
      const empConditions: string[] = [];
      const empParams: unknown[] = [];

      if (params.id) {
        empConditions.push(`employee_id = $${empParams.length + 1}`);
        empParams.push(params.id);
      }
      if (params.name) {
        empConditions.push(`(name ILIKE $${empParams.length + 1} OR similarity(name, $${empParams.length + 2}) > 0.3)`);
        empParams.push(`%${params.name}%`, params.name);
      }
      if (params.q) {
        empConditions.push(`(name ILIKE $${empParams.length + 1} OR employee_id = $${empParams.length + 2} OR similarity(name, $${empParams.length + 2}) > 0.25)`);
        empParams.push(`%${params.q}%`, params.q);
      }

      if (empConditions.length > 0) {
        const sortParam = params.q || params.name || '';
        empParams.push(sortParam);
        const { rows } = await query(
          `SELECT *, 'employee' AS _type,
             CASE WHEN employee_id = $${empParams.length} THEN 0
                  WHEN name ILIKE $${empParams.length} THEN 1
                  ELSE 2 END AS rank
           FROM ops_employees WHERE ${empConditions.join(' AND ')}
           ORDER BY rank, similarity(name, $${empParams.length}) DESC LIMIT 20`,
          empParams
        );
        results.employees = rows;
      }
    }

    // ── Program search ──
    if (entity === 'all' || entity === 'program') {
      const progConditions: string[] = [];
      const progParams: unknown[] = [];

      if (params.vessel) {
        progConditions.push(`(mother_vessel ILIKE $${progParams.length + 1} OR lighter_vessel ILIKE $${progParams.length + 1})`);
        progParams.push(`%${params.vessel}%`);
      }
      if (params.date) {
        progConditions.push(`start_date = $${progParams.length + 1}`);
        progParams.push(params.date);
      }
      if (params.name) {
        progConditions.push(`escort_name ILIKE $${progParams.length + 1}`);
        progParams.push(`%${params.name}%`);
      }
      if (params.q) {
        progConditions.push(`(mother_vessel ILIKE $${progParams.length + 1} OR lighter_vessel ILIKE $${progParams.length + 1} OR destination ILIKE $${progParams.length + 1} OR escort_name ILIKE $${progParams.length + 1} OR similarity(mother_vessel, $${progParams.length + 2}) > 0.25)`);
        progParams.push(`%${params.q}%`, params.q);
      }

      if (progConditions.length > 0) {
        const sortParam = params.q || params.vessel || '';
        progParams.push(sortParam);
        const { rows } = await query(
          `SELECT *, 'program' AS _type,
             CASE WHEN mother_vessel ILIKE $${progParams.length} THEN 0
                  WHEN lighter_vessel ILIKE $${progParams.length} THEN 1
                  ELSE 2 END AS rank
           FROM ops_programs WHERE ${progConditions.join(' AND ')}
           ORDER BY rank, start_date DESC LIMIT 20`,
          progParams
        );
        results.programs = rows;
      }
    }

    // ── Payment search ──
    if (entity === 'all' || entity === 'payment') {
      const payConditions: string[] = [];
      const payParams: unknown[] = [];

      if (params.id) {
        payConditions.push(`employee_id = $${payParams.length + 1}`);
        payParams.push(params.id);
      }
      if (params.name) {
        payConditions.push(`name ILIKE $${payParams.length + 1}`);
        payParams.push(`%${params.name}%`);
      }
      if (params.q) {
        payConditions.push(`(name ILIKE $${payParams.length + 1} OR employee_id = $${payParams.length + 2})`);
        payParams.push(`%${params.q}%`, params.q);
      }

      if (payConditions.length > 0) {
        const { rows } = await query(
          `SELECT *, 'payment' AS _type FROM ops_payments WHERE ${payConditions.join(' AND ')} ORDER BY payment_date DESC, created_at DESC LIMIT 20`,
          payParams
        );
        results.payments = rows;
      }
    }

    // ── Attendance search ──
    if (entity === 'all' || entity === 'attendance') {
      const attConditions: string[] = [];
      const attParams: unknown[] = [];

      if (params.id) {
        attConditions.push(`employee_id = $${attParams.length + 1}`);
        attParams.push(params.id);
      }
      if (params.location) {
        attConditions.push(`location ILIKE $${attParams.length + 1}`);
        attParams.push(`%${params.location}%`);
      }
      if (params.client) {
        attConditions.push(`client_name ILIKE $${attParams.length + 1}`);
        attParams.push(`%${params.client}%`);
      }
      if (params.date) {
        attConditions.push(`date = $${attParams.length + 1}`);
        attParams.push(params.date);
      }
      if (params.name) {
        attConditions.push(`name ILIKE $${attParams.length + 1}`);
        attParams.push(`%${params.name}%`);
      }
      if (params.q) {
        attConditions.push(`(name ILIKE $${attParams.length + 1} OR employee_id = $${attParams.length + 2} OR location ILIKE $${attParams.length + 1})`);
        attParams.push(`%${params.q}%`, params.q);
      }

      if (attConditions.length > 0) {
        const { rows } = await query(
          `SELECT *, 'attendance' AS _type FROM ops_attendance WHERE ${attConditions.join(' AND ')} ORDER BY date DESC LIMIT 20`,
          attParams
        );
        results.attendance = rows;
      }
    }

    return results;
  });

  // Typeahead suggestions endpoint
  app.get('/suggest', async (req) => {
    const { q } = req.query as { q: string };
    if (!q || q.length < 2) return { suggestions: [] };

    // Search employees by name similarity
    const { rows: empSuggestions } = await query(
      `SELECT employee_id AS id, name, 'employee' AS type, similarity(name, $1) AS score
       FROM ops_employees
       WHERE name ILIKE $2 OR similarity(name, $1) > 0.25
       ORDER BY score DESC LIMIT 5`,
      [q, `%${q}%`]
    );

    // Search vessels
    const { rows: vesselSuggestions } = await query(
      `SELECT DISTINCT mother_vessel AS name, 'vessel' AS type
       FROM ops_programs
       WHERE mother_vessel ILIKE $1
       LIMIT 5`,
      [`%${q}%`]
    );

    return {
      suggestions: [
        ...empSuggestions.map(e => ({ label: `${e.name} (${e.id})`, type: e.type, id: e.id })),
        ...vesselSuggestions.map(v => ({ label: v.name, type: v.type })),
      ]
    };
  });
}
