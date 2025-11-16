# Forecasting Summary Cards Assessment

**Date:** 2025-11-15  
**Assessment Type:** Dynamic vs Static Data Analysis  
**Page:** `http://localhost:3001/forecasting`

## Executive Summary

The Forecasting page displays 4 summary cards at the top. This assessment evaluates whether each card displays **dynamic** (database-driven, updates with training) or **static** (hardcoded/fallback) values.

### Summary Cards

1. **Products Forecasted: 38** ✅ **DYNAMIC**
2. **Reorder Alerts: 5** ✅ **DYNAMIC**
3. **Avg Accuracy: 77.0%** ⚠️ **PARTIALLY DYNAMIC** (falls back to static)
4. **Models Active: 6** ⚠️ **PARTIALLY DYNAMIC** (falls back to static)

## Detailed Analysis

### 1. Products Forecasted: 38 ✅ **DYNAMIC**

**Source:** `dashboardData?.forecast_summary?.total_skus`

**Calculation:**
- Calls `get_forecast_summary_data()` which:
  - Queries database: `SELECT DISTINCT sku FROM inventory_items`
  - Generates real-time forecasts for each SKU
  - Returns count of SKUs with valid forecasts

**Status:** ✅ **FULLY DYNAMIC**
- Updates based on inventory items in database
- Reflects actual SKUs with forecast data
- Changes when inventory items are added/removed

**Code Location:**
- Frontend: `src/ui/web/src/pages/Forecasting.tsx:315`
- Backend: `src/api/routers/advanced_forecasting.py:890-974`

---

### 2. Reorder Alerts: 5 ✅ **DYNAMIC**

**Source:** `dashboardData?.reorder_recommendations?.filter(r => r.urgency_level === 'HIGH' || r.urgency_level === 'CRITICAL').length`

**Calculation:**
- Calls `generate_reorder_recommendations()` which:
  - Queries database: `SELECT sku, quantity, reorder_point FROM inventory_items WHERE quantity <= reorder_point * 1.5`
  - For each low-stock item:
    - Generates real-time forecast using `get_real_time_forecast()`
    - Calculates days remaining based on current stock and forecasted demand
    - Determines urgency level (CRITICAL, HIGH, MEDIUM, LOW)
  - Returns recommendations with urgency levels

**Status:** ✅ **FULLY DYNAMIC**
- Updates based on current inventory levels
- Reflects real-time stock status
- Changes as inventory moves and forecasts update
- Urgency levels calculated from actual stock vs forecasted demand

**Code Location:**
- Frontend: `src/ui/web/src/pages/Forecasting.tsx:330-332`
- Backend: `src/api/routers/advanced_forecasting.py:195-268`

---

### 3. Avg Accuracy: 77.0% ⚠️ **PARTIALLY DYNAMIC**

**Source:** `dashboardData?.model_performance.reduce((acc, m) => acc + m.accuracy_score, 0) / dashboardData.model_performance.length * 100`

**Calculation:**
- Calls `get_model_performance_metrics()` which:
  1. **First attempts** to calculate real metrics from database:
     - Queries `model_training_history` for active models
     - Queries `model_predictions` for accuracy calculations
     - Calculates MAPE, drift scores, etc. from actual data
  2. **Falls back** to static/hardcoded values if database is empty:
     ```python
     metrics = [
         ModelPerformanceMetrics(
             model_name="Random Forest",
             accuracy_score=0.85,  # Static
             mape=12.5,  # Static
             ...
         ),
         # ... 5 more static models
     ]
     ```

**Current Status:** ⚠️ **USING STATIC FALLBACK**
- Database tables (`model_training_history`, `model_predictions`) are empty
- System falls back to hardcoded values:
  - Random Forest: 85%
  - XGBoost: 82%
  - Gradient Boosting: 78%
  - Linear Regression: 72%
  - Ridge Regression: 75%
  - SVR: 70%
  - **Average: 77.0%** ✅ (matches displayed value)

**Status:** ⚠️ **PARTIALLY DYNAMIC**
- **Intended to be dynamic** - queries database for real metrics
- **Currently static** - database tables are empty, using fallback values
- **Will become dynamic** once training data is stored in database

**Code Location:**
- Frontend: `src/ui/web/src/pages/Forecasting.tsx:347-349`
- Backend: `src/api/routers/advanced_forecasting.py:270-345`

---

### 4. Models Active: 6 ⚠️ **PARTIALLY DYNAMIC**

**Source:** `dashboardData?.model_performance?.length`

**Calculation:**
- Same as Avg Accuracy - uses `get_model_performance_metrics()`
- Returns count of models in the metrics array
- Currently returns 6 (hardcoded fallback models)

**Current Status:** ⚠️ **USING STATIC FALLBACK**
- Returns 6 hardcoded models:
  1. Random Forest
  2. XGBoost
  3. Gradient Boosting
  4. Linear Regression
  5. Ridge Regression
  6. Support Vector Regression

**Status:** ⚠️ **PARTIALLY DYNAMIC**
- **Intended to be dynamic** - queries `model_training_history` for active models
- **Currently static** - database table is empty, using fallback list
- **Will become dynamic** once training records are stored

**Code Location:**
- Frontend: `src/ui/web/src/pages/Forecasting.tsx:365`
- Backend: `src/api/routers/advanced_forecasting.py:270-345, 380-400`

---

## Database Tables Status

### Required Tables for Dynamic Metrics

1. **`model_training_history`** ❌ **EMPTY**
   - Should store: model_name, training_date, accuracy_score, mape_score
   - Used to: Get active models, last training dates

2. **`model_predictions`** ❌ **EMPTY**
   - Should store: model_name, sku, predicted_value, actual_value, prediction_date
   - Used to: Calculate accuracy, MAPE, drift scores

3. **`model_performance_history`** ❌ **EMPTY**
   - Should store: model_name, accuracy_score, mape_score, drift_score, status
   - Used to: Track performance over time

### Tables Exist But Are Empty

The tables are created by `scripts/setup/create_model_tracking_tables.sql` but are not being populated when models are trained.

---

## Recommendations

### Immediate Actions

1. ✅ **Products Forecasted** - Already dynamic, no action needed
2. ✅ **Reorder Alerts** - Already dynamic, no action needed
3. ⚠️ **Avg Accuracy** - Needs database population
4. ⚠️ **Models Active** - Needs database population

### To Make Metrics Fully Dynamic

1. **Populate Training History**
   - When models are trained, insert records into `model_training_history`
   - Include: model_name, training_date, accuracy_score, mape_score

2. **Track Predictions**
   - When forecasts are generated, insert into `model_predictions`
   - Include: model_name, sku, predicted_value, prediction_date
   - Update with `actual_value` when actual demand is known

3. **Update Performance History**
   - Periodically calculate and store metrics in `model_performance_history`
   - Use for trend analysis and drift detection

4. **Training Integration**
   - Modify training scripts to write to database
   - Update `scripts/forecasting/phase3_advanced_forecasting.py`
   - Update `scripts/forecasting/rapids_gpu_forecasting.py`

### Code Changes Needed

1. **After Training:**
   ```python
   # In training scripts, after model training:
   await conn.execute("""
       INSERT INTO model_training_history 
       (model_name, training_date, accuracy_score, mape_score, status)
       VALUES ($1, $2, $3, $4, 'completed')
   """, model_name, datetime.now(), accuracy, mape)
   ```

2. **After Forecasting:**
   ```python
   # In forecasting service, after generating forecast:
   await conn.execute("""
       INSERT INTO model_predictions 
       (model_name, sku, predicted_value, prediction_date)
       VALUES ($1, $2, $3, $4)
   """, model_name, sku, predicted_value, datetime.now())
   ```

3. **Periodic Performance Calculation:**
   ```python
   # Run periodically to update performance history:
   for model_name in active_models:
       accuracy = calculate_accuracy(model_name)
       mape = calculate_mape(model_name)
       drift = calculate_drift(model_name)
       status = determine_status(accuracy, drift)
       
       await conn.execute("""
           INSERT INTO model_performance_history 
           (model_name, accuracy_score, mape_score, drift_score, status)
           VALUES ($1, $2, $3, $4, $5)
       """, model_name, accuracy, mape, drift, status)
   ```

---

## Conclusion

### Current State

- **2 out of 4 cards are fully dynamic** ✅
  - Products Forecasted: Dynamic
  - Reorder Alerts: Dynamic

- **2 out of 4 cards use static fallback** ⚠️
  - Avg Accuracy: Static fallback (77.0%)
  - Models Active: Static fallback (6 models)

### Intended State

All 4 cards are **designed to be dynamic** but the model performance metrics fall back to static values when database tables are empty.

### Next Steps

1. Integrate database writes into training scripts
2. Track predictions in `model_predictions` table
3. Populate `model_training_history` during training
4. Once populated, metrics will automatically become dynamic

---

**Assessment Date:** 2025-11-15  
**Assessed By:** Automated Testing & Code Analysis

