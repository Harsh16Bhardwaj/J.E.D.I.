ALTER TABLE "User" ADD COLUMN "sessionVersion" INTEGER NOT NULL DEFAULT 0;

CREATE TABLE "PasswordReset" (
  "userId" TEXT NOT NULL,
  "tokenHash" TEXT,
  "requestedAt" TIMESTAMPTZ(3) NOT NULL,
  "expiresAt" TIMESTAMPTZ(3) NOT NULL,
  CONSTRAINT "PasswordReset_pkey" PRIMARY KEY ("userId"),
  CONSTRAINT "PasswordReset_userId_fkey" FOREIGN KEY ("userId")
    REFERENCES "User"("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE UNIQUE INDEX "PasswordReset_tokenHash_key" ON "PasswordReset"("tokenHash");
ALTER TABLE "PasswordReset" ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE "PasswordReset" FROM anon, authenticated;
