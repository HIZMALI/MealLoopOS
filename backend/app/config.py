"""Server-owned modes. No request can change configuration or database selection."""
import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mode: str = "LOCAL"
    hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")

    @property
    def public(self):
        return self.mode == "PUBLIC_DEMO"

    @classmethod
    def from_env(cls):
        mode = os.environ.get("MEALLOOP_MODE", "LOCAL")
        if mode not in ("LOCAL", "PUBLIC_DEMO"):
            raise ValueError("MEALLOOP_MODE must be exactly LOCAL or PUBLIC_DEMO.")
        if mode == "LOCAL":
            return cls()
        if "MEALLOOP_DATABASE_URL" in os.environ:
            raise ValueError("PUBLIC_DEMO forbids MEALLOOP_DATABASE_URL; its database is server-fixed and isolated.")
        hosts = tuple(os.environ.get("MEALLOOP_PUBLIC_HOSTS", "").split(","))
        if not hosts or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", h)
                            or ".." in h for h in hosts):
            raise ValueError("PUBLIC_DEMO requires explicit comma-separated MEALLOOP_PUBLIC_HOSTS, without schemes, wildcards or ports.")
        return cls(mode, hosts)
