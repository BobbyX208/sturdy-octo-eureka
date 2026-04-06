from typing import Dict, List, Any, Tuple

class GameConstants:
    
    JOB_BASE_PAY: Dict[str, int] = {
        "street_cleaner": 50,
        "delivery_driver": 80,
        "security_guard": 100,
        "cashier": 70,
        "warehouse_worker": 90,
        "office_clerk": 120,
        "bartender": 110,
        "junior_dev": 150,
        "trader": 200,
        "analyst": 250,
        "manager": 300,
    }
    
    JOB_HIRE_CHANCE: Dict[str, float] = {
        "street_cleaner": 0.95,
        "delivery_driver": 0.90,
        "security_guard": 0.85,
        "cashier": 0.90,
        "warehouse_worker": 0.85,
        "office_clerk": 0.80,
        "bartender": 0.85,
        "junior_dev": 0.70,
        "trader": 0.60,
        "analyst": 0.55,
        "manager": 0.50,
    }
    
    JOB_PASSIVE_INCOME: Dict[str, int] = {
        "street_cleaner": 25,
        "delivery_driver": 40,
        "security_guard": 50,
        "cashier": 35,
        "warehouse_worker": 45,
        "office_clerk": 60,
        "bartender": 55,
        "junior_dev": 75,
        "trader": 100,
        "analyst": 125,
        "manager": 150,
    }
    
    CRIME_TYPES: Dict[str, Dict[str, Any]] = {
        "pickpocket": {
            "min_rep": 0,
            "success_rate": 0.55,
            "min_loot": 30,
            "max_loot": 120,
            "min_fine": 150,
            "max_fine": 400,
            "jail_chance": 0.25,
            "rep_loss": 8,
        },
        "shoplift": {
            "min_rep": 0,
            "success_rate": 0.48,
            "min_loot": 60,
            "max_loot": 250,
            "min_fine": 300,
            "max_fine": 800,
            "jail_chance": 0.32,
            "rep_loss": 15,
        },
        "burglary": {
            "min_rep": 2,
            "success_rate": 0.38,
            "min_loot": 300,
            "max_loot": 1000,
            "min_fine": 1500,
            "max_fine": 5000,
            "jail_chance": 0.45,
            "rep_loss": 35,
        },
        "car_theft": {
            "min_rep": 3,
            "success_rate": 0.32,
            "min_loot": 600,
            "max_loot": 2000,
            "min_fine": 3000,
            "max_fine": 8000,
            "jail_chance": 0.52,
            "rep_loss": 55,
        },
        "bank_robbery": {
            "min_rep": 5,
            "success_rate": 0.22,
            "min_loot": 3000,
            "max_loot": 12000,
            "min_fine": 15000,
            "max_fine": 75000,
            "jail_chance": 0.68,
            "rep_loss": 120,
        },
        "heist": {
            "min_rep": 6,
            "success_rate": 0.28,
            "min_loot": 8000,
            "max_loot": 35000,
            "min_fine": 25000,
            "max_fine": 120000,
            "jail_chance": 0.62,
            "rep_loss": 90,
        },
    }
    
    GAMBLING_GAMES: Dict[str, Dict[str, Any]] = {
        "slots": {
            "cost": 100,
            "payouts": {
                "777": 35.0,
                "bar": 8.0,
                "cherry": 4.0,
                "lemon": 1.5,
            },
            "house_edge": 0.12,
        },
        "blackjack": {
            "min_bet": 100,
            "max_bet": 10000,
            "house_edge": 0.01,
        },
        "dice": {
            "min_bet": 50,
            "max_bet": 5000,
            "multiplier_range": (1.5, 8.0),
        },
        "roulette": {
            "min_bet": 100,
            "max_bet": 10000,
            "payouts": {
                "single": 32.0,
                "red": 1.8,
                "black": 1.8,
                "even": 1.8,
                "odd": 1.8,
                "dozen": 2.5,
            },
        },
    }
    
    HEIST_LOBBY_SECONDS: int = 90
    HEIST_MIN_PLAYERS: int = 2
    HEIST_MAX_PLAYERS: int = 5
    HEIST_BASE_SUCCESS_RATE: float = 0.42
    HEIST_PLAYER_BONUS: float = 0.04
    
    FACTION_MAX_MEMBERS: int = 20
    FACTION_BASE_CREATION_COST: int = 100000
    FACTION_MIN_REP_TO_CREATE: int = 6
    FACTION_CLAIM_COST: int = 10000
    FACTION_WEEKLY_DUES_BASE: int = 500
    
    DISTRICT_BONUSES: Dict[int, Dict[str, Any]] = {
        1: {"name": "Slums", "crime_bonus": 0.08, "job_penalty": -0.15, "business_penalty": -0.15},
        2: {"name": "Industrial", "job_bonus": 0.08, "crime_penalty": -0.08, "business_bonus": 0.05},
        3: {"name": "Downtown", "business_bonus": 0.10, "job_bonus": 0.05, "crime_penalty": -0.08},
        4: {"name": "Financial District", "investment_bonus": 0.12, "crime_penalty": -0.12, "business_bonus": 0.08},
        5: {"name": "The Strip", "gambling_bonus": 0.08, "crime_bonus": 0.05, "business_bonus": 0.08},
        6: {"name": "Underground", "crime_bonus": 0.12, "heist_bonus": 0.08, "business_penalty": -0.08},
    }
    
    PRESTIGE_MIN_REP: int = 8
    PRESTIGE_MIN_EARNED: int = 1000000
    PRESTIGE_BONUS_MULTIPLIER: float = 0.05
    
    STREAK_DAILY_BONUS_MULTIPLIER: float = 0.08
    STREAK_MAX_DAYS: int = 7
    STREAK_MISS_PENALTY: int = 100
    STREAK_MISS_CONSECUTIVE_LIMIT: int = 3
    
    REFERRAL_BONUS: int = 500
    REFERRAL_MAX_PER_USER: int = 100
    
    MAX_DAILY_JOBS: int = 5
    MAX_DAILY_GAMBLED: int = 50000
    BANK_WITHDRAW_FEE: float = 0.01
    BANK_DEPOSIT_FEE: float = 0.005
    
    PROFILE_CARD_WIDTH: int = 800
    PROFILE_CARD_HEIGHT: int = 400
    MAP_CARD_WIDTH: int = 1200
    MAP_CARD_HEIGHT: int = 800
    LEADERBOARD_CARD_WIDTH: int = 600
    LEADERBOARD_CARD_HEIGHT: int = 800
    
    COLOR_PRIMARY: tuple = (46, 139, 87)
    COLOR_SUCCESS: tuple = (34, 139, 34)
    COLOR_ERROR: tuple = (220, 20, 60)
    COLOR_WARNING: tuple = (255, 165, 0)
    COLOR_INFO: tuple = (70, 130, 200)
    COLOR_PREMIUM_CITIZEN: tuple = (128, 128, 128)
    COLOR_PREMIUM_RESIDENT: tuple = (0, 128, 255)
    COLOR_PREMIUM_ELITE: tuple = (255, 215, 0)
    COLOR_PREMIUM_OBSIDIAN: tuple = (128, 0, 128)
    
    EMOJI_SC: str = "<:simcoin:1234567890>"
    EMOJI_REP: str = "⭐"
    EMOJI_BANK: str = "🏦"
    EMOJI_WALLET: str = "👛"
    EMOJI_JAIL: str = "🔒"
    EMOJI_PREMIUM: str = "💎"
    EMOJI_CRIME: str = "🔪"
    EMOJI_BUSINESS: str = "🏪"
    EMOJI_STOCKS_UP: str = "📈"
    EMOJI_STOCKS_DOWN: str = "📉"
    EMOJI_STOCKS_FLAT: str = "📊"
    EMOJI_FACTION: str = "⚔️"

    IMAGE_CACHE_TTL_HOURS: int = 24