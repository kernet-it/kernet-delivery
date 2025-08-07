import logging

import requests

from odoo import _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

REDUR_PROD_URL = "https://serviciosweb.redur.es/RedurWS/shipments"
REDUR_TEST_URL = "https://serviciosweb.redur.es/RedurWSTest/shipments"


class RedurRequest:
    """Interface between Redur API and Odoo recordset
    Abstract Redur API Operations to connect them with Odoo
    """

    def __init__(self, carrier):
        self.carrier = carrier
        self.common_vals = {
            "userName": self.carrier.redur_username,
            "clientId": self.carrier.redur_client_id or "",
            "password": self.carrier.redur_password,
            "preferredLanguage": self.carrier._redur_map_language(),
        }
        self.url = (
            REDUR_TEST_URL if not self.carrier.prod_environment else REDUR_PROD_URL
        )

    def _send_api_request(self, request_type, url, data=None):
        if data is None:
            data = {}
        try:
            headers = {
                "Content-Type": "application/json",
            }
            if request_type == "GET":
                res = requests.get(url=url, headers=headers, timeout=60)
            elif request_type == "POST":
                res = requests.post(url=url, json=data, headers=headers, timeout=60)
                _logger.info("POST request sent to REDUR (%s) with data: %s", url, data)
            else:
                raise UserError(
                    _("Unsupported request type, please only use 'GET' or 'POST'")
                )
            res.raise_for_status()
        except requests.exceptions.Timeout:
            raise UserError(_("Timeout: the server did not reply within 60s")) from None
        except (ValueError, requests.exceptions.ConnectionError):
            raise UserError(_("Server not reachable, please try again later")) from None
        except requests.exceptions.HTTPError as e:
            error_message = _("%(error)s\n%(message)s") % {
                "error": str(e),
                "message": res.json().get("Message", "") if res.text else "",
            }
            raise UserError(error_message) from None
        return res

    def get_senders(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/getSenders"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def create_shipment(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/newShipment"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def delete_shipment(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/deleteShipment"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def get_shipment_state(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/getShipmentState"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def get_shipment(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/getShipment"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def get_labels(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/getLabels"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def retain_new_shipment(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/retainNewShipment"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()

    def send_shipments(self, vals=None):
        if not vals:
            vals = {}
        url = f"{self.url}/sendShipments"
        data = {**self.common_vals, **vals}
        res = self._send_api_request(request_type="POST", url=url, data=data)
        return res.json()
