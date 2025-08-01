from . import models
from odoo import api, SUPERUSER_ID


def initial_config(env):
    def activate_currencies(env):
        try:
            currencies = env['res.currency'].with_context(active_test=False).search([])
            if currencies:
                for i in currencies:
                    i.active = True
            print("Currencies activated")
        except Exception as e:
            print("Exception in init hook - activate_currencies:", e)

    def create_dashboards_if_needed(env):
        try: 
            users = env['res.users'].search([])
            for user in users:
                if not env['cashmind.dashboard'].search([('user_id', '=', user.id)]):
                    env['cashmind.dashboard'].create({'user_id': user.id})
            print("Dashboard created")
        except Exception as e:
            print("Exception in init hook - create_dashboards_if_needed", e)
        

    activate_currencies(env)
    create_dashboards_if_needed(env)

    
