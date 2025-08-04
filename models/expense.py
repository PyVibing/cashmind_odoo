from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import datetime
from ..utils import notification, update_balance, clean_input

class Expense(models.Model):
    _name = "cashmind.expense"
    
    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    name = fields.Char(string="Nombre", required=True)    
    budget = fields.Many2one("cashmind.budget", string="Presupuesto", ondelete="restrict", domain="[('user_id', '=', uid)]")
    budget_available = fields.Monetary(string="Disponible", compute="_compute_budget_availability", currency_field="currency_id", 
                                readonly=True)
    account = fields.Many2one("cashmind.account", string="Cuenta de origen", ondelete="restrict", domain="[('user_id', '=', uid)]")
    available = fields.Monetary(string="Disponible", compute="_compute_availability", currency_field="currency_id", 
                                readonly=True)
    category = fields.Many2one("cashmind.category", string="Categoría", required=True,
                               domain="[('category_type', '!=', 'income'), ('user_id', '=', uid)]")
    currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                store=True, compute="_compute_source_currency", default=lambda self: self._default_currency())
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
            if rec.account:
                rec.available = rec.account.balance
                if rec.budget:
                    rec.budget = False
                    rec.budget_available = False
            else:
                rec.available = 0.0

    @api.onchange("budget")
    def _compute_budget_availability(self):
        for rec in self:
            if rec.budget:
                rec.budget_available = rec.budget.balance
                if rec.account:
                    rec.account = False
                    rec.available = False
            else:
                rec.budget_available = 0.0
  
    @api.depends("account", "budget")
    def _compute_source_currency(self):
        for rec in self:
            if rec.account:
                rec.currency_id = rec.account.currency_id
            elif rec.budget:
                rec.currency_id = rec.budget.currency_id
    
    @api.depends("invoice")
    def _compute_has_invoice(self):
        for rec in self:
            rec.has_invoice = bool(rec.invoice)
    
    def create(self, vals):
        if isinstance(vals, list):
            vals = vals[0]

        # Cleaning the name and description
        name = clean_input(vals["name"], "title") if "name" in vals else None
        name = name.lower() if name else None
        note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

        # Check if this name already exists for another record
        name_exists = self.env["cashmind.expense"].search([
            ("name", "=", name.capitalize()),
            ("user_id", "=", self.env.uid)]) if name else None
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe un gasto con este mismo nombre. Por favor, elija un nombre diferente.")
            
        # Check mandatory source account (only one, no less and no more than that)
        if "budget" in vals and not vals["budget"] and "account" in vals and not vals["account"]:
            raise ValidationError("Debe seleccionar una cuenta de origen para este gasto.")
        elif "budget" in vals and vals["budget"] and "account" in vals and vals["account"]:
            raise ValidationError("Debe seleccionar solamente una cuenta de origen para este gasto.")

        # Check amount is greater than 0
        if "amount" in vals and vals["amount"] <= 0:
            raise ValidationError("La cantidad a gastar debe ser mayor que 0.")
        
        # Check availability
        if "budget" in vals and vals["budget"]:
            budget_record = self.env["cashmind.budget"].browse(vals["budget"])
            available = budget_record.amount - budget_record.expended
        elif "account" in vals and vals["account"]:
            account_record = self.env["cashmind.account"].browse(vals["account"])
            available = account_record.balance
        
        
        if "amount" in vals and vals["amount"] > available:
            raise ValidationError("No hay saldo suficiente para realizar esta operación.")
        
        # Check date is not in the future
        if "date" in vals and datetime.strptime(vals["date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha del gasto no puede ser posterior a hoy. Ingrese una fecha válida.")

        vals["name"] = name.capitalize() if "name" in vals else None
        if note:
            vals["note"] = note

        expense = super().create(vals)

        # Update balance
        if expense.budget:
            update_balance(budget_record, expense.amount, "expended")
            notification(expense, "Saldo actualizado",
                    "Se actualizó correctamente el saldo del presupuesto asociado a este gasto.",
                    "success")
        elif expense.account:
            update_balance(account_record, expense.amount * -1)
            notification(expense, "Saldo actualizado",
                    "Se actualizó correctamente el saldo de la cuenta asociada a este gasto.",
                    "success") 
            
        # Recalculate dashboard stats
        user_id = expense.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()
        
        return expense 
    
    def write(self, vals):
        for rec in self:
            # Check date is not in the future
            if "date" in vals and datetime.strptime(vals["date"], "%Y-%m-%d") > datetime.today():
                raise ValidationError("La fecha del gasto no puede ser posterior a hoy. Ingrese una fecha válida.")
            
            # Check if there is only one source account for this expense, as it should be
            if ("account" in vals and vals["account"]) and ("budget" in vals and vals["budget"]):
                raise ValidationError("Debe seleccionar solamente una cuenta de origen para este gasto.")
            
            # Cleaning the name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another record
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.expense"].search([
                    ("name", "=", new_name.capitalize()),
                    ("user_id", "=", self.env.uid)])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe un gasto con este mismo nombre. Por favor, elija un nombre diferente.")
            
            current_amount_expense = rec.amount
            new_amount_expense = vals.get("amount", None)
            current_account_expense_id = rec.account.id if rec.account is not None else None
            current_budget_expense_id = rec.budget.id if rec.budget is not None else None
            if current_account_expense_id and current_budget_expense_id: # only for development
                raise ValidationError("Este registro no puede tener cuenta ordinaria y presupuesto asociados.")
            
            if current_account_expense_id:
                current_account_record = self.env["cashmind.account"].browse(current_account_expense_id)
                current_available = current_account_record.balance
            elif current_budget_expense_id:
                current_account_record = self.env["cashmind.budget"].browse(current_budget_expense_id)
                current_available = current_account_record.amount - current_account_record.expended
            
            if "budget" in vals and vals["budget"]:
                new_account_expense_id = vals["budget"]
                new_account_record = self.env["cashmind.budget"].browse(new_account_expense_id)
                new_available = new_account_record.amount - new_account_record.expended
            elif "account" in vals and vals["account"]:
                new_account_expense_id = vals["account"]
                new_account_record = self.env["cashmind.account"].browse(new_account_expense_id)
                new_available = new_account_record.balance
            else:
                new_account_expense_id = None
                new_account_record = None
                     
            # Check amount is greater than 0
            if new_amount_expense is not None and new_amount_expense <= 0:
                raise ValidationError("La cantidad a gastar debe ser mayor que 0.")
            
            # Check availability
            if not new_account_expense_id:
                if new_amount_expense:
                    current_available += current_amount_expense
                    if new_amount_expense > current_available:
                        raise ValidationError("No hay saldo suficiente para realizar esta operación.")
            else: # If new account
                if new_amount_expense and new_amount_expense > new_available:
                    raise ValidationError("No hay saldo suficiente para realizar esta operación.")
                elif not new_amount_expense and current_amount_expense > new_available:
                    raise ValidationError("No hay saldo suficiente para realizar esta operación.")
            
            # If only modifying the quantity (amount), not the account name
            if not new_account_expense_id and new_amount_expense:
                # Update the wrong amount for the current account
                difference = new_amount_expense - current_amount_expense
                if current_account_expense_id:
                    update_balance(current_account_record, difference * -1)
                elif current_budget_expense_id:
                    update_balance(current_account_record, difference, "expended")

                notification(self, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de la cuenta asociada a este gasto.",
                             "success")
            
            # If only modifying the account name, not the quantity (amount)
            elif new_account_expense_id and not new_amount_expense:
                # Adding the amount to the current account before substracting it from the new account
                if current_account_expense_id:
                    update_balance(current_account_record, current_amount_expense)
                elif current_budget_expense_id:
                    update_balance(current_account_record, current_amount_expense * -1, "expended")
                # Substracting the amount from the new account balance
                if "account" in vals and vals["account"]:
                    update_balance(new_account_record, current_amount_expense * -1)
                elif "budget" in vals and vals["budget"]:
                    update_balance(new_account_record, current_amount_expense, "expended")
                
                notification(self, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de las cuentas asociadas a este gasto.",
                             "success")

            # If modifying both the account name and the quantity (amount)
            elif new_account_expense_id and new_amount_expense:
                # Increase the wrong amount for the current account before substracting the right amount from the new account
                if current_account_expense_id:
                    update_balance(current_account_record, current_amount_expense)
                elif current_budget_expense_id:
                    update_balance(current_account_record, current_amount_expense * -1, "expended")
                # Substracting the right amount from the new account
                if new_account_expense_id:
                    if "account" in vals and vals["account"]:
                        update_balance(new_account_record, new_amount_expense * -1)
                    elif "budget" in vals and vals["budget"]:
                        update_balance(new_account_record, new_amount_expense, "expended")
            
            else:  
                amount_changed = False if not new_amount_expense else new_amount_expense != current_amount_expense
                account_changed = False if not new_account_expense_id else new_account_expense_id != current_account_expense_id
                if not amount_changed or not account_changed:
                    notification(rec, "Datos actualizados", "Se actualizaron correctamente los datos del gasto.", "success")

            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note
        
        expense = super().write(vals)
        
        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', rec.user_id.id)])
        dashboards.recalculate_dashboard()
        
        return expense
    
    def unlink(self): 
        for rec in self:
            # Update the amount in the account or in the budget
            existing_account = rec.account
            existing_budget = rec.budget

            if existing_account:
                update_balance(existing_account, rec.amount)
            elif existing_budget:
                update_balance(existing_budget, rec.amount * -1, "expended")
        
        if len(self) < 2:
            notification(self, "Gasto eliminado",
                        "Se actualizó correctamente el saldo de la cuenta asociada a este gasto.",
                        "success")
        else:
            notification(self, "Gastos eliminados",
                        "Se actualizó correctamente el saldo de la cuenta asociada a cada gasto.",
                        "success")
        
        user_id = self.user_id.id
        expense = super().unlink()

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()
        
        return expense