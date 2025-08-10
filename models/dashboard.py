from odoo import fields, models, api
from lxml import etree
from ..utils import get_current_month_range, get_last_month_range, convert_currencies

import logging
_logger = logging.getLogger(__name__)


class Dashboard(models.Model):
    _name = "cashmind.dashboard"

    name = "MI DASHBOARD"
    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    currency_id = fields.Many2one("res.currency", required=True, default=125)
        
    # CURRENT TOTALS 
    total_savinggoal = fields.Monetary(currency_field="currency_id")
    total_account = fields.Monetary(currency_field="currency_id")
    total_budget = fields.Monetary(currency_field="currency_id")    
    total_amount = fields.Monetary(currency_field="currency_id", compute="_compute_current_total_amount", store=True)
    
    # CURRENT MONTH TOTAL VARIABLES
    total_save_month = fields.Monetary(currency_field="currency_id", compute="_compute_save_month_stats", store=True)
    total_income_month = fields.Monetary(currency_field="currency_id", compute="_compute_income_month_stats", store=True)
    total_expense_month = fields.Monetary(currency_field="currency_id", compute="_compute_expense_month_stats", store=True)
    total_transfer_month = fields.Monetary(currency_field="currency_id", compute="_compute_transfer_month_stats", store=True)
    total_transfer_external_sent_month = fields.Monetary(currency_field="currency_id", compute="_compute_transfer_external_sent_month_stats", store=True)
    total_transfer_external_received_month = fields.Monetary(currency_field="currency_id", compute="_compute_transfer_external_received_month_stats", store=True)
    
    # Categories (for small cards under total month income and total month expense)
    total_income_cat_month = fields.Json(compute="_compute_income_month_stats", store=True) # {category_name: category_value} All the categories and its values
    total_expense_cat_month = fields.Json(compute="_compute_expense_month_stats", store=True) # {category_name: category_value} All the categories and its values
    category_income_top1 = fields.Json(compute="_compute_top1_income_cat", store=True) # {category_name: "name", category_value: value}
    category_expense_top1 = fields.Json(compute="_compute_top1_expense_cat", store=True) # {category_name: "name", category_value: value}
    # To show on dashboard (with monetary format, instead float from the json)
    category_income_top1_name = fields.Char(compute="_compute_top1_income_cat_name_value")
    category_income_top1_value = fields.Monetary(compute="_compute_top1_income_cat_name_value", currency_field="currency_id")
    # To show on dashboard (with monetary format, instead float from the json)
    category_expense_top1_name = fields.Char(compute="_compute_top1_expense_cat_name_value")
    category_expense_top1_value = fields.Monetary(compute="_compute_top1_expense_cat_name_value", currency_field="currency_id")

    # Save (for small card under total month save)
    total_save_name_value = fields.Json(compute="_compute_save_month_stats", store=True) # {save_name: save_value} All the saves and its values
    save_top1 = fields.Json(compute="_compute_top1_save", store=True) # {save_name: "name", save_value: value}
    # To show on dashboard (with monetary format, instead float from the json)
    save_top1_name = fields.Char(compute="_compute_top1_save_name_value")
    save_top1_value = fields.Monetary(compute="_compute_top1_save_name_value", currency_field="currency_id")

    # Transfer (for small card under total month transfer)
    total_transfer_name_value = fields.Json(compute="_compute_transfer_month_stats", store=True) # {transfer_name: transfer_value} All the transfer and its values
    transfer_top1 = fields.Json(compute="_compute_top1_transfer", store=True) # {transfer_name: "name", transfer_value: value}
    # To show on dashboard (with monetary format, instead float from the json)
    transfer_top1_name = fields.Char(compute="_compute_top1_transfer_name_value")
    transfer_top1_value = fields.Monetary(compute="_compute_top1_transfer_name_value", currency_field="currency_id")

    # LAST MONTH TOTAL VARIABLES
    total_save_last_month = fields.Monetary(currency_field="currency_id", compute="_compute_save_last_month_stats", store=True)
    total_income_last_month = fields.Monetary(currency_field="currency_id", compute="_compute_income_last_month_stats", store=True)
    total_expense_last_month = fields.Monetary(currency_field="currency_id", compute="_compute_expense_last_month_stats", store=True)
    total_transfer_last_month = fields.Monetary(currency_field="currency_id", compute="_compute_transfer_last_month_stats", store=True)
    total_transfer_external_sent_last_month = fields.Monetary(currency_field="currency_id", compute="_compute_transfer_external_sent_last_month_stats", store=True)
    total_transfer_external_received_last_month = fields.Monetary(currency_field="currency_id", compute="_compute_transfer_external_received_last_month_stats", store=True)
    
    # Categories (income and expense last month) Will be used only for calculate % variation
    category_income_last_top1_value = fields.Monetary(currency_field="currency_id", store=True)
    category_expense_last_top1_value = fields.Monetary(currency_field="currency_id", store=True)

    # DIFFERENCE (IN %) BETWEEN CURRENT AND LAST MONTH VARIABLES
    difference_expense = fields.Float(compute="_compute_expense_variation")
    difference_income = fields.Float(compute="_compute_income_variation")
    difference_save = fields.Float(compute="_compute_save_variation")
    difference_transfer = fields.Float(compute="_compute_transfer_variation")
    difference_transfer_ext_sent = fields.Float(compute="_compute_transfer_ext_sent_variation")
    difference_transfer_ext_received = fields.Float(compute="_compute_transfer_ext_received_variation")

    # Small cards TOP1
    difference_category_income_top1 = fields.Float(compute="_compute_category_income_top1_variation")
    difference_category_expense_top1 = fields.Float(compute="_compute_category_expense_top1_variation")
    difference_save_top1 = fields.Float(compute="_compute_save_top1_variation")
    difference_transfer_top1 = fields.Float(compute="_compute_transfer_top1_variation")

    # ------------- METHODS FOR RECALCULATING AMOUNTS DEPENDING ON THE CURRENCY_ID (START) -------------
    @api.model
    def get_used_currencies(self, model):
        query = f"""
            SELECT DISTINCT currency_id
            FROM {model}
            WHERE currency_id IS NOT NULL
            AND user_id = %s
        """
        self.env.cr.execute(query, (self.env.uid,))
        currency_ids = [row[0] for row in self.env.cr.fetchall()]
        return currency_ids if currency_ids else False
    
        
    # ------------- METHODS FOR RECALCULATING MAIN MONTH STATS AND TOTAL BALANCE (START) -------------
    @api.depends("total_account", "total_savinggoal", "total_budget")
    def _compute_current_total_amount(self):
        for rec in self:
            rec.total_amount = rec.total_account + rec.total_savinggoal + rec.total_budget

    @api.depends("total_amount")
    def _compute_save_month_stats(self):
        for rec in self:
            user = rec.user_id
            current_month_range = get_current_month_range()            

            save = self.env['cashmind.save'].search([
                ('user_id', '=', user.id),
                ("date", ">=", current_month_range[0]),
                ("date", "<=", current_month_range[1])
                ])
            
            # Recalculate save in format name: value for current month
            data = {}
            for r in save:
                save_currency = r.source_currency_id
                if r.name in data:
                    if save_currency.id != rec.currency_id.id:
                        data[r.name] += convert_currencies(from_currency=save_currency.name, to_currency=rec.currency_id.name, amount=r.amount)
                    else:
                        data[r.name] += r.amount
                else:
                    if save_currency.id != rec.currency_id.id:
                        data[r.name] = convert_currencies(from_currency=save_currency.name, to_currency=rec.currency_id.name, amount=r.amount)
                    else:
                        data[r.name] = r.amount
            sorted_data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)) if data else None
            rec.total_save_name_value = sorted_data

            rec.total_save_month = sum(sorted_data.values()) if sorted_data else 0.00

    @api.depends("total_amount")
    def _compute_income_month_stats(self):
        for rec in self:
            user = rec.user_id
            current_month_range = get_current_month_range()
            
            income = self.env['cashmind.income'].search([
                ('user_id', '=', user.id),
                ("date", ">=", current_month_range[0]),
                ("date", "<=", current_month_range[1])
                ])
            
            # Recalculate cashmind.income stats per category
            data = {}
            for r in income:
                income_currency = r.currency_id
                if r.category.name != "AJUSTE DE SALDO":
                    if r.category.name in data:
                        if income_currency.id != rec.currency_id.id:
                            data[r.category.name] += convert_currencies(from_currency=income_currency.name, 
                                                                        to_currency=rec.currency_id.name, amount=r.amount)
                        else:
                            data[r.category.name] += r.amount
                    else:
                        if income_currency.id != rec.currency_id.id:
                            data[r.category.name] = convert_currencies(from_currency=income_currency.name, 
                                                                    to_currency=rec.currency_id.name, amount=r.amount)
                        else:
                            data[r.category.name] = r.amount
            sorted_data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)) if data else None 
            rec.total_income_cat_month = sorted_data

            rec.total_income_month = sum(sorted_data.values()) if sorted_data else 0.00
    
    @api.depends("total_amount")
    def _compute_expense_month_stats(self):
        for rec in self:
            user = rec.user_id
            current_month_range = get_current_month_range()
            
            expense = self.env['cashmind.expense'].search([
                ('user_id', '=', user.id),
                ("date", ">=", current_month_range[0]),
                ("date", "<=", current_month_range[1])
                ])
            
            # Recalculate cashmind.expense stats per category
            data = {}
            for r in expense:
                expense_currency = r.currency_id
                if r.category.name != "AJUSTE DE SALDO":
                    if r.category.name in data:
                        if expense_currency.id != rec.currency_id.id:
                            data[r.category.name] += convert_currencies(from_currency=expense_currency.name, 
                                                                        to_currency=rec.currency_id.name, amount=r.amount)
                        else:
                            data[r.category.name] += r.amount
                    else:
                        if expense_currency.id != rec.currency_id.id:
                            data[r.category.name] = convert_currencies(from_currency=expense_currency.name, 
                                                                    to_currency=rec.currency_id.name, amount=r.amount)
                        else:
                            data[r.category.name] = r.amount
            sorted_data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)) if data else None 
            rec.total_expense_cat_month = sorted_data

            rec.total_expense_month = sum(sorted_data.values()) if sorted_data else 0.00
    
    @api.depends("total_amount")
    def _compute_transfer_month_stats(self):
        for rec in self:
            user = rec.user_id
            current_month_range = get_current_month_range()            

            transfer = self.env['cashmind.transfer'].search([
                ('user_id', '=', user.id),
                ("transfer_date", ">=", current_month_range[0]),
                ("transfer_date", "<=", current_month_range[1])
                ])
            
            # Recalculate transfer in format name: value for current month
            data = {}
            for r in transfer:
                transfer_currency = r.source_currency_id
                if r.name in data:
                    if transfer_currency.id != rec.currency_id.id:
                        data[r.name] += convert_currencies(from_currency=transfer_currency.name, to_currency=rec.currency_id.name, 
                                                           amount=r.amount)
                    else:
                        data[r.name] += r.amount
                else:
                    if transfer_currency.id != rec.currency_id.id:
                        data[r.name] = convert_currencies(from_currency=transfer_currency.name, to_currency=rec.currency_id.name, 
                                                          amount=r.amount)
                    else:
                        data[r.name] = r.amount
            sorted_data = dict(sorted(data.items(), key=lambda x: x[1], reverse=True)) if data else None
            rec.total_transfer_name_value = sorted_data

            rec.total_transfer_month = sum(sorted_data.values()) if sorted_data else 0.00
    
    @api.depends("total_amount")
    def _compute_transfer_external_sent_month_stats(self):
        for rec in self:
            user = rec.user_id
            current_month_range = get_current_month_range()

            transfer = self.env['cashmind.transfer_external'].search([
                ('user_id', '=', user.id),
                ("transfer_date", ">=", current_month_range[0]),
                ("transfer_date", "<=", current_month_range[1])
                ])
            
            # Recalculate cashmind.transfer_external sent stats
            pre_total_month_converted = 0.00
            pre_total_month = 0.00
            for r in transfer:
                if r.source_currency_id.id == rec.currency_id.id:
                    pre_total_month += r.amount
                else:
                    pre_total_month_converted += convert_currencies(from_currency=r.source_currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_transfer_external_sent_month = pre_total_month + pre_total_month_converted


    @api.depends("total_amount")
    def _compute_transfer_external_received_month_stats(self):
        for rec in self:
            user = rec.user_id
            current_month_range = get_current_month_range()

            transfer = self.env['cashmind.transfer_external'].search([
                ('external_user_id', '=', user.id),
                ("transfer_date", ">=", current_month_range[0]),
                ("transfer_date", "<=", current_month_range[1])
                ])
            
           # Recalculate cashmind.transfer_external received stats
            pre_total_month_converted = 0.00
            pre_total_month = 0.00
            for r in transfer:
                if r.source_currency_id.id == rec.currency_id.id:
                    pre_total_month += r.amount
                else:
                    pre_total_month_converted += convert_currencies(from_currency=r.source_currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_transfer_external_received_month = pre_total_month + pre_total_month_converted
    # ------------- METHODS FOR RECALCULATING MAIN MONTH STATS AND TOTAL BALANCE (END) -------------

    # ------------- METHODS FOR RECALCULATING MAIN LAST MONTH STATS (START) -------------
    @api.depends("total_amount")
    def _compute_save_last_month_stats(self):
        for rec in self:
            user = rec.user_id
            last_month_range = get_last_month_range()

            save_last = self.env['cashmind.save'].search([
                ('user_id', '=', user.id),
                ("date", ">=", last_month_range[0]),
                ("date", "<=", last_month_range[1])
                ])
            
            pre_total_last_month_converted = 0.00
            pre_total_last_month = 0.00
            for r in save_last:
                if r.source_currency_id.id == rec.currency_id.id:
                    pre_total_last_month += r.amount
                else:
                    pre_total_last_month_converted += convert_currencies(from_currency=r.source_currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_save_last_month = pre_total_last_month + pre_total_last_month_converted

    @api.depends("total_amount")
    def _compute_income_last_month_stats(self):
        for rec in self:
            user = rec.user_id
            last_month_range = get_last_month_range()

            income_last = self.env['cashmind.income'].search([
                ('user_id', '=', user.id),
                ("date", ">=", last_month_range[0]),
                ("date", "<=", last_month_range[1])
                ])
            
            pre_total_last_month_converted = 0.00
            pre_total_last_month = 0.00
            for r in income_last:
                if r.currency_id.id == rec.currency_id.id:
                    pre_total_last_month += r.amount
                else:
                    pre_total_last_month_converted += convert_currencies(from_currency=r.currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_income_last_month = pre_total_last_month + pre_total_last_month_converted

            # Recalculate last month category income value for the last top1 income category
            pre_total = float(0.00)
            if rec.total_income_cat_month:
                for cat_name, _ in rec.total_income_cat_month.items():
                    # Filtering by cat_name and last month
                    income_cat_top1_last = self.env['cashmind.income'].search([
                        ('user_id', '=', user.id),
                        ("date", ">=", last_month_range[0]),
                        ("date", "<=", last_month_range[1]),
                        ("category", "=", cat_name)
                        ])

                    if income_cat_top1_last:
                        for r in income_cat_top1_last:
                            if r.currency_id.id != rec.currency_id.id:
                                pre_total += convert_currencies(from_currency=r.currency_id.name, to_currency=rec.currency_id.name, 
                                                                amount=r.amount)
                            else:
                                pre_total += r.amount
                    # Break because we only want the first category in the ordered dict (reverse=True)
                    break
                rec.category_income_last_top1_value = pre_total
    
    @api.depends("total_amount")
    def _compute_expense_last_month_stats(self):
        for rec in self:
            user = rec.user_id
            last_month_range = get_last_month_range()

            expense_last = self.env['cashmind.expense'].search([
                ('user_id', '=', user.id),
                ("date", ">=", last_month_range[0]),
                ("date", "<=", last_month_range[1])
                ])
            
            pre_total_last_month_converted = 0.00
            pre_total_last_month = 0.00
            for r in expense_last:
                if r.currency_id.id == rec.currency_id.id:
                    pre_total_last_month += r.amount
                else:
                    pre_total_last_month_converted += convert_currencies(from_currency=r.currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_expense_last_month = pre_total_last_month + pre_total_last_month_converted

            # Recalculate last month category expense value for the last top1 expense category
            pre_total = float(0.00)
            if rec.total_expense_cat_month:
                for cat_name, _ in rec.total_expense_cat_month.items():
                    # Filtering by cat_name and last month
                    expense_cat_top1_last = self.env['cashmind.expense'].search([
                        ('user_id', '=', user.id),
                        ("date", ">=", last_month_range[0]),
                        ("date", "<=", last_month_range[1]),
                        ("category", "=", cat_name)
                        ])

                    if expense_cat_top1_last:
                        for r in expense_cat_top1_last:
                            if r.currency_id.id != rec.currency_id.id:
                                pre_total += convert_currencies(from_currency=r.currency_id.name, to_currency=rec.currency_id.name, 
                                                                amount=r.amount)
                            else:
                                pre_total += r.amount
                    # Break because we only want the first category in the ordered dict (reverse=True)
                    break
                rec.category_expense_last_top1_value = pre_total
            
    
    @api.depends("total_amount")
    def _compute_transfer_last_month_stats(self):
        for rec in self:
            user = rec.user_id
            last_month_range = get_last_month_range()

            transfer_last = self.env['cashmind.transfer'].search([
                ('user_id', '=', user.id),
                ("transfer_date", ">=", last_month_range[0]),
                ("transfer_date", "<=", last_month_range[1])
                ])
            
            pre_total_last_month_converted = 0.00
            pre_total_last_month = 0.00
            for r in transfer_last:
                if r.source_currency_id.id == rec.currency_id.id:
                    pre_total_last_month += r.amount
                else:
                    pre_total_last_month_converted += convert_currencies(from_currency=r.source_currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_transfer_last_month = pre_total_last_month + pre_total_last_month_converted

    @api.depends("total_amount")
    def _compute_transfer_external_sent_last_month_stats(self):
        for rec in self:
            user = rec.user_id
            last_month_range = get_last_month_range()

            transfer_last = self.env['cashmind.transfer_external'].search([
                ('user_id', '=', user.id),
                ("transfer_date", ">=", last_month_range[0]),
                ("transfer_date", "<=", last_month_range[1])
                ])
            
            # Recalculate cashmind.transfer_external sent stats
            pre_total_month_converted = 0.00
            pre_total_month = 0.00
            for r in transfer_last:
                if r.source_currency_id.id == rec.currency_id.id:
                    pre_total_month += r.amount
                else:
                    pre_total_month_converted += convert_currencies(from_currency=r.source_currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_transfer_external_sent_last_month = pre_total_month + pre_total_month_converted
    
    @api.depends("total_amount")
    def _compute_transfer_external_received_last_month_stats(self):
        for rec in self:
            user = rec.user_id
            last_month_range = get_last_month_range()

            transfer_last = self.env['cashmind.transfer_external'].search([
                ('external_user_id', '=', user.id),
                ("transfer_date", ">=", last_month_range[0]),
                ("transfer_date", "<=", last_month_range[1])
                ])
            
            # Recalculate cashmind.transfer_external received stats
            pre_total_month_converted = 0.00
            pre_total_month = 0.00
            for r in transfer_last:
                if r.source_currency_id.id == rec.currency_id.id:
                    pre_total_month += r.amount
                else:
                    pre_total_month_converted += convert_currencies(from_currency=r.source_currency_id.name, 
                                                                         to_currency=rec.currency_id.name, amount=r.amount)
            
            rec.total_transfer_external_received_last_month = pre_total_month + pre_total_month_converted
    # ------------- METHODS FOR RECALCULATING MAIN LAST MONTH STATS (END) -------------




    # ------------- METHODS FOR RECALCULATING VARIATIONS (START) -------------
    @api.depends("total_expense_month", "total_expense_last_month")
    def _compute_expense_variation(self):
        for rec in self:
            difference = rec.total_expense_month - rec.total_expense_last_month
            if not difference:
                rec.difference_expense = float(0.00)
            else:
                if rec.total_expense_last_month == 0:
                    rec.difference_expense = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_expense = float(rec.total_expense_month / rec.total_expense_last_month * 100)
                    elif difference < 0:
                        rec.difference_expense = float(rec.total_expense_month / rec.total_expense_last_month * 100 - 100)
    
    @api.depends("total_income_month", "total_income_last_month")
    def _compute_income_variation(self):
        for rec in self:
            difference = rec.total_income_month - rec.total_income_last_month
            if not difference:
                rec.difference_income = float(0.00)
            else:
                if rec.total_income_last_month == 0:
                    rec.difference_income = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_income = float(rec.total_income_month / rec.total_income_last_month * 100)
                    elif difference < 0:
                        rec.difference_income = float(rec.total_income_month / rec.total_income_last_month * 100 - 100)
    
    @api.depends("total_save_month", "total_save_last_month")
    def _compute_save_variation(self):
        for rec in self:
            difference = rec.total_save_month - rec.total_save_last_month
            if not difference:
                rec.difference_save = float(0.00)
            else:
                if rec.total_save_last_month == 0:
                    rec.difference_save = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_save = float(rec.total_save_month / rec.total_save_last_month * 100)
                    elif difference < 0:
                        rec.difference_save = float(rec.total_save_month / rec.total_save_last_month * 100 - 100)

    @api.depends("total_transfer_month", "total_transfer_last_month")
    def _compute_transfer_variation(self):
        for rec in self:
            difference = rec.total_transfer_month - rec.total_transfer_last_month
            if not difference:
                rec.difference_transfer = float(0.00)
            else:
                if rec.total_transfer_last_month == 0:
                    rec.difference_transfer = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_transfer = float(rec.total_transfer_month / rec.total_transfer_last_month * 100)
                    elif difference < 0:
                        rec.difference_transfer = float(rec.total_transfer_month / rec.total_transfer_last_month * 100 - 100)

    @api.depends("total_amount")
    def _compute_transfer_ext_sent_variation(self):
        for rec in self:
            difference = rec.total_transfer_external_sent_month - rec.total_transfer_external_sent_last_month
            if not difference:
                rec.difference_transfer_ext_sent = float(0.00)
            else:
                if rec.total_transfer_external_sent_last_month == 0:
                    rec.difference_transfer_ext_sent = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_transfer_ext_sent = float(
                            rec.total_transfer_external_sent_month / rec.total_transfer_external_sent_last_month * 100
                            )
                    elif difference < 0:
                        rec.difference_transfer_ext_sent = float(
                            rec.total_transfer_external_sent_month / rec.total_transfer_external_sent_last_month * 100 - 100
                            )

    @api.depends("total_amount")
    def _compute_transfer_ext_received_variation(self):
        for rec in self:
            difference = rec.total_transfer_external_received_month - rec.total_transfer_external_received_last_month
            if not difference:
                rec.difference_transfer_ext_received = float(0.00)
            else:
                if rec.total_transfer_external_received_last_month == 0:
                    rec.difference_transfer_ext_received = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_transfer_ext_received = float(
                            rec.total_transfer_external_received_month / rec.total_transfer_external_received_last_month * 100
                            )
                    elif difference < 0:
                        rec.difference_transfer_ext_received = float(
                            rec.total_transfer_external_received_month / rec.total_transfer_external_received_last_month * 100 - 100
                            )

    @api.depends("category_income_top1_value", "category_income_last_top1_value")
    def _compute_category_income_top1_variation(self):
        for rec in self:
            difference = rec.category_income_top1_value - rec.category_income_last_top1_value
            if not difference:
                rec.difference_category_income_top1 = float(0.00)
            else:
                if rec.category_income_last_top1_value == 0:
                    rec.difference_category_income_top1 = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_category_income_top1 = float(rec.category_income_top1_value / rec.category_income_last_top1_value * 100)
                    elif difference < 0:
                        rec.difference_category_income_top1 = float(rec.category_income_top1_value / rec.category_income_last_top1_value * 100 - 100)

    @api.depends("category_expense_top1_value", "category_expense_last_top1_value")
    def _compute_category_expense_top1_variation(self):
        for rec in self:
            difference = rec.category_expense_top1_value - rec.category_expense_last_top1_value
            if not difference:
                rec.difference_category_expense_top1 = float(0.00)
            else:
                if rec.category_expense_last_top1_value == 0:
                    rec.difference_category_expense_top1 = float(100.00)
                else:
                    if difference > 0:
                        rec.difference_category_expense_top1 = float(rec.category_expense_top1_value / rec.category_expense_last_top1_value * 100)
                    elif difference < 0:
                        rec.difference_category_expense_top1 = float(rec.category_expense_top1_value / rec.category_expense_last_top1_value * 100 - 100)

    @api.depends("save_top1_value", "total_save_month")
    def _compute_save_top1_variation(self):
        for rec in self:
            rec.difference_save_top1 = rec.save_top1_value / rec.total_save_month * 100 if (rec.save_top1_value and rec.total_save_month) else float(0.00)
    
    @api.depends("transfer_top1_value", "total_transfer_month")
    def _compute_transfer_top1_variation(self):
        for rec in self:
            rec.difference_transfer_top1 = rec.transfer_top1_value / rec.total_transfer_month * 100 if (rec.transfer_top1_value and rec.total_transfer_month) else float(0.00)
    # ------------- METHOD FOR RECALCULATING VARIATIONS (END) -------------
    

    # ------------- METHODS FOR CALCULATING TOP1 OF SOME MODELS / CURRENT MONTH (START) -------------
    @api.depends("total_income_cat_month")
    def _compute_top1_income_cat(self):
        for rec in self:
            if rec.total_income_cat_month:
                top1 = {}
                for key, value in rec.total_income_cat_month.items():
                    top1 = {"category_name": key, "category_value": float(value)}
                    break # We only need the first one for the TOP1
                rec.category_income_top1 = top1
            else:
                rec.category_income_top1 = {"category_name": "(sin datos)", "category_value": float(0.00)}
          
    @api.depends("total_expense_cat_month")
    def _compute_top1_expense_cat(self):
        for rec in self:
            if rec.total_expense_cat_month:
                top1 = {}
                for key, value in rec.total_expense_cat_month.items():
                    top1 = {"category_name": key, "category_value": float(value)}
                    break # We only need the first one for the TOP1
                rec.category_expense_top1 = top1
            else:
                rec.category_expense_top1 = {"category_name": "(sin datos)", "category_value": float(0.00)}

    @api.depends("total_save_name_value")
    def _compute_top1_save(self):
        for rec in self:
            if rec.total_save_name_value:
                top1 = {}
                for key, value in rec.total_save_name_value.items():
                    top1 = {"save_name": key, "save_value": float(value)}
                    break # We only need the first one for the TOP1
                rec.save_top1 = top1
            else:
                rec.save_top1 = {"save_name": "(sin datos)", "save_value": float(0.00)}

    @api.depends("total_transfer_name_value")
    def _compute_top1_transfer(self):
        for rec in self:
            if rec.total_transfer_name_value:
                top1 = {}
                for key, value in rec.total_transfer_name_value.items():
                    top1 = {"transfer_name": key, "transfer_value": float(value)}
                    break # We only need the first one for the TOP1
                rec.transfer_top1 = top1
            else:
                rec.transfer_top1 = {"transfer_name": "(sin datos)", "transfer_value": float(0.00)}
    # ------------- METHODS FOR CATEGORY STATS / CURRENT MONTH (END) -------------

    # ------------- METHODS FOR DIVIDING JSON VARIABLES INTO 2 VARIABLES (NAME AND VALUE) (START) -------------
    # It is better dividing the JSON variables (top1) into 2 different variables (name, value)
    # This way, the value (now a monetary field) is correctly displayed in the kanban view (dashboard)
    @api.depends("category_income_top1")
    def _compute_top1_income_cat_name_value(self):
        for rec in self:
            if rec.category_income_top1:
                rec.category_income_top1_name = rec.category_income_top1["category_name"]
                rec.category_income_top1_value = float(rec.category_income_top1["category_value"])
    
    @api.depends("category_expense_top1")
    def _compute_top1_expense_cat_name_value(self):
        for rec in self:
            if rec.category_expense_top1:
                rec.category_expense_top1_name = rec.category_expense_top1["category_name"]
                rec.category_expense_top1_value = float(rec.category_expense_top1["category_value"])
    
    @api.depends("save_top1")
    def _compute_top1_save_name_value(self):
        for rec in self:
            if rec.save_top1:
                rec.save_top1_name = rec.save_top1["save_name"]
                rec.save_top1_value = float(rec.save_top1["save_value"])

    @api.depends("transfer_top1")
    def _compute_top1_transfer_name_value(self):
        for rec in self:
            if rec.transfer_top1:
                rec.transfer_top1_name = rec.transfer_top1["transfer_name"]
                rec.transfer_top1_value = float(rec.transfer_top1["transfer_value"])
    # ------------- METHODS FOR DIVIDING JSON VARIABLES INTO 2 VARIABLES (NAME AND VALUE) (END) -------------
    

    # ------------- METHOD FOR RECALCULATING DASHBOARD STATS -------------
    # Recalculating will be manually called from other models (create(), write(), unlink()) OR when changing currency_id
    def recalculate_dashboard(self, external_user_id = None):
        for dashboard in self:
            user = dashboard.user_id if not external_user_id else external_user_id
            current_currency_name = self.env["res.currency"].search([("id", "=", dashboard.currency_id.id)])[0].name

            def recalculate_for_model(model_underscore, model_dot):
                # Recalculating for TOTAL_BUDGET
                current_currency = {}
                other_currencies = {}
                used_currencies = dashboard.get_used_currencies(model=model_underscore)
                if used_currencies:
                    for currency_id in used_currencies:                    
                        mod = self.env[model_dot].search([("user_id", "=", user.id), ("currency_id", "=", currency_id)])
                        total = sum(mod.mapped("balance")) if mod else 0.00
                        if currency_id != dashboard.currency_id.id:
                            currency_name = self.env["res.currency"].search([("id", "=", currency_id)])[0].name
                            other_currencies[currency_name] = total
                        else:
                            current_currency[current_currency_name] = total
                
                # Amount already in the current currency_id
                pre_total = current_currency[current_currency_name] if current_currency else 0.00

                # Let's convert to the current currency
                pre_total_converted = 0.00
                if other_currencies:                
                    for currency, amount in other_currencies.items():
                        total = convert_currencies(from_currency=currency, to_currency=current_currency_name, 
                                                            amount=amount)
                        pre_total_converted += total
                
                return pre_total + pre_total_converted

            dashboard.total_budget = recalculate_for_model(model_underscore="cashmind_budget", model_dot="cashmind.budget")
            dashboard.total_account = recalculate_for_model(model_underscore="cashmind_account", model_dot="cashmind.account")
            dashboard.total_savinggoal = recalculate_for_model(model_underscore="cashmind_savinggoal", model_dot="cashmind.savinggoal")

    def write(self, vals):
        for rec in self:
            if "currency_id" in vals and vals["currency_id"] != rec.currency_id.id:
                dashboard = super().write(vals)
                rec.recalculate_dashboard()
                return dashboard
            
            return super().write(vals)
    
  
             