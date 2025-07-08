from odoo import fields, models, api
from odoo.exceptions import ValidationError
from ..utils import notification, clean_input
from datetime import datetime

class SavingGoal(models.Model):
    _name = "cashmind.savinggoal" 

    name = fields.Char(string="Nombre", required=True)
    currency_id = fields.Many2one("res.currency", string="Moneda", required=True, 
                                  default=lambda self: self._default_currency())
    amount = fields.Monetary(string="Objetivo", currency_field="currency_id", required=True)
    balance = fields.Monetary(string="Ahorrado", currency_field="currency_id", readonly=True, store=True)
    start_date = fields.Date(string="Fecha de inicio", required=True)
    limit_date = fields.Date(string="Fecha límite", required=True)
    reached_percent = fields.Float(string="Porcentaje", readonly=True, compute="_calculate_percent_reached")
    reached_percent_str = fields.Char(string="Progreso", compute="_compute_percent_str", store=False)
    active = fields.Boolean(string="Mostrar", default=True)
    note = fields.Text(string="Notas")
    percent_for_bar = fields.Html(string="Progreso visual", compute="_compute_percent_for_bar", sanitize=False, store=False)
    goal_completed = fields.Boolean(string="Completada", compute="_compute_goal_completed", store=True)
    save_ids = fields.One2many("cashmind.save", "destination_savinggoal_account", string="Ahorros")

    @api.depends("amount", "balance")
    def _compute_goal_completed(self):
        for rec in self:
            rec.goal_completed = rec.balance >= rec.amount

    @api.depends("reached_percent")
    def _compute_percent_str(self):
        for rec in self:
            percent = round(rec.reached_percent, 2)
            rec.reached_percent_str = f"{percent:.2f} %"

    @api.depends("reached_percent")
    def _compute_percent_for_bar(self):
        for rec in self:
            percent = min(rec.reached_percent, 100) # Limit to 100%
            rec.percent_for_bar = f"""
            <div style="background: #e0e0e0; border-radius: 5px; height: 20px; overflow: hidden;">
                <div style="width: {percent}%; background: #4caf50; height: 100%;"></div>
            </div>
            """

    @api.model
    def _default_currency(self):
        currency = self.env["res.currency"].search([("name", "=", "EUR")], limit=1)
        return currency.id if currency else False

    @api.depends("balance", "amount")
    def _calculate_percent_reached(self):
        for rec in self:
            if rec.amount == 0: # Just in case, but it shouldn't be 0
                rec.reached_percent = 0
            else:
                rec.reached_percent = rec.balance / rec.amount * 100

    def create(self, vals):
        # Cleaning the category name and description
        name = clean_input(vals["name"], "title")
        name = name.lower()
        note = clean_input(vals["note"], "note") if vals["note"] else None

        # Check if this name already exists for another budget
        name_exists = self.env["cashmind.savinggoal"].search([("name", "=", name.capitalize())])
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe una meta de ahorro con este mismo nombre. Por favor, elija un nombre diferente.")
            
        # Check amount(Objetivo) is greater than 0
        if vals["amount"] <= 0:
            raise ValidationError("El objetivo de ahorro debe ser mayor que 0.")
        
        start_date = datetime.strptime(vals["start_date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(vals["limit_date"], "%Y-%m-%d").date()
        
        # Check start_date is not in the future
        if start_date > datetime.today().date():
            raise ValidationError("La fecha de inicio no puede ser posterior a hoy.")
        if end_date <= start_date:
            raise ValidationError("La fecha de finalización debe ser posterior a la fecha de inicio.")
        
        vals["name"] = name.capitalize()
        if note:
            vals["note"] = note

        savinggoal = super().create(vals)
        notification(savinggoal, "Meta de ahorro creada",
                    "La meta de ahorro ha sido creada correctamente.",
                    "success")
        
        return savinggoal
    
    def write(self, vals):
        for rec in self:
            # Cleaning the category name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_note = clean_input(vals["note"], "note") if "note" in vals and vals["note"] else None

            # Check if this name already exists for another account
            if new_name and new_name != rec.name.lower():
                name_exists = self.env["cashmind.savinggoal"].search([("name", "=", new_name.capitalize())])
                if name_exists:
                    if new_name == name_exists.name.lower():
                        raise ValidationError("Ya existe una cuenta de ahorro con este mismo nombre. Por favor, elija un nombre diferente.")
                    
            current_goal_status = rec.goal_completed

            # Check amount(Objetivo) is greater than 0
            if "amount" in vals and vals["amount"] <= 0:
                raise ValidationError("El objetivo de ahorro debe ser mayor que 0.")
            
            # Check start_date is not in the future
            
            start_date = datetime.strptime(vals["start_date"], "%Y-%m-%d").date() if "start_date" in vals else rec.start_date
            end_date = datetime.strptime(vals["limit_date"], "%Y-%m-%d").date() if "limit_date" in vals else rec.limit_date
            
            if start_date > datetime.today().date():
                raise ValidationError("La fecha de inicio no puede ser posterior a hoy.")
            if end_date <= start_date:
                raise ValidationError("La fecha de finalización debe ser posterior a la fecha de inicio.")
            
            # If there is a record from any other model (save) pointing to this account,
            # currency cannot be changed
            save_record = self.env["cashmind.save"].search([("destination_savinggoal_account", "=", rec.id)])
            
            if "currency_id" in vals:
                current_currency_id = rec.currency_id.id
                new_currency_id = vals["currency_id"]
                                
                if save_record:
                    if current_currency_id != new_currency_id:
                        raise ValidationError("No es posible cambiar el tipo de moneda mientras exista " \
                                                "al menos un movimiento asociado a esta cuenta.")
            
            if new_name:
                vals["name"] = new_name.capitalize()
            if new_note:
                vals["note"] = new_note

            saving_goal = super().write(vals)
            
            if not self.env.context.get("deny_notification"):     
                notification(self, "Meta de ahorro actualizada",
                            "La meta de ahorro ha sido actualizada correctamente.",
                            "success")
                
            if rec.goal_completed:
                if not current_goal_status:
                    notification(rec, "Meta de ahorro completada", "FELICIDADES. Ha alcanzado el objetivo de su meta de ahorro.", "success")

            return saving_goal

    def unlink(self):
        for rec in self:
            # Check if there are other models pointing to this one
            save_record = self.env["cashmind.save"].search([("destination_savinggoal_account", "=", rec.id)])
            if save_record:
                raise ValidationError("Esta meta de ahorro no puede eliminarse mientras existan registros de ahorro asociados " \
                                    "a esta. Intente archivar la meta de ahorro si no quiere eliminar los registros asociados.")
            if len(self) < 2:
                notification(self, "Cuenta de ahorro eliminada",
                            "Se eliminó correctamente la cuenta de ahorro seleccionada.",
                            "success")
            else:
                notification(self, "Cuentas de ahorros eliminadas",
                            "Se eliminaron correctamente las cuentas de ahorro seleccionadas.",
                            "success")
            
        return super().unlink()