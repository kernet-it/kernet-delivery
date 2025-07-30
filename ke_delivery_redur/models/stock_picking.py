from odoo import _, fields, models

from .redur_data import SHIPMENT_LOCATION, SHIPMENT_STATE


class StockPicking(models.Model):
    _inherit = "stock.picking"

    redur_shipment_state = fields.Selection(
        selection=SHIPMENT_STATE,
        help="Los estados en los que se puede encontrar un envío documentado",
    )
    redur_shipment_location = fields.Selection(
        selection=SHIPMENT_LOCATION,
        help="Las situaciones en las que se puede encontrar un envío, "
        "así como sus bultos.",
    )
    redur_shipping_notes = fields.Text(string="Notas de envío REDUR")

    def redur_get_label(self):
        self.ensure_one()
        if self.delivery_type != "redur" or not self.carrier_tracking_ref:
            return
        if self.carrier_id.redur_printer_type == "L":
            pdf = self.carrier_id.redur_get_label(self)
            if pdf:
                label_name = f"redur_{self.carrier_tracking_ref}.pdf"
                self.message_post(
                    body=(_("REDUR label for %s") % self.carrier_tracking_ref),
                    attachments=[(label_name, pdf)],
                )

    def redur_toggle_retain_shipment(self):
        self.ensure_one()
        if not self.delivery_type == "redur" or not self.carrier_tracking_ref:
            return
        self.carrier_id.redur_retain_shipment(self)
