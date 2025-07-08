from odoo.exceptions import ValidationError

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
