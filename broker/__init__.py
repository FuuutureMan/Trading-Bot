from config import settings

from .paper_portfolio import PaperPortfolio
from .webull_portfolio import WebullPortfolio


def create_portfolio():
    if settings.BROKER_MODE == "webull":
        return WebullPortfolio()
    return PaperPortfolio(starting_balance=settings.PAPER_BALANCE)
