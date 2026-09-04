"""Zoho People connector.

Zoho People's People API takes form records via ``/forms/employee/insertRecord``
and authenticates with an OAuth refresh-token flow. The adapter stores the
long-lived refresh token plus client credentials and sends the access token as a
``Zoho-oauthtoken`` header; obtaining that token is the customer's setup step,
so a blank ``api_key`` simply reports the connector as unconfigured.
"""

import json

from integrations.connectors.base import Connector, ConnectorResult, employee_payload


class ZohoPeopleConnector(Connector):
    kind = "ZOHO_PEOPLE"
    label = "Zoho People"
    required_settings = ("api_key", "data_center")
    optional_settings = ("form_name",)
    probe_path = "/forms/employee/getRecords?sIndex=1&limit=1"

    def base_url(self):
        override = self.get("base_url")
        if override:
            return override
        return f"https://people.zoho.{self.get('data_center') or 'in'}/people/api"

    def headers(self):
        return {
            "Authorization": f"Zoho-oauthtoken {self.get('api_key')}",
            "Accept": "application/json",
        }

    def form_name(self):
        return self.get("form_name") or "employee"

    def employee_body(self, application):
        record = employee_payload(application)
        fields = {
            "EmailID": record["email"],
            "FirstName": record["first_name"] or record["full_name"],
            "LastName": record["last_name"] or "-",
            "Mobile": record["phone"],
            "Designation": record["job_title"],
            "Work_location": record["location"],
        }
        if record["joining_date"]:
            fields["Dateofjoining"] = record["joining_date"]
        return {"inputData": json.dumps(fields)}

    def push_hire(self, application) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult.skipped(
                "not configured: missing " + ", ".join(self.missing_settings())
            )
        return self._call(
            "POST",
            f"/forms/{self.form_name()}/insertRecord",
            json=self.employee_body(application),
            success=f"employee record inserted for application {application.pk}",
        )
