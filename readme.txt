💸 CashMind – Gestión Financiera Personal (módulo para Odoo)
🤝 Autor: Desarrollado con 💻 y café ☕ por Jeffry Hernández Gutierrez
🆕 Última versión: v2.2


**CashMind** es un módulo para Odoo diseñado para ayudarte a llevar un control claro, simple y visual de tus finanzas personales. Administra tus ingresos, gastos y cuentas con comodidad, directamente desde tu entorno Odoo favorito.

----------------------------------------------------------------------------------------------------
🚀 Novedades  y cambios en la Versión v2.2

1- ➕ Agregado en la vista del form del modelo transfer_external, campo para seleccionar external_user_id a quien se va a transferir
2- ⬆️ Modificada la vista dentro del modelo accounts a readonly (notebook Transferencias / Externas para que no permita crear un registro nuevo ni editar una transferencia externa recibida o enviada.
3- ⬆️ Modificada vista kanban y list para que muestre el nombre del usuario externo que recibe la transferencia.
4- ➖ Eliminada la opción de actualizar el saldo transferido a otros usuarios o cambiar la cuenta de destino. Tampoco es posible eliminar una transferencia hecha a un usuario externo.
5- ✔️ Solucionado el bug que hacía que no se actualizara el dashboard del usuario externo al recibir una transferencia externa.

----------------------------------------------------------------------------------------------------

🚀 Novedades y cambios en la Versión v2.1

Estas son las mejoras y nuevas funcionalidades de esta versión:

1. ⬆️ Añadido el correcto manejo para multiusuarios. Anteriormente, los usuarios podían ver y gestionar las cuentas y movimientos de otros usuarios. Aun no se habia implementado la funcionalidad de multiuser.
	1.1 Creado nuevo modelo transfer_external para manejar las transferencias a otros usuarios
	1.2 Actualizada vistas notebook dentro de la vista form del modelo Account
	1.3 Actualizados los domain de los Many2one de los distintos modelos, para que solo muestren en los dropbox las categorías del usuario actual
	
2. 🛠 Resolución de bugs y cambios menores de la versión anterior.




----------------------------------------------------------------------------------------------------
🚀 Novedades y cambios en la Versión v2.0

Estas son las mejoras y nuevas funcionalidades de esta versión:

1. 🛠 Solucionado el multi-triggering del método write() del modelo cashmind.expense, que provocaba múltiples ejecuciones innecesarias.
2. 🐞 Corrección de bugs menores detectados en la versión anterior.
3. 🗂 Nueva vista Kanban para una gestión más visual de los elementos clave del módulo.
4. 📊 Nuevo dashboard Kanban basado en el modelo cashmind.dashboard para mostrar estadísticas clave de forma clara y atractiva.

----------------------------------------------------------------------------------------------------

📦 Características Principales de la Versión v1.0

- Cuenta con tres menús principales:

	1 - Movimientos:
	  - Ingresos a cuenta
	  - Gastos desde cuenta (gasto imprevisto) o presupuesto (previamente creado)
	  - Transferencias de saldo entre cuentas
	  - Ahorrar (para transferir dinero a Metas de Ahorro, previamente creadas)
	
	2 - Planificación:
	  - Presupuestos (se crean los presupuestos, que toman dinero de una de las cuentas)
	  - Metas de ahorro (se crean las metas de ahorro, a las que se les puede transferir desde AHORRAR)

	3 - Configuración:
	  - Cuentas (se crean las cuentas)
	  - Categorías (se crean las categorías)

- Principales funcionalidades:
	1 - Cuentas: una vez creadas las cuentas (con balance 0 o con balance mayor que 0), no se puede cambiar manualmente el saldo. Esto debe hacerse a través de ingresos y saldos.
	2 - Categorías: 
		- Existen categorías de Ingresos y Gastos, cada una con posibles categorías superiores o subcategorías.
	 	- Es posible crear una única categoría especial, (AJUSTE DE SALDO) y tipo de categoría AJUSTE DE SALDO. Es utilizada para que movimientos de Ingresos y Gastos no computen 		en las estadísticas de ingresos y gastos.
	3 - Al crear un presupuesto, se define un monto inicial. Si luego se elimina o modifica, el saldo de la cuenta de donde toma el dinero es recalculado.
	4 - Al crear una meta de ahorro, se define un objetivo inicial. Al completar o sobrepasar el objetivo, se envía notificación popup.
	5 - Al ingresar dinero, se define un monto. Si luego se elimina o se modifica, el saldo de la cuenta a donde ingresó el dinero es recalculado.
	6 - Al gastar dinero, se puede tomar de un presupuesto o de una cuenta (como gasto imprevisto). Si luego se elimina o se modifica, el saldo de la cuenta a donde ingresó el dinero 		es recalculado.
	7 - Al transferir dinero, se define un monto. Si luego se elimina o se modifica, el saldo de la cuenta de donde tomó y a donde ingresó el dinero es recalculado.
	8 - Al crear un movimiento de ahorro, se define un monto. Si luego se elimina o se modifica, el saldo de la cuenta de ahorro a donde ingresó el dinero o de la cuenta de donde lo 		tomó es recalculado.

- Principales restricciones: (aplican a creación y modificaciones posteriores)
	1 - No se puede transferir entre cuentas con distintos tipos de moneda.
	2 - Las fechas de los movimientos de dinero pueden ser pasadas o presentes, pero no futuras.
	3 - Al modificar el monto de un movimiento (ingreso, gasto, etc.), si el resultado del balance de la cuenta asociada es negativo, no se efectuará la modificación.
	4 - No es posible eliminar una cuenta, presupuesto o meta de ahorro mientras haya un movimiento de dinero asociado a estos,
	5 - No es posible eliminar una categoría mientras al menos una subcategoría asociada.

----------------------------------------------------------------------------------------------------



