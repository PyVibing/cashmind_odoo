from odoo.exceptions import ValidationError
from datetime import date, datetime, timedelta

def notification(self, title, body, message_type, sticky=False):
    self.env["bus.bus"]._sendone(
        self.env.user.partner_id,
        "simple_notification",
        {
            "type": f"{message_type}",
            "title": f"{title}",
            "message": f"{body}",
            "sticky": False
        },
    ) 


def update_balance(account_record, amount, balance_field_name="balance"):
    """Amount could be positive or negative, depending if you want to add or substract."""
    if account_record and account_record.id:
        if balance_field_name == "balance":
            # Avoid getting balance < 0
            if account_record.balance + amount < 0:
                raise ValidationError("No se pudo completar esta operación. " \
                                    "El balance de la cuenta no puede quedar en negativo.")
            account_record.with_context(allow_balance_update=True, deny_notification=True).write({
                "balance": account_record.balance + amount
            })
        elif balance_field_name == "expended":
            account_record.with_context(allow_balance_update=True, deny_notification=True).write({
                "expended": account_record.expended + amount
            })
        
    else:
        print("Cuenta no encontrada o inválida:", account_record)


def clean_input(text_to_clean: str, field: str):
    """Limpia el texto según el campo. Acepta solo letras, números, espacios y signos permitidos."""

    if not isinstance(text_to_clean, str):
        raise ValueError("El texto a ingresar debe estar en formato de texto.")
    if not isinstance(field, str):
        raise ValueError("El parámetro field debe ser una opción válida.")
    
    if field == "title":
        allowed_signs = ["-", "_"]
        message = "El nombre"
    elif field in ("note", "description"):
        allowed_signs = ["-", "_", ",", "."]
        message = "El texto"
    else:
        allowed_signs = []
        message = "El contenido"

    clean_name = ""
    previous_space = False  # Se inicializa una sola vez fuera del bucle

    for c in text_to_clean:
        if not (c.isalnum() or c.isspace() or c in allowed_signs):
            allowed_str = ", ".join(f"( {s} )" for s in allowed_signs)
            raise ValidationError(
                f"{message} proporcionado no es válido. "
                f"Solo se permiten letras, números, espacios y los signos {allowed_str}."
            )

        if c.isspace():
            if not previous_space:
                clean_name += " "
                previous_space = True
        else:
            clean_name += c
            previous_space = False

    return clean_name.strip()

def get_current_month_range(full_date=None):
            if full_date is None:
                full_date = datetime.now()
            
            current_month = full_date.month
            current_year = full_date.year

            if current_month < 12:
                next_month = current_month + 1
                next_month_year = current_year
            else:
                next_month = 1
                next_month_year = current_year + 1
            
            first_day_next_month = date(next_month_year, next_month, 1)
            last_day_current_month = first_day_next_month - timedelta(days=1)
            first_day_current_month = date(current_year, current_month, 1)
            current_month_range = [first_day_current_month, last_day_current_month]

            return current_month_range

def get_last_month_range(full_date=None):
            if full_date is None:
                full_date = datetime.now()
            
            current_month = full_date.month
            current_year = full_date.year

            first_day_current_month = date(current_year, current_month, 1)
            if current_month > 1:
                last_month = current_month - 1
                last_month_year = current_year
            else:
                last_month = 12
                last_month_year = current_year - 1
            
            last_day_last_month = first_day_current_month - timedelta(days=1)
            first_day_last_month = date(last_month_year, last_month, 1)
            last_month_range = [first_day_last_month, last_day_last_month]

            return last_month_range