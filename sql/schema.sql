-- ============================================================
-- 1. MODEL IDENTITY (the one small dimension table)
-- ============================================================
CREATE TABLE IF NOT EXISTS models (
    model_name   VARCHAR NOT NULL,                    -- 'BigFork'
    model_year   INT NOT NULL,                        -- end year from GLOBAL
    run_id       VARCHAR NOT NULL DEFAULT 'base',     -- 'base', 'cal_47', etc.
    start_year   INT,
    notes        VARCHAR,
    created_at   TIMESTAMP DEFAULT current_timestamp,
    UNIQUE (model_name, model_year, run_id)
);

-- ============================================================
-- 2. UCI STRUCTURE (keyed to model, NOT run)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS uci;

CREATE TABLE IF NOT EXISTS uci.operations (
    model_name       VARCHAR NOT NULL,
    model_year       INT NOT NULL,
    operation_type   VARCHAR NOT NULL,
    operation_id     INT NOT NULL,
    metzone          VARCHAR
);

CREATE TABLE IF NOT EXISTS uci.schematics (
    model_name   VARCHAR NOT NULL,
    model_year   INT NOT NULL,
    SVOL         VARCHAR,
    SVOLNO       INT,
    TVOL         VARCHAR,
    TVOLNO       INT,
    MLNO         VARCHAR,
    AFACTR       DOUBLE,
    TMEMSB1      INT,
    TMEMSB2      INT
);

CREATE TABLE IF NOT EXISTS uci.masslinks (
    model_name   VARCHAR NOT NULL,
    model_year   INT NOT NULL,
    MLNO         VARCHAR NOT NULL,
    SVOL         VARCHAR,
    SGRPN        VARCHAR,
    SMEMN        VARCHAR,
    SMEMSB1      INT,
    SMEMSB2      INT,
    MFACTR       DOUBLE,
    TVOL         VARCHAR,
    TGRPN        VARCHAR,
    TMEMN        VARCHAR,
    TMEMSB1      INT,
    TMEMSB2      INT
);

CREATE TABLE IF NOT EXISTS uci.ftables (
    model_name   VARCHAR NOT NULL,
    model_year   INT NOT NULL,
    reach_id     INT NOT NULL,
    depth        DOUBLE,
    area         DOUBLE,
    volume       DOUBLE,
    discharge    DOUBLE
);

CREATE TABLE IF NOT EXISTS uci.extsources (
    model_name   VARCHAR NOT NULL,
    model_year   INT NOT NULL,
    SVOL         VARCHAR,
    SVOLNO       INT,
    SMESSION     VARCHAR,
    SGRPN        VARCHAR,
    SMEMN        VARCHAR,
    SMEMSB1      INT,
    SMEMSB2      INT,
    SVARI        VARCHAR,
    MFACTR       DOUBLE,
    TRAN         VARCHAR,
    TVOL         VARCHAR,
    TOPFST       INT,
    TOPLST       INT,
    TGRPN        VARCHAR,
    TMEMN        VARCHAR,
    TMEMSB1      INT,
    TMEMSB2      INT,
    TSTEFP       VARCHAR,
    APTS         VARCHAR
);

CREATE TABLE IF NOT EXISTS uci.exttargets (
    model_name   VARCHAR NOT NULL,
    model_year   INT NOT NULL,
    SVOL         VARCHAR,
    SVOLNO       INT,
    SGRPN        VARCHAR,
    SMEMN        VARCHAR,
    SMEMSB1      INT,
    SMEMSB2      INT,
    MFACTR       DOUBLE,
    TRAN         VARCHAR,
    TVOL         VARCHAR,
    TVOLNO       INT,
    TGRPN        VARCHAR,
    TMEMN        VARCHAR,
    TMEMSB1      INT,
    TMEMSB2      INT,
    APTS         VARCHAR
);

CREATE TABLE IF NOT EXISTS uci.networks (
    model_name   VARCHAR NOT NULL,
    model_year   INT NOT NULL,
    SVOL         VARCHAR,
    SVOLNO       INT,
    SGRPN        VARCHAR,
    SMEMN        VARCHAR,
    SMEMSB1      INT,
    SMEMSB2      INT,
    MFACTR       DOUBLE,
    TVOL         VARCHAR,
    TOPFST       INT,
    TOPLST       INT,
    TGRPN        VARCHAR,
    TMEMN        VARCHAR,
    TMEMSB1      INT,
    TMEMSB2      INT
);

-- ============================================================
-- 3. UCI PARAMETERS (keyed to model + run)
-- ============================================================
CREATE TABLE IF NOT EXISTS uci.parameters (
    model_name       VARCHAR NOT NULL,
    model_year       INT NOT NULL,
    run_id           VARCHAR NOT NULL DEFAULT 'base',
    operation_type   VARCHAR NOT NULL,
    operation_id     INT NOT NULL,
    table_name       VARCHAR NOT NULL,
    parameter_name   VARCHAR NOT NULL,
    parameter_value  DOUBLE
);

CREATE TABLE IF NOT EXISTS uci.flags (
    model_name       VARCHAR NOT NULL,
    model_year       INT NOT NULL,
    run_id           VARCHAR NOT NULL DEFAULT 'base',
    operation_type   VARCHAR NOT NULL,
    operation_id     INT NOT NULL,
    table_name       VARCHAR NOT NULL,
    flag_name        VARCHAR NOT NULL,
    flag_value       INT
);

CREATE TABLE IF NOT EXISTS uci.properties (
    model_name       VARCHAR NOT NULL,
    model_year       INT NOT NULL,
    run_id           VARCHAR NOT NULL DEFAULT 'base',
    operation_type   VARCHAR NOT NULL,
    operation_id     INT NOT NULL,
    table_name       VARCHAR NOT NULL,
    property_name    VARCHAR NOT NULL,
    property_value   VARCHAR
);

-- ============================================================
-- 4. OUTPUT TIMESERIES (from HBN)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS output;

CREATE TABLE IF NOT EXISTS output.timeseries (
    model_name       VARCHAR NOT NULL,
    model_year       INT NOT NULL,
    run_id           VARCHAR NOT NULL DEFAULT 'base',
    operation_type   VARCHAR NOT NULL,
    operation_id     INT NOT NULL,
    activity         VARCHAR NOT NULL,
    ts_name          VARCHAR NOT NULL,
    timestep         VARCHAR NOT NULL,
    datetime         TIMESTAMP NOT NULL,
    value            DOUBLE
);

-- ============================================================
-- 5. REPORTS
-- ============================================================
CREATE SCHEMA IF NOT EXISTS reports;

CREATE TABLE IF NOT EXISTS reports.catchment_loading (
    model_name       VARCHAR NOT NULL,
    model_year       INT NOT NULL,
    run_id           VARCHAR NOT NULL DEFAULT 'base',
    datetime         TIMESTAMP NOT NULL,
    reach_id         INT NOT NULL,
    constituent      VARCHAR NOT NULL,
    operation_type   VARCHAR,
    operation_id     INT,
    load             DOUBLE,
    loading_rate     DOUBLE,
    landcover_area   DOUBLE
);
