-- database/schema.sql

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Players Table
CREATE TABLE IF NOT EXISTS players (
    discord_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL,
    wallet BIGINT DEFAULT 0 CHECK (wallet >= 0),
    bank BIGINT DEFAULT 0 CHECK (bank >= 0),
    total_earned BIGINT DEFAULT 0,
    district SMALLINT DEFAULT 1,
    reputation INT DEFAULT 0,
    rep_rank SMALLINT DEFAULT 1,
    prestige SMALLINT DEFAULT 0,
    premium_tier TEXT DEFAULT 'citizen',
    premium_expires TIMESTAMPTZ,
    system_role TEXT DEFAULT 'player',
    is_jailed BOOL DEFAULT FALSE,
    jail_until TIMESTAMPTZ,
    business_efficiency FLOAT DEFAULT 1.0,
    daily_earned BIGINT DEFAULT 0,
    daily_jobs SMALLINT DEFAULT 0,
    daily_gambled BIGINT DEFAULT 0,
    story_flags JSONB DEFAULT '{}'::jsonb,
    referrer_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    weekly_challenges JSONB DEFAULT '{}'::jsonb,
    monthly_challenges JSONB DEFAULT '{}'::jsonb,
    daily_streak SMALLINT DEFAULT 0,
    last_daily TIMESTAMPTZ,
    is_banned BOOL DEFAULT FALSE,
    ban_reason TEXT,
    heat_level SMALLINT DEFAULT 0,
    
    CONSTRAINT valid_district CHECK (district BETWEEN 1 AND 6),
    CONSTRAINT valid_premium_tier CHECK (premium_tier IN ('citizen', 'resident', 'elite', 'obsidian')),
    CONSTRAINT valid_system_role CHECK (system_role IN ('player', 'beta_tester', 'mod', 'dev'))
);

-- Cooldowns Table
CREATE TABLE IF NOT EXISTS cooldowns (
    discord_id BIGINT REFERENCES players(discord_id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (discord_id, action)
);

CREATE INDEX idx_cooldowns_expires ON cooldowns(expires_at);

-- Inventory Table
CREATE TABLE IF NOT EXISTS inventory (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    quantity INT DEFAULT 1 CHECK (quantity > 0),
    equipped BOOL DEFAULT FALSE,
    acquired_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(discord_id, item_id)
);

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    amount BIGINT NOT NULL,
    balance_after BIGINT NOT NULL,
    tx_type TEXT NOT NULL,
    description TEXT,
    related_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_transactions_discord_id ON transactions(discord_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);

-- Interaction Log
CREATE TABLE IF NOT EXISTS interaction_log (
    id BIGSERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL,
    guild_id BIGINT,
    command TEXT NOT NULL,
    params JSONB DEFAULT '{}'::jsonb,
    outcome JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_interaction_log_discord_id ON interaction_log(discord_id);
CREATE INDEX idx_interaction_log_created_at ON interaction_log(created_at);

-- Story Beats Log
CREATE TABLE IF NOT EXISTS story_beats_log (
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    beat_id TEXT NOT NULL,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (discord_id, beat_id)
);

-- AI NPC Memory
CREATE TABLE IF NOT EXISTS ai_npc_memory (
    id BIGSERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL,
    context_summary TEXT NOT NULL,
    ai_response TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_npc_memory_discord_id ON ai_npc_memory(discord_id);
CREATE INDEX idx_ai_npc_memory_npc_id ON ai_npc_memory(npc_id);

-- AI Response Cache
CREATE TABLE IF NOT EXISTS ai_response_cache (
    cache_key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    hit_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_ai_response_cache_expires ON ai_response_cache(expires_at);

-- AI Error Log
CREATE TABLE IF NOT EXISTS ai_error_log (
    id BIGSERIAL PRIMARY KEY,
    npc_id TEXT,
    error_type TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_error_log_created_at ON ai_error_log(created_at);

-- Jobs Active
CREATE TABLE IF NOT EXISTS jobs_active (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    job_id TEXT NOT NULL,
    hired_at TIMESTAMPTZ DEFAULT NOW(),
    last_worked TIMESTAMPTZ,
    last_passive_collected TIMESTAMPTZ DEFAULT NOW(),
    daily_work_count SMALLINT DEFAULT 0,
    UNIQUE(discord_id, job_id)
);

-- Businesses
CREATE TABLE IF NOT EXISTS businesses (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    business_type TEXT NOT NULL,
    district SMALLINT NOT NULL,
    tier SMALLINT DEFAULT 1,
    daily_income INT NOT NULL,
    upkeep_cost INT NOT NULL,
    stock_level SMALLINT DEFAULT 100,
    staff_count SMALLINT DEFAULT 0,
    security_level SMALLINT DEFAULT 0,
    efficiency_override FLOAT,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    last_restocked TIMESTAMPTZ DEFAULT NOW(),
    last_collected TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'active',
    
    CONSTRAINT valid_tier CHECK (tier BETWEEN 1 AND 3),
    CONSTRAINT valid_status CHECK (status IN ('active', 'neglected', 'closed'))
);

-- Market Listings
CREATE TABLE IF NOT EXISTS market_listings (
    id SERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    item_id TEXT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    price_per_unit INT NOT NULL CHECK (price_per_unit > 0),
    listed_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days',
    status TEXT DEFAULT 'active'
);

CREATE INDEX idx_market_listings_expires ON market_listings(expires_at);

-- Investments
CREATE TABLE IF NOT EXISTS investments (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    company_id TEXT NOT NULL,
    shares INT NOT NULL CHECK (shares > 0),
    avg_buy_price INT NOT NULL,
    purchased_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(discord_id, company_id)
);

-- Stock Prices
CREATE TABLE IF NOT EXISTS stock_prices (
    company_id TEXT NOT NULL,
    price INT NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (company_id, recorded_at)
);

CREATE INDEX idx_stock_prices_company_id ON stock_prices(company_id);

-- Stock Sentiment
CREATE TABLE IF NOT EXISTS stock_sentiment (
    company_id TEXT NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    buy_volume BIGINT DEFAULT 0,
    sell_volume BIGINT DEFAULT 0,
    net_pressure BIGINT DEFAULT 0,
    applied BOOL DEFAULT FALSE,
    PRIMARY KEY (company_id, period_start)
);

-- Market News
CREATE TABLE IF NOT EXISTS market_news (
    id SERIAL PRIMARY KEY,
    headline TEXT NOT NULL,
    sector TEXT,
    modifier FLOAT DEFAULT 1.0,
    direction TEXT DEFAULT 'neutral',
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    applied_ticks INT DEFAULT 0
);

CREATE INDEX idx_market_news_expires ON market_news(expires_at);

-- Stock Events
CREATE TABLE IF NOT EXISTS stock_events (
    id SERIAL PRIMARY KEY,
    company_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    multiplier FLOAT NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ends_at TIMESTAMPTZ NOT NULL
);

-- Factions
CREATE TABLE IF NOT EXISTS factions (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    tag TEXT UNIQUE NOT NULL,
    faction_type TEXT DEFAULT 'standard',
    leader_id BIGINT NOT NULL REFERENCES players(discord_id),
    treasury BIGINT DEFAULT 0,
    reputation INT DEFAULT 0,
    discord_server_id BIGINT,
    weekly_dues INT DEFAULT 500,
    founded_at TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'active',
    
    CONSTRAINT valid_status CHECK (status IN ('active', 'disbanded'))
);

-- Faction Members
CREATE TABLE IF NOT EXISTS faction_members (
    faction_id INT NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member',
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    weekly_contrib BIGINT DEFAULT 0,
    PRIMARY KEY (faction_id, discord_id),
    CONSTRAINT valid_role CHECK (role IN ('member', 'officer', 'leader'))
);

-- District Control
CREATE TABLE IF NOT EXISTS district_control (
    district SMALLINT PRIMARY KEY,
    faction_id INT REFERENCES factions(id) ON DELETE SET NULL,
    controlled_since TIMESTAMPTZ DEFAULT NOW(),
    contest_ends TIMESTAMPTZ,
    CONSTRAINT valid_district CHECK (district BETWEEN 1 AND 6)
);

-- Heist Sessions
CREATE TABLE IF NOT EXISTS heist_sessions (
    id SERIAL PRIMARY KEY,
    initiator_id BIGINT NOT NULL REFERENCES players(discord_id),
    district SMALLINT NOT NULL,
    state TEXT DEFAULT 'pending',
    participants JSONB DEFAULT '[]'::jsonb,
    loot BIGINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    CONSTRAINT valid_state CHECK (state IN ('pending', 'active', 'completed', 'failed'))
);

-- Seasons
CREATE TABLE IF NOT EXISTS seasons (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    theme TEXT,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    is_active BOOL DEFAULT FALSE,
    global_bonuses JSONB DEFAULT '{}'::jsonb
);

-- Challenges
CREATE TABLE IF NOT EXISTS challenges (
    id SERIAL PRIMARY KEY,
    season_id TEXT REFERENCES seasons(id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    challenge_type TEXT NOT NULL,
    requirement JSONB NOT NULL,
    reward JSONB NOT NULL,
    resets_at TIMESTAMPTZ
);

-- Billboard Queue
CREATE TABLE IF NOT EXISTS billboard_queue (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id),
    brief TEXT NOT NULL,
    ai_output TEXT,
    status TEXT DEFAULT 'pending',
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    posted_at TIMESTAMPTZ,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'approved', 'rejected', 'posted'))
);

-- Server Premium
CREATE TABLE IF NOT EXISTS server_premium (
    guild_id BIGINT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    features JSONB DEFAULT '{}'::jsonb
);

-- City Feed Log
CREATE TABLE IF NOT EXISTS city_feed_log (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    event_key TEXT NOT NULL,
    content TEXT,
    posted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Invite Tracker
CREATE TABLE IF NOT EXISTS invite_tracker (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id),
    invite_code TEXT NOT NULL,
    uses INT DEFAULT 0,
    successful INT DEFAULT 0,
    sc_earned BIGINT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tester Applications
CREATE TABLE IF NOT EXISTS tester_applications (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL REFERENCES players(discord_id),
    reason TEXT NOT NULL,
    activity_level TEXT,
    status TEXT DEFAULT 'pending',
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by BIGINT,
    CONSTRAINT valid_status CHECK (status IN ('pending', 'approved', 'rejected'))
);

-- Tickets
CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    discord_id BIGINT NOT NULL,
    category TEXT NOT NULL,
    channel_id BIGINT NOT NULL,
    status TEXT DEFAULT 'open',
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    closed_by BIGINT,
    CONSTRAINT valid_status CHECK (status IN ('open', 'closed'))
);

-- Bounties
CREATE TABLE IF NOT EXISTS bounties (
    id SERIAL PRIMARY KEY,
    poster_id BIGINT NOT NULL REFERENCES players(discord_id),
    target_id BIGINT NOT NULL REFERENCES players(discord_id),
    amount INT NOT NULL CHECK (amount > 0),
    status TEXT DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    claimed_by BIGINT REFERENCES players(discord_id),
    CONSTRAINT valid_status CHECK (status IN ('active', 'claimed', 'expired'))
);

-- Weekly Gazette
CREATE TABLE IF NOT EXISTS weekly_gazette (
    id SERIAL PRIMARY KEY,
    season_id TEXT REFERENCES seasons(id),
    content JSONB NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    posted_at TIMESTAMPTZ
);

-- Heartbeat Log
CREATE TABLE IF NOT EXISTS heartbeat_log (
    id SERIAL PRIMARY KEY,
    bot_id BIGINT NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    guild_count INT,
    latency FLOAT
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_players_discord_id ON players(discord_id);
CREATE INDEX IF NOT EXISTS idx_players_district ON players(district);
CREATE INDEX IF NOT EXISTS idx_players_rep_rank ON players(rep_rank);
CREATE INDEX IF NOT EXISTS idx_players_premium_tier ON players(premium_tier);
CREATE INDEX IF NOT EXISTS idx_players_is_jailed ON players(is_jailed);
CREATE INDEX IF NOT EXISTS idx_businesses_discord_id ON businesses(discord_id);
CREATE INDEX IF NOT EXISTS idx_businesses_district ON businesses(district);
CREATE INDEX IF NOT EXISTS idx_investments_discord_id ON investments(discord_id);
CREATE INDEX IF NOT EXISTS idx_faction_members_faction_id ON faction_members(faction_id);
CREATE INDEX IF NOT EXISTS idx_faction_members_discord_id ON faction_members(discord_id);
CREATE INDEX IF NOT EXISTS idx_bounties_target_id ON bounties(target_id);
CREATE INDEX IF NOT EXISTS idx_bounties_status ON bounties(status);

-- Create function for updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for players table
DROP TRIGGER IF EXISTS update_players_updated_at ON players;
CREATE TRIGGER update_players_updated_at
    BEFORE UPDATE ON players
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Insert default district control
INSERT INTO district_control (district, faction_id, controlled_since)
VALUES 
    (1, NULL, NOW()),
    (2, NULL, NOW()),
    (3, NULL, NOW()),
    (4, NULL, NOW()),
    (5, NULL, NOW()),
    (6, NULL, NOW())
ON CONFLICT (district) DO NOTHING;