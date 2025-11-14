"""
MCP Service Discovery and Registry

This module provides service discovery and registry capabilities for the MCP system,
enabling automatic discovery, registration, and management of MCP services and adapters.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import uuid
import hashlib

from .base import MCPAdapter, MCPManager, AdapterType
from .tool_discovery import ToolDiscoveryService, DiscoveredTool, ToolCategory

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status enumeration."""

    UNKNOWN = "unknown"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    MAINTENANCE = "maintenance"


class ServiceType(Enum):
    """Service type enumeration."""

    MCP_SERVER = "mcp_server"
    MCP_CLIENT = "mcp_client"
    MCP_ADAPTER = "mcp_adapter"
    TOOL_DISCOVERY = "tool_discovery"
    TOOL_BINDING = "tool_binding"
    TOOL_ROUTING = "tool_routing"
    TOOL_VALIDATION = "tool_validation"
    EXTERNAL_SERVICE = "external_service"


@dataclass
class ServiceInfo:
    """Information about a registered service."""

    service_id: str
    service_name: str
    service_type: ServiceType
    version: str
    status: ServiceStatus
    endpoint: str
    health_check_url: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: Optional[datetime] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class ServiceHealth:
    """Health information for a service."""

    service_id: str
    is_healthy: bool
    response_time: float
    last_check: datetime
    error_message: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ServiceDiscoveryConfig:
    """Configuration for service discovery."""

    discovery_interval: int = 30  # seconds
    health_check_interval: int = 60  # seconds
    service_timeout: int = 30  # seconds
    max_retries: int = 3
    enable_auto_registration: bool = True
    enable_health_monitoring: bool = True
    enable_load_balancing: bool = True
    registry_ttl: int = 300  # seconds


class ServiceRegistry:
    """
    Registry for MCP services and adapters.

    This registry provides:
    - Service registration and deregistration
    - Service discovery and lookup
    - Health monitoring and status tracking
    - Load balancing and failover
    - Service metadata management
    """

    def __init__(self, config: ServiceDiscoveryConfig = None):
        self.config = config or ServiceDiscoveryConfig()
        self.services: Dict[str, ServiceInfo] = {}
        self.health_status: Dict[str, ServiceHealth] = {}
        self.service_endpoints: Dict[str, List[str]] = {}
        self.service_tags: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
        self._health_check_task = None
        self._running = False

    async def start(self) -> None:
        """Start the service registry."""
        if self._running:
            return

        self._running = True
        logger.info("Starting MCP Service Registry")

        # Start health monitoring
        if self.config.enable_health_monitoring:
            self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def stop(self) -> None:
        """Stop the service registry."""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info("MCP Service Registry stopped")

    async def register_service(
        self,
        service_name: str,
        service_type: ServiceType,
        version: str,
        endpoint: str,
        capabilities: List[str] = None,
        metadata: Dict[str, Any] = None,
        health_check_url: Optional[str] = None,
        tags: List[str] = None,
    ) -> str:
        """
        Register a service with the registry.

        Args:
            service_name: Name of the service
            service_type: Type of service
            version: Service version
            endpoint: Service endpoint URL
            capabilities: List of service capabilities
            metadata: Additional metadata
            health_check_url: Health check endpoint URL
            tags: Service tags for filtering

        Returns:
            Service ID
        """
        async with self._lock:
            service_id = self._generate_service_id(service_name, endpoint)

            service_info = ServiceInfo(
                service_id=service_id,
                service_name=service_name,
                service_type=service_type,
                version=version,
                status=ServiceStatus.STARTING,
                endpoint=endpoint,
                health_check_url=health_check_url,
                capabilities=capabilities or [],
                metadata=metadata or {},
                tags=tags or [],
            )

            self.services[service_id] = service_info
            self._update_service_endpoints(service_info)
            self._update_service_tags(service_info)

            logger.info(f"Registered service: {service_name} ({service_id})")
            return service_id

    async def deregister_service(self, service_id: str) -> bool:
        """
        Deregister a service from the registry.

        Args:
            service_id: Service ID to deregister

        Returns:
            True if service was deregistered, False if not found
        """
        async with self._lock:
            if service_id not in self.services:
                return False

            service_info = self.services[service_id]

            # Remove from endpoints
            if service_info.endpoint in self.service_endpoints:
                self.service_endpoints[service_info.endpoint].remove(service_id)
                if not self.service_endpoints[service_info.endpoint]:
                    del self.service_endpoints[service_info.endpoint]

            # Remove from tags
            for tag in service_info.tags:
                if tag in self.service_tags:
                    self.service_tags[tag].discard(service_id)
                    if not self.service_tags[tag]:
                        del self.service_tags[tag]

            # Remove service
            del self.services[service_id]

            # Remove health status
            if service_id in self.health_status:
                del self.health_status[service_id]

            logger.info(f"Deregistered service: {service_id}")
            return True

    async def discover_services(
        self,
        service_type: Optional[ServiceType] = None,
        tags: List[str] = None,
        status: Optional[ServiceStatus] = None,
        healthy_only: bool = False,
    ) -> List[ServiceInfo]:
        """
        Discover services matching criteria.

        Args:
            service_type: Filter by service type
            tags: Filter by tags
            status: Filter by status
            healthy_only: Only return healthy services

        Returns:
            List of matching services
        """
        async with self._lock:
            matching_services = []

            for service_info in self.services.values():
                # Filter by service type
                if service_type and service_info.service_type != service_type:
                    continue

                # Filter by status
                if status and service_info.status != status:
                    continue

                # Filter by tags
                if tags and not any(tag in service_info.tags for tag in tags):
                    continue

                # Filter by health
                if healthy_only:
                    health = self.health_status.get(service_info.service_id)
                    if not health or not health.is_healthy:
                        continue

                matching_services.append(service_info)

            return matching_services

    async def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """Get service information by ID."""
        async with self._lock:
            return self.services.get(service_id)

    async def get_service_by_name(self, service_name: str) -> List[ServiceInfo]:
        """Get services by name."""
        async with self._lock:
            return [s for s in self.services.values() if s.service_name == service_name]

    async def get_service_by_endpoint(self, endpoint: str) -> List[ServiceInfo]:
        """Get services by endpoint."""
        async with self._lock:
            service_ids = self.service_endpoints.get(endpoint, [])
            return [self.services[sid] for sid in service_ids if sid in self.services]

    async def get_services_by_tag(self, tag: str) -> List[ServiceInfo]:
        """Get services by tag."""
        async with self._lock:
            service_ids = self.service_tags.get(tag, set())
            return [self.services[sid] for sid in service_ids if sid in self.services]

    async def update_service_status(
        self, service_id: str, status: ServiceStatus
    ) -> bool:
        """Update service status."""
        async with self._lock:
            if service_id not in self.services:
                return False

            self.services[service_id].status = status
            self.services[service_id].last_heartbeat = datetime.utcnow()
            return True

    async def heartbeat(self, service_id: str) -> bool:
        """Record service heartbeat."""
        async with self._lock:
            if service_id not in self.services:
                return False

            self.services[service_id].last_heartbeat = datetime.utcnow()
            return True

    async def get_service_health(self, service_id: str) -> Optional[ServiceHealth]:
        """Get service health information."""
        async with self._lock:
            return self.health_status.get(service_id)

    async def get_all_services(self) -> List[ServiceInfo]:
        """Get all registered services."""
        async with self._lock:
            return list(self.services.values())

    async def get_service_statistics(self) -> Dict[str, Any]:
        """Get service registry statistics."""
        async with self._lock:
            total_services = len(self.services)
            healthy_services = sum(
                1 for h in self.health_status.values() if h.is_healthy
            )

            service_types = {}
            for service in self.services.values():
                service_types[service.service_type.value] = (
                    service_types.get(service.service_type.value, 0) + 1
                )

            return {
                "total_services": total_services,
                "healthy_services": healthy_services,
                "unhealthy_services": total_services - healthy_services,
                "service_types": service_types,
                "registry_uptime": datetime.utcnow().isoformat(),
            }

    def _generate_service_id(self, service_name: str, endpoint: str) -> str:
        """Generate unique service ID."""
        content = f"{service_name}:{endpoint}:{datetime.utcnow().timestamp()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _update_service_endpoints(self, service_info: ServiceInfo) -> None:
        """Update service endpoints mapping."""
        if service_info.endpoint not in self.service_endpoints:
            self.service_endpoints[service_info.endpoint] = []

        if service_info.service_id not in self.service_endpoints[service_info.endpoint]:
            self.service_endpoints[service_info.endpoint].append(
                service_info.service_id
            )

    def _update_service_tags(self, service_info: ServiceInfo) -> None:
        """Update service tags mapping."""
        for tag in service_info.tags:
            if tag not in self.service_tags:
                self.service_tags[tag] = set()
            self.service_tags[tag].add(service_info.service_id)

    async def _health_check_loop(self) -> None:
        """Health check loop."""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                if self._running:
                    await self._perform_health_checks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def _perform_health_checks(self) -> None:
        """Perform health checks on all services."""
        tasks = []

        for service_id, service_info in self.services.items():
            if service_info.health_check_url:
                task = asyncio.create_task(
                    self._check_service_health(service_id, service_info)
                )
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_service_health(
        self, service_id: str, service_info: ServiceInfo
    ) -> None:
        """Check health of a specific service."""
        try:
            import aiohttp

            start_time = datetime.utcnow()

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.service_timeout)
            ) as session:
                async with session.get(service_info.health_check_url) as response:
                    response_time = (datetime.utcnow() - start_time).total_seconds()

                    health = ServiceHealth(
                        service_id=service_id,
                        is_healthy=response.status == 200,
                        response_time=response_time,
                        last_check=datetime.utcnow(),
                        error_message=(
                            None
                            if response.status == 200
                            else f"HTTP {response.status}"
                        ),
                    )

                    if response.status == 200:
                        try:
                            data = await response.json()
                            health.metrics = data.get("metrics", {})
                        except:
                            pass

                    self.health_status[service_id] = health

        except Exception as e:
            health = ServiceHealth(
                service_id=service_id,
                is_healthy=False,
                response_time=0.0,
                last_check=datetime.utcnow(),
                error_message=str(e),
            )
            self.health_status[service_id] = health


class ServiceDiscovery:
    """
    Service discovery manager for MCP system.

    This manager provides:
    - Automatic service discovery
    - Service registration and management
    - Load balancing and failover
    - Service health monitoring
    - Service metadata and capabilities management
    """

    def __init__(self, registry: ServiceRegistry, tool_discovery: ToolDiscoveryService):
        self.registry = registry
        self.tool_discovery = tool_discovery
        self.discovery_callbacks: List[Callable] = []
        self._running = False

    async def start(self) -> None:
        """Start service discovery."""
        if self._running:
            return

        self._running = True
        await self.registry.start()

        # Register with tool discovery
        await self.tool_discovery.register_discovery_source(
            "service_discovery", self, "external"
        )

        logger.info("MCP Service Discovery started")

    async def stop(self) -> None:
        """Stop service discovery."""
        self._running = False
        await self.registry.stop()
        logger.info("MCP Service Discovery stopped")

    async def register_adapter(
        self, adapter: MCPAdapter, service_name: str = None
    ) -> str:
        """Register an MCP adapter as a service."""
        service_name = service_name or adapter.config.name

        capabilities = []
        if hasattr(adapter, "tools"):
            capabilities.extend(
                [f"tool:{tool_name}" for tool_name in adapter.tools.keys()]
            )

        metadata = {
            "adapter_type": adapter.config.adapter_type.value,
            "tools_count": len(adapter.tools) if hasattr(adapter, "tools") else 0,
            "config": adapter.config.__dict__,
        }

        return await self.registry.register_service(
            service_name=service_name,
            service_type=ServiceType.MCP_ADAPTER,
            version="1.0.0",
            endpoint=f"mcp://adapter/{service_name}",
            capabilities=capabilities,
            metadata=metadata,
            tags=["adapter", adapter.config.adapter_type.value],
        )

    async def discover_adapters(
        self, adapter_type: AdapterType = None
    ) -> List[ServiceInfo]:
        """Discover MCP adapters."""
        tags = ["adapter"]
        if adapter_type:
            tags.append(adapter_type.value)

        return await self.registry.discover_services(
            service_type=ServiceType.MCP_ADAPTER, tags=tags, healthy_only=True
        )

    async def discover_tools(
        self, tool_category: ToolCategory = None
    ) -> List[DiscoveredTool]:
        """Discover tools from all registered services."""
        tools = []

        # Get all adapter services
        adapters = await self.discover_adapters()

        for adapter_info in adapters:
            try:
                # This would integrate with the actual adapter to get tools
                # For now, we'll return empty list
                pass
            except Exception as e:
                logger.error(
                    f"Error discovering tools from adapter {adapter_info.service_id}: {e}"
                )

        return tools

    async def get_service_endpoint(
        self, service_name: str, load_balance: bool = True
    ) -> Optional[str]:
        """Get endpoint for a service with optional load balancing."""
        services = await self.registry.get_service_by_name(service_name)

        if not services:
            return None

        # Filter healthy services
        healthy_services = []
        for service in services:
            health = await self.registry.get_service_health(service.service_id)
            if health and health.is_healthy:
                healthy_services.append(service)

        if not healthy_services:
            return None

        if load_balance and len(healthy_services) > 1:
            # Simple round-robin load balancing
            # In production, this would use more sophisticated algorithms
            import random

            service = random.choice(healthy_services)
        else:
            service = healthy_services[0]

        return service.endpoint

    async def add_discovery_callback(self, callback: Callable) -> None:
        """Add a callback for service discovery events."""
        self.discovery_callbacks.append(callback)

    async def remove_discovery_callback(self, callback: Callable) -> None:
        """Remove a discovery callback."""
        if callback in self.discovery_callbacks:
            self.discovery_callbacks.remove(callback)

    async def _notify_discovery_callbacks(
        self, event_type: str, service_info: ServiceInfo
    ) -> None:
        """Notify discovery callbacks of events."""
        for callback in self.discovery_callbacks:
            try:
                await callback(event_type, service_info)
            except Exception as e:
                logger.error(f"Error in discovery callback: {e}")

    async def get_discovery_status(self) -> Dict[str, Any]:
        """Get service discovery status."""
        registry_stats = await self.registry.get_service_statistics()

        return {
            "running": self._running,
            "registry": registry_stats,
            "callbacks": len(self.discovery_callbacks),
        }
