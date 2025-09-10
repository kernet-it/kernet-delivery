=====================================
Kernet Delivery Redur
=====================================


.. |badge1| image:: https://img.shields.io/badge/licence-AGPL--3-blue.png
    :target: http://www.gnu.org/licenses/agpl-3.0-standalone.html
    :alt: License: AGPL-3


|badge1|


**Table of contents**

.. contents::
   :local:

Configuration
=============

To use this module, you need to:

#. Go to *Inventory > Configuration > Delivery > Delivery Methods* and
  create a new one.
#. Choose *REDUR* as the provider.
#. Configure the service data you have contracted and the shipping product
  you want to use.
#. The Reur sender code is get directly from the API, click on the button
  "Get Sender Code" to fetch it.

Usage
=====

These are the different operations possible with this module:

Create Shipment
---------------

#. When confirming the delivery order, the service will be registered with REDUR.
#. Upon receiving the response, the shipment reference and corresponding labels will be posted in the chatter.
#. To manage the shipment packages, you can use the "number of packages" field provided by delivery_package_number (see the README for more information) or Odoo's native shipping packages workflow. he module will send the correct number to the REDUR API, and you will be able to download the PDF labels with the corresponding numbering.

Cancel Shipment
---------------

#. To cancel the shipment, go to the "Other Information" tab. If the delivery order has been confirmed, a "Cancel" button will appear to the right of the carrier reference.
#. Once cancelled, you can generate a new shipment using the "Send to Carrier" button in the header of the delivery


Get Labels
----------

#. If you accidentally deleted or lost the attached label when the shipment was created, you can regenerate the REDUR labels using the "REDUR Label" button in the header.


Shipment Tracking
-----------------

#. You can view the shipment status in the "Additional Info" tab, on the right under "Shipment Status". To update the status, simply click on "Update Tracking".
#. You can also access the tracking link provided by REDUR by clicking the "Tracking" smart button.




Bug Tracker
===========



Authors
-------

* Kernet Internet y Nuevas Tecnologias S.L.

Contributors
------------

- `Kernet Internet y Nuevas Tecnologias S.L. <https://www.kernet.es>`__:

  - Alejandro Aladro



Maintainers
~~~~~~~~~~~

This module is maintained by Kernet. Internet y Nuevas Tecnologias S.L.

.. image:: https://kernet.es/wp-content/uploads/2021/11/logo-grande-fondo-transparente.png
   :alt: Kernet Internet y Nuevas Tecnologias S.L.
   :target: https://kernet.es/
