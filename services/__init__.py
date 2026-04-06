from services.player_service import PlayerService
from services.economy_service import EconomyService
from services.crime_service import CrimeService
from services.market_service import MarketService
from services.investment_service import InvestmentService
from services.business_service import BusinessService
from services.faction_service import FactionService
from services.ai_service import AIService
from services.image_service import ImageService
from services.world_service import WorldService


class ServiceContainer:
    
    def __init__(
        self,
        player: PlayerService,
        economy: EconomyService,
        crime: CrimeService,
        market: MarketService,
        investment: InvestmentService,
        business: BusinessService,
        faction: FactionService,
        ai: AIService,
        image: ImageService,
        world: WorldService
    ):
        self.player = player
        self.economy = economy
        self.crime = crime
        self.market = market
        self.investment = investment
        self.business = business
        self.faction = faction
        self.ai = ai
        self.image = image
        self.world = world


__all__ = [
    "PlayerService",
    "EconomyService", 
    "CrimeService",
    "MarketService",
    "InvestmentService",
    "BusinessService",
    "FactionService",
    "AIService",
    "ImageService",
    "WorldService",
    "ServiceContainer"
]