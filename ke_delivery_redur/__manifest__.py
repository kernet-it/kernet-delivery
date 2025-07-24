{
    "name": "Kernet: Delivery Redur",
    "author": "Kernet",
    "website": "http://www.kernet.es",
    "category": "Personalizaciones Kernet",
    "version": "17.0.1.0.1",
    "depends": [
        "delivery_package_number",
        "delivery_state",
        "base_iso3166",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/delivery_carrier_views.xml",
        "views/stock_picking_views.xml",
        "views/redur_sender_code_views.xml",
    ],
    "license": "AGPL-3",
    "installable": True,
}
