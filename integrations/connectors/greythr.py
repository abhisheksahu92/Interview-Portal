"""greytHR connector.

greytHR is hosted per customer domain (``https://<domain>/api/v2``) and takes a
bearer access token. Employee creation posts to ``/employee/v2/employees``.
"""

from integrations.connectors.base import Connector, ConnectorResult, employee_payload


class GreytHRConnector(Connector):
    kind = "GREYTHR"
    label = "greytHR"
    required_settings = ("api_key", "domain")
    optional_settings = ("business_unit",)
    probe_path = "/employee/v2/employees?limit=1"

    def base_url(self):
        override = self.get("base_url")
        if override:
            return override
        return f"https://{self.get('domain')}/api/v2"

    def employee_body(self, application):
        record = employee_payload(application)
        body = {
            "employee": {
                "firstName": record["first_name"] or record["full_name"],
                "lastName": record["last_name"],
                "personalEmail": record["email"],
                "mobile": record["phone"],
                "designation": record["job_title"],
                "workLocation": record["location"],
                "dateOfJoining": record["joining_date"],
            },
            "externalRef": f"ip-application-{record['application_id']}",
        }
        if self.get("business_unit"):
            body["employee"]["businessUnit"] = self.get("business_unit")
        return body

    def push_hire(self, application) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult.skipped(
                "not configured: missing " + ", ".join(self.missing_settings())
            )
        return self._call(
            "POST",
            "/employee/v2/employees",
            json=self.employee_body(application),
            success=f"employee created for application {application.pk}",
        )
