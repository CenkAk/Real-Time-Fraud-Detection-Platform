from __future__ import annotations

import os
import socket
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    configured = os.getenv("INTEGRATION_DATABASE_URL")
    if configured:
        yield configured
        return

    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="psycopg") as container:
        yield container.get_connection_url()


@pytest.fixture(scope="session")
def kafka_bootstrap_servers() -> Iterator[str]:
    configured = os.getenv("INTEGRATION_KAFKA_BOOTSTRAP_SERVERS")
    if configured:
        yield configured
        return

    from testcontainers.core.container import DockerContainer
    from testcontainers.core.waiting_utils import wait_for_logs

    with socket.socket() as port_probe:
        port_probe.bind(("", 0))
        host_port = port_probe.getsockname()[1]
    advertised_host = os.getenv("TESTCONTAINERS_HOST_OVERRIDE", "127.0.0.1")
    container = (
        DockerContainer("redpandadata/redpanda:v24.2.18")
        .with_bind_ports(9092, host_port)
        .with_command(
            "redpanda start --overprovisioned --smp=1 --memory=512M "
            "--reserve-memory=0M --node-id=0 --check=false "
            "--kafka-addr=0.0.0.0:9092 "
            f"--advertise-kafka-addr={advertised_host}:{host_port}"
        )
    )
    with container:
        wait_for_logs(container, "Successfully started Redpanda")
        host = container.get_container_host_ip()
        port = container.get_exposed_port(9092)
        yield f"{host}:{port}"
