"""Configuration management for Basel Capital Engine."""

from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import BaseModel, Field


class BaselConfig(BaseModel):
    """Basel Capital Engine configuration."""
    
    risk_weights: Dict[str, Any] = Field(default_factory=dict)
    buffers: Dict[str, Any] = Field(default_factory=dict) 
    minimum_ratios: Dict[str, float] = Field(default_factory=dict)
    crm: Dict[str, Any] = Field(default_factory=dict)
    operational_risk: Dict[str, Any] = Field(default_factory=dict)
    stress_scenarios: Dict[str, Any] = Field(default_factory=dict)
    correlations: Dict[str, Any] = Field(default_factory=dict)
    validation: Dict[str, Any] = Field(default_factory=dict)
    
    @classmethod
    def load_default(cls) -> "BaselConfig":
        """Load default configuration from package yaml file."""
        config_path = Path(__file__).parent.parent / "config.yaml"
        return cls.load_from_file(config_path)
    
    @classmethod
    def load_from_file(cls, config_path: Path) -> "BaselConfig":
        """Load configuration from YAML file."""
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
        return cls(**config_data)
    
    def save_to_file(self, config_path: Path) -> None:
        """Save configuration to YAML file."""
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, indent=2)
    
    def get_risk_weight(self, asset_class: str, rating: Optional[str] = None) -> float:
        """Get risk weight for specific asset class and rating."""
        credit_weights = self.risk_weights.get("credit", {})
        
        if rating:
            key = f"{asset_class}_{rating.lower()}"
            if key in credit_weights:
                return credit_weights[key]
        
        # Fallback to asset class default
        if asset_class in credit_weights:
            return credit_weights[asset_class]
        
        # Ultimate fallback
        return credit_weights.get("other_assets", 1.25)
    
    def get_buffer_requirement(self, buffer_type: str, **kwargs: Any) -> float:
        """Get buffer requirement for specific type."""
        buffers = self.buffers
        
        if buffer_type == "conservation":
            return buffers.get("conservation", 0.025)
        elif buffer_type == "countercyclical":
            return buffers.get("countercyclical", 0.0)
        elif buffer_type == "sifi":
            sifi_buffers = buffers.get("sifi", {})
            bucket = kwargs.get("bucket", "d_sib")
            return sifi_buffers.get(bucket, 0.01)
        
        return 0.0
    
    def get_minimum_ratio(self, ratio_type: str) -> float:
        """Get minimum required ratio."""
        return self.minimum_ratios.get(ratio_type, 0.08)
    
    def get_stress_scenario(self, scenario_name: str) -> Dict[str, Any]:
        """Get stress scenario parameters."""
        return self.stress_scenarios.get(scenario_name, {})
    
    def validate_exposure_data(self, exposure_amount: float, pd: float, lgd: float, maturity: float) -> bool:
        """Validate exposure data against configured limits."""
        validation = self.validation
        
        # Check exposure limits
        if exposure_amount > validation.get("max_exposure_single", float("inf")):
            return False
        
        # Check PD bounds
        min_pd = validation.get("min_pd", 0.0001)
        max_pd = validation.get("max_pd", 0.99)
        if not (min_pd <= pd <= max_pd):
            return False
        
        # Check LGD bounds  
        min_lgd = validation.get("min_lgd", 0.01)
        max_lgd = validation.get("max_lgd", 1.0)
        if not (min_lgd <= lgd <= max_lgd):
            return False
        
        # Check maturity bounds
        min_maturity = validation.get("min_maturity", 0.003)
        max_maturity = validation.get("max_maturity", 50)
        if not (min_maturity <= maturity <= max_maturity):
            return False
        
        return True
