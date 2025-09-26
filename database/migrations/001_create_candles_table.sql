-- Description: Create market_data_candles table with indexes and constraints for OHLCV data storage
-- Version: 1.0.0
-- Author: Trading Bot Team
-- Created: 2024-12-26

-- Create market_data_candles table for OHLCV cryptocurrency data
CREATE TABLE IF NOT EXISTS market_data_candles (
    -- Primary key
    id BIGSERIAL PRIMARY KEY,
    
    -- Market identification
    symbol VARCHAR(20) NOT NULL,
    interval VARCHAR(10) NOT NULL,
    
    -- Time data (with timezone support)
    open_time TIMESTAMPTZ NOT NULL,
    close_time TIMESTAMPTZ NOT NULL,
    
    -- OHLCV data (using NUMERIC for financial precision)
    open_price NUMERIC(20,8) NOT NULL,
    high_price NUMERIC(20,8) NOT NULL,
    low_price NUMERIC(20,8) NOT NULL,
    close_price NUMERIC(20,8) NOT NULL,
    volume NUMERIC(20,8) NOT NULL,
    
    -- Extended market data
    quote_volume NUMERIC(20,8),
    number_of_trades BIGINT,
    taker_buy_base_volume NUMERIC(20,8),
    taker_buy_quote_volume NUMERIC(20,8),
    
    -- Metadata
    data_source VARCHAR(50) DEFAULT 'bybit',
    raw_data JSONB,
    
    -- System timestamps
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add table comment
COMMENT ON TABLE market_data_candles IS 'OHLCV candle data for cryptocurrency market analysis and technical indicators';

-- Column comments
COMMENT ON COLUMN market_data_candles.symbol IS 'Trading symbol (e.g., BTCUSDT)';
COMMENT ON COLUMN market_data_candles.interval IS 'Candle interval (1m, 5m, 1h, etc.)';
COMMENT ON COLUMN market_data_candles.open_time IS 'Candle open timestamp in UTC';
COMMENT ON COLUMN market_data_candles.close_time IS 'Candle close timestamp in UTC';
COMMENT ON COLUMN market_data_candles.open_price IS 'Opening price with 8 decimal precision';
COMMENT ON COLUMN market_data_candles.high_price IS 'Highest price in candle period';
COMMENT ON COLUMN market_data_candles.low_price IS 'Lowest price in candle period';
COMMENT ON COLUMN market_data_candles.close_price IS 'Closing price with 8 decimal precision';
COMMENT ON COLUMN market_data_candles.volume IS 'Trading volume in base asset';
COMMENT ON COLUMN market_data_candles.quote_volume IS 'Trading volume in quote asset';
COMMENT ON COLUMN market_data_candles.number_of_trades IS 'Number of individual trades';
COMMENT ON COLUMN market_data_candles.taker_buy_base_volume IS 'Taker buy volume in base asset';
COMMENT ON COLUMN market_data_candles.taker_buy_quote_volume IS 'Taker buy volume in quote asset';
COMMENT ON COLUMN market_data_candles.data_source IS 'Source of the data (bybit, binance, etc.)';
COMMENT ON COLUMN market_data_candles.raw_data IS 'Original API response data for debugging';

-- Create unique constraint to prevent duplicate candles
ALTER TABLE market_data_candles 
ADD CONSTRAINT uq_candle_symbol_interval_time 
UNIQUE (symbol, interval, open_time);

-- Add check constraints for data integrity
ALTER TABLE market_data_candles ADD CONSTRAINT ck_open_price_positive CHECK (open_price > 0);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_high_price_positive CHECK (high_price > 0);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_low_price_positive CHECK (low_price > 0);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_close_price_positive CHECK (close_price > 0);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_volume_non_negative CHECK (volume >= 0);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_high_gte_low CHECK (high_price >= low_price);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_high_gte_open CHECK (high_price >= open_price);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_high_gte_close CHECK (high_price >= close_price);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_low_lte_open CHECK (low_price <= open_price);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_low_lte_close CHECK (low_price <= close_price);
ALTER TABLE market_data_candles ADD CONSTRAINT ck_close_after_open CHECK (close_time > open_time);

-- Create performance indexes for time-series queries
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_symbol_interval_open_time 
ON market_data_candles (symbol, interval, open_time);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_close_time 
ON market_data_candles (close_time);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_symbol_close_time 
ON market_data_candles (symbol, close_time);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_created_at 
ON market_data_candles (created_at);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_data_source 
ON market_data_candles (data_source);

-- Partial indexes for most common queries (BTCUSDT optimization)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_btcusdt_1m 
ON market_data_candles (open_time) 
WHERE symbol = 'BTCUSDT' AND interval = '1m';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_btcusdt_5m 
ON market_data_candles (open_time) 
WHERE symbol = 'BTCUSDT' AND interval = '5m';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_btcusdt_1h 
ON market_data_candles (open_time) 
WHERE symbol = 'BTCUSDT' AND interval = '1h';

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_btcusdt_1d 
ON market_data_candles (open_time) 
WHERE symbol = 'BTCUSDT' AND interval = '1d';

-- JSONB index for raw_data queries (if needed for debugging)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_candles_raw_data_gin 
ON market_data_candles USING gin (raw_data);

-- Create function for automatic updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for automatic updated_at updates
DROP TRIGGER IF EXISTS tr_candles_updated_at ON market_data_candles;
CREATE TRIGGER tr_candles_updated_at
    BEFORE UPDATE ON market_data_candles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add validation function for interval values
CREATE OR REPLACE FUNCTION validate_candle_interval(interval_value TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN interval_value IN (
        '1m', '3m', '5m', '15m', '30m',
        '1h', '2h', '4h', '6h', '12h',
        '1d', '1w', '1M'
    );
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Add constraint for valid intervals
ALTER TABLE market_data_candles 
ADD CONSTRAINT ck_valid_interval 
CHECK (validate_candle_interval(interval));

-- Create view for latest candles per symbol/interval
CREATE OR REPLACE VIEW latest_candles AS
SELECT DISTINCT ON (symbol, interval)
    symbol,
    interval,
    open_time,
    close_time,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    created_at
FROM market_data_candles
ORDER BY symbol, interval, open_time DESC;

COMMENT ON VIEW latest_candles IS 'Latest candle for each symbol/interval combination';

-- Create materialized view for daily statistics (for performance)
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_candle_stats AS
SELECT 
    symbol,
    interval,
    DATE(open_time) as date,
    COUNT(*) as candle_count,
    MIN(low_price) as day_low,
    MAX(high_price) as day_high,
    FIRST_VALUE(open_price ORDER BY open_time) as day_open,
    LAST_VALUE(close_price ORDER BY open_time ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) as day_close,
    SUM(volume) as day_volume,
    AVG(close_price) as avg_price
FROM market_data_candles
GROUP BY symbol, interval, DATE(open_time)
ORDER BY symbol, interval, DATE(open_time) DESC;

-- Create unique index on materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_stats_symbol_interval_date
ON daily_candle_stats (symbol, interval, date);

COMMENT ON MATERIALIZED VIEW daily_candle_stats IS 'Daily aggregated statistics for faster reporting queries';

-- Function to refresh materialized view (can be called by cron job)
CREATE OR REPLACE FUNCTION refresh_daily_stats()
RETURNS VOID AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY daily_candle_stats;
    PERFORM pg_notify('daily_stats_refreshed', 'Daily candle statistics updated');
END;
$$ LANGUAGE plpgsql;

-- Create helper function for price change calculations
CREATE OR REPLACE FUNCTION calculate_price_change(
    p_symbol TEXT,
    p_interval TEXT, 
    p_periods INTEGER DEFAULT 1
)
RETURNS TABLE(
    open_time TIMESTAMPTZ,
    close_price NUMERIC,
    price_change NUMERIC,
    price_change_percent NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.open_time,
        c.close_price,
        c.close_price - LAG(c.close_price, p_periods) OVER (ORDER BY c.open_time) as price_change,
        CASE 
            WHEN LAG(c.close_price, p_periods) OVER (ORDER BY c.open_time) > 0 THEN
                ((c.close_price - LAG(c.close_price, p_periods) OVER (ORDER BY c.open_time)) / 
                 LAG(c.close_price, p_periods) OVER (ORDER BY c.open_time)) * 100
            ELSE NULL
        END as price_change_percent
    FROM market_data_candles c
    WHERE c.symbol = p_symbol AND c.interval = p_interval
    ORDER BY c.open_time;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION calculate_price_change IS 'Calculate price changes over specified periods';

-- Grant appropriate permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON market_data_candles TO trading_bot;
GRANT USAGE, SELECT ON SEQUENCE market_data_candles_id_seq TO trading_bot;
GRANT SELECT ON latest_candles TO trading_bot;
GRANT SELECT ON daily_candle_stats TO trading_bot;

-- Create notification function for real-time updates
CREATE OR REPLACE FUNCTION notify_candle_insert()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'candle_inserted', 
        json_build_object(
            'symbol', NEW.symbol,
            'interval', NEW.interval,
            'open_time', NEW.open_time,
            'close_price', NEW.close_price
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger for real-time notifications (optional - enable if needed)
-- CREATE TRIGGER tr_notify_candle_insert
--     AFTER INSERT ON market_data_candles
--     FOR EACH ROW
--     EXECUTE FUNCTION notify_candle_insert();

-- Log successful migration
INSERT INTO database_migrations (migration_name, checksum, execution_time_ms)
VALUES ('001_create_candles_table', 'auto_calculated', 0)
ON CONFLICT (migration_name) DO NOTHING;

-- Success message
DO $$
BEGIN
    RAISE NOTICE 'Migration 001_create_candles_table completed successfully';
    RAISE NOTICE 'Created table: market_data_candles with % indexes and constraints', 
        (SELECT COUNT(*) FROM pg_indexes WHERE tablename = 'market_data_candles');
END
$$;
