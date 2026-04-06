from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, List
import re


def format_sc(amount: int) -> str:
    if amount >= 1000000:
        return f"{amount/1000000:.1f}M"
    elif amount >= 1000:
        return f"{amount/1000:.1f}K"
    else:
        return str(amount)


def format_time(seconds: int) -> str:
    if seconds <= 0:
        return "now"
    
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and len(parts) < 3:
        parts.append(f"{secs}s")
    
    return " ".join(parts[:3]) if parts else "0s"


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def format_relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    diff = now - dt
    
    if diff.total_seconds() < 60:
        return "just now"
    elif diff.total_seconds() < 3600:
        minutes = int(diff.total_seconds() // 60)
        return f"{minutes}m ago"
    elif diff.total_seconds() < 86400:
        hours = int(diff.total_seconds() // 3600)
        return f"{hours}h ago"
    elif diff.total_seconds() < 604800:
        days = int(diff.total_seconds() // 86400)
        return f"{days}d ago"
    else:
        return dt.strftime("%b %d")


def format_number(num: int) -> str:
    if num >= 1000000:
        return f"{num/1000000:.1f}M"
    elif num >= 1000:
        return f"{num/1000:.1f}K"
    else:
        return str(num)


def progress_bar(current: int, max_value: int, length: int = 10, filled: str = "█", empty: str = "░") -> str:
    if max_value <= 0:
        return empty * length
    
    ratio = min(current / max_value, 1.0)
    filled_count = int(length * ratio)
    
    return filled * filled_count + empty * (length - filled_count)


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def capitalize_words(text: str) -> str:
    return " ".join(word.capitalize() for word in text.split())


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    
    return f"{n}{suffix}"


def format_percent(value: float, decimals: int = 1) -> str:
    if value > 0:
        return f"+{value * 100:.{decimals}f}%"
    else:
        return f"{value * 100:.{decimals}f}%"


def format_delta(delta: int) -> str:
    if delta > 0:
        return f"+{format_number(delta)}"
    elif delta < 0:
        return f"-{format_number(abs(delta))}"
    else:
        return "0"


def parse_duration(duration_str: str) -> Optional[int]:
    pattern = r"^(\d+)([smhdw])$"
    match = re.match(pattern, duration_str.lower())
    
    if not match:
        return None
    
    value = int(match.group(1))
    unit = match.group(2)
    
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800
    }
    
    return value * multipliers.get(unit, 1)


def format_list(items: List[str], conjunction: str = "and") -> str:
    if not items:
        return ""
    
    if len(items) == 1:
        return items[0]
    
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    
    return f"{', '.join(items[:-1])}, {conjunction} {items[-1]}"


def format_streak(streak: int) -> str:
    if streak <= 0:
        return "No streak"
    elif streak == 1:
        return "1 day"
    else:
        return f"{streak} days"


def format_balance(wallet: int, bank: int) -> str:
    total = wallet + bank
    return f"👛 {format_sc(wallet)} | 🏦 {format_sc(bank)} | 📊 {format_sc(total)}"