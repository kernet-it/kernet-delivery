import base64
from xml.sax.saxutils import escape

from odoo import _, fields, models
from odoo.exceptions import UserError

from .redur_data import (
    ERRO_CODE,
    PAYMENT_TYPE,
    PRINTER_TYPE,
    PRODUCT_LINE,
    SERVICE_TYPE,
)
from .redur_request import RedurRequest


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("redur", "REDUR")], ondelete={"redur": "set default"}
    )
    redur_username = fields.Char(
        help="Usuario proporcionado por REDUR y que pertenece al cliente"
    )
    redur_password = fields.Char(
        help="Hash de la contraseña proporcionada por REDUR para este usuario y cliente"
    )
    redur_client_id = fields.Char(
        help="Código del cliente del cuál se quieren imprimir etiquetas."
        " Si no se introduce este valor se utilizará el código de "
        "cliente asociado al usuario en caso de solo tener un cliente"
    )
    redur_sender_code_id = fields.Many2one(
        comodel_name="redur.sender.code",
        help="Código de remitente proporcionado por REDUR."
        "Puede existir uno o varios códigos de remitentes,"
        "creados por dirección de recogida, por cuentas de"
        "facturación o por otros motivos. ",
    )
    redur_product_line = fields.Selection(
        selection=PRODUCT_LINE,
        help="Código proporcionado por REDUR. Puede ser un"
        "campo fijo, o puede tener valores distintos en cada"
        "expedición, en función del destino, del tipo de envío… ",
    )
    redur_payment_type = fields.Selection(
        selection=PAYMENT_TYPE,
        help="Tipo de Portes del envío. ",
    )
    redur_service_type = fields.Selection(
        selection=SERVICE_TYPE,
        help="Tipo de servicio o identificador de las "
        "características de los envíos dentro de la red de REDUR.",
    )
    redur_printer_type = fields.Selection(
        selection=PRINTER_TYPE,
        default="L",
        help="Tipo de etiquetadora/impresora. Dependiendo de la"
        "misma se devolverá la etiqueta utilizando las"
        "secuencias de control del lenguaje de la misma. ",
    )
    redur_pickup_sheet_ids = fields.One2many(
        comodel_name="redur.pickup.sheet",
        inverse_name="carrier_id",
    )

    def _redur_map_language(self):
        """
        Redur Allowed languages for the carrier.
        options:
        - 'es' for Spanish
        - 'pt' for Portuguese
        - 'uk' for English (default)
        """
        lang = self.env.context.get("lang", "en_US")
        res = "uk"
        if lang == "es_ES":
            res = "es"
        elif lang == "pt_PT":
            res = "pt"
        return res

    def _prepare_redur_sender_code_values(self, vals):
        active = vals.get("active", "0")
        if active == "1":
            active = True
        else:
            active = False

        values = {
            "name": vals.get("name", ""),
            "sender_code": vals.get("senderCode", ""),
            "client_id": vals.get("clientId", ""),
            "default": vals.get("default", False),
            "address": vals.get("address", ""),
            "city": vals.get("city", ""),
            "postal_code": vals.get("postalCode", ""),
            "province": vals.get("province", ""),
            "country_code": vals.get("countryCode", ""),
            "active": active,
        }
        return values

    def _create_redur_sender_code(self, sender_vals):
        for val in sender_vals:
            sender_code = val.get("senderCode", "")
            already_exists = self.env["redur.sender.code"].search_count(
                [("sender_code", "=", sender_code)]
            )
            if not already_exists:
                values = self._prepare_redur_sender_code_values(val)
                self.env["redur.sender.code"].create(values)

    def redur_get_sender_code(self):
        self.ensure_one()
        response = RedurRequest(self).get_senders()
        sender_vals = response.get("senders", [])
        if not sender_vals:
            raise UserError(_("No sender codes found for the current user in Redur."))
        self._create_redur_sender_code(sender_vals)
        return True

    def redur_rate_shipment(self, order):
        """Redur doesn't provide a method to compute delivery rates."""
        return {
            "success": True,
            "price": self.product_id.lst_price,
            "error_message": _(
                """REDUR API doesn't provide methods to compute delivery rates, so
                you should rely on another price method instead or override this
                one in your custom code."""
            ),
            "warning_message": _(
                """REDUR API doesn't provide methods to compute delivery rates, so
                you should rely on another price method instead or override this
                one in your custom code."""
            ),
        }

    def _prepare_redur_send_shipping_values(self, picking):
        # TODO At least one of the following fields is required:
        # packages, pallets, longPackages or irregularPackages
        # with a value greater than zero.
        # For now, we only pass the number of packages.
        consignee = picking.partner_id
        values = {
            "senderCode": self.redur_sender_code_id.sender_code or "",
            "printerType": self.redur_printer_type,
            "productLine": self.redur_product_line,
            "yourReference": picking.name,
            "yourReference2": "",
            "originShipmentNumber": picking.origin,
            "paymentType": self.redur_payment_type,
            "serviceType": self.redur_service_type,
            "weight": round(
                picking.shipping_weight, 1
            ),  # 8 digits: 7 before the decimal and 1 after
            # it is recommended to set the default value to 0.01
            "consigneeName": consignee.name,
            "consigneeAddress": escape(consignee.street or ""),
            "consigneeCity": escape(consignee.city or ""),
            "consigneePostalCode": consignee.zip,
            "consigneeProvince": escape(
                (consignee.state_id.name or "")[:25]
            ),  # REDUR max 25 chars
            "consigneeCountry": consignee.country_id.code_numeric,
            "additionalClientInformation": "",
            "saveConsignee": 0,
            "packages": picking.number_of_packages or 1,  # See TODO
            "pallets": "",  # See TODO
            "longPackages": "",  # See TODO
            "irregularPackages": "",  # See TODO
            "exceptedPackages": "",
            "contactPerson": consignee.name,
            # Recipient's email for sending notifications.
            # This service must be activated commercially with REDUR
            "contactEmail": consignee.email,
            # This service must be commercially activated with REDUR
            "comments": picking.redur_shipping_notes,
            # comments2: We include the recipient's phone number as recommended,
            # so it appears on the label
            "comments2": consignee.phone or consignee.mobile,
            "comments3": "",
            "linkForDownload": False,  # False – Returns the labels in BASE64,
            # True – Returns a link to download the labels
        }
        return values

    def redur_send_shipping(self, pickings):
        redur_request = RedurRequest(self)
        result = []
        for picking in pickings:
            values = self._prepare_redur_send_shipping_values(picking)
            response = redur_request.create_shipment(values)
            self._check_redur_error(response)
            values.update({"tracking_number": False, "exact_price": 0})
            values["tracking_number"] = response.get("trackingNumber")
            result.append(values)
            labels = response.get("labels")
            picking.redur_shipment_state = "1"
            label_format = "pdf" if self.redur_printer_type == "L" else "txt"
            if labels:
                attachment = [
                    (
                        "redur_label_{}.{}".format(
                            response.get("trackingNumber"), label_format
                        ),
                        base64.b64decode(labels),
                    )
                ]
                picking.message_post(
                    body=_("Redur label for shipment %s") % picking.name,
                    attachments=attachment,
                )
        return result

    def redur_get_tracking_link(self, picking):
        url = "https://redur.es/en/track-trace/?idioma=%s&buscarpor=EXPEDICION&valor=%s"
        lang = self._redur_map_language()
        tracking_number = picking.carrier_tracking_ref
        return url % (lang, tracking_number)

    def redur_cancel_shipment(self, pickings):
        redur_request = RedurRequest(self)
        for picking in pickings:
            tracking_number = picking.carrier_tracking_ref
            values = {
                "trackingNumber": tracking_number,
            }
            response = redur_request.delete_shipment(values)
            self._check_redur_error(response)
            picking.carrier_tracking_ref = False
            picking.redur_shipment_state = False
            picking.message_post(
                body=_("REDUR Expedition with reference %s cancelled") % tracking_number
            )

    def _redur_update_shipment_state(self, picking):
        redur_request = RedurRequest(self)
        values = {
            "trackingNumber": picking.carrier_tracking_ref,
        }
        response = redur_request.get_shipment(values)
        self._check_redur_error(response)
        state_code = response.get("shipment", "").get("newShipmentStatusCode", "")
        if state_code:
            picking.redur_shipment_state = state_code
        return True

    def _redur_update_shipment_location(self, picking):
        redur_request = RedurRequest(self)
        # searchBy Options: EXPEDICION | SU_REFERENCIA | SU_REFERENCIA2 | REF_INTERNACIONAL | REF_COLABORADOR | NTRACKING | REF_AGRUP # noqa
        values = {
            "searchBy": "EXPEDICION",
            "value": picking.carrier_tracking_ref,
        }
        response = redur_request.get_shipment_state(values)
        self._check_redur_error(response)
        state_code = response.get("shipmentStateCode2", "")
        if state_code:
            picking.redur_shipment_location = state_code
        return True

    def redur_tracking_state_update(self, picking):
        self._redur_update_shipment_state(picking)
        self._redur_update_shipment_location(picking)

    def redur_get_label(self, picking):
        redur_request = RedurRequest(self)
        values = {
            "printerType": self.redur_printer_type,
            "trackingNumber": picking.carrier_tracking_ref,
            "linkForDownload": False,
        }
        response = redur_request.get_labels(values)
        self._check_redur_error(response)
        labels = response.get("labels")
        return base64.b64decode(labels) if labels else False

    def redur_retain_shipment(self, picking):
        redur_request = RedurRequest(self)
        values = {
            "trackingNumber": picking.carrier_tracking_ref,
        }
        result = redur_request.retain_new_shipment(values)
        self._check_redur_error(result)
        new_state = result.get("newShipmentStatusCode", "")
        if new_state:
            picking.redur_shipment_state = new_state
        return True

    def redur_send_shipments(self):
        redur_request = RedurRequest(self)
        response = redur_request.send_shipments()
        self._check_redur_error(response)

        pdf = response.get("pdf")
        sheetId = response.get("collectionSheetId")
        self._create_shipments_sheet(pdf, sheetId)
        return True

    def _check_redur_error(self, result):
        error_details = result.get("errorDetails", [])
        if error_details:
            message = []
            for error in error_details:
                error_code = error.get("errorCode", "")
                field = error.get("affectedField", "")
                description = error.get("errorDescription", "")
                error_message = ERRO_CODE.get(error_code, _("Unknown error"))
                message.append(
                    f"{error_code}: {error_message} \n{field}: {description}"
                )
            message = "\n".join(message)
            raise UserError(_("Error creating shipment in Redur:\n%s") % message)

    def _create_shipments_sheet(self, pdf, sheetId):
        new_sheet = self.env["redur.pickup.sheet"].create(
            {
                "name": sheetId,
                "file": base64.b64decode(pdf),
                "file_name": f"redur_pickup_sheet_{sheetId}.pdf",
                "carrier_id": self.id,
            }
        )
        return new_sheet
