from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import datetime
from ..utils import notification, update_balance, clean_input

class Transfer(models.Model):
    _name = "cashmind.transfer"

    name = fields.Char(string="Nombre", required=True)
    source_account = fields.Many2one("cashmind.account", string="Cuenta de origen", required=True)
    source_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                         store=True, compute="_compute_source_currency",
                                         default=lambda self: self._default_currency())
    available_source_balance = fields.Monetary(string="Balance", currency_field="source_currency_id", readonly=True,
                                               compute="_compute_source_availability")
    destination_account = fields.Many2one("cashmind.account", string="Cuenta de destino", required=True)
    destination_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                              store=True, compute="_compute_destination_currency")
    available_destination_balance = fields.Monetary(string="Balance", currency_field="destination_currency_id", readonly=True,
                                                    compute="_compute_destination_availability")
    amount = fields.Monetary(string="Cantidad", currency_field="source_currency_id", required=True)
    transfer_date = fields.Date(string="Fecha", default=lambda self: fields.Date.context_today(self), 
                                required=True)
    active = fields.Boolean(string="Mostrar", default=True)
    note = fields.Text(string="Notas")

    @api.model
    def _default_currency(self):
        currency = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        return currency.id if currency else False
    
    @api.onchange("source_account")
    def _compute_source_availability(self):
        for rec in self:
            rec.available_source_balance = rec.source_account.balance
    
    @api.onchange("destination_account")
    def _compute_destination_availability(self):
        for rec in self:
            rec.available_destination_balance = rec.destination_account.balance 

    @api.depends("source_account")
    def _compute_source_currency(self):
        for rec in self:
            rec.source_currency_id = rec.source_account.currency_id
    
    @api.depends("destination_account")
    def _compute_destination_currency(self):
        for rec in self:
            rec.destination_currency_id = rec.destination_account.currency_id
    
    @api.onchange("source_account", "destination_account")
    def _onchange_check_same_acount(self):
        for rec in self:
            if rec.source_account and rec.destination_account and rec.source_account == rec.destination_account:
                notification(rec, "Error de cuenta", "La cuenta de destino y de origen no pueden ser la misma.",
                             "warning")
        
    def create(self, vals):
        if isinstance(vals, list):
            vals = vals[0]
        
        # Cleaning the category name and description
        name = clean_input(vals["name"], "title")
        name = name.lower()
        note = clean_input(vals["note"], "note") if vals["note"] else None

        # Check if this name already exists for another budget
        name_exists = self.env["cashmind.transfer"].search([("name", "=", name.capitalize())])
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe una transferencia con este mismo nombre. Por favor, elija un nombre diferente.")
            
        # Check same currencies
        source_account_id = vals["source_account"]
        source_account_record = self.env["cashmind.account"].browse(source_account_id)
        destination_account_id = vals["destination_account"]
        destination_account_record = self.env["cashmind.account"].browse(destination_account_id)

        if source_account_record.currency_id != destination_account_record.currency_id:
            raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")

        # Check same accounts
        if vals["source_account"] == vals["destination_account"]:
            raise ValidationError("Las cuentas de origen y destino no pueden ser la misma.")
        
        # Check amount > 0
        if vals["amount"] is not None and vals["amount"] <= 0:
            raise ValidationError("La cantidad a transferir debe ser mayor que 0")

        # Check amount <= available_source_balance
        available_source_balance = source_account_record.balance
        if vals["amount"] > available_source_balance:
            raise ValidationError("No hay saldo suficiente en la cuenta de origen para realizar la transferencia.")
        
        # Check if date is maximum today
        if datetime.strptime(vals["transfer_date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha de la transferencia no puede ser posterior a hoy.")
        
        vals["name"] = name.capitalize()
        if note:
            vals["note"] = note

        transfer = super().create(vals)

        for rec in transfer:
            # Substract amount from source_account
            update_balance(source_account_record, vals["amount"] * -1)

            # Add amount to destination_account
            update_balance(destination_account_record, vals["amount"])

        notification(transfer, "Saldo actualizado", 
                     "Se actualizó correctamente el saldo de las cuentas asociadas a esta transferencia.",
                    "success")

        return transfer
    
    def write(self, vals):
        # Check if date is maximum today
        if "transer_date" in vals and datetime.strptime(vals["transfer_date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha de la transferencia no puede ser posterior a hoy.")
                
        for rec in self:
            current_source_account_id= rec.source_account.id
            current_amount = rec.amount

            new_source_account_id= vals.get("source_account", None)
            new_amount = vals.get("amount", None)

            current_destination_account_id= rec.destination_account.id
            new_destination_account_id= vals.get("destination_account", None)

            # Cleaning the category name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another account
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.transfer"].search([("name", "=", new_name.capitalize())])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe una transferencia con este mismo nombre. Por favor, elija un nombre diferente.")
                    
            # Check if amount is > 0
            if new_source_account_id:
                account_record = self.env["cashmind.account"].browse(new_source_account_id)
            else:
                account_record = rec.source_account
            if new_amount is not None and new_amount <= 0:
                raise ValidationError("La cantidad a transferir debe ser mayor que 0")
            
            # Convert accounts_id to record
            current_source_account_record = rec.env["cashmind.account"].browse(current_source_account_id)
            current_destination_account_record = rec.env["cashmind.account"].browse(current_destination_account_id)
            if new_source_account_id:
                new_source_account_record = rec.env["cashmind.account"].browse(new_source_account_id)
            if new_destination_account_id:
                new_destination_account_record = rec.env["cashmind.account"].browse(new_destination_account_id)

            # Check same accounts and different currencies for both accounts
            if new_source_account_id and new_destination_account_id:
                if new_source_account_id ==  new_destination_account_id:
                    raise ValidationError("Las cuentas de origen y destino no pueden ser la misma.")
                elif new_source_account_record.currency_id != new_destination_account_record.currency_id:
                    raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")
            elif not new_source_account_id and new_destination_account_id:
                if current_source_account_id == new_destination_account_id:
                    raise ValidationError("Las cuentas de origen y destino no pueden ser la misma.")
                elif current_source_account_record.currency_id != new_destination_account_record.currency_id:
                    raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")
            elif new_source_account_id and not new_destination_account_id:
                if new_source_account_id == current_destination_account_id:
                    raise ValidationError("Las cuentas de origen y destino no pueden ser la misma.")
                elif new_source_account_record.currency_id != current_destination_account_record.currency_id:
                    raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")

            # Check available balance for source_account
            available_balance = account_record.balance
            # If only modifying the amount, and not any account (source or destination)
            if not new_source_account_id and not new_destination_account_id:
                available_balance += rec.amount
                            
            if "amount" in vals and vals["amount"] > available_balance:
                raise ValidationError("No hay saldo suficiente en la cuenta de origen para realizar la operación.")
            elif not "amount" in vals and rec.amount > available_balance:
                raise ValidationError("No hay saldo suficiente en la cuenta de origen para realizar la operación.")
                        
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

            source_account_changed = False if not new_source_account_id else new_source_account_id != current_source_account_id
            destination_account_changed = False if not new_destination_account_id else new_destination_account_id != current_destination_account_id
            amount_changed = False if not new_amount else new_amount != current_amount

            if not source_account_changed and not destination_account_changed and not amount_changed:
                notification(rec, "Datos actualizados", "Se actualizaron correctamente los datos de esta transferencia.", "success")
            else:
                notification(rec, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de las cuentas asociadas a esta transferencia.",
                             "success")
            
            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note
        
        return super().write(vals)

    def unlink(self):
        for rec in self:
            source_account_record = rec.source_account
            current_amount = rec.amount
            destination_account_record = rec.destination_account
            
            # Update the amount in the source_account
            update_balance(source_account_record, current_amount)

            # Update the amount in the destination_account
            update_balance(destination_account_record, current_amount * -1)
            
        if len(self) < 2:
            notification(self, "Transferencia eliminada",
                        "Se actualizó correctamente el saldo de las cuentas asociadas a esta transferencia.",
                        "success")
        else:
            notification(self, "Transferencias eliminadas",
                        "Se actualizó correctamente el saldo de las cuentas asociadas a estas transferencias.",
                        "success")
        
        return super().unlink()