import "server-only";

import { neonConfig } from "@neondatabase/serverless";
import { PrismaNeon } from "@prisma/adapter-neon";
import ws from "ws";

import { PrismaClient } from "@/generated/prisma/client";

const connectionString = process.env.DATABASE_URL;

if (!connectionString) {
  throw new Error("DATABASE_URL is required before database access.");
}

neonConfig.webSocketConstructor = ws;

const globalForPrisma = globalThis as unknown as {
  jediPrisma: PrismaClient | undefined;
};

const adapter = new PrismaNeon({ connectionString });

export const db =
  globalForPrisma.jediPrisma ??
  new PrismaClient({
    adapter,
    log: process.env.NODE_ENV === "development" ? ["warn", "error"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.jediPrisma = db;
}
