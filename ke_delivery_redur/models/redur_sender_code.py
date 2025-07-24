from odoo import api, fields, models


class RedurSenderCode(models.Model):
    _name = "redur.sender.code"
    _description = "Redur Sender Code"

    name = fields.Char(required=True)
    sender_code = fields.Char(
        required=True,
        help="Unique code for the sender, provided by Redur.",
    )
    client_id = fields.Char(
        string="Client ID",
        help="Client ID associated with this sender code.",
    )
    default = fields.Boolean(
        string="Default Sender Code",
        help="Indicates if this sender code is the default for the client.",
        default=False,
    )
    address = fields.Char(
        help="Address associated with the sender code.",
    )
    city = fields.Char(
        help="City associated with the sender code.",
    )
    postal_code = fields.Char(
        help="Postal code associated with the sender code.",
    )
    province = fields.Char(
        help="Province associated with the sender code.",
    )
    country_code = fields.Char(
        help="Country code associated with the sender code.",
    )
    active = fields.Boolean(
        default=True,
        help="Indicates if the sender code is active.",
    )

    @api.depends("name", "sender_code")
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.sender_code})"

    @api.constrains("sender_code")
    def _check_unique_sender_code(self):
        for record in self:
            if self.search_count([("sender_code", "=", record.sender_code)]) > 1:
                raise ValueError(f"Sender code '{record.sender_code}' must be unique.")
