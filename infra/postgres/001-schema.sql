-- Initial migration, applied once to a new database by the owner.
CREATE ROLE analyst_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE analyst_audit LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO analyst_reader, analyst_audit;
CREATE TABLE sales (
 id INTEGER PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL, sold_on DATE NOT NULL,
 product VARCHAR(80) NOT NULL, revenue_minor BIGINT NOT NULL CHECK (revenue_minor >= 0),
 status VARCHAR(20) NOT NULL CHECK (status IN ('completed','cancelled'))
);
CREATE INDEX sales_tenant_date ON sales (tenant_id, sold_on);
CREATE TABLE coverage (
 tenant_id VARCHAR(64) NOT NULL, starts_on DATE NOT NULL, ends_on DATE NOT NULL,
 PRIMARY KEY (tenant_id,starts_on), CHECK (starts_on < ends_on)
);
CREATE TABLE reports (
 id VARCHAR(36) PRIMARY KEY, tenant_id VARCHAR(64) NOT NULL,
 created_at VARCHAR(40) NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX reports_tenant_created ON reports (tenant_id,created_at);
ALTER TABLE sales ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales FORCE ROW LEVEL SECURITY;
ALTER TABLE coverage ENABLE ROW LEVEL SECURITY;
ALTER TABLE coverage FORCE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports FORCE ROW LEVEL SECURITY;
CREATE POLICY sales_tenant ON sales TO analyst_reader
 USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY coverage_tenant ON coverage TO analyst_reader
 USING (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY report_tenant ON reports TO analyst_audit
 USING (tenant_id = current_setting('app.tenant_id', true))
 WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
GRANT SELECT ON sales, coverage TO analyst_reader;
GRANT SELECT, INSERT ON reports TO analyst_audit;
ALTER ROLE analyst_reader SET default_transaction_read_only = on;
ALTER ROLE analyst_reader SET statement_timeout = '3s';
ALTER ROLE analyst_audit SET statement_timeout = '3s';
