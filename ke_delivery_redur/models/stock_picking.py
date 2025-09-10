from odoo import _, fields, models

from .redur_data import SHIPMENT_LOCATION, SHIPMENT_STATE


class StockPicking(models.Model):
    _inherit = "stock.picking"

    redur_shipment_state = fields.Selection(
        selection=SHIPMENT_STATE,
        help="The states in which a documented shipment can be found",
    )
    redur_shipment_location = fields.Selection(
        selection=SHIPMENT_LOCATION,
        help="The situations in which a shipment and its packages can be found.",
    )
    redur_shipping_notes = fields.Text(string="REDUR Shipping Notes")

    def redur_get_label(self):
        self.ensure_one()
        if self.delivery_type != "redur" or not self.carrier_tracking_ref:
            return

        label = self.carrier_id.redur_get_label(self)
        if label:
            label_format = "pdf" if self.carrier_id.redur_printer_type == "L" else "txt"
            label_name = f"redur_{self.carrier_tracking_ref}.{label_format}"
            self.message_post(
                body=(_("REDUR label for %s") % self.carrier_tracking_ref),
                attachments=[(label_name, label)],
            )

    def redur_toggle_retain_shipment(self):
        self.ensure_one()
        if not self.delivery_type == "redur" or not self.carrier_tracking_ref:
            return
        self.carrier_id.redur_retain_shipment(self)
