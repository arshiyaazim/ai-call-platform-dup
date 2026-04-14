/**
 * Alerts Service — smart detection for ops anomalies.
 *
 * Endpoints:
 *   GET /alerts/all — all active alerts
 *   GET /alerts/pending-duties?days=7 — programs running > X days
 *   GET /alerts/payment-issues — duplicate/missing/abnormal payments
 */

import { FastifyInstance } from 'fastify';
import { query } from '../db';

interface Alert {
  type: 'pending_duty' | 'duplicate_payment' | 'missing_payment' | 'abnormal_payment' | 'no_attendance';
  severity: 'high' | 'medium' | 'low';
  title: string;
  description: string;
  entity_id?: number | string;
  entity_type?: string;
  data?: Record<string, any>;
}

export async function alertRoutes(app: FastifyInstance) {

  // ── All alerts combined ──
  app.get('/all', async (req) => {
    const { days } = req.query as { days?: string };
    const maxDays = parseInt(days || '7');

    const [pendingDuties, paymentIssues] = await Promise.all([
      getPendingDutyAlerts(maxDays),
      getPaymentIssueAlerts(),
    ]);

    const alerts = [...pendingDuties, ...paymentIssues];
    alerts.sort((a, b) => {
      const sev = { high: 0, medium: 1, low: 2 };
      return sev[a.severity] - sev[b.severity];
    });

    return {
      alerts,
      count: alerts.length,
      summary: {
        high: alerts.filter(a => a.severity === 'high').length,
        medium: alerts.filter(a => a.severity === 'medium').length,
        low: alerts.filter(a => a.severity === 'low').length,
      },
    };
  });

  // ── Pending duties (long-running programs) ──
  app.get('/pending-duties', async (req) => {
    const { days } = req.query as { days?: string };
    const maxDays = parseInt(days || '7');
    const alerts = await getPendingDutyAlerts(maxDays);
    return { alerts, count: alerts.length };
  });

  // ── Payment issues ──
  app.get('/payment-issues', async (req) => {
    const alerts = await getPaymentIssueAlerts();
    return { alerts, count: alerts.length };
  });
}

// ── Pending duty detection ──
async function getPendingDutyAlerts(maxDays: number): Promise<Alert[]> {
  const { rows } = await query(`
    SELECT id, mother_vessel, lighter_vessel, escort_name, escort_mobile,
      start_date, destination,
      (CURRENT_DATE - start_date) AS days_running
    FROM ops_programs
    WHERE status = 'running'
      AND (CURRENT_DATE - start_date) > $1
    ORDER BY days_running DESC
  `, [maxDays]);

  return rows.map(r => ({
    type: 'pending_duty' as const,
    severity: parseInt(r.days_running) > maxDays * 2 ? 'high' as const : 'medium' as const,
    title: `Program running ${r.days_running} days`,
    description: `${r.mother_vessel} → ${r.destination || 'N/A'} | Escort: ${r.escort_name || 'N/A'} | Started: ${r.start_date}`,
    entity_id: r.id,
    entity_type: 'program',
    data: {
      program_id: r.id,
      mother_vessel: r.mother_vessel,
      lighter_vessel: r.lighter_vessel,
      escort_name: r.escort_name,
      escort_mobile: r.escort_mobile,
      start_date: r.start_date,
      days_running: parseInt(r.days_running),
    },
  }));
}

// ── Payment issue detection ──
async function getPaymentIssueAlerts(): Promise<Alert[]> {
  const alerts: Alert[] = [];

  // 1. Duplicate payments — same employee, same amount, same day
  const { rows: duplicates } = await query(`
    SELECT employee_id, name, amount, DATE(created_at) AS pay_date, COUNT(*) AS dup_count
    FROM ops_payments
    WHERE status = 'running'
    GROUP BY employee_id, name, amount, DATE(created_at)
    HAVING COUNT(*) > 1
    ORDER BY pay_date DESC
  `);

  for (const d of duplicates) {
    alerts.push({
      type: 'duplicate_payment',
      severity: 'high',
      title: `Duplicate: ${d.name} ৳${d.amount} x${d.dup_count}`,
      description: `${d.name} (${d.employee_id}) has ${d.dup_count} payments of ৳${d.amount} on ${d.pay_date}`,
      entity_id: d.employee_id,
      entity_type: 'payment',
      data: { employee_id: d.employee_id, amount: d.amount, date: d.pay_date, count: parseInt(d.dup_count) },
    });
  }

  // 2. Missing payments — completed programs with zero payments
  const { rows: missing } = await query(`
    SELECT p.id, p.mother_vessel, p.escort_name, p.start_date, p.end_date
    FROM ops_programs p
    LEFT JOIN ops_payments pay ON pay.program_id = p.id
    WHERE p.status = 'completed'
    GROUP BY p.id
    HAVING COUNT(pay.id) = 0
    ORDER BY p.end_date DESC
    LIMIT 20
  `);

  for (const m of missing) {
    alerts.push({
      type: 'missing_payment',
      severity: 'medium',
      title: `No payments: ${m.mother_vessel}`,
      description: `Program #${m.id} (${m.mother_vessel}) completed with no payments. Escort: ${m.escort_name || 'N/A'}`,
      entity_id: m.id,
      entity_type: 'program',
      data: { program_id: m.id, mother_vessel: m.mother_vessel, start_date: m.start_date, end_date: m.end_date },
    });
  }

  // 3. Abnormal payments — amount > 2x the average for that employee
  const { rows: abnormal } = await query(`
    WITH emp_avg AS (
      SELECT employee_id, AVG(amount) AS avg_amount, STDDEV(amount) AS std_amount
      FROM ops_payments
      GROUP BY employee_id
      HAVING COUNT(*) > 2
    )
    SELECT p.id, p.employee_id, p.name, p.amount, p.created_at,
      ea.avg_amount, ea.std_amount
    FROM ops_payments p
    JOIN emp_avg ea ON ea.employee_id = p.employee_id
    WHERE p.amount > ea.avg_amount * 2
      AND p.status = 'running'
    ORDER BY p.created_at DESC
    LIMIT 20
  `);

  for (const a of abnormal) {
    alerts.push({
      type: 'abnormal_payment',
      severity: 'medium',
      title: `Abnormal: ${a.name} ৳${a.amount}`,
      description: `${a.name} payment ৳${a.amount} is >2x their average (৳${Math.round(a.avg_amount)})`,
      entity_id: a.id,
      entity_type: 'payment',
      data: { payment_id: a.id, employee_id: a.employee_id, amount: parseInt(a.amount), avg: Math.round(a.avg_amount) },
    });
  }

  return alerts;
}
