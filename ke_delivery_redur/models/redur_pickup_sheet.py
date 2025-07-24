from odoo import fields, models


class RedurPickupSheet(models.Model):
    _name = "redur.pickup.sheet"
    _description = "Redur Pickup Sheet"

    name = fields.Char(
        string="Sheet Id",
        required=True,
        help="Identificador de la hoja de recogida",
    )
    file = fields.Binary(
        required=True,
        help="Archivo de la hoja de recogida en formato PDF",
    )
    file_name = fields.Char()
    date = fields.Datetime(
        default=lambda self: fields.Datetime.now(),
        help="Fecha de creación de la hoja de recogida",
    )
    carrier_id = fields.Many2one(
        comodel_name="delivery.carrier",
        required=True,
        help="Transportista asociado a la hoja de recogida",
    )
