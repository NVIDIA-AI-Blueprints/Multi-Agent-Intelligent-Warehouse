# Synthetic Data Generators

This directory contains comprehensive synthetic data generators for the Warehouse Operational Assistant system. These tools create realistic warehouse data across all databases to enable impressive demos and thorough testing. ## Quick Start ### Quick Demo Data (Recommended for Demos)
For a fast demo setup with realistic data:

```bash
cd scripts
./run_quick_demo.sh
```

This generates:
- 12 users across all roles
- 25 inventory items (including low stock alerts)
- 8 tasks with various statuses
- 8 safety incidents with different severities
- 7 days of equipment telemetry data
- 50 audit log entries ### Full Synthetic Data (Comprehensive)
For a complete warehouse simulation:

```bash
cd scripts
./run_data_generation.sh
```

This generates:
- 50 users across all roles
- 1,000 inventory items with realistic locations
- 500 tasks with various statuses and realistic payloads
- 100 safety incidents with different severities and types
- 30 days of equipment telemetry data (50 pieces of equipment)
- 200 audit log entries for user actions
- 1,000 vector embeddings for knowledge base
- Redis cache data for sessions and metrics ## Generated Data Overview ### Database Coverage
-**PostgreSQL/TimescaleDB**: All structured data including inventory, tasks, users, safety incidents, equipment telemetry, and audit logs
-**Milvus**: Vector embeddings for knowledge base and document search
-**Redis**: Session data, cache data, and real-time metrics ### Data Types Generated #### 👥 Users
-**Roles**: admin, manager, supervisor, operator, viewer
-**Realistic Names**: Generated using Faker library
-**Authentication**: Properly hashed passwords (default: "password123")
-**Activity**: Last login times and session data #### Inventory Items
-**SKUs**: Realistic product codes (SKU001, SKU002, etc.)
-**Locations**: Zone-based warehouse locations (Zone A-Aisle 1-Rack 2-Level 3)
-**Quantities**: Realistic stock levels with some items below reorder point
-**Categories**: Electronics, Clothing, Home & Garden, Automotive, Tools, etc. #### Tasks
-**Types**: pick, pack, putaway, cycle_count, replenishment, inspection
-**Statuses**: pending, in_progress, completed, cancelled
-**Payloads**: Realistic task data including order IDs, priorities, equipment assignments
-**Assignees**: Linked to actual users in the system #### Safety Incidents
-**Types**: slip_and_fall, equipment_malfunction, chemical_spill, fire_hazard, etc.
-**Severities**: low, medium, high, critical
-**Descriptions**: Realistic incident descriptions
-**Reporters**: Linked to actual users #### Equipment Telemetry
-**Equipment Types**: forklift, pallet_jack, conveyor, scanner, printer, crane, etc.
-**Metrics**: battery_level, temperature, vibration, usage_hours, power_consumption
-**Time Series**: Realistic data points over time with proper timestamps
-**Equipment Status**: Online/offline states and performance metrics #### Audit Logs
-**Actions**: login, logout, inventory_view, task_create, safety_report, etc.
-**Resource Types**: inventory, task, user, equipment, safety, system
-**Details**: IP addresses, user agents, timestamps, additional context
-**User Tracking**: All actions linked to actual users ## 🛠️ Technical Details ### Prerequisites
- Python 3.9+
- PostgreSQL/TimescaleDB running on port 5435
- Redis running on port 6379 (optional)
- Milvus running on port 19530 (optional) ### Dependencies
- `psycopg[binary]` - PostgreSQL async driver
- `bcrypt` - Password hashing
- `faker` - Realistic data generation
- `pymilvus` - Milvus vector database client
- `redis` - Redis client ### Database Credentials
The generators use the following default credentials:
-**PostgreSQL**: `warehouse:warehousepw@localhost:5435/warehouse`
-**Redis**: `localhost:6379`
-**Milvus**: `localhost:19530` ## Use Cases ### Demo Preparation
1.**Quick Demo**: Use `run_quick_demo.sh` for fast setup
2.**Full Demo**: Use `run_data_generation.sh` for comprehensive data
3.**Custom Data**: Modify the Python scripts for specific requirements ### Testing
-**Unit Testing**: Generate specific data sets for testing
-**Performance Testing**: Create large datasets for load testing
-**Integration Testing**: Ensure all systems work with realistic data ### Development
-**Feature Development**: Test new features with realistic data
-**Bug Reproduction**: Create specific data scenarios for debugging
-**UI Development**: Populate frontend with realistic warehouse data ## Customization ### Modifying Data Generation
Edit the Python scripts to customize:
-**Data Volume**: Change counts in the generator functions
-**Data Types**: Add new product categories, incident types, etc.
-**Realism**: Adjust ranges, distributions, and relationships
-**Warehouse Layout**: Modify zones, aisles, racks, and levels ### Adding New Data Types
1. Create a new generator method in the class
2. Add the method to `generate_all_demo_data()`
3. Update the summary logging
4. Test with the existing database schema ## Important Notes ### Data Safety
-**WARNING**: These scripts will DELETE existing data before generating new data
-**Backup**: Always backup your database before running data generation
-**Production**: Never run these scripts on production databases ### Performance
-**Quick Demo**: ~30 seconds to generate
-**Full Synthetic**: ~5-10 minutes to generate
-**Database Size**: Full synthetic data creates ~100MB+ of data ### Troubleshooting
-**Connection Issues**: Ensure all databases are running
-**Permission Issues**: Check database user permissions
-**Memory Issues**: Reduce data counts for large datasets
-**Foreign Key Errors**: Ensure data generation order respects dependencies ## Data Quality Features ### Realistic Relationships
-**User-Task Links**: Tasks assigned to actual users
-**Inventory Locations**: Realistic warehouse zone assignments
-**Equipment Metrics**: Type-specific telemetry data
-**Audit Trails**: Complete user action tracking ### Data Consistency
-**Foreign Keys**: All relationships properly maintained
-**Timestamps**: Realistic time sequences and durations
-**Status Flows**: Logical task and incident status progressions
-**Geographic Data**: Consistent location hierarchies ### Alert Generation
-**Low Stock**: Items below reorder point for inventory alerts
-**Critical Incidents**: High-severity safety incidents
-**Equipment Issues**: Offline equipment and performance problems
-**Task Overdue**: Tasks past due dates ## Success Indicators

After running the data generators, you should see:
-  All database tables populated with realistic data
-  Frontend showing populated inventory, tasks, and incidents
-  Chat interface working with realistic warehouse queries
-  Monitoring dashboards displaying metrics and KPIs
-  User authentication working with generated users
-  Action tools executing with realistic data context

Your warehouse is now ready for an impressive demo! 
