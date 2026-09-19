"""Initial PostgreSQL 17 + pgvector schema for releases and provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_postgresql_provenance"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = public, pg_catalog")
    # Extensions are shared database infrastructure.  The migration may use them,
    # but downgrade deliberately leaves them in place for other applications.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'budget_lifecycle') THEN
                CREATE ROLE budget_lifecycle NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOREPLICATION;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'budget_lifecycle_caller'
            ) THEN
                CREATE ROLE budget_lifecycle_caller NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOREPLICATION;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'budget_app') THEN
                CREATE ROLE budget_app NOLOGIN INHERIT NOSUPERUSER NOCREATEDB
                    NOCREATEROLE NOREPLICATION;
            END IF;
        END
        $$
        """
    )
    op.execute("GRANT budget_lifecycle_caller TO budget_app")

    op.execute(
        """
        CREATE TABLE source_documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            url text NOT NULL CHECK (
                url ~* '^https?://([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?[.])*'
                      '[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?([/?#][^[:space:]]*)?$'
            ),
            document_type varchar(80) NOT NULL CHECK (btrim(document_type) <> ''),
            legal_stage varchar(3) NOT NULL CHECK (legal_stage IN ('PLF', 'LFI')),
            fiscal_year smallint NOT NULL CHECK (fiscal_year IN (2025, 2026)),
            source_version varchar(120) NOT NULL CHECK (btrim(source_version) <> ''),
            collected_at timestamptz NOT NULL,
            sha256 varchar(64) NOT NULL CHECK (sha256 ~ '^[0-9a-fA-F]{64}$'),
            publication_date date,
            media_type varchar(160) NOT NULL CHECK (btrim(media_type) <> ''),
            storage_key text,
            storage_size_bytes bigint CHECK (storage_size_bytes IS NULL OR storage_size_bytes >= 0),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (url, source_version, sha256)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE releases (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            fiscal_year smallint NOT NULL CHECK (fiscal_year IN (2025, 2026)),
            legal_stage varchar(3) NOT NULL CHECK (legal_stage IN ('PLF', 'LFI')),
            version varchar(120) NOT NULL CHECK (btrim(version) <> ''),
            status varchar(12) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'validated', 'published', 'rejected')),
            source_snapshot_hash varchar(64) NOT NULL
                CHECK (source_snapshot_hash ~ '^[0-9a-fA-F]{64}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            validated_at timestamptz,
            released_at timestamptz,
            rejected_at timestamptz,
            UNIQUE (fiscal_year, legal_stage, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE source_fragments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_document_id uuid NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
            fragment_hash varchar(64) NOT NULL CHECK (fragment_hash ~ '^[0-9a-fA-F]{64}$'),
            locator text NOT NULL CHECK (btrim(locator) <> ''),
            content text NOT NULL CHECK (btrim(content) <> ''),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector('french'::regconfig, coalesce(content, ''::text))
            ) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (source_document_id, fragment_hash)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE release_source_documents (
            release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
            source_document_id uuid NOT NULL REFERENCES source_documents(id) ON DELETE RESTRICT,
            attached_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (release_id, source_document_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE budget_nodes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
            parent_id uuid,
            node_type varchar(10) NOT NULL CHECK (node_type IN ('mission', 'programme', 'action')),
            code text NOT NULL CHECK (btrim(code) <> ''),
            slug text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9-]*$'),
            name text NOT NULL CHECK (btrim(name) <> ''),
            description text,
            search_vector tsvector GENERATED ALWAYS AS (
                to_tsvector(
                    'french'::regconfig,
                    name || ' ' || code || ' ' || slug || ' ' || coalesce(description, '')
                )
            ) STORED,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (release_id, id),
            FOREIGN KEY (release_id, parent_id)
                REFERENCES budget_nodes(release_id, id)
                ON DELETE RESTRICT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE budget_amounts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            node_id uuid NOT NULL REFERENCES budget_nodes(id) ON DELETE RESTRICT,
            metric varchar(2) NOT NULL CHECK (metric IN ('AE', 'CP')),
            amount numeric NOT NULL,
            unit varchar(40) NOT NULL CHECK (btrim(unit) <> ''),
            aggregation varchar(40) NOT NULL CHECK (btrim(aggregation) <> ''),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (node_id, metric)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE amount_source_fragments (
            amount_id uuid NOT NULL REFERENCES budget_amounts(id) ON DELETE RESTRICT,
            source_fragment_id uuid NOT NULL REFERENCES source_fragments(id) ON DELETE RESTRICT,
            linked_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (amount_id, source_fragment_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE anomalies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
            node_id uuid,
            code varchar(120) NOT NULL CHECK (btrim(code) <> ''),
            severity varchar(8) NOT NULL CHECK (
                severity IN ('info', 'warning', 'error', 'critical')
            ),
            message text NOT NULL CHECK (btrim(message) <> ''),
            blocked boolean NOT NULL DEFAULT false,
            details jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CHECK (severity NOT IN ('error', 'critical') OR blocked),
            FOREIGN KEY (release_id, node_id)
                REFERENCES budget_nodes(release_id, id)
                ON DELETE RESTRICT
        )
        """
    )

    op.execute(
        """
        CREATE TABLE validations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
            validation_type varchar(120) NOT NULL CHECK (btrim(validation_type) <> ''),
            result varchar(12) NOT NULL CHECK (result IN ('passed', 'failed', 'warning')),
            blocking boolean NOT NULL DEFAULT true,
            validator varchar(160) NOT NULL CHECK (btrim(validator) <> ''),
            details jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        )
        """
    )

    op.execute(
        """
        CREATE TABLE ingestion_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            release_id uuid REFERENCES releases(id) ON DELETE RESTRICT,
            source_document_id uuid REFERENCES source_documents(id) ON DELETE RESTRICT,
            pipeline varchar(160) NOT NULL CHECK (btrim(pipeline) <> ''),
            status varchar(16) NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
            started_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz,
            row_count bigint CHECK (row_count IS NULL OR row_count >= 0),
            error_details jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )

    op.execute(
        """
        CREATE TABLE published_releases (
            fiscal_year smallint NOT NULL CHECK (fiscal_year IN (2025, 2026)),
            legal_stage varchar(3) NOT NULL CHECK (legal_stage IN ('PLF', 'LFI')),
            release_id uuid NOT NULL REFERENCES releases(id) ON DELETE RESTRICT,
            published_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (fiscal_year, legal_stage)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE fragment_embeddings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            source_fragment_id uuid NOT NULL REFERENCES source_fragments(id) ON DELETE RESTRICT,
            model varchar(160) NOT NULL CHECK (btrim(model) <> ''),
            embedding vector(1536) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (source_fragment_id, model)
        )
        """
    )

    op.execute(
        "CREATE INDEX source_fragments_search_idx ON source_fragments USING gin (search_vector)"
    )
    op.execute("CREATE INDEX budget_nodes_search_idx ON budget_nodes USING gin (search_vector)")
    op.execute(
        "CREATE INDEX budget_nodes_release_parent_idx ON budget_nodes (release_id, parent_id)"
    )
    op.execute("CREATE INDEX budget_amounts_node_idx ON budget_amounts (node_id)")
    op.execute("CREATE INDEX anomalies_release_blocked_idx ON anomalies (release_id, blocked)")
    op.execute(
        """
        CREATE UNIQUE INDEX budget_nodes_code_scope_idx ON budget_nodes (
            release_id, coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), code
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX budget_nodes_slug_scope_idx ON budget_nodes (
            release_id, coalesce(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), slug
        )
        """
    )
    op.execute(
        """
        CREATE INDEX fragment_embeddings_hnsw_idx
        ON fragment_embeddings USING hnsw (embedding vector_cosine_ops)
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_lock_release(p_release_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            ignored_status text;
        BEGIN
            IF p_release_id IS NULL THEN
                RETURN;
            END IF;
            SELECT status INTO ignored_status
            FROM public.releases
            WHERE id = p_release_id
            FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'release % does not exist', p_release_id;
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_lock_release_pair(
            p_old_release_id uuid,
            p_new_release_id uuid
        )
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF p_old_release_id IS NULL THEN
                PERFORM public.budget_lock_release(p_new_release_id);
            ELSIF p_new_release_id IS NULL THEN
                PERFORM public.budget_lock_release(p_old_release_id);
            ELSIF p_old_release_id = p_new_release_id THEN
                PERFORM public.budget_lock_release(p_old_release_id);
            ELSIF p_old_release_id < p_new_release_id THEN
                PERFORM public.budget_lock_release(p_old_release_id);
                PERFORM public.budget_lock_release(p_new_release_id);
            ELSE
                PERFORM public.budget_lock_release(p_new_release_id);
                PERFORM public.budget_lock_release(p_old_release_id);
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_lock_document_releases(p_document_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            release_row record;
        BEGIN
            FOR release_row IN
                SELECT DISTINCT release_id
                FROM (
                    SELECT rs.release_id
                    FROM public.release_source_documents rs
                    WHERE rs.source_document_id = p_document_id
                    UNION
                    SELECT bn.release_id
                    FROM public.source_fragments sf
                    JOIN public.amount_source_fragments asf
                        ON asf.source_fragment_id = sf.id
                    JOIN public.budget_amounts ba ON ba.id = asf.amount_id
                    JOIN public.budget_nodes bn ON bn.id = ba.node_id
                    WHERE sf.source_document_id = p_document_id
                ) owned
                ORDER BY release_id
            LOOP
                PERFORM public.budget_lock_release(release_row.release_id);
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_lock_fragment_releases(p_fragment_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            release_row record;
        BEGIN
            FOR release_row IN
                SELECT DISTINCT release_id
                FROM (
                    SELECT rs.release_id
                    FROM public.release_source_documents rs
                    JOIN public.source_fragments sf
                        ON sf.source_document_id = rs.source_document_id
                    WHERE sf.id = p_fragment_id
                    UNION
                    SELECT bn.release_id
                    FROM public.amount_source_fragments asf
                    JOIN public.budget_amounts ba ON ba.id = asf.amount_id
                    JOIN public.budget_nodes bn ON bn.id = ba.node_id
                    WHERE asf.source_fragment_id = p_fragment_id
                ) owned
                ORDER BY release_id
            LOOP
                PERFORM public.budget_lock_release(release_row.release_id);
            END LOOP;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_lock_amount_releases(p_amount_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            release_id uuid;
        BEGIN
            SELECT bn.release_id INTO release_id
            FROM public.budget_amounts ba
            JOIN public.budget_nodes bn ON bn.id = ba.node_id
            WHERE ba.id = p_amount_id;
            IF release_id IS NOT NULL THEN
                PERFORM public.budget_lock_release(release_id);
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_assert_lifecycle_caller()
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_roles
                WHERE rolname = session_user AND rolsuper
            ) THEN
                RETURN;
            END IF;
            IF NOT pg_has_role(session_user, 'budget_lifecycle_caller', 'member') THEN
                RAISE EXCEPTION 'caller is not allowed to use release lifecycle functions'
                    USING ERRCODE = '42501';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_assert_release_mutable(p_release_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF p_release_id IS NULL THEN
                RETURN;
            END IF;
            PERFORM public.budget_lock_release(p_release_id);
            IF EXISTS (
                SELECT 1 FROM public.releases
                WHERE id = p_release_id AND status = 'published'
            ) THEN
                RAISE EXCEPTION 'release % is immutable after publication', p_release_id
                    USING ERRCODE = '55000';
            END IF;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_enforce_release_status()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF TG_OP = 'INSERT' THEN
                IF NEW.status <> 'draft' THEN
                    RAISE EXCEPTION 'new releases must start in draft status';
                END IF;
                RETURN NEW;
            END IF;

            IF TG_OP = 'DELETE' THEN
                PERFORM public.budget_lock_release(OLD.id);
                IF OLD.status = 'published' THEN
                    RAISE EXCEPTION 'published releases are immutable'
                        USING ERRCODE = '55000';
                END IF;
                RETURN OLD;
            END IF;

            PERFORM public.budget_lock_release(OLD.id);
            IF NEW.id IS DISTINCT FROM OLD.id THEN
                RAISE EXCEPTION 'release identity is immutable' USING ERRCODE = '55000';
            END IF;
            IF OLD.status = 'published' THEN
                RAISE EXCEPTION 'published releases are immutable' USING ERRCODE = '55000';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status
                AND current_user <> 'budget_lifecycle' THEN
                RAISE EXCEPTION 'release status is managed by lifecycle functions'
                    USING ERRCODE = '42501';
            END IF;
            IF NEW.status IS DISTINCT FROM OLD.status AND NOT (
                (OLD.status = 'draft' AND NEW.status IN ('validated', 'rejected'))
                OR (OLD.status = 'validated' AND NEW.status IN ('published', 'rejected'))
            ) THEN
                RAISE EXCEPTION 'invalid release status transition: % -> %',
                    OLD.status, NEW.status;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER releases_status_transition
        BEFORE INSERT OR UPDATE ON releases
        FOR EACH ROW EXECUTE FUNCTION budget_enforce_release_status()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_protect_source_document()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            target_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                RETURN NEW;
            END IF;
            target_id := OLD.id;
            PERFORM public.budget_lock_document_releases(target_id);
            IF EXISTS (
                SELECT 1
                FROM public.release_source_documents rs
                JOIN public.releases r ON r.id = rs.release_id
                WHERE rs.source_document_id = target_id AND r.status = 'published'
            ) OR EXISTS (
                SELECT 1
                FROM public.source_fragments sf
                JOIN public.amount_source_fragments asf ON asf.source_fragment_id = sf.id
                JOIN public.budget_amounts ba ON ba.id = asf.amount_id
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                JOIN public.releases r ON r.id = bn.release_id
                WHERE sf.source_document_id = target_id AND r.status = 'published'
            ) THEN
                RAISE EXCEPTION 'source document % is immutable after publication', target_id
                    USING ERRCODE = '55000';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER source_documents_immutable
        BEFORE UPDATE OR DELETE ON source_documents
        FOR EACH ROW EXECUTE FUNCTION budget_protect_source_document()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_protect_source_fragment()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            target_id uuid;
        BEGIN
            IF TG_OP = 'INSERT' THEN
                target_id := NEW.source_document_id;
                PERFORM public.budget_lock_document_releases(target_id);
                IF EXISTS (
                    SELECT 1
                    FROM public.release_source_documents rs
                    JOIN public.releases r ON r.id = rs.release_id
                    WHERE rs.source_document_id = target_id AND r.status = 'published'
                ) THEN
                    RAISE EXCEPTION 'source document % is immutable after publication', target_id
                        USING ERRCODE = '55000';
                END IF;
                RETURN NEW;
            END IF;

            PERFORM public.budget_lock_fragment_releases(OLD.id);
            PERFORM public.budget_lock_document_releases(OLD.source_document_id);
            IF TG_OP = 'UPDATE' THEN
                PERFORM public.budget_lock_document_releases(NEW.source_document_id);
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.release_source_documents rs
                JOIN public.source_fragments sf ON sf.source_document_id = rs.source_document_id
                JOIN public.releases r ON r.id = rs.release_id
                WHERE sf.id = OLD.id AND r.status = 'published'
            ) OR EXISTS (
                SELECT 1
                FROM public.amount_source_fragments asf
                JOIN public.budget_amounts ba ON ba.id = asf.amount_id
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                JOIN public.releases r ON r.id = bn.release_id
                WHERE asf.source_fragment_id = OLD.id AND r.status = 'published'
            ) THEN
                RAISE EXCEPTION 'source fragment % is immutable after publication', OLD.id
                    USING ERRCODE = '55000';
            END IF;
            IF TG_OP = 'UPDATE' AND EXISTS (
                SELECT 1
                FROM public.release_source_documents rs
                JOIN public.releases r ON r.id = rs.release_id
                WHERE rs.source_document_id = NEW.source_document_id AND r.status = 'published'
            ) THEN
                RAISE EXCEPTION 'source document % is immutable after publication',
                    NEW.source_document_id
                    USING ERRCODE = '55000';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER source_fragments_immutable
        BEFORE INSERT OR UPDATE OR DELETE ON source_fragments
        FOR EACH ROW EXECUTE FUNCTION budget_protect_source_fragment()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_guard_fragment_embedding()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            fragment_id uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                fragment_id := OLD.source_fragment_id;
                PERFORM public.budget_lock_fragment_releases(fragment_id);
            ELSE
                fragment_id := NEW.source_fragment_id;
                PERFORM public.budget_lock_fragment_releases(fragment_id);
                IF TG_OP = 'UPDATE' THEN
                    PERFORM public.budget_lock_fragment_releases(OLD.source_fragment_id);
                END IF;
            END IF;
            IF TG_OP = 'UPDATE' AND EXISTS (
                SELECT 1
                FROM public.amount_source_fragments asf
                JOIN public.budget_amounts ba ON ba.id = asf.amount_id
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                JOIN public.releases r ON r.id = bn.release_id
                WHERE asf.source_fragment_id = OLD.source_fragment_id AND r.status = 'published'
            ) THEN
                RAISE EXCEPTION 'source fragment % embedding is immutable', OLD.source_fragment_id
                    USING ERRCODE = '55000';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.release_source_documents rs
                JOIN public.source_fragments sf ON sf.source_document_id = rs.source_document_id
                JOIN public.releases r ON r.id = rs.release_id
                WHERE sf.id = fragment_id AND r.status = 'published'
            ) OR EXISTS (
                SELECT 1
                FROM public.amount_source_fragments asf
                JOIN public.budget_amounts ba ON ba.id = asf.amount_id
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                JOIN public.releases r ON r.id = bn.release_id
                WHERE asf.source_fragment_id = fragment_id AND r.status = 'published'
            ) THEN
                RAISE EXCEPTION 'source fragment % embedding is immutable', fragment_id
                    USING ERRCODE = '55000';
            END IF;
            RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER fragment_embeddings_guard
        BEFORE INSERT OR UPDATE OR DELETE ON fragment_embeddings
        FOR EACH ROW EXECUTE FUNCTION budget_guard_fragment_embedding()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_enforce_release_source()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            release_year smallint;
            release_stage text;
            document_year smallint;
            document_stage text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM public.budget_assert_release_mutable(OLD.release_id);
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                PERFORM public.budget_lock_release_pair(OLD.release_id, NEW.release_id);
                IF NEW.release_id IS DISTINCT FROM OLD.release_id THEN
                    RAISE EXCEPTION 'release ownership is immutable'
                        USING ERRCODE = '55000';
                END IF;
                PERFORM public.budget_assert_release_mutable(OLD.release_id);
            ELSE
                PERFORM public.budget_assert_release_mutable(NEW.release_id);
            END IF;
            PERFORM public.budget_assert_release_mutable(NEW.release_id);
            SELECT fiscal_year, legal_stage INTO release_year, release_stage
            FROM public.releases WHERE id = NEW.release_id;
            SELECT fiscal_year, legal_stage INTO document_year, document_stage
            FROM public.source_documents WHERE id = NEW.source_document_id;
            IF release_year IS NULL OR document_year IS NULL THEN
                RAISE EXCEPTION 'release and source document must exist';
            END IF;
            IF release_year <> document_year OR release_stage <> document_stage THEN
                RAISE EXCEPTION 'source document legal stage and year must match its release';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER release_source_documents_guard
        BEFORE INSERT OR UPDATE OR DELETE ON release_source_documents
        FOR EACH ROW EXECUTE FUNCTION budget_enforce_release_source()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_enforce_node_hierarchy()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            parent_type text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM public.budget_assert_release_mutable(OLD.release_id);
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                PERFORM public.budget_lock_release_pair(OLD.release_id, NEW.release_id);
                IF NEW.id IS DISTINCT FROM OLD.id THEN
                    RAISE EXCEPTION 'budget node identity is immutable'
                        USING ERRCODE = '55000';
                END IF;
                IF NEW.release_id IS DISTINCT FROM OLD.release_id THEN
                    RAISE EXCEPTION 'budget node release ownership is immutable'
                        USING ERRCODE = '55000';
                END IF;
                PERFORM public.budget_assert_release_mutable(OLD.release_id);
            END IF;
            PERFORM public.budget_assert_release_mutable(NEW.release_id);

            IF NEW.node_type = 'mission' AND NEW.parent_id IS NOT NULL THEN
                RAISE EXCEPTION 'mission nodes cannot have a parent';
            ELSIF NEW.node_type IN ('programme', 'action') AND NEW.parent_id IS NULL THEN
                RAISE EXCEPTION '% nodes must have a parent', NEW.node_type;
            END IF;

            IF NEW.parent_id IS NOT NULL THEN
                SELECT node_type INTO parent_type
                FROM budget_nodes
                WHERE id = NEW.parent_id AND release_id = NEW.release_id;
                IF parent_type IS NULL THEN
                    RAISE EXCEPTION 'parent % does not exist in the same release', NEW.parent_id;
                END IF;
                IF (NEW.node_type = 'programme' AND parent_type <> 'mission')
                    OR (NEW.node_type = 'action' AND parent_type <> 'programme') THEN
                    RAISE EXCEPTION 'invalid parent type for % node', NEW.node_type;
                END IF;
            END IF;

            IF NEW.parent_id IS NOT NULL AND EXISTS (
                WITH RECURSIVE ancestors(id) AS (
                    SELECT parent_id
                    FROM budget_nodes
                    WHERE id = NEW.parent_id AND release_id = NEW.release_id
                    UNION
                    SELECT n.parent_id
                    FROM budget_nodes n
                    JOIN ancestors a ON n.id = a.id
                    WHERE n.release_id = NEW.release_id AND n.parent_id IS NOT NULL
                )
                SELECT 1 FROM ancestors WHERE id = NEW.id
            ) THEN
                RAISE EXCEPTION 'budget node hierarchy cannot contain cycles';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER budget_nodes_hierarchy_guard
        BEFORE INSERT OR UPDATE OR DELETE ON budget_nodes
        FOR EACH ROW EXECUTE FUNCTION budget_enforce_node_hierarchy()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_guard_node_amount()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            old_release_id uuid;
            new_release_id uuid;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                SELECT bn.release_id INTO old_release_id
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                WHERE ba.id = OLD.id;
                PERFORM public.budget_assert_release_mutable(old_release_id);
                RETURN OLD;
            END IF;

            SELECT bn.release_id INTO new_release_id
            FROM public.budget_nodes bn
            WHERE bn.id = NEW.node_id;
            IF new_release_id IS NULL THEN
                RAISE EXCEPTION 'budget amount must reference an existing node';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                SELECT bn.release_id INTO old_release_id
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                WHERE ba.id = OLD.id;
                PERFORM public.budget_lock_release_pair(old_release_id, new_release_id);
                IF new_release_id IS DISTINCT FROM old_release_id THEN
                    RAISE EXCEPTION 'budget amount release ownership is immutable'
                        USING ERRCODE = '55000';
                END IF;
                PERFORM public.budget_assert_release_mutable(old_release_id);
            END IF;
            PERFORM public.budget_assert_release_mutable(new_release_id);
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER budget_amounts_immutability_guard
        BEFORE INSERT OR UPDATE OR DELETE ON budget_amounts
        FOR EACH ROW EXECUTE FUNCTION budget_guard_node_amount()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_enforce_amount_provenance()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            old_release_id uuid;
            new_release_id uuid;
            amount_year smallint;
            amount_stage text;
            document_id uuid;
            document_year smallint;
            document_stage text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                SELECT bn.release_id INTO old_release_id
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                WHERE ba.id = OLD.amount_id;
                PERFORM public.budget_lock_amount_releases(OLD.amount_id);
                PERFORM public.budget_lock_fragment_releases(OLD.source_fragment_id);
                PERFORM public.budget_assert_release_mutable(old_release_id);
                RETURN OLD;
            END IF;

            SELECT bn.release_id, r.fiscal_year, r.legal_stage,
                   sf.source_document_id, sd.fiscal_year, sd.legal_stage
            INTO new_release_id, amount_year, amount_stage, document_id,
                 document_year, document_stage
            FROM public.budget_amounts ba
            JOIN public.budget_nodes bn ON bn.id = ba.node_id
            JOIN public.releases r ON r.id = bn.release_id
            JOIN public.source_fragments sf ON sf.id = NEW.source_fragment_id
            JOIN public.source_documents sd ON sd.id = sf.source_document_id
            WHERE ba.id = NEW.amount_id;
            IF new_release_id IS NULL THEN
                RAISE EXCEPTION 'amount provenance requires existing amount and fragment';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                SELECT bn.release_id INTO old_release_id
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                WHERE ba.id = OLD.amount_id;
                PERFORM public.budget_lock_release_pair(old_release_id, new_release_id);
                IF new_release_id IS DISTINCT FROM old_release_id THEN
                    RAISE EXCEPTION 'amount provenance release ownership is immutable'
                        USING ERRCODE = '55000';
                END IF;
                PERFORM public.budget_lock_amount_releases(OLD.amount_id);
                PERFORM public.budget_lock_fragment_releases(OLD.source_fragment_id);
                PERFORM public.budget_assert_release_mutable(old_release_id);
            END IF;
            PERFORM public.budget_lock_amount_releases(NEW.amount_id);
            PERFORM public.budget_lock_fragment_releases(NEW.source_fragment_id);
            PERFORM public.budget_assert_release_mutable(new_release_id);
            IF amount_year <> document_year OR amount_stage <> document_stage THEN
                RAISE EXCEPTION 'source document must match release year and legal stage';
            END IF;
            INSERT INTO public.release_source_documents (release_id, source_document_id)
            VALUES (new_release_id, document_id)
            ON CONFLICT ON CONSTRAINT release_source_documents_pkey DO NOTHING;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER amount_source_fragments_guard
        BEFORE INSERT OR UPDATE OR DELETE ON amount_source_fragments
        FOR EACH ROW EXECUTE FUNCTION budget_enforce_amount_provenance()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_guard_release_child()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                PERFORM public.budget_assert_release_mutable(OLD.release_id);
                RETURN OLD;
            END IF;
            IF TG_OP = 'UPDATE' THEN
                PERFORM public.budget_lock_release_pair(OLD.release_id, NEW.release_id);
                IF OLD.release_id IS NOT NULL
                    AND NEW.release_id IS DISTINCT FROM OLD.release_id THEN
                    RAISE EXCEPTION 'release ownership is immutable'
                        USING ERRCODE = '55000';
                END IF;
                PERFORM public.budget_assert_release_mutable(OLD.release_id);
            END IF;
            PERFORM public.budget_assert_release_mutable(NEW.release_id);
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER anomalies_release_guard
        BEFORE INSERT OR UPDATE OR DELETE ON anomalies
        FOR EACH ROW EXECUTE FUNCTION budget_guard_release_child()
        """
    )
    op.execute(
        """
        CREATE TRIGGER validations_release_guard
        BEFORE INSERT OR UPDATE OR DELETE ON validations
        FOR EACH ROW EXECUTE FUNCTION budget_guard_release_child()
        """
    )
    op.execute(
        """
        CREATE TRIGGER ingestion_runs_release_guard
        BEFORE INSERT OR UPDATE OR DELETE ON ingestion_runs
        FOR EACH ROW EXECUTE FUNCTION budget_guard_release_child()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_enforce_published_pointer()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            release_year smallint;
            release_stage text;
            release_status text;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'published release pointers cannot be deleted';
            END IF;
            IF current_user <> 'budget_lifecycle' THEN
                RAISE EXCEPTION 'published release pointers are managed by publication only'
                    USING ERRCODE = '42501';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                PERFORM public.budget_lock_release_pair(OLD.release_id, NEW.release_id);
            ELSE
                PERFORM public.budget_lock_release(NEW.release_id);
            END IF;
            SELECT fiscal_year, legal_stage, status
            INTO release_year, release_stage, release_status
            FROM public.releases WHERE id = NEW.release_id;
            IF release_status <> 'published'
                OR release_year <> NEW.fiscal_year
                OR release_stage <> NEW.legal_stage THEN
                RAISE EXCEPTION 'published pointer must target a matching published release';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER published_releases_guard
        BEFORE INSERT OR UPDATE OR DELETE ON published_releases
        FOR EACH ROW EXECUTE FUNCTION budget_enforce_published_pointer()
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_release_assert_publishable(p_release_id uuid)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM public.releases WHERE id = p_release_id) THEN
                RAISE EXCEPTION 'release % does not exist', p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.anomalies
                WHERE release_id = p_release_id AND blocked
            ) THEN
                RAISE EXCEPTION 'release % has a blocking anomaly', p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.anomalies
                WHERE release_id = p_release_id AND severity IN ('error', 'critical')
            ) THEN
                RAISE EXCEPTION 'release % has an error or critical anomaly', p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.validations
                WHERE release_id = p_release_id
                  AND blocking AND result <> 'passed'
            ) THEN
                RAISE EXCEPTION 'release % has a failed blocking validation', p_release_id;
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                WHERE bn.release_id = p_release_id
            ) THEN
                RAISE EXCEPTION 'release % has no budget amounts', p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.budget_nodes n
                WHERE n.release_id = p_release_id
                  AND NOT EXISTS (
                      SELECT 1 FROM public.budget_amounts ba
                      WHERE ba.node_id = n.id AND ba.metric IN ('AE', 'CP')
                  )
            ) THEN
                RAISE EXCEPTION 'release % contains a public node without a budget amount',
                    p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                WHERE bn.release_id = p_release_id
                  AND NOT EXISTS (
                      SELECT 1 FROM public.amount_source_fragments asf
                      WHERE asf.amount_id = ba.id
                  )
            ) THEN
                RAISE EXCEPTION 'release % contains an unsourced budget amount', p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.budget_nodes n
                WHERE n.release_id = p_release_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.budget_amounts ba
                      JOIN public.amount_source_fragments asf ON asf.amount_id = ba.id
                      WHERE ba.node_id = n.id
                  )
            ) THEN
                RAISE EXCEPTION 'release % contains a node without provenance', p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.budget_amounts ba
                JOIN public.budget_nodes bn ON bn.id = ba.node_id
                JOIN public.amount_source_fragments asf ON asf.amount_id = ba.id
                JOIN public.source_fragments sf ON sf.id = asf.source_fragment_id
                WHERE bn.release_id = p_release_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM public.release_source_documents rs
                      WHERE rs.release_id = p_release_id
                        AND rs.source_document_id = sf.source_document_id
                  )
            ) THEN
                RAISE EXCEPTION
                    'release % contains an amount whose source document is not attached',
                    p_release_id;
            END IF;
            IF EXISTS (
                SELECT 1
                FROM public.budget_nodes n
                LEFT JOIN public.budget_nodes p
                    ON p.id = n.parent_id AND p.release_id = n.release_id
                WHERE n.release_id = p_release_id
                  AND (
                      (n.node_type = 'mission' AND n.parent_id IS NOT NULL)
                      OR (
                          n.node_type = 'programme'
                          AND (n.parent_id IS NULL OR p.node_type <> 'mission')
                      )
                      OR (
                          n.node_type = 'action'
                          AND (n.parent_id IS NULL OR p.node_type <> 'programme')
                      )
                  )
            ) THEN
                RAISE EXCEPTION 'release % contains an invalid budget tree', p_release_id;
            END IF;
            IF EXISTS (
                WITH RECURSIVE walk(start_id, current_id, path) AS (
                    SELECT id, parent_id, ARRAY[id]::uuid[]
                    FROM public.budget_nodes
                    WHERE release_id = p_release_id AND parent_id IS NOT NULL
                    UNION ALL
                    SELECT w.start_id, n.parent_id, w.path || n.id
                    FROM walk w
                    JOIN public.budget_nodes n
                        ON n.id = w.current_id AND n.release_id = p_release_id
                    WHERE w.current_id IS NOT NULL AND cardinality(w.path) < 100
                )
                SELECT 1 FROM walk WHERE current_id = ANY(path)
            ) THEN
                RAISE EXCEPTION 'release % contains a cycle', p_release_id;
            END IF;
            IF EXISTS (
                WITH metrics(metric) AS (
                    VALUES ('AE'::text), ('CP'::text)
                ), parent_metrics AS (
                    SELECT p.id AS parent_id,
                           m.metric,
                           count(c.id) AS child_count,
                           count(ca.id) AS child_metric_count,
                           sum(ca.amount) AS child_total
                    FROM public.budget_nodes p
                    CROSS JOIN metrics m
                    LEFT JOIN public.budget_nodes c
                        ON c.release_id = p.release_id AND c.parent_id = p.id
                    LEFT JOIN public.budget_amounts ca
                        ON ca.node_id = c.id AND ca.metric = m.metric
                    WHERE p.release_id = p_release_id
                    GROUP BY p.id, m.metric
                )
                SELECT 1
                FROM parent_metrics pm
                LEFT JOIN public.budget_amounts pa
                    ON pa.node_id = pm.parent_id AND pa.metric = pm.metric
                WHERE pm.child_count > 0
                  AND (
                      (pm.child_metric_count = 0 AND pa.id IS NOT NULL)
                      OR (pm.child_metric_count > 0
                          AND (pa.id IS NULL OR pa.amount IS DISTINCT FROM pm.child_total))
                  )
            ) THEN
                RAISE EXCEPTION 'release % has hierarchy totals that do not reconcile',
                    p_release_id;
            END IF;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_validate_release(
            p_release_id uuid,
            p_validator text
        )
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            current_status text;
        BEGIN
            PERFORM public.budget_assert_lifecycle_caller();
            IF btrim(p_validator) = '' THEN
                RAISE EXCEPTION 'validator must not be empty';
            END IF;
            SELECT status INTO current_status
            FROM public.releases WHERE id = p_release_id FOR UPDATE;
            IF current_status IS NULL THEN
                RAISE EXCEPTION 'release % does not exist', p_release_id;
            END IF;
            IF current_status <> 'draft' THEN
                RAISE EXCEPTION 'only draft releases can be validated';
            END IF;
            PERFORM public.budget_release_assert_publishable(p_release_id);
            INSERT INTO public.validations (
                release_id, validation_type, result, blocking, validator, details, completed_at
            ) VALUES (
                p_release_id, 'release_publishability', 'passed', true, p_validator,
                '{"source": "database"}'::jsonb, now()
            );
            UPDATE public.releases
            SET status = 'validated', validated_at = now()
            WHERE id = p_release_id;
            RETURN p_release_id;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_reject_release(p_release_id uuid)
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            current_status text;
        BEGIN
            PERFORM public.budget_assert_lifecycle_caller();
            SELECT status INTO current_status
            FROM public.releases WHERE id = p_release_id FOR UPDATE;
            IF current_status IS NULL THEN
                RAISE EXCEPTION 'release % does not exist', p_release_id;
            END IF;
            IF current_status NOT IN ('draft', 'validated') THEN
                RAISE EXCEPTION 'only draft or validated releases can be rejected';
            END IF;
            UPDATE public.releases
            SET status = 'rejected', rejected_at = now()
            WHERE id = p_release_id;
            RETURN p_release_id;
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION budget_publish_release(p_release_id uuid)
        RETURNS uuid
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            release_year smallint;
            release_stage text;
            release_status text;
        BEGIN
            PERFORM public.budget_assert_lifecycle_caller();
            SELECT fiscal_year, legal_stage, status
            INTO release_year, release_stage, release_status
            FROM public.releases WHERE id = p_release_id FOR UPDATE;
            IF release_status IS NULL THEN
                RAISE EXCEPTION 'release % does not exist', p_release_id;
            END IF;
            IF release_status <> 'validated' THEN
                RAISE EXCEPTION 'only validated releases can be published';
            END IF;
            IF EXISTS (
                SELECT 1 FROM public.validations
                WHERE release_id = p_release_id AND blocking AND result <> 'passed'
            ) THEN
                RAISE EXCEPTION 'release % has a failed blocking validation', p_release_id;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM public.validations
                WHERE release_id = p_release_id AND result = 'passed'
            ) THEN
                RAISE EXCEPTION 'release % has no passing validation', p_release_id;
            END IF;
            PERFORM public.budget_release_assert_publishable(p_release_id);
            PERFORM pg_advisory_xact_lock(
                hashtextextended(format('%s:%s', release_year, release_stage), 0)
            );
            UPDATE public.releases
            SET status = 'published', released_at = now()
            WHERE id = p_release_id;
            INSERT INTO public.published_releases (
                fiscal_year, legal_stage, release_id, published_at
            ) VALUES (release_year, release_stage, p_release_id, now())
            ON CONFLICT (fiscal_year, legal_stage)
            DO UPDATE SET release_id = EXCLUDED.release_id, published_at = EXCLUDED.published_at;
            RETURN p_release_id;
        END;
        $$
        """
    )
    op.execute(
        """
        ALTER FUNCTION public.budget_lock_release(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_lock_release_pair(uuid, uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_lock_document_releases(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_lock_fragment_releases(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_lock_amount_releases(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_assert_lifecycle_caller() OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_assert_release_mutable(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_release_assert_publishable(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_validate_release(uuid, text) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_reject_release(uuid) OWNER TO budget_lifecycle;
        ALTER FUNCTION public.budget_publish_release(uuid) OWNER TO budget_lifecycle;
        """
    )
    op.execute(
        """
        REVOKE ALL ON FUNCTION public.budget_lock_release(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_lock_release_pair(uuid, uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_lock_document_releases(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_lock_fragment_releases(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_lock_amount_releases(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_assert_lifecycle_caller() FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_assert_release_mutable(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_release_assert_publishable(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_validate_release(uuid, text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_reject_release(uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION public.budget_publish_release(uuid) FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION public.budget_lock_release(uuid) TO budget_app;
        GRANT EXECUTE ON FUNCTION public.budget_lock_release_pair(uuid, uuid) TO budget_app;
        GRANT EXECUTE ON FUNCTION public.budget_lock_document_releases(uuid) TO budget_app;
        GRANT EXECUTE ON FUNCTION public.budget_lock_fragment_releases(uuid) TO budget_app;
        GRANT EXECUTE ON FUNCTION public.budget_lock_amount_releases(uuid) TO budget_app;
        GRANT EXECUTE ON FUNCTION public.budget_assert_release_mutable(uuid) TO budget_app;
        GRANT EXECUTE ON FUNCTION public.budget_validate_release(uuid, text)
            TO budget_lifecycle_caller;
        GRANT EXECUTE ON FUNCTION public.budget_reject_release(uuid)
            TO budget_lifecycle_caller;
        GRANT EXECUTE ON FUNCTION public.budget_publish_release(uuid)
            TO budget_lifecycle_caller;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO budget_app, budget_lifecycle")
    op.execute(
        """
        REVOKE ALL ON TABLE
            public.source_documents,
            public.source_fragments,
            public.release_source_documents,
            public.budget_nodes,
            public.budget_amounts,
            public.amount_source_fragments,
            public.anomalies,
            public.validations,
            public.ingestion_runs,
            public.releases,
            public.published_releases,
            public.fragment_embeddings
        FROM PUBLIC;
        GRANT SELECT ON TABLE
            public.releases,
            public.published_releases,
            public.source_documents,
            public.source_fragments,
            public.release_source_documents,
            public.budget_nodes,
            public.budget_amounts,
            public.amount_source_fragments,
            public.anomalies,
            public.validations,
            public.ingestion_runs,
            public.fragment_embeddings
        TO budget_app;
        GRANT INSERT, UPDATE, DELETE ON TABLE
            public.source_documents,
            public.source_fragments,
            public.release_source_documents,
            public.budget_nodes,
            public.budget_amounts,
            public.amount_source_fragments,
            public.anomalies,
            public.validations,
            public.ingestion_runs,
            public.fragment_embeddings
        TO budget_app;
        GRANT INSERT (
            id, fiscal_year, legal_stage, version, source_snapshot_hash,
            created_at
        ) ON public.releases TO budget_app;
        GRANT ALL ON TABLE
            public.source_documents,
            public.source_fragments,
            public.release_source_documents,
            public.budget_nodes,
            public.budget_amounts,
            public.amount_source_fragments,
            public.anomalies,
            public.validations,
            public.ingestion_runs,
            public.releases,
            public.published_releases,
            public.fragment_embeddings
        TO budget_lifecycle;
        """
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, pg_catalog")
    for trigger, table in (
        ("fragment_embeddings_guard", "fragment_embeddings"),
        ("published_releases_guard", "published_releases"),
        ("ingestion_runs_release_guard", "ingestion_runs"),
        ("validations_release_guard", "validations"),
        ("anomalies_release_guard", "anomalies"),
        ("amount_source_fragments_guard", "amount_source_fragments"),
        ("budget_amounts_immutability_guard", "budget_amounts"),
        ("budget_nodes_hierarchy_guard", "budget_nodes"),
        ("release_source_documents_guard", "release_source_documents"),
        ("source_fragments_immutable", "source_fragments"),
        ("source_documents_immutable", "source_documents"),
        ("releases_status_transition", "releases"),
    ):
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger} ON {table}"))

    op.execute("DROP FUNCTION IF EXISTS budget_publish_release(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_reject_release(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_validate_release(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS budget_release_assert_publishable(uuid)")

    op.execute("DROP FUNCTION IF EXISTS budget_lock_amount_releases(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_lock_fragment_releases(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_lock_document_releases(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_lock_release_pair(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_lock_release(uuid)")
    op.execute("DROP FUNCTION IF EXISTS budget_assert_lifecycle_caller()")
    op.execute("DROP FUNCTION IF EXISTS budget_guard_fragment_embedding()")
    op.execute("DROP FUNCTION IF EXISTS budget_enforce_published_pointer()")
    op.execute("DROP FUNCTION IF EXISTS budget_guard_release_child()")
    op.execute("DROP FUNCTION IF EXISTS budget_enforce_amount_provenance()")
    op.execute("DROP FUNCTION IF EXISTS budget_guard_node_amount()")
    op.execute("DROP FUNCTION IF EXISTS budget_enforce_node_hierarchy()")
    op.execute("DROP FUNCTION IF EXISTS budget_enforce_release_source()")
    op.execute("DROP FUNCTION IF EXISTS budget_protect_source_fragment()")
    op.execute("DROP FUNCTION IF EXISTS budget_protect_source_document()")
    op.execute("DROP FUNCTION IF EXISTS budget_enforce_release_status()")
    op.execute("DROP FUNCTION IF EXISTS budget_assert_release_mutable(uuid)")
    for table in (
        "fragment_embeddings",
        "published_releases",
        "ingestion_runs",
        "validations",
        "anomalies",
        "amount_source_fragments",
        "budget_amounts",
        "budget_nodes",
        "release_source_documents",
        "source_fragments",
        "releases",
        "source_documents",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
