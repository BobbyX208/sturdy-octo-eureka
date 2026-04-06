-- Create properties table
CREATE TABLE IF NOT EXISTS properties (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id),
    property_type TEXT NOT NULL,
    district SMALLINT NOT NULL,
    tier SMALLINT DEFAULT 1,
    monthly_cost INT NOT NULL,
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    last_maintained TIMESTAMPTZ DEFAULT NOW()
);

-- Create scheduled_transfers table
CREATE TABLE IF NOT EXISTS scheduled_transfers (
    id SERIAL PRIMARY KEY,
    from_id BIGINT NOT NULL REFERENCES players(discord_id),
    to_id BIGINT NOT NULL REFERENCES players(discord_id),
    amount INT NOT NULL,
    scheduled_time TIMESTAMPTZ NOT NULL,
    note TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_properties_discord_id ON properties(discord_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_from_id ON scheduled_transfers(from_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_to_id ON scheduled_transfers(to_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_transfers_scheduled_time ON scheduled_transfers(scheduled_time);