import os
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()


class Config:
    
    DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
    MOD_BOT_TOKEN: str = os.getenv("MOD_BOT_TOKEN", "")
    COMMAND_PREFIX: str = os.getenv("COMMAND_PREFIX", "s!")
    TEST_GUILD_ID: Optional[int] = int(os.getenv("TEST_GUILD_ID")) if os.getenv("TEST_GUILD_ID") else None
    
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://localhost:5432/simcoin")
    DATABASE_POOL_SIZE: int = int(os.getenv("DATABASE_POOL_SIZE", "20"))
    DATABASE_MAX_OVERFLOW: int = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    AI_TIMEOUT_SECONDS: float = float(os.getenv("AI_TIMEOUT_SECONDS", "3.0"))
    AI_CACHE_TTL_HOURS: int = int(os.getenv("AI_CACHE_TTL_HOURS", "72"))
    AI_MAX_RETRIES: int = int(os.getenv("AI_MAX_RETRIES", "2"))
    
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")
    
    MAX_WALLET: int = int(os.getenv("MAX_WALLET", "1000000000"))
    MAX_BANK: int = int(os.getenv("MAX_BANK", "10000000000"))
    DAILY_BASE_MIN: int = int(os.getenv("DAILY_BASE_MIN", "200"))
    DAILY_BASE_MAX: int = int(os.getenv("DAILY_BASE_MAX", "800"))
    
    WORK_COOLDOWN: int = int(os.getenv("WORK_COOLDOWN", "3600"))
    CRIME_COOLDOWN: int = int(os.getenv("CRIME_COOLDOWN", "900"))
    TRAVEL_COOLDOWN: int = int(os.getenv("TRAVEL_COOLDOWN", "300"))
    INVEST_COOLDOWN: int = int(os.getenv("INVEST_COOLDOWN", "1800"))
    DAILY_COOLDOWN: int = int(os.getenv("DAILY_COOLDOWN", "86400"))
    
    WALLET_TAX_RATE: float = float(os.getenv("WALLET_TAX_RATE", "0.01"))
    WALLET_TAX_MAX: int = int(os.getenv("WALLET_TAX_MAX", "500"))
    WEALTH_TAX_THRESHOLD: int = int(os.getenv("WEALTH_TAX_THRESHOLD", "500000"))
    WEALTH_TAX_RATE: float = float(os.getenv("WEALTH_TAX_RATE", "0.005"))
    INVESTMENT_GAIN_TAX: float = float(os.getenv("INVESTMENT_GAIN_TAX", "0.15"))
    
    JAIL_BASE_HOURS: int = int(os.getenv("JAIL_BASE_HOURS", "2"))
    JAIL_MAX_HOURS: int = int(os.getenv("JAIL_MAX_HOURS", "48"))
    
    BUSINESS_NEGLECT_HOURS: int = int(os.getenv("BUSINESS_NEGLECT_HOURS", "48"))
    BUSINESS_EFFICIENCY_PENALTY: float = float(os.getenv("BUSINESS_EFFICIENCY_PENALTY", "0.2"))
    
    GBM_MU: float = float(os.getenv("GBM_MU", "0.05"))
    GBM_SIGMA: float = float(os.getenv("GBM_SIGMA", "0.2"))
    SENTIMENT_MAX_PRESSURE: float = float(os.getenv("SENTIMENT_MAX_PRESSURE", "0.1"))
    STOCK_PRICE_FLOOR: int = int(os.getenv("STOCK_PRICE_FLOOR", "10"))
    STOCK_PRICE_CEILING: int = int(os.getenv("STOCK_PRICE_CEILING", "10000"))
    
    IMAGE_CACHE_TTL_HOURS: int = int(os.getenv("IMAGE_CACHE_TTL_HOURS", "24"))
    IMAGE_THREAD_POOL_SIZE: int = int(os.getenv("IMAGE_THREAD_POOL_SIZE", "4"))
    

    DATA_DIR: str = os.getenv("DATA_DIR", "data/")
    
    REP_RANKS: list = [
        {"rank": 1, "min_rep": 0, "title": "Newcomer"},
        {"rank": 2, "min_rep": 100, "title": "Recognized"},
        {"rank": 3, "min_rep": 500, "title": "Known"},
        {"rank": 4, "min_rep": 1000, "title": "Respected"},
        {"rank": 5, "min_rep": 2500, "title": "Prominent"},
        {"rank": 6, "min_rep": 5000, "title": "Influential"},
        {"rank": 7, "min_rep": 10000, "title": "City Icon"},
        {"rank": 8, "min_rep": 25000, "title": "Legend"},
        {"rank": 9, "min_rep": 50000, "title": "Mythic"},
        {"rank": 10, "min_rep": 100000, "title": "Simora Royalty"}
    ]
    
    DISTRICTS: list = [
        {"id": 1, "name": "Slums", "required_rep": 0, "color": "#8B5A2B"},
        {"id": 2, "name": "Industrial", "required_rep": 2, "color": "#4A4A4A"},
        {"id": 3, "name": "Downtown", "required_rep": 4, "color": "#2E8B57"},
        {"id": 4, "name": "Financial District", "required_rep": 6, "color": "#FFD700"},
        {"id": 5, "name": "The Strip", "required_rep": 8, "color": "#FF69B4"},
        {"id": 6, "name": "Underground", "required_rep": 10, "color": "#800080"}
    ]
    
    PREMIUM_TIERS: dict = {
        "citizen": {"price": 0, "daily_bonus": 1.0, "cooldown_reduction": 0, "max_jobs": 3, "max_businesses": 3, "memory_depth": 5},
        "resident": {"price": 2.99, "daily_bonus": 1.2, "cooldown_reduction": 0.1, "max_jobs": 3, "max_businesses": 3, "memory_depth": 5},
        "elite": {"price": 7.99, "daily_bonus": 1.4, "cooldown_reduction": 0.2, "max_jobs": 4, "max_businesses": 4, "memory_depth": 10},
        "obsidian": {"price": 19.99, "daily_bonus": 2.0, "cooldown_reduction": 0.3, "max_jobs": 5, "max_businesses": 5, "memory_depth": 20}
    }
    
    OFFICIAL_GUILD_ID: int = int(os.getenv("OFFICIAL_GUILD_ID", "0"))
    
    PREMIUM_RESIDENT_PRICE: float = float(os.getenv("PREMIUM_RESIDENT_PRICE", "2.99"))
    PREMIUM_ELITE_PRICE: float = float(os.getenv("PREMIUM_ELITE_PRICE", "7.99"))
    PREMIUM_OBSIDIAN_PRICE: float = float(os.getenv("PREMIUM_OBSIDIAN_PRICE", "19.99"))
    
    SERVER_PREMIUM_PRICE: float = float(os.getenv("SERVER_PREMIUM_PRICE", "9.99"))
    
    STRIPE_API_KEY: Optional[str] = os.getenv("STRIPE_API_KEY", None)
    STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET", None)
    
    TOP_GG_TOKEN: Optional[str] = os.getenv("TOP_GG_TOKEN", None)
    
    SENTRY_DSN: Optional[str] = os.getenv("SENTRY_DSN", None)
    
    HEARTBEAT_INTERVAL: int = int(os.getenv("HEARTBEAT_INTERVAL", "60"))
    HEALTH_CHECK_ENABLED: bool = os.getenv("HEALTH_CHECK_ENABLED", "true").lower() == "true"
    
    ENABLE_ANALYST: bool = os.getenv("ENABLE_ANALYST", "true").lower() == "true"
    ENABLE_BILLBOARD: bool = os.getenv("ENABLE_BILLBOARD", "true").lower() == "true"
    ENABLE_SEASONS: bool = os.getenv("ENABLE_SEASONS", "true").lower() == "true"
    ENABLE_REFERRALS: bool = os.getenv("ENABLE_REFERRALS", "true").lower() == "true"
    ENABLE_BOUNTIES: bool = os.getenv("ENABLE_BOUNTIES", "true").lower() == "true"
    ENABLE_TICKETS: bool = os.getenv("ENABLE_TICKETS", "true").lower() == "true"
    
    GLOBAL_RATE_LIMIT: int = int(os.getenv("GLOBAL_RATE_LIMIT", "30"))
    GLOBAL_RATE_LIMIT_PERIOD: int = int(os.getenv("GLOBAL_RATE_LIMIT_PERIOD", "10"))
    
    MAINTENANCE_MODE: bool = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
    MAINTENANCE_MESSAGE: str = os.getenv("MAINTENANCE_MESSAGE", "SimCoin is under maintenance. Please check back soon.")
    
    DEV_MODE: bool = os.getenv("DEV_MODE", "false").lower() == "true"
    DEV_GUILD_IDS: List[int] = [int(x.strip()) for x in os.getenv("DEV_GUILD_IDS", "").split(",") if x.strip()]
    
    BACKUP_ENABLED: bool = os.getenv("BACKUP_ENABLED", "true").lower() == "true"
    BACKUP_INTERVAL_HOURS: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))
    BACKUP_RETENTION_DAYS: int = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
    
    ANNOUNCEMENT_CHANNEL_ID: Optional[int] = int(os.getenv("ANNOUNCEMENT_CHANNEL_ID")) if os.getenv("ANNOUNCEMENT_CHANNEL_ID") else None
    MOD_ALERTS_CHANNEL_ID: Optional[int] = int(os.getenv("MOD_ALERTS_CHANNEL_ID")) if os.getenv("MOD_ALERTS_CHANNEL_ID") else None
    MOD_DAILY_CHANNEL_ID: Optional[int] = int(os.getenv("MOD_DAILY_CHANNEL_ID")) if os.getenv("MOD_DAILY_CHANNEL_ID") else None
    MOD_ACTIONS_CHANNEL_ID: Optional[int] = int(os.getenv("MOD_ACTIONS_CHANNEL_ID")) if os.getenv("MOD_ACTIONS_CHANNEL_ID") else None
    CITY_FEED_CHANNEL_ID: Optional[int] = int(os.getenv("CITY_FEED_CHANNEL_ID")) if os.getenv("CITY_FEED_CHANNEL_ID") else None
    WELCOME_CHANNEL_ID: Optional[int] = int(os.getenv("WELCOME_CHANNEL_ID")) if os.getenv("WELCOME_CHANNEL_ID") else None
    INVITE_LEADERBOARD_CHANNEL_ID: Optional[int] = int(os.getenv("INVITE_LEADERBOARD_CHANNEL_ID")) if os.getenv("INVITE_LEADERBOARD_CHANNEL_ID") else None
    
    BETA_TESTER_ROLE_ID: Optional[int] = int(os.getenv("BETA_TESTER_ROLE_ID")) if os.getenv("BETA_TESTER_ROLE_ID") else None
    MOD_ROLE_ID: Optional[int] = int(os.getenv("MOD_ROLE_ID")) if os.getenv("MOD_ROLE_ID") else None
    DEV_ROLE_ID: Optional[int] = int(os.getenv("DEV_ROLE_ID")) if os.getenv("DEV_ROLE_ID") else None
    PREMIUM_RESIDENT_ROLE_ID: Optional[int] = int(os.getenv("PREMIUM_RESIDENT_ROLE_ID")) if os.getenv("PREMIUM_RESIDENT_ROLE_ID") else None
    PREMIUM_ELITE_ROLE_ID: Optional[int] = int(os.getenv("PREMIUM_ELITE_ROLE_ID")) if os.getenv("PREMIUM_ELITE_ROLE_ID") else None
    PREMIUM_OBSIDIAN_ROLE_ID: Optional[int] = int(os.getenv("PREMIUM_OBSIDIAN_ROLE_ID")) if os.getenv("PREMIUM_OBSIDIAN_ROLE_ID") else None
    
    DISTRICT_SLUMS_ROLE_ID: Optional[int] = int(os.getenv("DISTRICT_SLUMS_ROLE_ID")) if os.getenv("DISTRICT_SLUMS_ROLE_ID") else None
    DISTRICT_INDUSTRIAL_ROLE_ID: Optional[int] = int(os.getenv("DISTRICT_INDUSTRIAL_ROLE_ID")) if os.getenv("DISTRICT_INDUSTRIAL_ROLE_ID") else None
    DISTRICT_DOWNTOWN_ROLE_ID: Optional[int] = int(os.getenv("DISTRICT_DOWNTOWN_ROLE_ID")) if os.getenv("DISTRICT_DOWNTOWN_ROLE_ID") else None
    DISTRICT_FINANCIAL_ROLE_ID: Optional[int] = int(os.getenv("DISTRICT_FINANCIAL_ROLE_ID")) if os.getenv("DISTRICT_FINANCIAL_ROLE_ID") else None
    DISTRICT_STRIP_ROLE_ID: Optional[int] = int(os.getenv("DISTRICT_STRIP_ROLE_ID")) if os.getenv("DISTRICT_STRIP_ROLE_ID") else None
    DISTRICT_UNDERGROUND_ROLE_ID: Optional[int] = int(os.getenv("DISTRICT_UNDERGROUND_ROLE_ID")) if os.getenv("DISTRICT_UNDERGROUND_ROLE_ID") else None
    
    @classmethod
    def validate(cls) -> bool:
        required = [
            ("DISCORD_TOKEN", cls.DISCORD_TOKEN),
            ("DATABASE_URL", cls.DATABASE_URL),
            ("GROQ_API_KEY", cls.GROQ_API_KEY),
            ("GEMINI_API_KEY", cls.GEMINI_API_KEY),
            ("OFFICIAL_GUILD_ID", cls.OFFICIAL_GUILD_ID),
        ]
        
        missing = [name for name, value in required if not value or (name == "OFFICIAL_GUILD_ID" and value == 0)]
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        if cls.DEV_MODE and not cls.DEV_GUILD_IDS:
            raise ValueError("DEV_MODE is enabled but DEV_GUILD_IDS is empty")
        
        return True