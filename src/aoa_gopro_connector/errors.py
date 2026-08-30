"""Connector error taxonomy."""

from __future__ import annotations


class GoProConnectorError(RuntimeError):
    """Base class for expected connector failures."""


class ContractError(GoProConnectorError, ValueError):
    """A typed packet or domain invariant is invalid."""


class PublicSafetyError(GoProConnectorError, ValueError):
    """A value is not safe for a public artifact."""


class TransportError(GoProConnectorError):
    """A read transport failed without establishing a result."""
