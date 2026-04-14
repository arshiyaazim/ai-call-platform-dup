import Fastify from 'fastify';
import cors from '@fastify/cors';
import { pool, query } from './db';
import { opsRouter } from './routes';
import { runMigrations } from './migrate';

const PORT = parseInt(process.env.PORT || '9850', 10);
const HOST = process.env.HOST || '0.0.0.0';

async function main() {
  const app = Fastify({ logger: true });

  await app.register(cors, {
    origin: [
      'https://iamazim.com',
      'https://fazle.iamazim.com',
    ],
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
  });

  // Health check
  app.get('/health', async () => ({
    status: 'healthy',
    service: 'ops-core-service',
    timestamp: new Date().toISOString(),
  }));

  // Register routes
  app.register(opsRouter, { prefix: '/ops' });

  // Run DB migrations on startup
  try {
    await runMigrations();
    app.log.info('Database migrations completed');
  } catch (err) {
    app.log.error('Migration failed — service will start but DB may be incomplete');
    app.log.error(err);
  }

  // Seed owner as admin in ops_users (if SOCIAL_OWNER_PHONE is set)
  const ownerPhone = process.env.SOCIAL_OWNER_PHONE || process.env.OWNER_PHONE;
  if (ownerPhone) {
    try {
      await query(
        `INSERT INTO ops_users (name, whatsapp_number, role)
         VALUES ('Azim (Owner)', $1, 'admin')
         ON CONFLICT (whatsapp_number) DO UPDATE SET role = 'admin'`,
        [ownerPhone]
      );
      app.log.info(`Owner ${ownerPhone} seeded as admin in ops_users`);
    } catch (err) {
      app.log.warn(`Owner seed skipped: ${err}`);
    }
  }

  // Graceful shutdown
  const shutdown = async () => {
    app.log.info('Shutting down...');
    await app.close();
    await pool.end();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);

  await app.listen({ port: PORT, host: HOST });
  app.log.info(`ops-core-service listening on ${HOST}:${PORT}`);
}

main().catch((err) => {
  console.error('Fatal startup error:', err);
  process.exit(1);
});
