from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import datetime
from ..utils import update_balance, notification, clean_input

class Save(models.Model):
    _name = "cashmind.save"

    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    name = fields.Char(string="Nombre", required=True)
    source_account = fields.Many2one("cashmind.account", string="Cuenta de origen", required=True, domain="[('user_id', '=', uid)]")
    source_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                         store=True, compute="_compute_source_currency")
    available = fields.Monetary(string="Disponible", compute="_compute_availability", currency_field="source_currency_id", 
                                readonly=True)
    amount = fields.Monetary(string="Cantidad", required=True, currency_field="source_currency_id")
    destination_savinggoal_account = fields.Many2one("cashmind.savinggoal", string="Cuenta de ahorro", required=True, 
                                                     domain="[('user_id', '=', uid)]")
    destination_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                              store=True, compute="_compute_destination_currency")
    available_destination = fields.Monetary(string="Balance actual", compute="_compute_destination_availability", 
                                            currency_field="destination_currency_id", readonly=True)
    date = fields.Date(string="Fecha", default=datetime.today(), required=True)
    note = fields.Text(string="Notas")
    active = fields.Boolean(string="Activo", default=True)
    goal_savinggoal_account = fields.Monetary(string="Objetivo", currency_field="destination_currency_id", compute="_get_goal", store=False)

    @api.depends("destination_savinggoal_account")
    def _get_goal(self):
        for rec in self:
            rec.goal_savinggoal_account = rec.destination_savinggoal_account.amount # Field 'amount' is the saving goal

    @api.onchange("source_account")
    def _onchange_no_balance(self):
        for rec in self:
            if rec.source_account and rec.source_account.balance == 0:
                notification(rec, "Cuenta sin saldo", "La cuenta seleccionada no tiene saldo disponible.",
                             "warning")
                return

    @api.onchange("source_account")
    def _compute_availability(self):
        for rec in self:
            rec.available = rec.source_account.balance

    @api.onchange("destination_savinggoal_account")
    def _compute_destination_availability(self):
        for rec in self:
            rec.available_destination = rec.destination_savinggoal_account.balance

    @api.depends("source_account")
    def _compute_source_currency(self):
        for rec in self:
            rec.source_currency_id = rec.source_account.currency_id
    
    @api.depends("destination_savinggoal_account")
    def _compute_destination_currency(self):
        for rec in self:
            rec.destination_currency_id = rec.destination_savinggoal_account.currency_id
    
    def create(self, vals):
        if isinstance(vals, list):
            vals = vals[0]

        # Cleaning the name and description
        name = clean_input(vals["name"], "title") if "name" in vals else None
        name = name.lower() if name else None
        note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

        # Check if this name already exists for another record
        name_exists = self.env["cashmind.save"].search([
            ("name", "=", name.capitalize()),
            ("user_id", "=", self.env.uid)]) if name else None
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe un movimiento de ahorro con este mismo nombre. Por favor, elija un nombre diferente.")
            
        # Check same currencies
        source_account_id = vals["source_account"]
        source_account_record = self.env["cashmind.account"].browse(source_account_id)
        destination_account_id = vals["destination_savinggoal_account"]
        destination_account_record = self.env["cashmind.savinggoal"].browse(destination_account_id)

        if source_account_record.currency_id != destination_account_record.currency_id:
            raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")

        # Check amount > 0
        if "amount" in vals and vals["amount"] is not None and vals["amount"] <= 0:
            raise ValidationError("La cantidad a ahorrar debe ser mayor que 0")

        # Check amount <= available_source_balance
        available_source_balance = source_account_record.balance
        if "amount" in vals and vals["amount"] > available_source_balance:
            raise ValidationError("No hay saldo suficiente en la cuenta de origen para realizar la operación.")
        
        # Check if date is maximum today
        if "date" in vals and datetime.strptime(vals["date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha del ahorro no puede ser posterior a hoy.")
        
        vals["name"] = name.capitalize() if name else None
        if note:
            vals["note"] = note

        save = super().create(vals)

        for rec in save:
            # Substract amount from source_account
            update_balance(source_account_record, vals["amount"] * -1)

            # Add amount to destination_account
            update_balance(destination_account_record, vals["amount"])

        notification(save, "Saldo actualizado", 
                     "Se actualizó correctamente el saldo de las cuentas asociadas a este ahorro.",
                    "success")
        
        # Recalculate dashboard stats
        user_id = save.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return save 
        
    
    def write(self, vals):
       # Check if date is maximum today
        if "date" in vals and datetime.strptime(vals["date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha del ahorro no puede ser posterior a hoy.")
        
        for rec in self:
            current_source_account_id = rec.source_account.id
            current_amount = rec.amount

            new_source_account_id = vals.get("source_account", None)
            new_amount = vals.get("amount", None)

            current_destination_account_id = rec.destination_savinggoal_account.id
            new_destination_account_id = vals.get("destination_savinggoal_account", None)

            # Cleaning the name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another record
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.save"].search([
                    ("name", "=", new_name.capitalize()),
                    ("user_id", "=", self.env.uid)])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe un movimiento de ahorro con este mismo nombre. Por favor, elija un nombre diferente.")
                
            # Check if amount is > 0
            if new_source_account_id:
                account_record = self.env["cashmind.account"].browse(new_source_account_id)
            else:
                account_record = rec.source_account
            if new_amount is not None and new_amount <= 0:
                raise ValidationError(f"La cantidad a ahorrar debe ser mayor que 0.")
            
            # Convert accounts_id to record
            current_source_account_record = rec.env["cashmind.account"].browse(current_source_account_id)
            current_destination_account_record = rec.env["cashmind.savinggoal"].browse(current_destination_account_id)
            current_goal_status = current_destination_account_record.goal_completed
            if new_source_account_id:
                new_source_account_record = rec.env["cashmind.account"].browse(new_source_account_id)
            if new_destination_account_id:
                new_destination_account_record = rec.env["cashmind.savinggoal"].browse(new_destination_account_id)
                new_goal_status = new_destination_account_record.goal_completed

            # Check different currencies
            if new_source_account_id:
                currency_source_account = new_source_account_record.currency_id
            else:
                currency_source_account = current_source_account_record.currency_id
            if new_destination_account_id:
                currency_destination_account = new_destination_account_record.currency_id
            else:
                currency_destination_account = current_destination_account_record.currency_id
            if currency_source_account != currency_destination_account:
                raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")

            # Check availability
            available_balance = account_record.balance
            if not new_source_account_id:
                if new_amount:
                    available_balance += current_amount
                    if new_amount > available_balance:
                        raise ValidationError("No hay saldo suficiente para realizar esta operación.")
            else: # If new source account
                if new_amount and new_amount > available_balance:
                    raise ValidationError("No hay saldo suficiente para realizar esta operación.")
                elif not new_amount and current_amount > available_balance:
                    raise ValidationError("No hay saldo suficiente para realizar esta operación.")
                        
            # If modifying the quantity (amount)
            if new_amount:
                # Calculate the difference between amounts (current and new)
                difference = new_amount - current_amount

                # If modifying the source_account 
                if new_source_account_id:
                    # Add current_amount back to current_source_account
                    update_balance(current_source_account_record, current_amount)
                    # Substract new_amount from new_source_account
                    update_balance(new_source_account_record, new_amount * -1)
                # If not modifying the source_account
                else:
                    # Update the balance in the source_account
                    update_balance(current_source_account_record, difference * -1)
                
                # If modifying the destination_account
                if new_destination_account_id:
                    # Substract current_amount back from current_destination_account
                    update_balance(current_destination_account_record, current_amount * -1)
                    # Add new_amount to new_destination_account
                    update_balance(new_destination_account_record, new_amount)
                # If not modifying the destination_account
                else:
                    # Update the balance
                    update_balance(current_destination_account_record, difference)
            
            else:
                # If modifying the source_account 
                if new_source_account_id:
                    # Add current_amount back to current_source_account
                    update_balance(current_source_account_record, current_amount)
                    # Substract current_amount from new_source_account
                    update_balance(new_source_account_record, current_amount * -1)
                
                # If modifying the destination_account
                if new_destination_account_id:
                    # Substract current_amount back from current_destination_account
                    update_balance(current_destination_account_record, current_amount * -1)
                    # Add current_amount to new_destination_account
                    update_balance(new_destination_account_record, current_amount)
            
            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note
            
        save = super().write(vals)
        
        if ((new_amount and new_amount != current_amount) or 
            (new_destination_account_id and new_destination_account_id != current_destination_account_id) or 
            (new_source_account_id and new_source_account_id != current_source_account_id)):
            notification(rec, "Saldo actualizado",
                        "Se actualizó correctamente el saldo de las cuentas asociadas a este movimiento.",
                        "success")
        else:
            notification(rec, "Datos actualizados",
                        "Se actualizaron correctamente los datos de este movimiento de ahorro.",
                        "success")

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', rec.user_id.id)])
        dashboards.recalculate_dashboard()

        return save

    def unlink(self):
        for rec in self:
            source_account_record = rec.source_account
            current_amount = rec.amount
            destination_account_record = rec.destination_savinggoal_account
            
            # Update the amount in the source_account
            update_balance(source_account_record, current_amount)

            # Update the amount in the destination_account
            update_balance(destination_account_record, current_amount * -1)
        
        if len (self) < 2:
            notification(self, "Ahorro eliminado",
                        "Se actualizó correctamente el saldo de las cuentas asociadas a este ahorro.",
                        "success")
        else:
            notification(self, "Ahorros eliminados",
                        "Se actualizó correctamente el saldo de las cuentas asociadas a estos ahorros.",
                        "success")
        
        user_id = self.user_id.id
        save = super().unlink()
        
        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return save