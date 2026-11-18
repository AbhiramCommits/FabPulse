-- FabPulse warehouse DDL (PostgreSQL 15+). Generated from fabpulse.schema.
-- The API auto-creates the same tables on SQLite when no server is available.

CREATE TABLE dim_tool (
	tool_key SERIAL NOT NULL, 
	tool_id VARCHAR(32) NOT NULL, 
	tool_family VARCHAR(32) NOT NULL, 
	fab_site VARCHAR(16) NOT NULL, 
	install_date DATE, 
	CONSTRAINT pk_dim_tool PRIMARY KEY (tool_key), 
	CONSTRAINT uq_dim_tool_tool_id UNIQUE (tool_id)
);

CREATE TABLE dim_date (
	date_key SERIAL NOT NULL, 
	date DATE NOT NULL, 
	year SMALLINT NOT NULL, 
	month SMALLINT NOT NULL, 
	iso_week SMALLINT NOT NULL, 
	day_of_week SMALLINT NOT NULL, 
	is_weekend BOOLEAN NOT NULL, 
	CONSTRAINT pk_dim_date PRIMARY KEY (date_key), 
	CONSTRAINT uq_dim_date_date UNIQUE (date)
);

CREATE TABLE dim_shift (
	shift_key SMALLSERIAL NOT NULL, 
	shift_code VARCHAR(1) NOT NULL, 
	start_hour SMALLINT NOT NULL, 
	end_hour SMALLINT NOT NULL, 
	CONSTRAINT pk_dim_shift PRIMARY KEY (shift_key), 
	CONSTRAINT uq_dim_shift_shift_code UNIQUE (shift_code)
);

CREATE TABLE dim_fault (
	fault_key SMALLSERIAL NOT NULL, 
	fault_code VARCHAR(32) NOT NULL, 
	fault_category VARCHAR(32) NOT NULL, 
	severity VARCHAR(16) NOT NULL, 
	CONSTRAINT pk_dim_fault PRIMARY KEY (fault_key), 
	CONSTRAINT uq_dim_fault_fault_code UNIQUE (fault_code)
);

CREATE TABLE fact_tool_event (
	event_key BIGSERIAL NOT NULL, 
	tool_key INTEGER NOT NULL, 
	date_key INTEGER NOT NULL, 
	shift_key SMALLINT NOT NULL, 
	fault_key SMALLINT, 
	ts TIMESTAMP WITH TIME ZONE NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	wafers_processed INTEGER DEFAULT 0 NOT NULL, 
	throughput_wph FLOAT DEFAULT 0 NOT NULL, 
	yield_pct FLOAT, 
	duration_s INTEGER NOT NULL, 
	recipe_id VARCHAR(32), 
	CONSTRAINT pk_fact_tool_event PRIMARY KEY (event_key), 
	CONSTRAINT fk_fact_tool_event_tool_key_dim_tool FOREIGN KEY(tool_key) REFERENCES dim_tool (tool_key), 
	CONSTRAINT fk_fact_tool_event_date_key_dim_date FOREIGN KEY(date_key) REFERENCES dim_date (date_key), 
	CONSTRAINT fk_fact_tool_event_shift_key_dim_shift FOREIGN KEY(shift_key) REFERENCES dim_shift (shift_key), 
	CONSTRAINT fk_fact_tool_event_fault_key_dim_fault FOREIGN KEY(fault_key) REFERENCES dim_fault (fault_key)
);
CREATE INDEX ix_fact_date_shift ON fact_tool_event (date_key, shift_key);
CREATE INDEX ix_fact_fault ON fact_tool_event (fault_key);
CREATE INDEX ix_fact_state ON fact_tool_event (state);
CREATE INDEX ix_fact_tool_ts ON fact_tool_event (tool_key, ts);
