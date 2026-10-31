"""Fixed research settings. Changing any of these after a test has run is logged in RESEARCH_LOG.md."""

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "research" / "results"

LOT_MWH = 50
MIN_TRADES_TO_TRADE = 10        # below this NSE sets the settlement price by formula
MAX_SHARE_OF_DAY = 0.05         # a strategy trades at most 5% of the day's lots
MARGIN_RATE = 0.20              # assumed initial margin, share of notional

# Pre-futures period used to choose and calibrate models (no futures existed then)
CALIBRATION_START = "2023-04-04"   # Rs 10,000 cap in force from here
CALIBRATION_END = "2025-06-30"


@dataclass(frozen=True)
class Costs:
    """Per side. Prices in Rs/MWh."""
    half_spread: float = 5.0       # NSE market-maker obligation: spread <= Rs 10/MWh
    slippage: float = 5.0
    exchange_fee: float = 0.0001   # share of value; NSE waiver ended Dec 2025, rate unconfirmed
    ctt_sell: float = 0.0001       # commodity transaction tax, sell side
    stamp_buy: float = 0.00002
    brokerage_per_order: float = 20.0

    def per_mwh(self, price, side, lots=1, at_expiry=False):
        """Cost in Rs/MWh of one side of a trade. Expiry is cash settled: no spread or slippage."""
        c = price * self.exchange_fee
        c += price * (self.ctt_sell if side < 0 else self.stamp_buy)
        if not at_expiry:
            c += self.half_spread + self.slippage + self.brokerage_per_order / (lots * LOT_MWH)
        return c

    def scaled(self, k):
        return Costs(self.half_spread * k, self.slippage * k, self.exchange_fee * k,
                     self.ctt_sell, self.stamp_buy, self.brokerage_per_order * k)
