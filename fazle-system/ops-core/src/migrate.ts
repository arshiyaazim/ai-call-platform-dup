import * as fs from 'fs';
import * as path from 'path';
import { query } from './db';

export async function runMigrations() {
  // Create migrations tracking table
  await query(`
    CREATE TABLE IF NOT EXISTS ops_migrations (
      id SERIAL PRIMARY KEY,
      filename TEXT NOT NULL UNIQUE,
      applied_at TIMESTAMP DEFAULT NOW()
    )
  `);

  const migrationsDir = path.resolve(__dirname, '..', 'migrations');
  if (!fs.existsSync(migrationsDir)) {
    console.log('No migrations directory found, skipping');
    return;
  }

  const files = fs.readdirSync(migrationsDir)
    .filter(f => f.endsWith('.sql'))
    .sort();

  for (const file of files) {
    const { rows } = await query(
      'SELECT 1 FROM ops_migrations WHERE filename = $1',
      [file]
    );
    if (rows.length > 0) {
      console.log(`Migration ${file} already applied, skipping`);
      continue;
    }

    const sql = fs.readFileSync(path.join(migrationsDir, file), 'utf8');
    console.log(`Applying migration: ${file}`);
    await query(sql);
    await query('INSERT INTO ops_migrations (filename) VALUES ($1)', [file]);
    console.log(`Migration ${file} applied successfully`);
  }
}
