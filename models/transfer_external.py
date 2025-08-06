from odoo import fields, models, api
from odoo.exceptions import ValidationError
from datetime import datetime
from ..utils import notification, update_balance, clean_input

class Transfer_external(models.Model):
    _name = "cashmind.transfer_external"

    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", default=lambda self: self.env.user)
    external_user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", 
                                        domain="[('id', '!=', uid)]")
    name = fields.Char(string="Nombre", required=True)
    source_account = fields.Many2one("cashmind.account", string="Cuenta de origen", required=True, domain="[('user_id', '=', uid)]")
    source_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                         store=True, compute="_compute_source_currency",
                                         default=lambda self: self._default_currency())
    available_source_balance = fields.Monetary(string="Balance", currency_field="source_currency_id", readonly=True,
                                               compute="_compute_source_availability")
    destination_account = fields.Many2one("cashmind.account", string="Cuenta de destino", required=True, 
                                          domain="[('user_id', '=', external_user_id)]")
    destination_currency_id = fields.Many2one("res.currency", string="Moneda", readonly=True, 
                                              store=True, compute="_compute_destination_currency")
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
        
        # Cleaning the name and description
        name = clean_input(vals["name"], "title") if "name" in vals else None
        name = name.lower() if name else None
        note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

        # Check if this name already exists for another record
        name_exists = self.env["cashmind.transfer_external"].search([
            ("name", "=", name.capitalize()),
            ("user_id", "=", self.env.uid)]) if name else None
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

        # Check amount > 0
        if "amount" in vals and vals["amount"] is not None and vals["amount"] <= 0:
            raise ValidationError("La cantidad a transferir debe ser mayor que 0")

        # Check amount <= available_source_balance
        available_source_balance = source_account_record.balance
        if "amount" in vals and vals["amount"] > available_source_balance:
            raise ValidationError("No hay saldo suficiente en la cuenta de origen para realizar la transferencia.")
        
        # Check if date is maximum today
        if "transfer_date" in vals and datetime.strptime(vals["transfer_date"], "%Y-%m-%d") > datetime.today():
            raise ValidationError("La fecha de la transferencia no puede ser posterior a hoy.")
        
        vals["name"] = name.capitalize() if "name" in vals else None
        if note:
            vals["note"] = note

        transfer = super().create(vals)

        for rec in transfer:
            # Substract amount from source_account
            if "amount" in vals:
                updated_source = update_balance(source_account_record, vals["amount"] * -1)

                # Add amount to destination_account
                updated_destination = update_balance(destination_account_record, vals["amount"])

        if updated_source and updated_destination:
            notification(transfer, "Saldo actualizado", 
                        "Se actualizó correctamente el saldo de las cuentas asociadas a esta transferencia.",
                        "success")
        
        # Recalculate dashboard stats
        user_id = transfer.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        # Recalculate external_user dashboard stats
        external_user_id = transfer.external_user_id
        ext_dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', external_user_id.id)])
        ext_dashboards.recalculate_dashboard(external_user_id=external_user_id)

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

            if new_amount and new_amount != current_amount:
                raise ValidationError("No puede modificar la cantidad de una transferencia hecha a un usuario externo.")

            current_destination_account_id= rec.destination_account.id
            new_destination_account_id= vals.get("destination_account", None)

            if new_destination_account_id and new_destination_account_id != current_destination_account_id:
                raise ValidationError("No puede modificar la cuenta de destino de una transferencia hecha a un usuario externo.")

            # Cleaning the name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another record
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.transfer_external"].search([
                    ("name", "=", new_name.capitalize()),
                    ("user_id", "=", self.env.uid)])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe una transferencia con este mismo nombre. Por favor, elija un nombre diferente.")
                    
            # Convert accounts_id to record
            current_source_account_record = rec.env["cashmind.account"].browse(current_source_account_id)
            current_destination_account_record = rec.env["cashmind.account"].browse(current_destination_account_id)
            if new_source_account_id:
                new_source_account_record = rec.env["cashmind.account"].browse(new_source_account_id)
            
            # Check different currencies for both accounts
            if new_source_account_id:
                if new_source_account_record.currency_id != current_destination_account_record.currency_id:
                    raise ValidationError("El tipo de moneda de la cuenta de origen y destino no pueden ser diferentes.")

            if new_source_account_id:
                # Add current_amount back to current_source_account
                update_balance(current_source_account_record, current_amount)
                # Substract current_amount from new_source_account
                update_balance(new_source_account_record, current_amount * -1)
            
            source_account_changed = False if not new_source_account_id else new_source_account_id != current_source_account_id
            
            if not source_account_changed:
                notification(rec, "Datos actualizados", "Se actualizaron correctamente los datos de esta transferencia.", "success")
            else:
                notification(rec, "Saldo actualizado",
                             "Se actualizó correctamente el saldo de las cuentas asociadas a esta transferencia.",
                             "success")
            
            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note
        
        transfer = super().write(vals)

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', self.user_id.id)])
        dashboards.recalculate_dashboard()

        # Recalculate external_user dashboard stats
        ext_dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', self.external_user_id.id)])
        ext_dashboards.recalculate_dashboard(external_user_id=self.external_user_id)
        
        return transfer

    def unlink(self):
        for rec in self:
            raise ValidationError("No puede eliminar una transferencia hecha a un usuario externo. Si prefiere, puede archivarla.")         

        return super().unlink()