# Money Making Platform

A modular-monolith starter for a legitimate online monetization platform. The initial foundation is a Next.js application backed by PostgreSQL, with Prisma as the persistence layer.

## Architecture

```text
Browser
  -> Next.js App Router (pages, layouts, route handlers)
      -> server-only application/data modules
          -> Prisma Client
              -> PostgreSQL
```

The app is organized by capability inside `src\app` and `src\server`, rather than split into separately deployed services. This keeps the first version straightforward to develop and deploy while leaving room to extract services if growth requires it.

## Stack

- Next.js App Router and React
- TypeScript with strict checking
- PostgreSQL
- Prisma ORM and migrations
- ESLint

## Project layout

- `src\app`: routes, shared layout, styles, and the health-check endpoint
- `src\server\db.ts`: server-only Prisma Client singleton
- `prisma\schema.prisma`: revenue stream and revenue entry data model
- `docker-compose.yml`: local PostgreSQL service
- `.env.example`: required local environment variable template

## Getting started

Requirements: Node.js 22 LTS, npm 10 or later, and Docker (or a PostgreSQL 16 instance).

On Windows, install the Node.js 22 LTS release using the official Node.js installer, then open a new terminal and verify `node --version` and `npm --version`. The repository's `.nvmrc` also declares the Node version for compatible version managers.

1. Copy `.env.example` to `.env` and keep the local database URL.
2. Start PostgreSQL with `docker compose up -d`.
3. Install dependencies with `npm install`.
4. Generate the Prisma Client and apply the initial migration:

   ```powershell
   npm run db:generate
   npm run db:migrate -- --name init
   ```

5. Start the development server with `npm run dev`.
6. Visit `http://localhost:3000`; `http://localhost:3000/api/health` checks database connectivity.

## Data model

`RevenueStream` represents a monetization channel. `RevenueEntry` records an amount, currency, occurrence time, and optional external reference for a stream. Monetary values use PostgreSQL `Decimal`, not floating point. The starter intentionally does not assume an authentication provider or payment processor; those integrations should be selected before handling real users or funds.

## Next steps

1. Choose and implement authentication and authorization before exposing user-specific data.
2. Define the product's revenue sources and ingestion workflows; add idempotency and audit history before importing real financial events.
3. Add focused tests, CI checks, observability, and deployment configuration for the chosen hosting environment.
