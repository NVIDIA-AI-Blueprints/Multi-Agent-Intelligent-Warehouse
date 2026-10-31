# How Reorder Recommendations Work in Forecasting Dashboard

## Overview
**Yes, reorder recommendations are directly based on demand forecasting results!** The system uses forecasted demand to calculate optimal reorder quantities and urgency levels.

---

## Complete Flow

### Step 1: Identify Low Stock Items
**Location:** `src/api/routers/advanced_forecasting.py:290-295`

```python
# Get current inventory levels
inventory_query = """
SELECT sku, name, quantity, reorder_point, location
FROM inventory_items
WHERE quantity <= reorder_point * 1.5
ORDER BY quantity ASC
"""
```

The system identifies items that are at or near their reorder point (within 150% of reorder point).

### Step 2: Get Demand Forecast for Each SKU
**Location:** `src/api/routers/advanced_forecasting.py:306-311`

For each low-stock item, the system:
1. Calls `get_real_time_forecast(sku, 30)` - Gets 30-day forecast
2. Extracts `recent_average_demand` from the forecast
3. Uses this as the **expected daily demand** for calculations

```python
# Get recent demand forecast
try:
    forecast = await self.get_real_time_forecast(sku, 30)
    avg_daily_demand = forecast['recent_average_demand']
except:
    avg_daily_demand = 10  # Default fallback
```

**Key Point:** The `recent_average_demand` is the mean daily outbound demand over the last 30 days of history (`inventory_movements`), computed by `get_real_time_forecast()`; it is not produced by the trained ML models.

### Step 3: Calculate Recommended Order Quantity
**Location:** `src/api/routers/advanced_forecasting.py:313-316`

```python
# Calculate recommended order quantity
safety_stock = max(reorder_point, avg_daily_demand * 7)  # 7 days safety stock
recommended_quantity = int(safety_stock * 2) - current_stock
recommended_quantity = max(0, recommended_quantity)
```

**Formula Breakdown:**
- **Safety Stock** = max(reorder_point, forecasted_daily_demand × 7 days)
- **Recommended Quantity** = (Safety Stock × 2) - Current Stock
- Ensures enough inventory for 14 days of forecasted demand

### Step 4: Determine Urgency Level
**Location:** `src/api/routers/advanced_forecasting.py:318-332`

The urgency is calculated based on **days until stockout**:

```python
days_remaining = current_stock / max(avg_daily_demand, 1)

if days_remaining <= 3:
    urgency = "CRITICAL"  # Stock will run out in 3 days or less
elif days_remaining <= 7:
    urgency = "HIGH"      # Stock will run out within a week
elif days_remaining <= 14:
    urgency = "MEDIUM"    # Stock will run out within 2 weeks
else:
    urgency = "LOW"       # Stock levels are adequate
```

**Key Calculation:** `days_remaining = current_stock ÷ forecasted_daily_demand`

This directly uses the forecast to predict when stockout will occur!

### Step 5: Calculate Confidence Score
**Location:** `src/api/routers/advanced_forecasting.py:334-335`

```python
confidence_score = min(0.95, max(0.5, 1.0 - (days_remaining / 30)))
```

Confidence increases as urgency increases (more urgent = higher confidence in the recommendation).

---

## Where Forecast Data Comes From

The `get_real_time_forecast()` method:
1. Checks Redis cache for a recent forecast (`forecast:{sku}:{horizon_days}`)
2. If not cached, queries the last 180 days of outbound `inventory_movements` for the SKU and computes a simple forecast (`model_type: real_time_simple`): the trailing 30-day mean demand × a seasonal factor (1.2 in summer, 0.8 on weekends), with small random variation per day
3. Caches the result in Redis for 1 hour and returns:
   - `recent_average_demand` - Used for reorder calculations
   - `predictions` - daily forecast for the horizon
   - `confidence_intervals` - ±1.96 × std-dev of the last 30 days
   - `seasonal_factor`, `model_type`

**Forecast Source:** historical demand statistics (`src/api/routers/advanced_forecasting.py:180-246`), not the trained ML models.

---

## How It Appears in the UI

**Location:** `src/ui/web/src/pages/Forecasting.tsx:398-445`

The forecasting dashboard displays reorder recommendations in a table showing:
- **SKU** - Item identifier
- **Current Stock** - Current inventory level
- **Recommended Order** - Calculated quantity to order
- **Urgency** - CRITICAL/HIGH/MEDIUM/LOW (color-coded chips)
- **Reason** - Explanation (e.g., "Stock will run out in 3 days or less")
- **Confidence** - Percentage confidence score

---

## Key Data Flow

```
Inventory Database
    ↓
[Items with quantity ≤ reorder_point × 1.5]
    ↓
For each SKU:
    ↓
get_real_time_forecast(SKU, 30 days)
    ↓
Trailing 30-day demand statistics (real_time_simple forecast)
    ↓
recent_average_demand (from forecast)
    ↓
Calculate:
  - Safety Stock = max(reorder_point, avg_daily_demand × 7)
  - Recommended Qty = (Safety Stock × 2) - Current Stock
  - Days Remaining = Current Stock ÷ avg_daily_demand
  - Urgency = Based on days_remaining
  - Confidence = Function of days_remaining
    ↓
ReorderRecommendation
    ↓
API Endpoint: /api/v1/forecasting/dashboard
    ↓
React UI: http://localhost:3001/forecasting
```

---

## Summary

Reorder recommendations are entirely based on demand forecasting results.

The system performs the following operations:

1. Estimates daily demand from recent historical demand
2. Calculates how many days of stock remain based on forecast
3. Determines urgency from predicted stockout date
4. Calculates optimal order quantity using forecasted demand
5. Provides confidence scores based on forecast reliability

Without the forecasting system, reorder recommendations would only use static `reorder_point` values. With forecasting, the system:

- Adapts to changing demand patterns
- Predicts stockout dates accurately
- Optimizes order quantities based on forecasted needs
- Prioritizes urgent items based on forecasted demand velocity

This makes the reorder system intelligent and proactive rather than reactive.

