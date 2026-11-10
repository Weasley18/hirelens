"""Run only against an explicitly supplied test database, in an isolated schema."""
import os
import uuid

import pytest
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="Set TEST_DATABASE_URL for isolated PostgreSQL integration")
def test_ingestion_replaces_renamed_deleted_chunks_and_rolls_back(tmp_path, monkeypatch):
    from rag import ingest
    url = os.environ["TEST_DATABASE_URL"]
    schema = "test_ingest_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute("CREATE EXTENSION IF NOT EXISTS vector")
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            isolated = make_conninfo(url, options=f"-c search_path={schema},public")
            with psycopg.connect(isolated, autocommit=True) as conn:
                conn.execute('CREATE TABLE "KnowledgeChunk" (id text PRIMARY KEY, content text, source text, embedding vector(384))')
                monkeypatch.setenv("DATABASE_URL", isolated)
                monkeypatch.setattr(ingest, "KNOWLEDGE_DIR", tmp_path)
                monkeypatch.setattr(ingest, "embed_documents", lambda texts: [[0.1] * 384 for _ in texts])
                monkeypatch.setattr("sys.argv", ["ingest"])
                document = tmp_path / "kb.md"
                document.write_text("# Old title\n## Old heading\n" + "Python example. " * 20)
                ingest.main()
                document.write_text("# New title\n## New heading\n" + "Go example. " * 20)
                ingest.main()
                assert conn.execute('SELECT source FROM "KnowledgeChunk"').fetchall() == [("New title: New heading",)]
                monkeypatch.setattr(ingest, "embed_documents", lambda texts: [[0.1] for _ in texts])
                with pytest.raises(psycopg.Error):
                    ingest.main()
                assert conn.execute('SELECT count(*) FROM "KnowledgeChunk"').fetchone()[0] == 1
                document.unlink()
                ingest.main()
                assert conn.execute('SELECT count(*) FROM "KnowledgeChunk"').fetchone()[0] == 0
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
