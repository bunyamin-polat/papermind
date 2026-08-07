-- Runs once, when the pgdata volume is first created.
-- The pgvector binary ships in the image, but the extension still has to be
-- enabled per database before `vector` exists as a column type.
CREATE EXTENSION IF NOT EXISTS vector;
