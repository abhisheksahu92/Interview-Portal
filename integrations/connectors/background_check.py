"""Background-verification connector (vendor-neutral stub).

Indian BGV vendors (AuthBridge, IDfy, SpringVerify, ...) all expose the same
shape: POST a candidate with the packages you want, get back a case id you poll.
This adapter models that generically — point ``base_url`` at the vendor and give
it an ``api_key``; ``packages`` is a comma-separated list.
"""

from integrations.connectors.base import Connector, ConnectorResult


class BackgroundCheckConnector(Connector):
    kind = "BACKGROUND_CHECK"
    label = "Background check"
    required_settings = ("api_key", "base_url")
    optional_settings = ("packages",)
    probe_path = "/v1/ping"

    def packages(self):
        raw = self.get("packages") or "identity,employment,education"
        return [part.strip() for part in raw.split(",") if part.strip()]

    def candidate_body(self, candidate):
        user = getattr(candidate, "user", None)
        return {
            "candidate": {
                "email": getattr(user, "email", "") or getattr(candidate, "email", "") or "",
                "name": (
                    getattr(user, "get_full_name", lambda: "")()
                    or getattr(candidate, "name", "")
                    or ""
                ),
                "phone": getattr(candidate, "phone", "") or "",
            },
            "packages": self.packages(),
            "reference": f"ip-candidate-{getattr(candidate, 'pk', '')}",
        }

    def start_check(self, candidate) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult.skipped(
                "not configured: missing " + ", ".join(self.missing_settings())
            )
        return self._call(
            "POST",
            "/v1/checks",
            json=self.candidate_body(candidate),
            success=f"background check started for candidate {getattr(candidate, 'pk', '')}",
        )
