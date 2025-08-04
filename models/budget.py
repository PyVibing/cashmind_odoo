from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import datetime
from ..utils import update_balance, notification, clean_input

class Budget(models.Model):
    _name = "cashmind.budget"

    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    name = fields.Char(string="Nombre", required=True)
    
    account = fields.Many2one("cashmind.account", string="Cuenta asociada", required=True, domain="[('user_id', '=', uid)]")
    available = fields.Monetary(string="Balance", compute="_compute_availability", currency_field="currency_id", 
                                readonly=True)
    currency_id = fields.Many2one('res.currency', string="Moneda", required=True, default=lambda self: self._default_currency(), 
                                  compute="_compute_source_currency", store=True
                                  )
    category = fields.Many2one("cashmind.category", string="Categoría", required=True, 
                               domain="[('category_type', '=', 'expense'), ('user_id', '=', uid)]")
    
    amount = fields.Monetary(string="Reservado", currency_field="currency_id", required=True)
    expended = fields.Monetary(string="Gastado", currency_field="currency_id", required=True, default=0.00, store=True)
    balance = fields.Monetary(string="Disponible", currency_field="currency_id", compute="_calculate_balance", store=True)
    start_date = fields.Date(string="Fecha de inicio", default=datetime.today().date(), required=True)
    end_date = fields.Date(string="Fecha de finalización", required=True)
    note = fields.Text(string="Notas")
    active = fields.Boolean(string="Mostrar", default=True)
    expense_ids = fields.One2many("cashmind.expense", "budget", string="Gastos")


    @api.depends("amount", "expended")
    def _calculate_balance(self):
        for rec in self:
            if rec.amount is not None and rec.expended is not None:
                rec.balance = rec.amount - rec.expended
            else:
                rec.balance = 0.00

    @api.onchange("account")
    def _compute_source_currency(self):
        for rec in self:
            rec.currency_id = rec.account.currency_id

    @api.onchange("account")
    def _compute_availability(self):
        for rec in self:
            rec.available = rec.account.balance

    @api.model
    def _default_currency(self):
        currency = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        return currency.id if currency else False
    
    def create(self, vals):
        if isinstance(vals, list):
            vals = vals[0]
        
        # Cleaning the name and description
        name = clean_input(vals["name"], "title") if "name" in vals else None
        name = name.lower() if name else None
        note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

        # Check if this name already exists for another record
        name_exists = self.env["cashmind.budget"].search([
            ("name", "=", name.capitalize()),
            ("user_id", "=", self.env.uid)]) if name else None
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe un presupuesto con este mismo nombre. Por favor, elija un nombre diferente.")
            
        amount = vals["amount"] if "amount" in vals else None
        start_date = datetime.strptime(vals["start_date"], "%Y-%m-%d").date() if "start_date" in vals else None
        end_date = datetime.strptime(vals["end_date"], "%Y-%m-%d").date() if "end_date" in vals else None
        account_id = vals["account"] if "account" in vals else None
        account_record = self.env["cashmind.account"].browse(account_id)
        available = account_record.balance

        # Check if amount is greater than 0
        if amount and amount <= 0:
            raise ValidationError(f"La cantidad del presupuesto debe ser mayor que 0.")
        
        # Check date is not in the future
        if start_date and start_date > datetime.today().date():
            raise ValidationError("La fecha de inicio no puede ser posterior a hoy.")
        if end_date and end_date <= start_date:
            raise ValidationError("La fecha de finalización debe ser posterior a la fecha de inicio.")
        
        # Check availability
        if amount and amount > available:
            raise ValidationError("No hay saldo suficiente para realizar esta operación.")
        
        vals["name"] = name.capitalize() if "name" in vals else None
        if note:
            vals["note"] = note

        budget = super().create(vals)
        
        for rec in budget:
            # Substract from the account
            update_balance(account_record, rec.amount * -1)
            notification(rec, "Saldo actualizado",
                                "Se actualizó correctamente el saldo de la cuenta asociada a este presupuesto.",
                                "success")
            
        # Recalculate dashboard stats
        user_id = budget.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return budget
    
    def write(self, vals):
        for rec in self:
            # Cleaning the name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another record
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.budget"].search([
                    ("name", "=", new_name.capitalize()),
                    ("user_id", "=", self.env.uid)])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe un presupuesto con este mismo nombre. Por favor, elija un nombre diferente.")
                    
            start_date = datetime.strptime(vals["start_date"], "%Y-%m-%d").date() if "start_date" in vals else rec.start_date
            end_date = datetime.strptime(vals["end_date"], "%Y-%m-%d").date() if "end_date" in vals else rec.end_date
            
            # Check date is not in the future
            if start_date and start_date > datetime.today().date():
                raise ValidationError("La fecha de inicio no puede ser posterior a hoy.")
            if end_date and end_date <= start_date:
                raise ValidationError("La fecha de finalización debe ser posterior a la fecha de inicio.")
        
            current_amount_budget = rec.amount
            current_account_budget_id = rec.account.id

            new_amount_budget = vals.get("amount", None)
            new_account_budget_id = vals.get("account", None)

            if new_amount_budget is not None and new_amount_budget <= 0:
                raise ValueError("La cantidad del presupuesto debe ser mayor que 0.")
            
            # If there is a record from any other model (expense) pointing to this account,
            # currency cannot be changed
            expense_record = self.env["cashmind.expense"].search([("budget", "=", rec.id)])
            
            if "currency_id" in vals:
                current_currency_id = rec.currency_id.id
                new_currency_id = vals["currency_id"]
                                
                if expense_record:
                    if current_currency_id != new_currency_id:
                        raise ValidationError("No es posible cambiar la cuenta si el tipo de moneda es diferente y existe " \
                                                "al menos un movimiento asociado a esta cuenta.")
                    
            # If changing the amount for this budget, what's already expended can't be greater than the new amount
            if "amount" in vals and vals["amount"] < rec.expended:
                raise ValidationError("La nueva cantidad asociada a este presupuesto no puede ser menor que la cantidad " \
                                    "gastada actualmente.")
            
            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note
                
            # If only modifying the quantity (amount), not the account name
            if not new_account_budget_id and new_amount_budget:
                # Update the wrong amount from the current account
                difference = new_amount_budget - current_amount_budget
                account_record = self.env["cashmind.account"].browse(current_account_budget_id)
                update_balance(account_record, difference * -1)
                notification(rec, "Saldo actualizado",
                            "Se actualizó correctamente el saldo de la cuenta asociada a este presupuesto.",
                            "success")
                
            # If only modifying the account name, not the quantity (amount)
            elif new_account_budget_id and not new_amount_budget:
                # Add the amount to the current account before substracting it from the new account
                current_account_record = self.env["cashmind.account"].browse(current_account_budget_id)
                update_balance(current_account_record, current_amount_budget)
                # Substracting the amount from the new account balance
                new_account_record = self.env["cashmind.account"].browse(new_account_budget_id)
                update_balance(new_account_record, current_amount_budget * -1)
                notification(rec, "Saldo actualizado",
                            "Se actualizó correctamente el saldo de las cuentas asociadas a este presupuesto.",
                            "success")

            # If modifying both the account name and the quantity (amount)
            elif new_account_budget_id and new_amount_budget:
                # Adding the wrong amount to the current account before substracting the right amount from the new account
                current_account_record = self.env["cashmind.account"].browse(current_account_budget_id)
                update_balance(current_account_record, current_amount_budget)
                # Substracting the right amount from the new account
                new_account_record = self.env["cashmind.account"].browse(new_account_budget_id)
                update_balance(new_account_record, new_amount_budget * -1)
                notification(rec, "Saldo actualizado",
                            "Se actualizó correctamente el saldo de las cuentas asociadas a este presupuesto.",
                            "success")
            
            else:
                if not self.env.context.get("deny_notification"):
                    notification(rec, "Datos actualizados", "Se actualizaron correctamente los datos del presupuesto.", "success")

        budget = super().write(vals)
        
        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', rec.user_id.id)])
        dashboards.recalculate_dashboard()

        return budget

    
    def unlink(self):
        for rec in self:
            # Check if there are other models pointing to this one
            expense_record = self.env["cashmind.expense"].search([("budget", "=", rec.id)])
            if expense_record:
                raise ValidationError("Este presupuesto no puede eliminarse mientras existan movimientos de gastos asociados " \
                                    "a este. Intente archivar el presupuesto si no quiere eliminar los registros asociados.")
            
            # Update the balance for the account associated to this budget
            update_balance(rec.account, rec.amount)
            if len(self) < 2:
                notification(rec, "Presupuesto eliminado", 
                            "Se actualizó correctamente el saldo de la cuenta asociada a este presupuesto.",
                            "success")
            else:
                notification(rec, "Presupuestos eliminados", 
                        "Se actualizó correctamente el saldo de las cuentas asociadas a estos presupuestos.",
                        "success")
        
        user_id = self.user_id.id
        budget = super().unlink()

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return budget