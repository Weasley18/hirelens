-- Irreversibly remove legacy candidate data; retain anonymous completion counts only.
ALTER TABLE "Analysis" DROP COLUMN "resumeText", DROP COLUMN "jdText",
  DROP COLUMN "fitScore", DROP COLUMN "gaps", DROP COLUMN "questions";
CREATE INDEX "Analysis_createdAt_idx" ON "Analysis"("createdAt");
