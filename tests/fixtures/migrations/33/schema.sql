CREATE SCHEMA sushi__dev;
CREATE SCHEMA sushi;
CREATE SCHEMA raw;
CREATE SCHEMA sqlmesh__sushi;
CREATE SCHEMA sqlmesh;



CREATE TABLE raw.demographics(customer_id INTEGER, zip VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_revenue_by_day__3608812833(waiter_id INTEGER, revenue DOUBLE, dummy_col VARCHAR, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_revenue_by_day__3608812833__temp(waiter_id INTEGER, revenue DOUBLE, dummy_col VARCHAR, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_as_customer_by_day__1695007643(waiter_id INTEGER, waiter_name VARCHAR, flag INTEGER, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_as_customer_by_day__1695007643__temp(waiter_id INTEGER, waiter_name VARCHAR, flag INTEGER, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_revenue_by_day__1623050846(waiter_id INTEGER, revenue DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_revenue_by_day__1623050846__temp(waiter_id INTEGER, revenue DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__customers__137303981(customer_id INTEGER, status VARCHAR, zip VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__customers__137303981__temp(customer_id INTEGER, status VARCHAR, zip VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__customer_revenue_lifetime__439196980(customer_id INTEGER, revenue DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__customer_revenue_lifetime__439196980__temp(customer_id INTEGER, revenue DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__customer_revenue_by_day__489697783(customer_id INTEGER, revenue DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__customer_revenue_by_day__489697783__temp(customer_id INTEGER, revenue DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__order_items__2521328603(id INTEGER, order_id INTEGER, item_id INTEGER, quantity INTEGER, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__order_items__2521328603__temp(id INTEGER, order_id INTEGER, item_id INTEGER, quantity INTEGER, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__marketing__3476342839(customer_id INTEGER, status VARCHAR, updated_at TIMESTAMP, valid_from TIMESTAMP, valid_to TIMESTAMP);
CREATE TABLE sqlmesh__sushi.sushi__marketing__3476342839__temp(customer_id INTEGER, status VARCHAR, updated_at TIMESTAMP, valid_from TIMESTAMP, valid_to TIMESTAMP);
CREATE TABLE sqlmesh__sushi.sushi__waiter_names__235351925(id BIGINT, "name" VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__waiter_names__235351925__temp(id BIGINT, "name" VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__raw_marketing__3933936918(customer_id INTEGER, status VARCHAR, updated_at TIMESTAMP);
CREATE TABLE sqlmesh__sushi.sushi__raw_marketing__3933936918__temp(customer_id INTEGER, status VARCHAR, updated_at TIMESTAMP);
CREATE TABLE sqlmesh__sushi.sushi__orders__1740723439(id INTEGER, customer_id INTEGER, waiter_id INTEGER, start_ts INTEGER, end_ts INTEGER, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__orders__1740723439__temp(id INTEGER, customer_id INTEGER, waiter_id INTEGER, start_ts INTEGER, end_ts INTEGER, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__items__115405787(id INTEGER, "name" VARCHAR, price DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh__sushi.sushi__items__115405787__temp(id INTEGER, "name" VARCHAR, price DOUBLE, ds VARCHAR);
CREATE TABLE sqlmesh._plan_dags(request_id VARCHAR, dag_id VARCHAR, dag_spec VARCHAR);
CREATE TABLE sqlmesh._intervals(id VARCHAR, created_ts BIGINT, "name" VARCHAR, identifier VARCHAR, "version" VARCHAR, start_ts BIGINT, end_ts BIGINT, is_dev BOOLEAN, is_removed BOOLEAN, is_compacted BOOLEAN);
CREATE TABLE sqlmesh._seeds("name" VARCHAR, identifier VARCHAR, "content" VARCHAR);
CREATE TABLE sqlmesh._versions(schema_version INTEGER, sqlglot_version VARCHAR, sqlmesh_version VARCHAR);
CREATE TABLE sqlmesh._environments("name" VARCHAR, snapshots VARCHAR, start_at VARCHAR, end_at VARCHAR, plan_id VARCHAR, previous_plan_id VARCHAR, expiration_ts BIGINT, finalized_ts BIGINT, promoted_snapshot_ids VARCHAR, suffix_target VARCHAR);
CREATE TABLE sqlmesh._snapshots("name" VARCHAR, identifier VARCHAR, "version" VARCHAR, "snapshot" VARCHAR, kind_name VARCHAR);

CREATE OR REPLACE VIEW "sqlmesh__sushi"."sushi__top_waiters__132946899" ("waiter_id", "revenue") AS SELECT CAST("waiter_revenue_by_day"."waiter_id" AS INT) AS "waiter_id", CAST("waiter_revenue_by_day"."revenue" AS DOUBLE) AS "revenue" FROM "sqlmesh__sushi"."sushi__waiter_revenue_by_day__1623050846" AS "waiter_revenue_by_day" WHERE "waiter_revenue_by_day"."ds" = (SELECT MAX("waiter_revenue_by_day"."ds") AS "_col_0" FROM "sqlmesh__sushi"."sushi__waiter_revenue_by_day__1623050846" AS "waiter_revenue_by_day") ORDER BY "revenue" DESC LIMIT 10
;
CREATE OR REPLACE VIEW "sqlmesh__sushi"."sushi__top_waiters__132946899__temp" AS SELECT CAST("waiter_revenue_by_day"."waiter_id" AS INT) AS "waiter_id", CAST("waiter_revenue_by_day"."revenue" AS DOUBLE) AS "revenue" FROM "sqlmesh__sushi"."sushi__waiter_revenue_by_day__3608812833" AS "waiter_revenue_by_day" WHERE "waiter_revenue_by_day"."ds" = (SELECT MAX("waiter_revenue_by_day"."ds") AS "_col_0" FROM "sqlmesh__sushi"."sushi__waiter_revenue_by_day__3608812833" AS "waiter_revenue_by_day") ORDER BY "revenue" DESC LIMIT 10
;
CREATE OR REPLACE VIEW "sushi__dev"."top_waiters" AS SELECT * FROM "sqlmesh__sushi"."sushi__top_waiters__132946899"
;
CREATE OR REPLACE VIEW "sushi__dev"."waiter_revenue_by_day" AS SELECT * FROM "sqlmesh__sushi"."sushi__waiter_revenue_by_day__3608812833"
;
CREATE OR REPLACE VIEW "sushi"."waiter_as_customer_by_day" AS SELECT * FROM "sqlmesh__sushi"."sushi__waiter_as_customer_by_day__1695007643"
;
CREATE OR REPLACE VIEW "sushi"."top_waiters" AS SELECT * FROM "sqlmesh__sushi"."sushi__top_waiters__132946899"
;
CREATE OR REPLACE VIEW "sushi"."waiter_revenue_by_day" AS SELECT * FROM "sqlmesh__sushi"."sushi__waiter_revenue_by_day__1623050846"
;
CREATE OR REPLACE VIEW "sushi"."customers" AS SELECT * FROM "sqlmesh__sushi"."sushi__customers__137303981"
;
CREATE OR REPLACE VIEW "sushi"."customer_revenue_lifetime" AS SELECT * FROM "sqlmesh__sushi"."sushi__customer_revenue_lifetime__439196980"
;
CREATE OR REPLACE VIEW "sushi"."customer_revenue_by_day" AS SELECT * FROM "sqlmesh__sushi"."sushi__customer_revenue_by_day__489697783"
;
CREATE OR REPLACE VIEW "sushi"."order_items" AS SELECT * FROM "sqlmesh__sushi"."sushi__order_items__2521328603"
;
CREATE OR REPLACE VIEW "sushi"."marketing" AS SELECT * FROM "sqlmesh__sushi"."sushi__marketing__3476342839"
;
CREATE OR REPLACE VIEW "sushi"."waiter_names" AS SELECT * FROM "sqlmesh__sushi"."sushi__waiter_names__235351925"
;
CREATE OR REPLACE VIEW "sushi"."raw_marketing" AS SELECT * FROM "sqlmesh__sushi"."sushi__raw_marketing__3933936918"
;
CREATE OR REPLACE VIEW "sushi"."orders" AS SELECT * FROM "sqlmesh__sushi"."sushi__orders__1740723439"
;
CREATE OR REPLACE VIEW "sushi"."items" AS SELECT * FROM "sqlmesh__sushi"."sushi__items__115405787"
;




