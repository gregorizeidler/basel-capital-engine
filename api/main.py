"""Main FastAPI application for Basel Capital Engine."""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import uuid

from .models import (
    PortfolioRequest, StressTestRequest,
    BaselResultsResponse, StressTestResponse, HealthResponse,
    ExplainResponse, CompareResponse, CapitalData
)
from .services import BaselCalculationService, StressTestService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Basel Capital Engine API",
    description="Open-source regulatory capital calculation engine implementing Basel III framework",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
calculation_service = BaselCalculationService()
stress_test_service = StressTestService()

# Store calculation results for explain endpoint
calculation_cache: Dict[str, Any] = {}


@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Basel Capital Engine API",
        "version": "0.1.0",
        "description": "Regulatory capital calculation engine",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    try:
        # Basic health checks
        status = "healthy"
        checks = {
            "api": "ok",
            "calculation_service": "ok" if calculation_service else "error",
            "stress_test_service": "ok" if stress_test_service else "error",
            "timestamp": datetime.now().isoformat()
        }
        
        # If any check fails, mark as unhealthy
        if "error" in checks.values():
            status = "unhealthy"
        
        return HealthResponse(
            status=status,
            timestamp=datetime.now(),
            checks=checks
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return HealthResponse(
            status="unhealthy",
            timestamp=datetime.now(),
            checks={"error": str(e)}
        )


@app.post("/portfolio", response_model=BaselResultsResponse)
async def calculate_portfolio_metrics(request: PortfolioRequest):
    """Calculate Basel metrics for a portfolio."""
    try:
        calculation_id = str(uuid.uuid4())
        logger.info(f"Calculating portfolio metrics for request {calculation_id}")
        
        # Perform calculation
        results = await calculation_service.calculate_basel_metrics(
            portfolio_data=request.portfolio,
            capital_data=request.capital,
            config_overrides=request.config_overrides
        )
        
        # Store results for explain endpoint
        calculation_cache[calculation_id] = {
            "request": request.dict(),
            "results": results,
            "timestamp": datetime.now()
        }
        
        # Create response
        response = BaselResultsResponse(
            calculation_id=calculation_id,
            **results
        )
        
        logger.info(f"Portfolio calculation completed: {calculation_id}")
        return response
        
    except Exception as e:
        logger.error(f"Portfolio calculation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Calculation failed: {str(e)}")


@app.post("/stress", response_model=StressTestResponse)
async def run_stress_test(request: StressTestRequest):
    """Run stress test scenarios on a portfolio."""
    try:
        test_id = str(uuid.uuid4())
        logger.info(f"Running stress test {test_id} with scenarios: {request.scenarios}")
        
        # Run stress tests
        results = await stress_test_service.run_stress_tests(
            portfolio_data=request.portfolio,
            capital_data=request.capital,
            scenarios=request.scenarios,
            config_overrides=request.config_overrides
        )
        
        # Store results
        calculation_cache[test_id] = {
            "request": request.dict(),
            "results": results,
            "timestamp": datetime.now(),
            "type": "stress_test"
        }
        
        response = StressTestResponse(
            test_id=test_id,
            **results
        )
        
        logger.info(f"Stress test completed: {test_id}")
        return response
        
    except Exception as e:
        logger.error(f"Stress test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Stress test failed: {str(e)}")


@app.get("/explain/{calculation_id}", response_model=ExplainResponse)
async def explain_calculation(calculation_id: str):
    """Get detailed explanation of a calculation."""
    try:
        if calculation_id not in calculation_cache:
            raise HTTPException(status_code=404, detail="Calculation not found")
        
        cached_data = calculation_cache[calculation_id]
        
        # Generate detailed explanation
        explanation = await calculation_service.generate_explanation(
            cached_data["request"],
            cached_data["results"]
        )
        
        return ExplainResponse(
            calculation_id=calculation_id,
            calculation_type=cached_data.get("type", "portfolio"),
            timestamp=cached_data["timestamp"],
            explanation=explanation
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Explanation generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Explanation failed: {str(e)}")


@app.post("/compare", response_model=CompareResponse)
async def compare_portfolios(portfolios: List[PortfolioRequest]):
    """Compare multiple portfolios side by side."""
    try:
        if len(portfolios) < 2:
            raise HTTPException(status_code=400, detail="At least 2 portfolios required for comparison")
        
        if len(portfolios) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 portfolios can be compared")
        
        comparison_id = str(uuid.uuid4())
        logger.info(f"Comparing {len(portfolios)} portfolios: {comparison_id}")
        
        # Calculate metrics for each portfolio
        results = []
        for i, portfolio_request in enumerate(portfolios):
            portfolio_results = await calculation_service.calculate_basel_metrics(
                portfolio_data=portfolio_request.portfolio,
                capital_data=portfolio_request.capital,
                config_overrides=portfolio_request.config_overrides
            )
            portfolio_results["portfolio_name"] = f"Portfolio {i+1}"
            results.append(portfolio_results)
        
        # Generate comparison analysis
        comparison_analysis = await calculation_service.compare_portfolios(results)
        
        response = CompareResponse(
            comparison_id=comparison_id,
            portfolios=results,
            comparison_analysis=comparison_analysis,
            timestamp=datetime.now()
        )
        
        logger.info(f"Portfolio comparison completed: {comparison_id}")
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portfolio comparison failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@app.get("/scenarios", response_model=List[Dict[str, Any]])
async def list_stress_scenarios():
    """List available stress test scenarios."""
    try:
        scenarios = stress_test_service.list_available_scenarios()
        return scenarios
    except Exception as e:
        logger.error(f"Failed to list scenarios: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list scenarios: {str(e)}")


@app.get("/config", response_model=Dict[str, Any])
async def get_configuration():
    """Get current Basel configuration parameters."""
    try:
        config = calculation_service.get_configuration()
        return config
    except Exception as e:
        logger.error(f"Failed to get configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get configuration: {str(e)}")


@app.post("/validate", response_model=Dict[str, Any])
async def validate_portfolio(request: PortfolioRequest):
    """Validate portfolio data without running calculations."""
    try:
        validation_results = await calculation_service.validate_portfolio_data(
            portfolio_data=request.portfolio,
            capital_data=request.capital
        )
        
        return {
            "valid": validation_results["valid"],
            "issues": validation_results["issues"],
            "warnings": validation_results["warnings"],
            "summary": validation_results["summary"]
        }
        
    except Exception as e:
        logger.error(f"Portfolio validation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@app.delete("/cache/{calculation_id}")
async def clear_calculation_cache(calculation_id: str):
    """Clear specific calculation from cache."""
    try:
        if calculation_id in calculation_cache:
            del calculation_cache[calculation_id]
            return {"message": f"Cache cleared for calculation {calculation_id}"}
        else:
            raise HTTPException(status_code=404, detail="Calculation not found in cache")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cache clear failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@app.delete("/cache")
async def clear_all_cache():
    """Clear all calculation cache."""
    try:
        cache_size = len(calculation_cache)
        calculation_cache.clear()
        return {"message": f"Cleared {cache_size} cached calculations"}
    except Exception as e:
        logger.error(f"Cache clear failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@app.get("/metrics", response_model=Dict[str, Any])
async def get_api_metrics():
    """Get API usage metrics."""
    try:
        metrics = {
            "cached_calculations": len(calculation_cache),
            "uptime": "unknown",  # Would implement proper uptime tracking
            "version": "0.1.0",
            "timestamp": datetime.now().isoformat()
        }
        
        # Add cache statistics
        if calculation_cache:
            cache_types = {}
            for calc_data in calculation_cache.values():
                calc_type = calc_data.get("type", "portfolio")
                cache_types[calc_type] = cache_types.get(calc_type, 0) + 1
            metrics["cache_breakdown"] = cache_types
        
        return metrics
    except Exception as e:
        logger.error(f"Metrics collection failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Metrics failed: {str(e)}")


# Error handlers
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    """Handle ValueError exceptions."""
    logger.error(f"ValueError: {str(exc)}")
    return JSONResponse(
        status_code=400,
        content={"detail": f"Invalid input: {str(exc)}"}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    logger.info("Basel Capital Engine API starting up...")
    
    # Initialize services
    await calculation_service.initialize()
    await stress_test_service.initialize()
    
    logger.info("Basel Capital Engine API ready")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    logger.info("Basel Capital Engine API shutting down...")
    
    # Cleanup tasks
    calculation_cache.clear()
    
    logger.info("Basel Capital Engine API shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
