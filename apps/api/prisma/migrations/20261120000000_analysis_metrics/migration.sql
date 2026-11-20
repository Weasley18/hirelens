-- Anonymous per-analysis metrics. Existing rows were all completed analyses.
ALTER TABLE "Analysis"
  ADD COLUMN "status" TEXT NOT NULL DEFAULT 'complete',
  ADD COLUMN "durationMs" INTEGER,
  ADD COLUMN "queueWaitMs" INTEGER,
  ADD COLUMN "backend" TEXT,
  ADD COLUMN "model" TEXT,
  ADD COLUMN "attempts" INTEGER,
  ADD COLUMN "inputTokens" INTEGER,
  ADD COLUMN "outputTokens" INTEGER,
  ADD COLUMN "costUsd" DOUBLE PRECISION,
  ADD COLUMN "citationsChecked" INTEGER,
  ADD COLUMN "citationsRemoved" INTEGER;
