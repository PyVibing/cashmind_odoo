from odoo import fields, models, api
from odoo.exceptions import ValidationError
from ..utils import notification, clean_input

class Account(models.Model):
    _name = "cashmind.account"

    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    name = fields.Char(string="Nombre de la cuenta", required=True)
    account_type = fields.Selection([
        ("bank", "Cuenta bancaria"),
        ("credit", "Tarjeta crédito"),
        ("debit", "Tarjeta débito"),
        ("cash", "Efectivo"),
        ("other", "Otro"),
        ], string="Tipo de cuenta", required=True, default="bank")
    currency_id = fields.Many2one("res.currency", string="Moneda", required=True, 
                                  default=lambda self: self._default_currency())
    balance = fields.Monetary(string="Balance", currency_field="currency_id", required=True)
    active = fields.Boolean(string="Mostrar", default=True)
    note = fields.Text(string="Notas")
    income_ids = fields.One2many("cashmind.income", "account", string="Ingresos")
    expense_ids = fields.One2many("cashmind.expense", "account", string="Gastos")
    budget_ids = fields.One2many("cashmind.budget", "account", string="Presupuestos")
    source_transfer_ids = fields.One2many("cashmind.transfer", "source_account", string="Transferencias enviadas")
    destination_transfer_ids = fields.One2many("cashmind.transfer", "destination_account", string="Transferencias recibidas")
    source_transfer_external_ids = fields.One2many("cashmind.transfer_external", "source_account", string="Transferencias enviadas")
    destination_transfer_external_ids = fields.One2many("cashmind.transfer_external", "destination_account", string="Transferencias recibidas")
    
    @api.model
    def _default_currency(self):
        currency = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        return currency.id if currency else False
    
    def create(self, vals):
        # Cleaning the name and description
        name = clean_input(vals["name"], "title") if "name" in vals else None
        name = name.lower() if name else None
        note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

        # Check if this name already exists for another record for this user
        name_exists = self.env["cashmind.account"].search([
            ("name", "=", name.capitalize()), 
            ("user_id", "=", self.env.uid)]) if name else None

        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe una cuenta con este mismo nombre. Por favor, elija un nombre diferente.")

        # Identify account type to personalize messages
        account_type = vals["account_type"] if "account_type" in vals else None
        
        if account_type == "bank":
            message = "cuenta bancaria"
        elif account_type == "debit":
            message = "tarjeta de débito"
        elif account_type == "credit":
            message = "tarjeta de crédito"
        elif account_type == "cash":
            message = "cuenta de efectivo"
        else:
            message = "cuenta"
        
        if "balance" in vals and vals["balance"] < 0:
            raise ValidationError(f"El balance de la {message} no puede ser menor que 0.")
        
        vals["name"] = name.capitalize() if "name" in vals else None
        if note:
            vals["note"] = note

        account = super().create(vals)
        notification(self, f"{message.capitalize()} creada",
                        f"La {message} ha sido creada correctamente.",
                        "success")
        
        # Recalculate dashboard stats
        user_id = account.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard() 

        return account
    
    
    def write(self, vals):
        for rec in self:
            # Cleaning the name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another record
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.account"].search([
                    ("name", "=", new_name.capitalize()),
                    ("user_id", "=", self.env.uid)])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe una cuenta con este mismo nombre. Por favor, elija un nombre diferente.")
            
            # Identify account type to personalize messages
            if "account_type" in vals:
                account_type = vals["account_type"]
            else:
                account_type = rec.account_type

            if account_type == "bank":
                message = "cuenta bancaria"
            elif account_type == "debit":
                message = "tarjeta de débito"
            elif account_type == "credit":
                message = "tarjeta de crédito"
            elif account_type == "cash":
                message = "cuenta de efectivo"
            else:
                message = "cuenta"

            if ("balance" in vals and 
                rec.balance != vals["balance"] and not 
                self.env.context.get("allow_balance_update")
            ):
                raise ValidationError(f"Para modificar el saldo de la {message}, hágalo a través de 'Ingresos' y 'Gastos'." \
                                    "IMPORTANTE: si quiere que este movimiento no sea calculado como gasto o ingreso, " \
                                    "cree una categoría llamada exactamente 'AJUSTE DE SALDO' (tipo de categoría: NO APLICA) " \
                                    "y cree un movimiento en 'Ingresos' o 'Gastos' asociado a dicha categoría.")

            # If there is a record from any other model (expense, income, etc) pointing to this account,
            # currency cannot be changed
            expense_record = self.env["cashmind.expense"].search([("account", "=", rec.id)])
            income_record = self.env["cashmind.income"].search([("account", "=", rec.id)])
            transfer_record_destination = self.env["cashmind.transfer"].search([("destination_account", "=", rec.id)])
            transfer_record_source = self.env["cashmind.transfer"].search([("source_account", "=", rec.id)])
            save_record = self.env["cashmind.save"].search([("source_account", "=", rec.id)])
            budget_record = self.env["cashmind.budget"].search([("account", "=", rec.id)])

            if "currency_id" in vals:
                current_currency_id = rec.currency_id.id
                new_currency_id = vals["currency_id"]
                                
                if (expense_record or income_record or transfer_record_destination or 
                    transfer_record_source or save_record or budget_record):
                    if current_currency_id != new_currency_id:
                        raise ValidationError("No es posible cambiar el tipo de moneda mientras exista " \
                                                f"al menos un movimiento asociado a esta {message}.")
            if "account_type" in vals:
                current_account_type = rec.account_type
                new_account_type = vals["account_type"]

                if (expense_record or income_record or transfer_record_destination or 
                    transfer_record_source or save_record or budget_record):
                    if current_account_type != new_account_type:
                        raise ValidationError("No es posible cambiar el tipo de cuenta mientras exista " \
                                                "al menos un movimiento asociado a esta cuenta.")

            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note

        account = super().write(vals)
        
        if not self.env.context.get("deny_notification"):
            notification(self, f"{message.capitalize()} actualizada",
                        f"La {message} ha sido actualizada correctamente.",
                        "success")

        return account

    def unlink(self):
        for rec in self:
            # Check if there are other models pointing to this one
            expense_record = self.env["cashmind.expense"].search([("account", "=", rec.id)])
            income_record = self.env["cashmind.income"].search([("account", "=", rec.id)])
            transfer_record_destination = self.env["cashmind.transfer"].search([("destination_account", "=", rec.id)])
            transfer_record_source = self.env["cashmind.transfer"].search([("source_account", "=", rec.id)])
            save_record = self.env["cashmind.save"].search([("source_account", "=", rec.id)])
            budget_record = self.env["cashmind.budget"].search([("account", "=", rec.id)])

            if (expense_record or income_record or transfer_record_source or transfer_record_destination or 
                save_record or budget_record):
                raise ValidationError("Esta cuenta no puede eliminarse mientras existan movimientos asociados a esta. " \
                                    "Intente archivar la cuenta si no quiere eliminar los registros asociados. ")

            # Avoid deleting the last account for an specific currency if dashboard is showing this currency
            dashboard_record = self.env["cashmind.dashboard"].search([("user_id", "=", rec.user_id)])
            currency_in_dashboard = dashboard_record.currency_id.id if dashboard_record else None

            if currency_in_dashboard:
                same_account_currency = self.env["cashmind.account"].search([("user_id", "=", rec.user_id), ("currency_id", "=", currency_in_dashboard)])
                if len(same_account_currency) <= 1:
                    raise ValidationError("Esta es su última cuenta en esta moneda. Antes de eliminarla, " \
                                            "cambie la vista del dashboard a una moneda diferente.")
                
                different_account_currency = self.env["cashmind.account"].search([("user_id", "=", rec.user_id), ("currency_id", "!=", currency_in_dashboard)])
                # ACTUALIZAR CURRENCY_ID DROPBOX eliminando el currency_id eliminado en esta accion
            
        user_id = self.user_id.id
        account = super().unlink()
        
        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return account