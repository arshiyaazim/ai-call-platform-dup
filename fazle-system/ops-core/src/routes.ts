import { FastifyInstance } from 'fastify';
import { employeeRoutes } from './services/employee.service';
import { programRoutes } from './services/program.service';
import { paymentRoutes } from './services/payment.service';
import { searchRoutes } from './services/search.service';
import { noteRoutes } from './services/note.service';
import { attendanceRoutes } from './services/attendance.service';
import { webhookRoutes } from './services/webhook.service';
import { userRoutes } from './services/user.service';
import { billingRoutes } from './services/billing.service';
import { salaryRoutes } from './services/salary.service';
import { alertRoutes } from './services/alerts.service';
import { exportRoutes } from './services/export.service';
import { query } from './db';

export async function opsRouter(app: FastifyInstance) {
  app.register(employeeRoutes, { prefix: '/employees' });
  app.register(programRoutes, { prefix: '/programs' });
  app.register(paymentRoutes, { prefix: '/payments' });
  app.register(searchRoutes, { prefix: '/search' });
  app.register(noteRoutes, { prefix: '/notes' });
  app.register(attendanceRoutes, { prefix: '/attendance' });
  app.register(webhookRoutes, { prefix: '/whatsapp' });
  app.register(userRoutes, { prefix: '/users' });

  // ── Business Intelligence routes ──
  app.register(billingRoutes, { prefix: '/billing' });
  app.register(salaryRoutes, { prefix: '/salary' });
  app.register(alertRoutes, { prefix: '/alerts' });
  app.register(exportRoutes, { prefix: '/export' });

  // Enhanced dashboard summary endpoint
  app.get('/dashboard/summary', async () => {
    const [progR, progC, payR, payC, empCount, attToday, completedToday, pendingDuties, topVessels, todayPayments, alertCount] = await Promise.all([
      query(`SELECT COUNT(*) AS c FROM ops_programs WHERE status = 'running'`),
      query(`SELECT COUNT(*) AS c FROM ops_programs WHERE status = 'completed'`),
      query(`SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS c FROM ops_payments WHERE status = 'running'`),
      query(`SELECT COALESCE(SUM(amount),0) AS total, COUNT(*) AS c FROM ops_payments WHERE status = 'completed'`),
      query(`SELECT COUNT(*) AS c FROM ops_employees`),
      query(`SELECT COUNT(DISTINCT employee_id) AS c FROM ops_attendance WHERE date = CURRENT_DATE`),
      // BI additions
      query(`SELECT COUNT(*) AS c FROM ops_programs WHERE status = 'completed' AND end_date = CURRENT_DATE`),
      query(`SELECT COUNT(*) AS c FROM ops_programs WHERE status = 'running' AND (CURRENT_DATE - start_date) > 7`),
      query(`
        SELECT mother_vessel, COUNT(*) AS trip_count, SUM(COALESCE(total_cost, 0)) AS total_cost
        FROM ops_programs
        GROUP BY mother_vessel ORDER BY trip_count DESC LIMIT 5
      `),
      query(`SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS c FROM ops_payments WHERE DATE(created_at) = CURRENT_DATE`),
      query(`
        SELECT COUNT(*) AS c FROM (
          SELECT 1 FROM ops_programs WHERE status = 'running' AND (CURRENT_DATE - start_date) > 7
          UNION ALL
          SELECT 1 FROM (
            SELECT employee_id, amount, DATE(created_at) AS d
            FROM ops_payments WHERE status = 'running'
            GROUP BY employee_id, amount, DATE(created_at) HAVING COUNT(*) > 1
          ) dup
        ) alerts
      `),
    ]);
    return {
      running_programs: parseInt(progR.rows[0].c),
      completed_programs: parseInt(progC.rows[0].c),
      running_payments: payR.rows[0].total,
      completed_payments: payC.rows[0].total,
      total_employees: parseInt(empCount.rows[0].c),
      today_attendance: parseInt(attToday.rows[0].c),
      // BI additions
      completed_today: parseInt(completedToday.rows[0].c),
      pending_duties: parseInt(pendingDuties.rows[0].c),
      top_vessels: topVessels.rows,
      today_payments: { total: todayPayments.rows[0].total, count: parseInt(todayPayments.rows[0].c) },
      active_alerts: parseInt(alertCount.rows[0].c),
    };
  });
}
