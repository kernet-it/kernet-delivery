from odoo import fields, models


class RedurPickupSheet(models.Model):
    _name = "redur.pickup.sheet"
    _description = "Redur Pickup Sheet"

    name = fields.Char(
        string="Sheet Id",
        required=True,
        help="Pickup sheet identifier",
    )
    file = fields.Binary(
        required=True,
        help="Pickup sheet file in PDF format",
    )
    file_name = fields.Char()
    date = fields.Datetime(
        default=lambda self: fields.Datetime.now(),
        help="Pickup sheet creation date",
    )
    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        required=True,
        help="Carrier associated with the pickup sheet",
    )
