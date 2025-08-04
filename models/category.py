from odoo import fields, models, api
from odoo.exceptions import ValidationError
from ..utils import notification, clean_input

class Category(models.Model):
    _name = "cashmind.category"

    user_id = fields.Many2one("res.users", string="Usuario", required=True, ondelete="cascade", unique=True,
                              default=lambda self: self.env.user)
    name = fields.Char(string="Categoría", required=True)
    category_type = fields.Selection([
            ("expense", "Gasto"),
            ("income", "Ingreso"),
            ("NA", "Ajuste de saldo")
        ], string="Tipo de categoría", required=True)

    parent_id = fields.Many2one("cashmind.category", string="Categoría superior", index=True, ondelete="cascade", 
                                domain="[('user_id', '=', uid)]")
    child_ids = fields.One2many("cashmind.category", "parent_id", string="Subcategorías")
    description = fields.Text(string="Descripción")
    active = fields.Boolean(string="Mostrar", default=True)
    income_ids = fields.One2many("cashmind.income", "category", string="Ingresos")
    expense_ids = fields.One2many("cashmind.expense", "category", string="Gastos")
    budget_ids = fields.One2many("cashmind.budget", "category", string="Presupuestos")
    is_used = fields.Boolean(string="Utilizada", compute="_compute_is_used", store=True)


    @api.depends("income_ids", "expense_ids", "budget_ids")
    def _compute_is_used(self):
        for rec in self:
            rec.is_used = bool(rec.income_ids or rec.expense_ids or rec.budget_ids)


    @api.onchange('category_type')
    def _onchange_category_type(self):
        self.parent_id = False

    def create(self, vals):
        name = clean_input(vals["name"], "title") if "name" in vals else None
        name = name.lower() if name else None
        description = clean_input(vals["description"], "description") if "description" in vals and vals["description"] else None

        if "category_type" in vals and vals["category_type"] == "NA":
            # Avoid creating another special category
            special_category = self.env["cashmind.category"].search([
                ("category_type", "=", "NA"),
                ("user_id", "=", self.env.uid)])
            if special_category:
                raise ValidationError("Solo puede existir una categoría especial llamada AJUSTE DE SALDO, y no puede crear " \
                                    "otra igual. Debe seleccionar obligatoriamente INGRESO o GASTO como tipo de categoría, y " \
                                    "darle un nombre diferente.")
            # Check name of this special category
            if name and name != "ajuste de saldo":
                raise ValidationError("Solo puede crear una categoría especial que no sea de tipo INGRESO ni GASTO, la cual " \
                                    "debe llamarse específicamente 'AJUSTE DE SALDO'. Esta categoría puede ser utilizada " \
                                    "para movimientos y ajustes de saldo que no cuentan como estadística de INGRESO o GASTO.")
                    
        else:
            forbidden_names = ["ajuste de saldo", "ajuste", "ajustar", "ajuste saldo", "ajustar saldo" ]
            if name and name in forbidden_names:
                raise ValidationError("El nombre 'AJUSTE DE SALDO' (o similares) está reservado para una categoría especial que no " \
                                    "computa como ingreso ni gasto. Si aun no la ha creado, puede hacerlo, definiendo como tipo de " \
                                    "categoría: 'AJUSTE DE SALDO' y nombrándola igualmente: 'AJUSTE DE SALDO")
            
        # Check if this name doesn't exist for another category
        name_exists = self.env["cashmind.category"].search([
            ("name", "=", name.capitalize()),
            ("user_id", "=", self.env.uid)]) if name else None
        if name_exists:
            if name == name_exists.name.lower():
                raise ValidationError("Ya existe una categoría con este mismo nombre. Por favor, elija un nombre diferente.")
        
        if name and name != "ajuste de saldo":
            vals["name"] = name.capitalize()
        else:
            vals["name"] = name.upper() if "name" in vals else None
            vals["parent_id"] = False if "parent_id" in vals else None
            vals["child_ids"] = False if "child_ids" in vals else None
        
        if description:
            vals["description"] = description

        category = super().create(vals)
        notification(category, "Categoría creada", "Se creó correctamente la categoría.", "success")

        # Recalculate dashboard stats
        user_id = category.user_id.id
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return category

    
    def write(self, vals):
        for rec in self:
            # Cleaning the name and description
            new_name = clean_input(vals["name"], "title") if "name" in vals and vals["name"] else None
            new_name = new_name.lower() if new_name else None
            new_description = clean_input(vals["description"], "description") if (
                            "description" in vals and vals["description"]) else None
                        
            current_name = rec.name.lower()

            if "category_type" in vals and vals["category_type"]:
                new_category_type = vals["category_type"]
            else:
                new_category_type = None
            current_category_type = rec.category_type

            special_category_exists = self.env["cashmind.category"].search([
                ("category_type", "=", "NA"),
                ("user_id", "=", self.env.uid)])

            # If trying to change the current_name
            forbidden_names = ["ajuste de saldo", "ajuste", "ajustar", "ajuste saldo", "ajustar saldo" ]
            if new_name and new_name != current_name:
                if new_name == "ajuste de saldo":
                    # Avoid creating another special category
                    if special_category_exists:
                        raise ValidationError("Ya existe la categoría especial AJUSTE DE SALDO, y no puede crear otra igual. Debe " \
                                            "seleccionar obligatoriamente INGRESO o GASTO como tipo de categoría, y darle un nombre " \
                                            "diferente.")
                    else: 
                        if new_name in forbidden_names:
                            raise ValidationError("El nombre 'AJUSTE DE SALDO' (o similares) está reservado para una categoría especial que no " \
                                    "computa como ingreso ni gasto. Si aun no la ha creado, puede hacerlo, definiendo como tipo de " \
                                    "categoría: 'AJUSTE DE SALDO' y nombrándola igualmente: 'AJUSTE DE SALDO")
                elif new_name in forbidden_names:
                    raise ValidationError("El nombre 'AJUSTE DE SALDO' (o similares) está reservado para una categoría especial que no " \
                                    "computa como ingreso ni gasto. Si aun no la ha creado, puede hacerlo, definiendo como tipo de " \
                                    "categoría: 'AJUSTE DE SALDO' y nombrándola igualmente: 'AJUSTE DE SALDO")
                    
                # Avoid changing name of special category
                if current_name == "ajuste de saldo":
                    raise ValidationError("No puede cambiar el nombre de la categoría especial AJUSTE DE SALDO. Si prefiere, " \
                                        "puede eliminarla.")
                else:
                    # Check if this name doesn't exist for another existing category
                    name_exists = rec.search([
                        ("name", "=", new_name.capitalize()),
                        ("user_id", "=", self.env.uid)])
                    if name_exists:
                        if new_name == name_exists.name.lower():
                            raise ValidationError("Ya existe una categoría con este mismo nombre. Por favor, elija un nombre diferente.")
                    
            # Check if there are other models pointing to this one
            expense_record = self.env["cashmind.expense"].search([("category", "=", rec.id)])
            income_record = self.env["cashmind.income"].search([("category", "=", rec.id)]) 
            budget_record = self.env["cashmind.budget"].search([("category", "=", rec.id)])
            category_record = self.env["cashmind.category"].search([("parent_id", "=", rec.id)])
                        
            if new_category_type and new_category_type != current_category_type:
                # Avoid creating another special category
                if new_category_type  == "NA":
                    if special_category_exists:
                        raise ValidationError("Ya existe la categoría especial AJUSTE DE SALDO, y no puede crear otra igual. Debe " \
                                            "seleccionar obligatoriamente INGRESO o GASTO como tipo de categoría, y darle un nombre " \
                                            "diferente.")
                    if (not new_name and current_name != "ajuste de saldo") or (new_name and new_name != "ajuste de saldo"):
                        raise ValidationError("Solo puede crear una categoría especial que no sea de tipo INGRESO ni GASTO, la cual " \
                                                "debe llamarse específicamente 'AJUSTE DE SALDO'. Esta categoría puede ser utilizada " \
                                                "para movimientos y ajustes de saldo que no cuentan como estadística de INGRESO o GASTO.")
                if current_category_type == "NA":
                    raise ValidationError("No puede cambiar el tipo de la categoría especial AJUSTE DE SALDO. Si prefiere, " \
                                            "puede eliminarla.")
                else:
                    # Avoid changing name of special category
                    if current_name == "ajuste de saldo":
                        raise ValidationError("No puede cambiar el tipo de la categoría especial AJUSTE DE SALDO. Si prefiere, " \
                                            "puede eliminarla.")
                    
                # If there are other models (or subcategories) pointing to this category, category_type cannot be changed
                if (expense_record or income_record or budget_record):
                    raise ValidationError("No puede cambiar el tipo de categoría mientras existan registros asociados a esta.")
                elif category_record:
                    raise ValidationError("No puede cambiar el tipo de categoría mientras esta tenga subcategorías asociadas.")

            if new_name:
                if new_name == "ajuste de saldo":
                    vals["name"] = new_name.upper()
                    vals["parent_id"] = False
                    vals["child_ids"] = False
                else:
                    vals["name"] = new_name.capitalize()
            else:
                if current_name == "ajuste de saldo":
                    vals["parent_id"] = False
                    vals["child_ids"] = False
            
            if new_description:
                vals["description"] = new_description

        category = super().write(vals)
        notification(rec, "Categoría actualizada", "Se actualizaron correctamente los datos de la categoría", "success")

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', rec.user_id.id)])
        dashboards.recalculate_dashboard()

        return category


    def unlink(self): 
        for rec in self:
            # Check if there are other models pointing to this one
            expense_record = self.env["cashmind.expense"].search([("category", "=", rec.id)])
            income_record = self.env["cashmind.income"].search([("category", "=", rec.id)]) 
            budget_record = self.env["cashmind.budget"].search([("category", "=", rec.id)])
            category_record = self.env["cashmind.category"].search([("parent_id", "=", rec.id)])


            if (expense_record or income_record or budget_record):
                raise ValidationError("Esta categoría no puede eliminarse mientras existan registros asociados a esta. " \
                                    "Intente archivar la categoría si no quiere eliminar los registros asociados. ")
            elif category_record:
                raise ValidationError("No puede eliminar una categoría que tenga subcategorías asociadas. " \
                                    "Intente archivar la categoría si no quiere eliminar las subcategorías asociadas a esta. ")
        
        user_id = self.user_id.id
        category = super().unlink()

        # Recalculate dashboard stats
        dashboards = self.env['cashmind.dashboard'].search([('user_id', '=', user_id)])
        dashboards.recalculate_dashboard()

        return category