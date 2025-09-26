"""Portfolio generation for Basel Capital Engine testing and demonstrations."""

from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import random
import numpy as np
from datetime import datetime, timedelta
import uuid

from ..core.exposure import Portfolio, Exposure, ExposureType, ExposureClass, CreditRiskMitigation
from ..core.capital import Capital, CapitalComponents, CapitalInstrument, CapitalTier


class BankSize(str, Enum):
    """Bank size categories for portfolio generation."""
    
    SMALL = "small"           # Community bank
    MEDIUM = "medium"         # Regional bank
    LARGE = "large"          # Large commercial bank
    GSIB = "gsib"            # Global systemically important bank


class PortfolioGenerator:
    """Generator for synthetic bank portfolios with realistic characteristics."""
    
    def __init__(self, seed: Optional[int] = None):
        """Initialize generator with optional random seed for reproducibility."""
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
        
        self.seed = seed
        
    def generate_bank_portfolio(self, size: BankSize = BankSize.MEDIUM, 
                              bank_name: Optional[str] = None) -> Tuple[Portfolio, Capital]:
        """Generate a complete synthetic bank portfolio and capital structure."""
        bank_name = bank_name or f"Synthetic Bank {random.randint(1000, 9999)}"
        
        # Generate portfolio based on bank size
        if size == BankSize.SMALL:
            portfolio = self._generate_small_bank_portfolio(bank_name)
            capital = self._generate_small_bank_capital(bank_name)
        elif size == BankSize.MEDIUM:
            portfolio = self._generate_medium_bank_portfolio(bank_name)
            capital = self._generate_medium_bank_capital(bank_name)
        elif size == BankSize.LARGE:
            portfolio = self._generate_large_bank_portfolio(bank_name)
            capital = self._generate_large_bank_capital(bank_name)
        else:  # GSIB
            portfolio = self._generate_gsib_portfolio(bank_name)
            capital = self._generate_gsib_capital(bank_name)
        
        return portfolio, capital
    
    def _generate_small_bank_portfolio(self, bank_name: str) -> Portfolio:
        """Generate portfolio for a small community bank."""
        portfolio = Portfolio(
            portfolio_id=f"portfolio_{uuid.uuid4().hex[:8]}",
            bank_name=bank_name,
            reporting_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        # Small bank characteristics: mostly retail loans and mortgages
        total_assets = random.uniform(500e6, 5e9)  # €500M - €5B
        
        # Generate loans (80% of assets)
        loan_amount = total_assets * 0.8
        self._add_retail_loans(portfolio, loan_amount * 0.4)  # 40% retail
        self._add_mortgage_loans(portfolio, loan_amount * 0.45)  # 45% mortgages
        self._add_commercial_loans(portfolio, loan_amount * 0.15)  # 15% commercial
        
        # Generate securities (15% of assets)
        securities_amount = total_assets * 0.15
        self._add_government_securities(portfolio, securities_amount * 0.7)
        self._add_corporate_bonds(portfolio, securities_amount * 0.3)
        
        # Generate cash and other assets (5% of assets)
        cash_amount = total_assets * 0.05
        self._add_cash_assets(portfolio, cash_amount)
        
        # Small amount of off-balance sheet
        self._add_commitments(portfolio, total_assets * 0.1)
        
        return portfolio
    
    def _generate_medium_bank_portfolio(self, bank_name: str) -> Portfolio:
        """Generate portfolio for a medium regional bank."""
        portfolio = Portfolio(
            portfolio_id=f"portfolio_{uuid.uuid4().hex[:8]}",
            bank_name=bank_name,
            reporting_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        # Medium bank characteristics: diversified lending and some trading
        total_assets = random.uniform(5e9, 50e9)  # €5B - €50B
        
        # Generate loans (70% of assets)
        loan_amount = total_assets * 0.7
        self._add_retail_loans(portfolio, loan_amount * 0.3)
        self._add_mortgage_loans(portfolio, loan_amount * 0.35)
        self._add_commercial_loans(portfolio, loan_amount * 0.25)
        self._add_corporate_loans(portfolio, loan_amount * 0.1)
        
        # Generate securities (20% of assets)
        securities_amount = total_assets * 0.2
        self._add_government_securities(portfolio, securities_amount * 0.5)
        self._add_corporate_bonds(portfolio, securities_amount * 0.3)
        self._add_bank_securities(portfolio, securities_amount * 0.2)
        
        # Generate trading assets (5% of assets)
        trading_amount = total_assets * 0.05
        self._add_trading_securities(portfolio, trading_amount * 0.7)
        self._add_derivatives(portfolio, trading_amount * 0.3)
        
        # Cash and other assets (5% of assets)
        self._add_cash_assets(portfolio, total_assets * 0.05)
        
        # Off-balance sheet exposures
        self._add_commitments(portfolio, total_assets * 0.2)
        self._add_guarantees(portfolio, total_assets * 0.05)
        
        return portfolio
    
    def _generate_large_bank_portfolio(self, bank_name: str) -> Portfolio:
        """Generate portfolio for a large commercial bank."""
        portfolio = Portfolio(
            portfolio_id=f"portfolio_{uuid.uuid4().hex[:8]}",
            bank_name=bank_name,
            reporting_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        # Large bank characteristics: diversified with significant trading
        total_assets = random.uniform(50e9, 500e9)  # €50B - €500B
        
        # Generate loans (60% of assets)
        loan_amount = total_assets * 0.6
        self._add_retail_loans(portfolio, loan_amount * 0.25)
        self._add_mortgage_loans(portfolio, loan_amount * 0.3)
        self._add_commercial_loans(portfolio, loan_amount * 0.2)
        self._add_corporate_loans(portfolio, loan_amount * 0.2)
        self._add_international_loans(portfolio, loan_amount * 0.05)
        
        # Generate securities (20% of assets)
        securities_amount = total_assets * 0.2
        self._add_government_securities(portfolio, securities_amount * 0.4)
        self._add_corporate_bonds(portfolio, securities_amount * 0.3)
        self._add_bank_securities(portfolio, securities_amount * 0.2)
        self._add_international_securities(portfolio, securities_amount * 0.1)
        
        # Generate trading assets (15% of assets)
        trading_amount = total_assets * 0.15
        self._add_trading_securities(portfolio, trading_amount * 0.5)
        self._add_derivatives(portfolio, trading_amount * 0.4)
        self._add_fx_positions(portfolio, trading_amount * 0.1)
        
        # Cash and other assets (5% of assets)
        self._add_cash_assets(portfolio, total_assets * 0.05)
        
        # Significant off-balance sheet exposures
        self._add_commitments(portfolio, total_assets * 0.3)
        self._add_guarantees(portfolio, total_assets * 0.1)
        
        return portfolio
    
    def _generate_gsib_portfolio(self, bank_name: str) -> Portfolio:
        """Generate portfolio for a global systemically important bank."""
        portfolio = Portfolio(
            portfolio_id=f"portfolio_{uuid.uuid4().hex[:8]}",
            bank_name=bank_name,
            reporting_date=datetime.now().strftime("%Y-%m-%d")
        )
        
        # GSIB characteristics: highly diversified, significant trading and international
        total_assets = random.uniform(500e9, 3000e9)  # €500B - €3T
        
        # Generate loans (50% of assets)
        loan_amount = total_assets * 0.5
        self._add_retail_loans(portfolio, loan_amount * 0.2)
        self._add_mortgage_loans(portfolio, loan_amount * 0.25)
        self._add_commercial_loans(portfolio, loan_amount * 0.2)
        self._add_corporate_loans(portfolio, loan_amount * 0.2)
        self._add_international_loans(portfolio, loan_amount * 0.15)
        
        # Generate securities (20% of assets)
        securities_amount = total_assets * 0.2
        self._add_government_securities(portfolio, securities_amount * 0.3)
        self._add_corporate_bonds(portfolio, securities_amount * 0.3)
        self._add_bank_securities(portfolio, securities_amount * 0.2)
        self._add_international_securities(portfolio, securities_amount * 0.2)
        
        # Generate trading assets (25% of assets)
        trading_amount = total_assets * 0.25
        self._add_trading_securities(portfolio, trading_amount * 0.4)
        self._add_derivatives(portfolio, trading_amount * 0.4)
        self._add_fx_positions(portfolio, trading_amount * 0.15)
        self._add_commodity_positions(portfolio, trading_amount * 0.05)
        
        # Cash and other assets (5% of assets)
        self._add_cash_assets(portfolio, total_assets * 0.05)
        
        # Large off-balance sheet exposures
        self._add_commitments(portfolio, total_assets * 0.5)
        self._add_guarantees(portfolio, total_assets * 0.2)
        
        return portfolio
    
    def _add_retail_loans(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add retail loan exposures."""
        num_loans = random.randint(1000, 10000)
        avg_loan_size = total_amount / num_loans
        
        for i in range(min(num_loans, 100)):  # Limit for performance
            loan_size = max(1000, np.random.lognormal(np.log(avg_loan_size), 0.5))
            
            # Adjust total if needed
            if i == 99:  # Last loan
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_class == ExposureClass.RETAIL_OTHER)
                loan_size = max(1000, remaining)
            
            exposure = Exposure(
                exposure_id=f"retail_loan_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"retail_customer_{random.randint(10000, 99999)}",
                exposure_type=ExposureType.LOANS,
                exposure_class=ExposureClass.RETAIL_OTHER,
                original_exposure=loan_size,
                current_exposure=loan_size * random.uniform(0.7, 1.0),
                probability_of_default=random.uniform(0.005, 0.05),  # 0.5% - 5%
                loss_given_default=random.uniform(0.3, 0.6),  # 30% - 60%
                maturity=random.uniform(1, 7),  # 1-7 years
                external_rating=random.choice([None, "BB", "B", "unrated"]),
                currency="EUR",
                geography=random.choice(["domestic", "EU", "other"]),
                sector=random.choice(["consumer", "retail", "services"])
            )
            
            # Add collateral for some loans
            if random.random() < 0.3:  # 30% have collateral
                exposure.crm = CreditRiskMitigation(
                    collateral_type=random.choice(["residential_property", "cash", "securities"]),
                    collateral_value=loan_size * random.uniform(0.8, 1.2)
                )
            
            portfolio.add_exposure(exposure)
    
    def _add_mortgage_loans(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add mortgage loan exposures."""
        num_mortgages = random.randint(500, 5000)
        avg_mortgage_size = total_amount / num_mortgages
        
        for i in range(min(num_mortgages, 100)):
            mortgage_size = max(50000, np.random.lognormal(np.log(avg_mortgage_size), 0.3))
            
            if i == 99:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_class == ExposureClass.RETAIL_MORTGAGE)
                mortgage_size = max(50000, remaining)
            
            exposure = Exposure(
                exposure_id=f"mortgage_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"homeowner_{random.randint(10000, 99999)}",
                exposure_type=ExposureType.LOANS,
                exposure_class=ExposureClass.RETAIL_MORTGAGE,
                original_exposure=mortgage_size,
                current_exposure=mortgage_size * random.uniform(0.8, 1.0),
                probability_of_default=random.uniform(0.001, 0.02),  # 0.1% - 2%
                loss_given_default=random.uniform(0.1, 0.4),  # 10% - 40%
                maturity=random.uniform(15, 30),  # 15-30 years
                external_rating=None,  # Mortgages typically unrated
                currency="EUR",
                geography="domestic",
                sector="real_estate"
            )
            
            # Mortgages typically have property collateral
            exposure.crm = CreditRiskMitigation(
                collateral_type="residential_property",
                collateral_value=mortgage_size * random.uniform(1.0, 1.5)
            )
            
            portfolio.add_exposure(exposure)
    
    def _add_commercial_loans(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add commercial loan exposures."""
        num_loans = random.randint(100, 1000)
        avg_loan_size = total_amount / num_loans
        
        for i in range(min(num_loans, 50)):
            loan_size = max(100000, np.random.lognormal(np.log(avg_loan_size), 0.7))
            
            if i == 49:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "commercial_loan" in exp.exposure_id)
                loan_size = max(100000, remaining)
            
            exposure = Exposure(
                exposure_id=f"commercial_loan_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"sme_{random.randint(1000, 9999)}",
                exposure_type=ExposureType.LOANS,
                exposure_class=ExposureClass.CORPORATE,
                original_exposure=loan_size,
                current_exposure=loan_size * random.uniform(0.9, 1.0),
                probability_of_default=random.uniform(0.01, 0.08),  # 1% - 8%
                loss_given_default=random.uniform(0.4, 0.7),  # 40% - 70%
                maturity=random.uniform(2, 10),  # 2-10 years
                external_rating=random.choice(["BBB", "BB", "B", "unrated"]),
                currency="EUR",
                geography=random.choice(["domestic", "EU"]),
                sector=random.choice(["manufacturing", "services", "retail", "construction", "agriculture"])
            )
            
            # Some commercial loans have collateral
            if random.random() < 0.6:  # 60% have collateral
                exposure.crm = CreditRiskMitigation(
                    collateral_type=random.choice(["commercial_property", "equipment", "inventory"]),
                    collateral_value=loan_size * random.uniform(0.7, 1.1)
                )
            
            portfolio.add_exposure(exposure)
    
    def _add_corporate_loans(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add large corporate loan exposures."""
        num_loans = random.randint(20, 200)
        avg_loan_size = total_amount / num_loans
        
        for i in range(min(num_loans, 30)):
            loan_size = max(1000000, np.random.lognormal(np.log(avg_loan_size), 0.8))
            
            if i == 29:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "corporate_loan" in exp.exposure_id)
                loan_size = max(1000000, remaining)
            
            exposure = Exposure(
                exposure_id=f"corporate_loan_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"corp_{random.randint(100, 999)}",
                exposure_type=ExposureType.LOANS,
                exposure_class=ExposureClass.CORPORATE,
                original_exposure=loan_size,
                current_exposure=loan_size * random.uniform(0.95, 1.0),
                probability_of_default=random.uniform(0.005, 0.05),  # 0.5% - 5%
                loss_given_default=random.uniform(0.3, 0.6),  # 30% - 60%
                maturity=random.uniform(3, 15),  # 3-15 years
                external_rating=random.choice(["AAA", "AA", "A", "BBB", "BB", "B"]),
                currency=random.choice(["EUR", "USD", "GBP"]),
                geography=random.choice(["domestic", "EU", "US", "other"]),
                sector=random.choice(["technology", "healthcare", "energy", "financial", "industrial", "consumer"])
            )
            
            portfolio.add_exposure(exposure)
    
    def _add_international_loans(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add international loan exposures."""
        num_loans = random.randint(10, 100)
        avg_loan_size = total_amount / num_loans
        
        for i in range(min(num_loans, 20)):
            loan_size = max(5000000, np.random.lognormal(np.log(avg_loan_size), 1.0))
            
            if i == 19:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "intl_loan" in exp.exposure_id)
                loan_size = max(5000000, remaining)
            
            exposure = Exposure(
                exposure_id=f"intl_loan_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"intl_corp_{random.randint(100, 999)}",
                exposure_type=ExposureType.LOANS,
                exposure_class=random.choice([ExposureClass.CORPORATE, ExposureClass.BANK, ExposureClass.SOVEREIGN]),
                original_exposure=loan_size,
                current_exposure=loan_size * random.uniform(0.9, 1.0),
                probability_of_default=random.uniform(0.01, 0.1),  # 1% - 10%
                loss_given_default=random.uniform(0.4, 0.8),  # 40% - 80%
                maturity=random.uniform(1, 10),  # 1-10 years
                external_rating=random.choice(["AA", "A", "BBB", "BB", "B", "unrated"]),
                currency=random.choice(["USD", "GBP", "JPY", "CHF", "CAD"]),
                geography=random.choice(["US", "UK", "Asia", "Americas", "other"]),
                sector=random.choice(["sovereign", "banking", "energy", "mining", "infrastructure"])
            )
            
            portfolio.add_exposure(exposure)
    
    def _add_government_securities(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add government securities."""
        num_securities = random.randint(10, 50)
        avg_security_size = total_amount / num_securities
        
        for i in range(min(num_securities, 20)):
            security_size = max(1000000, np.random.lognormal(np.log(avg_security_size), 0.5))
            
            if i == 19:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_class == ExposureClass.SOVEREIGN)
                security_size = max(1000000, remaining)
            
            exposure = Exposure(
                exposure_id=f"govt_bond_{uuid.uuid4().hex[:8]}",
                counterparty_id=random.choice(["DE_GOVT", "FR_GOVT", "IT_GOVT", "ES_GOVT", "US_GOVT"]),
                exposure_type=ExposureType.SECURITIES,
                exposure_class=ExposureClass.SOVEREIGN,
                original_exposure=security_size,
                current_exposure=security_size * random.uniform(0.95, 1.05),
                market_value=security_size * random.uniform(0.98, 1.02),
                maturity=random.uniform(1, 30),  # 1-30 years
                external_rating=random.choice(["AAA", "AA", "A"]),
                currency=random.choice(["EUR", "USD"]),
                geography=random.choice(["domestic", "EU", "US"]),
                sector="sovereign"
            )
            
            # Add interest rate sensitivities
            duration = min(exposure.maturity or 5, 20)  # Cap duration at 20
            exposure.sensitivities = {
                f"ir_{int(duration)}y": security_size * duration * 0.0001  # 1bp DV01
            }
            
            portfolio.add_exposure(exposure)
    
    def _add_corporate_bonds(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add corporate bond securities."""
        num_bonds = random.randint(20, 100)
        avg_bond_size = total_amount / num_bonds
        
        for i in range(min(num_bonds, 30)):
            bond_size = max(500000, np.random.lognormal(np.log(avg_bond_size), 0.6))
            
            if i == 29:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "corp_bond" in exp.exposure_id)
                bond_size = max(500000, remaining)
            
            exposure = Exposure(
                exposure_id=f"corp_bond_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"corp_{random.randint(100, 999)}",
                exposure_type=ExposureType.SECURITIES,
                exposure_class=ExposureClass.CORPORATE,
                original_exposure=bond_size,
                current_exposure=bond_size * random.uniform(0.9, 1.1),
                market_value=bond_size * random.uniform(0.95, 1.05),
                maturity=random.uniform(2, 15),  # 2-15 years
                external_rating=random.choice(["AAA", "AA", "A", "BBB", "BB", "B"]),
                currency=random.choice(["EUR", "USD"]),
                geography=random.choice(["domestic", "EU", "US", "other"]),
                sector=random.choice(["technology", "healthcare", "energy", "financial", "industrial"])
            )
            
            # Add sensitivities
            duration = min(exposure.maturity or 5, 15)
            exposure.sensitivities = {
                f"ir_{int(duration)}y": bond_size * duration * 0.0001,
                "credit_spread": bond_size * duration * 0.0001
            }
            
            portfolio.add_exposure(exposure)
    
    def _add_bank_securities(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add bank securities."""
        num_securities = random.randint(10, 50)
        avg_size = total_amount / num_securities
        
        for i in range(min(num_securities, 20)):
            size = max(1000000, np.random.lognormal(np.log(avg_size), 0.5))
            
            if i == 19:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_class == ExposureClass.BANK)
                size = max(1000000, remaining)
            
            exposure = Exposure(
                exposure_id=f"bank_bond_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"bank_{random.randint(100, 999)}",
                exposure_type=ExposureType.SECURITIES,
                exposure_class=ExposureClass.BANK,
                original_exposure=size,
                current_exposure=size * random.uniform(0.95, 1.05),
                market_value=size * random.uniform(0.98, 1.02),
                maturity=random.uniform(1, 10),
                external_rating=random.choice(["AA", "A", "BBB", "BB"]),
                currency=random.choice(["EUR", "USD"]),
                geography=random.choice(["domestic", "EU", "US"]),
                sector="banking"
            )
            
            portfolio.add_exposure(exposure)
    
    def _add_international_securities(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add international securities."""
        num_securities = random.randint(5, 30)
        avg_size = total_amount / num_securities
        
        for i in range(min(num_securities, 15)):
            size = max(2000000, np.random.lognormal(np.log(avg_size), 0.7))
            
            if i == 14:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "intl_sec" in exp.exposure_id)
                size = max(2000000, remaining)
            
            exposure = Exposure(
                exposure_id=f"intl_sec_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"intl_issuer_{random.randint(100, 999)}",
                exposure_type=ExposureType.SECURITIES,
                exposure_class=random.choice([ExposureClass.SOVEREIGN, ExposureClass.CORPORATE, ExposureClass.BANK]),
                original_exposure=size,
                current_exposure=size * random.uniform(0.9, 1.1),
                market_value=size * random.uniform(0.95, 1.05),
                maturity=random.uniform(1, 20),
                external_rating=random.choice(["AAA", "AA", "A", "BBB", "BB"]),
                currency=random.choice(["USD", "GBP", "JPY", "CHF"]),
                geography=random.choice(["US", "UK", "Asia", "other"]),
                sector=random.choice(["sovereign", "financial", "corporate"])
            )
            
            # Add FX sensitivity
            exposure.sensitivities = {
                "fx_delta": size * 0.01  # 1% FX sensitivity
            }
            
            portfolio.add_exposure(exposure)
    
    def _add_trading_securities(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add trading securities."""
        num_securities = random.randint(20, 100)
        avg_size = total_amount / num_securities
        
        for i in range(min(num_securities, 40)):
            size = max(100000, np.random.lognormal(np.log(avg_size), 0.8))
            
            if i == 39:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_type == ExposureType.TRADING_SECURITIES)
                size = max(100000, remaining)
            
            exposure = Exposure(
                exposure_id=f"trading_sec_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"issuer_{random.randint(100, 999)}",
                exposure_type=ExposureType.TRADING_SECURITIES,
                exposure_class=random.choice([ExposureClass.CORPORATE, ExposureClass.SOVEREIGN, ExposureClass.BANK]),
                original_exposure=size,
                current_exposure=size,
                market_value=size * random.uniform(0.9, 1.1),
                maturity=random.uniform(0.1, 10),
                external_rating=random.choice(["AAA", "AA", "A", "BBB", "BB", "B"]),
                currency=random.choice(["EUR", "USD", "GBP"]),
                business_line="trading",
                sector=random.choice(["financial", "corporate", "sovereign"])
            )
            
            # Add market risk sensitivities
            duration = min(exposure.maturity or 2, 10)
            exposure.sensitivities = {
                f"ir_{int(duration)}y": size * duration * 0.0001,
                "credit_spread": size * duration * 0.0001
            }
            
            if exposure.currency != "EUR":
                exposure.sensitivities["fx_delta"] = size * 0.01
            
            portfolio.add_exposure(exposure)
    
    def _add_derivatives(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add derivative exposures."""
        num_derivatives = random.randint(10, 50)
        avg_notional = total_amount / num_derivatives
        
        for i in range(min(num_derivatives, 25)):
            notional = max(1000000, np.random.lognormal(np.log(avg_notional), 1.0))
            
            if i == 24:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_type == ExposureType.DERIVATIVES)
                notional = max(1000000, remaining)
            
            derivative_type = random.choice(["swap", "option", "forward", "future"])
            asset_class = random.choice(["interest_rate", "fx", "equity", "credit"])
            
            # Market value is typically small relative to notional
            market_value = notional * random.uniform(-0.05, 0.05)
            
            exposure = Exposure(
                exposure_id=f"{derivative_type}_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"counterparty_{random.randint(100, 999)}",
                exposure_type=ExposureType.DERIVATIVES,
                exposure_class=ExposureClass.CORPORATE,  # Counterparty class
                original_exposure=notional,
                current_exposure=notional,
                market_value=market_value,
                maturity=random.uniform(0.1, 5),
                currency=random.choice(["EUR", "USD", "GBP"]),
                business_line="trading",
                sector="derivatives"
            )
            
            # Add sensitivities based on asset class
            if asset_class == "interest_rate":
                exposure.sensitivities = {
                    "ir_2y": notional * random.uniform(0.0001, 0.001),
                    "ir_5y": notional * random.uniform(0.0001, 0.001),
                    "ir_10y": notional * random.uniform(0.0001, 0.001)
                }
            elif asset_class == "fx":
                exposure.sensitivities = {
                    "fx_delta": notional * random.uniform(0.01, 0.1)
                }
            elif asset_class == "equity":
                exposure.sensitivities = {
                    "equity_delta": notional * random.uniform(0.01, 0.05)
                }
            elif asset_class == "credit":
                exposure.sensitivities = {
                    "credit_spread": notional * random.uniform(0.0001, 0.001)
                }
            
            portfolio.add_exposure(exposure)
    
    def _add_fx_positions(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add FX positions."""
        num_positions = random.randint(5, 20)
        avg_size = total_amount / num_positions
        
        currencies = ["USD", "GBP", "JPY", "CHF", "CAD", "AUD"]
        
        for i, currency in enumerate(currencies[:min(num_positions, len(currencies))]):
            size = max(500000, np.random.lognormal(np.log(avg_size), 0.6))
            
            if i == len(currencies) - 1:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "fx_pos" in exp.exposure_id)
                size = max(500000, remaining)
            
            exposure = Exposure(
                exposure_id=f"fx_pos_{currency}_{uuid.uuid4().hex[:8]}",
                exposure_type=ExposureType.TRADING_SECURITIES,
                exposure_class=ExposureClass.FX,
                original_exposure=size,
                current_exposure=size,
                market_value=size * random.uniform(0.98, 1.02),
                currency=currency,
                business_line="fx_trading",
                sector="fx"
            )
            
            exposure.sensitivities = {
                "fx_delta": size * 0.01  # 1% sensitivity
            }
            
            portfolio.add_exposure(exposure)
    
    def _add_commodity_positions(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add commodity positions."""
        num_positions = random.randint(3, 10)
        avg_size = total_amount / num_positions
        
        commodities = ["gold", "oil", "gas", "copper", "agricultural"]
        
        for i, commodity in enumerate(commodities[:min(num_positions, len(commodities))]):
            size = max(1000000, np.random.lognormal(np.log(avg_size), 0.8))
            
            if i == len(commodities) - 1:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if "comm_pos" in exp.exposure_id)
                size = max(1000000, remaining)
            
            exposure = Exposure(
                exposure_id=f"comm_pos_{commodity}_{uuid.uuid4().hex[:8]}",
                exposure_type=ExposureType.TRADING_SECURITIES,
                exposure_class=ExposureClass.COMMODITY,
                original_exposure=size,
                current_exposure=size,
                market_value=size * random.uniform(0.9, 1.1),
                currency="EUR",
                business_line="commodities_trading",
                sector=commodity
            )
            
            portfolio.add_exposure(exposure)
    
    def _add_cash_assets(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add cash and cash equivalents."""
        exposure = Exposure(
            exposure_id=f"cash_{uuid.uuid4().hex[:8]}",
            exposure_type=ExposureType.CASH,
            exposure_class=ExposureClass.OTHER_ASSETS,
            original_exposure=total_amount,
            current_exposure=total_amount,
            currency="EUR",
            sector="cash"
        )
        
        portfolio.add_exposure(exposure)
    
    def _add_commitments(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add off-balance sheet commitments."""
        num_commitments = random.randint(10, 100)
        avg_size = total_amount / num_commitments
        
        for i in range(min(num_commitments, 20)):
            size = max(100000, np.random.lognormal(np.log(avg_size), 0.7))
            
            if i == 19:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_type == ExposureType.COMMITMENTS)
                size = max(100000, remaining)
            
            exposure = Exposure(
                exposure_id=f"commitment_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"client_{random.randint(1000, 9999)}",
                exposure_type=ExposureType.COMMITMENTS,
                exposure_class=random.choice([ExposureClass.CORPORATE, ExposureClass.RETAIL_OTHER]),
                original_exposure=size,
                current_exposure=size,
                credit_conversion_factor=random.uniform(0.2, 0.75),
                probability_of_default=random.uniform(0.01, 0.05),
                loss_given_default=random.uniform(0.4, 0.6),
                maturity=random.uniform(1, 5),
                currency="EUR",
                sector=random.choice(["corporate", "retail", "commercial"])
            )
            
            portfolio.add_exposure(exposure)
    
    def _add_guarantees(self, portfolio: Portfolio, total_amount: float) -> None:
        """Add guarantees and similar instruments."""
        num_guarantees = random.randint(5, 50)
        avg_size = total_amount / num_guarantees
        
        for i in range(min(num_guarantees, 15)):
            size = max(500000, np.random.lognormal(np.log(avg_size), 0.8))
            
            if i == 14:
                remaining = total_amount - sum(exp.current_exposure for exp in portfolio.exposures 
                                             if exp.exposure_type == ExposureType.GUARANTEES)
                size = max(500000, remaining)
            
            exposure = Exposure(
                exposure_id=f"guarantee_{uuid.uuid4().hex[:8]}",
                counterparty_id=f"client_{random.randint(1000, 9999)}",
                exposure_type=ExposureType.GUARANTEES,
                exposure_class=ExposureClass.CORPORATE,
                original_exposure=size,
                current_exposure=size,
                credit_conversion_factor=1.0,  # Full conversion for guarantees
                probability_of_default=random.uniform(0.005, 0.03),
                loss_given_default=random.uniform(0.3, 0.5),
                maturity=random.uniform(1, 3),
                currency="EUR",
                sector="guarantee"
            )
            
            portfolio.add_exposure(exposure)
    
    # Capital generation methods
    
    def _generate_small_bank_capital(self, bank_name: str) -> Capital:
        """Generate capital structure for small bank."""
        return self._generate_capital_structure(
            bank_name=bank_name,
            total_assets=2.5e9,  # Average small bank size
            cet1_ratio=0.12,     # 12% CET1 ratio
            tier1_ratio=0.13,    # 13% Tier 1 ratio
            total_ratio=0.15     # 15% Total capital ratio
        )
    
    def _generate_medium_bank_capital(self, bank_name: str) -> Capital:
        """Generate capital structure for medium bank."""
        return self._generate_capital_structure(
            bank_name=bank_name,
            total_assets=25e9,   # Average medium bank size
            cet1_ratio=0.11,     # 11% CET1 ratio
            tier1_ratio=0.125,   # 12.5% Tier 1 ratio
            total_ratio=0.145    # 14.5% Total capital ratio
        )
    
    def _generate_large_bank_capital(self, bank_name: str) -> Capital:
        """Generate capital structure for large bank."""
        return self._generate_capital_structure(
            bank_name=bank_name,
            total_assets=250e9,  # Average large bank size
            cet1_ratio=0.105,    # 10.5% CET1 ratio
            tier1_ratio=0.12,    # 12% Tier 1 ratio
            total_ratio=0.14     # 14% Total capital ratio
        )
    
    def _generate_gsib_capital(self, bank_name: str) -> Capital:
        """Generate capital structure for GSIB."""
        return self._generate_capital_structure(
            bank_name=bank_name,
            total_assets=1500e9, # Average GSIB size
            cet1_ratio=0.13,     # 13% CET1 ratio (higher due to buffers)
            tier1_ratio=0.145,   # 14.5% Tier 1 ratio
            total_ratio=0.165    # 16.5% Total capital ratio
        )
    
    def _generate_capital_structure(self, bank_name: str, total_assets: float,
                                  cet1_ratio: float, tier1_ratio: float, 
                                  total_ratio: float) -> Capital:
        """Generate realistic capital structure."""
        # Estimate RWA (typically 60-80% of total assets)
        rwa_ratio = random.uniform(0.6, 0.8)
        estimated_rwa = total_assets * rwa_ratio
        
        # Calculate capital amounts
        cet1_capital = estimated_rwa * cet1_ratio
        tier1_capital = estimated_rwa * tier1_ratio
        total_capital = estimated_rwa * total_ratio
        
        at1_capital = tier1_capital - cet1_capital
        t2_capital = total_capital - tier1_capital
        
        # Create capital components
        components = CapitalComponents(
            common_shares=cet1_capital * 0.6,
            retained_earnings=cet1_capital * 0.35,
            accumulated_oci=cet1_capital * 0.05,
            at1_instruments=at1_capital,
            t2_instruments=t2_capital * 0.8,
            general_provisions=t2_capital * 0.2,
            # Regulatory adjustments (small amounts)
            goodwill=cet1_capital * 0.02,
            intangible_assets=cet1_capital * 0.01,
            deferred_tax_assets=cet1_capital * 0.005
        )
        
        capital = Capital(
            bank_name=bank_name,
            reporting_date=datetime.now().strftime("%Y-%m-%d"),
            components=components
        )
        
        # Add individual instruments
        if components.common_shares > 0:
            capital.add_instrument(CapitalInstrument(
                instrument_id="common_shares_001",
                instrument_name="Common Shares",
                tier=CapitalTier.CET1,
                amount=components.common_shares
            ))
        
        if components.at1_instruments > 0:
            capital.add_instrument(CapitalInstrument(
                instrument_id="at1_bond_001",
                instrument_name="Additional Tier 1 Bond",
                tier=CapitalTier.AT1,
                amount=components.at1_instruments,
                is_perpetual=True,
                conversion_trigger=0.05125  # 5.125% CET1 trigger
            ))
        
        if components.t2_instruments > 0:
            capital.add_instrument(CapitalInstrument(
                instrument_id="t2_bond_001",
                instrument_name="Tier 2 Subordinated Bond",
                tier=CapitalTier.T2,
                amount=components.t2_instruments
            ))
        
        return capital
    
    def generate_stressed_portfolio(self, base_portfolio: Portfolio, 
                                  stress_scenario: Dict[str, float]) -> Portfolio:
        """Generate a stressed version of the portfolio."""
        stressed_portfolio = Portfolio(
            portfolio_id=f"{base_portfolio.portfolio_id}_stressed",
            bank_name=base_portfolio.bank_name,
            reporting_date=base_portfolio.reporting_date,
            exposures=[]
        )
        
        for exposure in base_portfolio.exposures:
            # Create copy of exposure
            stressed_exposure = exposure.model_copy()
            
            # Apply stress to risk parameters
            if exposure.probability_of_default and "credit_shock" in stress_scenario:
                credit_multiplier = 1 + stress_scenario["credit_shock"]
                stressed_exposure.probability_of_default = min(
                    0.99, exposure.probability_of_default * credit_multiplier
                )
            
            if exposure.loss_given_default and "lgd_shock" in stress_scenario:
                lgd_addon = stress_scenario["lgd_shock"]
                stressed_exposure.loss_given_default = min(
                    1.0, exposure.loss_given_default + lgd_addon
                )
            
            # Apply market value stress
            if exposure.market_value:
                market_stress = 1.0
                
                if exposure.currency != "EUR" and "fx_shock" in stress_scenario:
                    market_stress *= (1 + stress_scenario["fx_shock"])
                
                if exposure.is_trading_book() and "equity_shock" in stress_scenario:
                    market_stress *= (1 + stress_scenario["equity_shock"])
                
                stressed_exposure.market_value = exposure.market_value * market_stress
            
            stressed_portfolio.add_exposure(stressed_exposure)
        
        return stressed_portfolio
