"""
Telemetry-specific SQL queries for warehouse operations.

Provides parameterized queries for IoT time-series data stored in TimescaleDB
including equipment monitoring, performance metrics, and operational analytics.
"""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from .sql_retriever import SQLRetriever

@dataclass
class TelemetryData:
    """Data class for telemetry measurements."""
    ts: datetime
    equipment_id: str
    metric: str
    value: float

@dataclass
class TelemetrySummary:
    """Summary statistics for telemetry data."""
    equipment_id: str
    metric: str
    avg_value: float
    min_value: float
    max_value: float
    count: int
    time_range: Tuple[datetime, datetime]

class TelemetryQueries:
    """Telemetry-specific query operations."""
    
    def __init__(self, sql_retriever: SQLRetriever):
        self.sql_retriever = sql_retriever
    
    async def get_equipment_telemetry(
        self,
        equipment_id: str,
        metric: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[TelemetryData]:
        """
        Get telemetry data for specific equipment.
        
        Args:
            equipment_id: Equipment identifier
            metric: Optional metric filter
            start_time: Start time for data range
            end_time: End time for data range
            limit: Maximum number of records to return
            
        Returns:
            List of TelemetryData objects
        """
        # Build dynamic WHERE clause
        where_conditions = ["equipment_id = $1"]
        params = [equipment_id]
        param_count = 1
        
        if metric:
            param_count += 1
            where_conditions.append(f"metric = ${param_count}")
            params.append(metric)
        
        if start_time:
            param_count += 1
            where_conditions.append(f"ts >= ${param_count}")
            params.append(start_time)
        
        if end_time:
            param_count += 1
            where_conditions.append(f"ts <= ${param_count}")
            params.append(end_time)
        
        where_clause = "WHERE " + " AND ".join(where_conditions)
        
        param_count += 1
        limit_param = f"${param_count}"
        params.append(limit)
        
        query = f"""
        SELECT ts, equipment_id, metric, value
        FROM equipment_telemetry 
        {where_clause}
        ORDER BY ts DESC
        LIMIT {limit_param}
        """
        
        try:
            results = await self.sql_retriever.execute_query(query, tuple(params))
            return [
                TelemetryData(
                    ts=row['ts'],
                    equipment_id=row['equipment_id'],
                    metric=row['metric'],
                    value=row['value']
                )
                for row in results
            ]
        except Exception as e:
            raise Exception(f"Failed to get telemetry data for equipment {equipment_id}: {e}")
    
    async def get_telemetry_summary(
        self,
        equipment_id: str,
        metric: str,
        time_range_hours: int = 24
    ) -> TelemetrySummary:
        """
        Get summary statistics for equipment telemetry.
        
        Args:
            equipment_id: Equipment identifier
            metric: Metric name
            time_range_hours: Time range in hours from now
            
        Returns:
            TelemetrySummary with statistics
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=time_range_hours)
        
        query = """
        SELECT 
            AVG(value) as avg_value,
            MIN(value) as min_value,
            MAX(value) as max_value,
            COUNT(*) as count,
            MIN(ts) as start_time,
            MAX(ts) as end_time
        FROM equipment_telemetry 
        WHERE equipment_id = $1 
        AND metric = $2 
        AND ts >= $3 
        AND ts <= $4
        """
        
        try:
            results = await self.sql_retriever.execute_query(
                query, 
                (equipment_id, metric, start_time, end_time)
            )
            
            if results and results[0]['count'] > 0:
                row = results[0]
                return TelemetrySummary(
                    equipment_id=equipment_id,
                    metric=metric,
                    avg_value=float(row['avg_value']),
                    min_value=float(row['min_value']),
                    max_value=float(row['max_value']),
                    count=int(row['count']),
                    time_range=(row['start_time'], row['end_time'])
                )
            else:
                return TelemetrySummary(
                    equipment_id=equipment_id,
                    metric=metric,
                    avg_value=0.0,
                    min_value=0.0,
                    max_value=0.0,
                    count=0,
                    time_range=(start_time, end_time)
                )
                
        except Exception as e:
            raise Exception(f"Failed to get telemetry summary for {equipment_id}:{metric}: {e}")
    
    async def get_equipment_list(self) -> List[str]:
        """Get list of all equipment IDs."""
        query = """
        SELECT DISTINCT equipment_id 
        FROM equipment_telemetry 
        ORDER BY equipment_id
        """
        
        try:
            results = await self.sql_retriever.execute_query(query)
            return [row['equipment_id'] for row in results]
        except Exception as e:
            raise Exception(f"Failed to get equipment list: {e}")
    
    async def get_metrics_list(self, equipment_id: Optional[str] = None) -> List[str]:
        """Get list of all metrics."""
        if equipment_id:
            query = """
            SELECT DISTINCT metric 
            FROM equipment_telemetry 
            WHERE equipment_id = $1
            ORDER BY metric
            """
            params = (equipment_id,)
        else:
            query = """
            SELECT DISTINCT metric 
            FROM equipment_telemetry 
            ORDER BY metric
            """
            params = None
        
        try:
            results = await self.sql_retriever.execute_query(query, params)
            return [row['metric'] for row in results]
        except Exception as e:
            raise Exception(f"Failed to get metrics list: {e}")
    
    async def get_equipment_health_status(self) -> Dict[str, Any]:
        """Get overall equipment health status."""
        query = """
        SELECT 
            equipment_id,
            metric,
            AVG(value) as avg_value,
            COUNT(*) as data_points,
            MAX(ts) as last_reading
        FROM equipment_telemetry 
        WHERE ts >= NOW() - INTERVAL '1 hour'
        GROUP BY equipment_id, metric
        ORDER BY equipment_id, metric
        """
        
        try:
            results = await self.sql_retriever.execute_query(query)
            return {
                "equipment_count": len(set(row['equipment_id'] for row in results)),
                "total_metrics": len(set(row['metric'] for row in results)),
                "data_points_last_hour": sum(row['data_points'] for row in results),
                "equipment_details": results
            }
        except Exception as e:
            raise Exception(f"Failed to get equipment health status: {e}")
