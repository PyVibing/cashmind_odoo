from . import models
from odoo import api, SUPERUSER_ID


def activate_currencies(env):
    try:
        currencies = env['res.currency'].with_context(active_test=False).search([])
        if currencies:
            for i in currencies:
                i.active = True
    except Exception as e:
        print(e)
    
