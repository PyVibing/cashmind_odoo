from odoo import fields, models, api
from odoo.exceptions import ValidationError
from ..utils import notification, update_balance, clean_input
from datetime import datetime

class Income(models.Model): 
    _name = "cashmind.income"
    
    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    name = fields.Char(string="Nombre", required=True)
    account = fields.Many2one("cashmind.account", string="Cuenta de destino", required=True)
    available = fields.Monetary(string="Balance", compute="_compute_availability", currency_field="currency_id", 
                                readonly=True)
    category = fields.Many2one("cashmind.category", string="Categoría", domain=[("category_type", "!=", "expense")], 
                               required=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                  store=True, compute="_compute_currency", default=lambda self: self._default_currency())
    amount = fields.Monetary(string="Cantidad", currency_field="currency_id", required=True)
    date = fields.Date(string="Fecha", default=datetime.today(), required=True)
    invoice = fields.Binary(string="Factura")
    has_invoice = fields.Boolean(string="Con factura", compute="_compute_has_invoice", store=True)
    note = fields.Text(string="Nota")
    active = fields.Boolean(string="Mostrar", default=True)

    @api.model
    def _default_currency(self):
        currency = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        return currency.id if currency else False

    @api.onchange("account")
    def _compute_availability(self):
        for rec in self:
            rec.available = rec.account.balance

    @api.depends("account")
    def _compute_currency(self):
        for rec in self:
            rec.currency_id = rec.account.currency_id
    
    @api.depends("invoice")
    def _compute_has_invoice(self):
        for rec in self:
            rec.has_invoice = bool(rec.invoice)
    
    def create(self, vals):
        if isinstance(vals, list):
            vals = vals[0]

        # Cleaning the category name and description
        name = clean_input(vals["name"], "title")
        name = name.lower()
        note = clean_input(vals["note"], "note") if vals["note"] else None

        # Check if this name already exists for another budget
        name_exists = self.env["cashmind.income"].search([("name", "=", name.capitalize())])
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe un ingreso con este mismo nombre. Por favor, elija un nombre diferente.")
            
        if vals["amount"] is not None and vals["amount"] <= 0:
            raise ValidationError("La cantidad a ingresar debe ser mayor que 0.")
        
        # Check if date is maximum today
        if datetime.strptime(vals["date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha del ingreso no puede ser posterior a hoy. Ingrese una fecha válida.")
        
        vals["name"] = name.capitalize()
        if note:
            vals["note"] = note

        income = super().create(vals)

        update_balance(income.account, income.amount)
        notification(income, "Saldo actualizado",
                    "Se actualizó correctamente el saldo de la cuenta asociada a este ingreso.",
                    "success")
        
        # Recalculate dashboard stats
        user_id = income.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()
        
        return income
    
    def write(self, vals):
        for rec in self:
            # Check if date is maximum today
            if "date" in vals and datetime.strptime(vals["date"], "%Y-%m-%d") > datetime.today():
                raise ValidationError("La fecha del ingreso no puede ser posterior a hoy. Ingrese una fecha válida.")
        
            # Cleaning the category name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another account
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.income"].search([("name", "=", new_name.capitalize())])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe un ingreso con este mismo nombre. Por favor, elija un nombre diferente.")
                    
            current_amount_income = rec.amount
            current_account_income_id = rec.account.id
                        
            new_amount_income = vals.get("amount",None)
            new_account_income_id = vals.get("account", None)
                 
            if new_amount_income is not None and new_amount_income <= 0:
                raise ValidationError("La cantidad a ingresar debe ser mayor que 0.")
                        
            # If only modifying the quantity (amount), not the account name
            if not new_account_income_id and new_amount_income:
                # Update the wrong amount from the current account
                difference = new_amount_income - current_amount_income
                account_record = self.env["cashmind.account"].browse(current_account_income_id)
                update_balance(account_record, difference)
                notification(rec, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de la cuenta asociada a este ingreso.",
                             "success")
                
            # If only modifying the account name, not the quantity (amount)
            elif new_account_income_id and not new_amount_income:
                # Decrease the amount from the current account before adding it to the new account
                current_account_record = self.env["cashmind.account"].browse(current_account_income_id)
                update_balance(current_account_record, current_amount_income * -1)
                # Adding the amount to the new account balance
                new_account_record = self.env["cashmind.account"].browse(new_account_income_id)
                update_balance(new_account_record, current_amount_income)
                notification(rec, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de las cuentas asociadas a este ingreso.",
                             "success")

            # If modifying both the account name and the quantity (amount)
            elif new_account_income_id and new_amount_income:
                # Decrease the wrong amount from the current account before adding the right amount to the new account
                current_account_record = self.env["cashmind.account"].browse(current_account_income_id)
                update_balance(current_account_record, current_amount_income * -1)
                # Adding the right amount to the new account
                new_account_record = self.env["cashmind.account"].browse(new_account_income_id)
                update_balance(new_account_record, new_amount_income)
                notification(rec, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de las cuentas asociadas a este ingreso.",
                             "success")
            
            else:
                notification(rec, "Datos actualizados", "Se actualizaron correctamente los datos del ingreso.", "success")
        
            if new_name:
                    vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note
        
        income = super().write(vals)

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', rec.user_id.id)])
        dashboards.recalculate_dashboard()

        return income 

    def unlink(self):
        for rec in self:
            current_amount_income = rec.amount
            current_account_record = rec.account
            
            # Update the amount in the account
            update_balance(current_account_record, current_amount_income * -1)
        
        if len(self) < 2:
            notification(self, "Ingreso eliminado",
                        "Se actualizó correctamente el saldo de la cuenta asociada a este ingreso.",
                        "success")
        else:
            notification(self, "Ingresos eliminados",
                        "Se actualizó correctamente el saldo de las cuentas asociadas a estos ingresos.",
                        "success")
        
        user_id = self.user_id.id
        income = super().unlink() 

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return income
    