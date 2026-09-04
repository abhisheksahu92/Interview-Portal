"""Keka HRMS connector.

Keka exposes a REST API under ``https://<subdomain>.keka.com/api/v1``; the
adapter needs an API key and the customer's subdomain. Employees are created
from the vendor-neutral payload in :func:`integrations.connectors.base.employee_payload`.
"""

from integrations.connectors.base import Connector, ConnectorResult, employee_payload


class KekaConnector(Connector):
    kind = "KEKA"
    label = "Keka HRMS"
    required_settings = ("api_key", "subdomain")
    optional_settings = ("department",)
    probe_path = "/employees?limit=1"

    def base_url(self):
        override = self.get("base_url")
        if override:
            return override
        return f"https://{self.get('subdomain')}.keka.com/api/v1"

    def employee_body(self, application):
        record = employee_payload(application)
        body = {
            "firstName": record["first_name"] or record["full_name"],
            "lastName": record["last_name"],
            "email": record["email"],
            "mobileNumber": record["phone"],
            "jobTitle": record["job_title"],
            "location": record["location"],
            "employmentType": record["employment_type"],
            "sourceApplicationId": record["application_id"],
        }
        if record["joining_date"]:
            body["joiningDate"] = record["joining_date"]
        if self.get("department"):
            body["department"] = self.get("department")
        return body

    def push_hire(self, application) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult.skipped(
                "not configured: missing " + ", ".join(self.missing_settings())
            )
        return self._call(
            "POST",
            "/employees",
            json=self.employee_body(application),
            success=f"employee created for application {application.pk}",
        )
