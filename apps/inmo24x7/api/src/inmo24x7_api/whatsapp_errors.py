"""Meta errors in plain Spanish for the inmobiliaria (what happened and what to do) and a
short technical line for admins. Core classifies Meta's code into a stable internal code
(followup_core.messaging.domain.meta_errors); this table is the product's copy for each one.

The connection status is data shown by the panel (S4, the error banner) and the backoffice
(S9), so the copy lives here once instead of in both frontends.
"""

from dataclasses import dataclass

from followup_core.messaging.domain.meta_errors import classify


@dataclass(frozen=True, slots=True)
class ErrorCopy:
    title: str
    message: str
    action: str
    admin_detail: str


GENERIC = ErrorCopy(
    "WhatsApp tuvo un problema",
    "Meta rechazó una operación y no nos dio más detalles.",
    "Probá volver a conectar. Si sigue pasando, escribinos.",
    "Código de Meta sin traducción: revisá el detalle técnico.",
)

COPY: dict[str, ErrorCopy] = {
    "token_revoked": ErrorCopy(
        "El permiso de Meta venció",
        "Tu agente no puede responder en WhatsApp porque el acceso de la app se perdió.",
        "Tocá “Volver a conectar” y entrá con tu cuenta de Facebook.",
        "El cliente quitó el acceso de la app en su cuenta de Meta.",
    ),
    "permission_missing": ErrorCopy(
        "Falta un permiso en Meta",
        "Al conectar no se aceptaron todos los permisos que necesita el agente.",
        "Volvé a conectar y aceptá todos los permisos que pide Meta.",
        "Permiso faltante o revocado (códigos 3, 10, 200-299).",
    ),
    "app_removed": ErrorCopy(
        "El permiso de Meta venció",
        "Se quitó el acceso de inmo24x7 a tu cuenta de WhatsApp Business.",
        "Tocá “Volver a conectar” para darle acceso de nuevo.",
        "account_update: PARTNER_APP_UNINSTALLED o PARTNER_REMOVED.",
    ),
    "account_deleted": ErrorCopy(
        "La cuenta de WhatsApp ya no existe",
        "Meta nos avisó que la cuenta de WhatsApp Business se eliminó.",
        "Conectá otra cuenta o escribinos si no fue intencional.",
        "account_update: ACCOUNT_DELETED.",
    ),
    "number_offboarded": ErrorCopy(
        "El número se desconectó",
        "El número se registró en otro teléfono o en otra app y dejó de recibir mensajes acá.",
        "Volvé a conectar el número desde acá.",
        "account_update: ACCOUNT_OFFBOARDED.",
    ),
    "account_disabled": ErrorCopy(
        "Meta deshabilitó tu cuenta de WhatsApp",
        "Meta bloqueó la cuenta por sus políticas y no se pueden enviar mensajes.",
        "Revisá el aviso en el WhatsApp Manager y pedí la revisión a Meta.",
        "account_update: DISABLED_UPDATE (DISABLE).",
    ),
    "account_restricted": ErrorCopy(
        "Meta restringió tu cuenta",
        "Meta limitó la cuenta por un tema de políticas o de datos de la empresa.",
        "Revisá los avisos en el WhatsApp Manager de Meta.",
        "Cuenta restringida (131031 / 368).",
    ),
    "sending_restricted": ErrorCopy(
        "Meta limitó los envíos",
        "Muchas personas bloquearon o reportaron mensajes y Meta frenó los envíos un tiempo.",
        "Esperá unas horas. Si sigue, revisá la calidad del número en el WhatsApp Manager.",
        "Envíos limitados por spam (131048).",
    ),
    "country_restricted": ErrorCopy(
        "No se puede escribir a ese país",
        "Meta no permite que esta cuenta escriba a números de algunos países.",
        "Revisá las restricciones en el WhatsApp Manager.",
        "Restricción por país (130497).",
    ),
    "payment_method": ErrorCopy(
        "Falta un medio de pago en Meta",
        "Meta necesita una tarjeta cargada para enviar algunos mensajes.",
        "Cargá un medio de pago en el WhatsApp Manager.",
        "Problema de facturación de la WABA (131042).",
    ),
    "display_name_missing": ErrorCopy(
        "Falta aprobar el nombre visible",
        "Meta todavía no aprobó el nombre con el que aparece tu número.",
        "Revisá el estado del nombre en el WhatsApp Manager.",
        "Número sin nombre visible aprobado (131037).",
    ),
    "number_maintenance": ErrorCopy(
        "El número está en mantenimiento",
        "Meta está haciendo cambios en el número y no se puede usar por un rato.",
        "Probá de nuevo en unos minutos.",
        "Número en modo mantenimiento (2494100).",
    ),
    "recipient_unavailable": ErrorCopy(
        "El mensaje no llegó",
        "Esa persona no usa WhatsApp o tiene una versión que no recibe estos mensajes.",
        "Contactala por otro medio.",
        "Destinatario no disponible (131026).",
    ),
    "recipient_is_sender": ErrorCopy(
        "Te escribiste a vos mismo",
        "El mensaje iba al mismo número que lo envía.",
        "Probá desde otro teléfono.",
        "Emisor y destinatario iguales (131021).",
    ),
    "outside_service_window": ErrorCopy(
        "Pasaron más de 24 horas",
        "WhatsApp solo deja responder libremente dentro de las 24 horas del último mensaje.",
        "Usá una plantilla aprobada o esperá a que la persona vuelva a escribir.",
        "Fuera de la ventana de 24 h (131047).",
    ),
    "unsupported_message": ErrorCopy(
        "Tipo de mensaje no soportado",
        "WhatsApp no acepta ese tipo de mensaje.",
        "Escribinos si vuelve a pasar.",
        "Tipo de mensaje no soportado (131051).",
    ),
    "template_parameters": ErrorCopy(
        "La plantilla no coincide",
        "Los datos que mandamos no coinciden con la plantilla aprobada en Meta.",
        "Revisá que la plantilla tenga 3 variables, como indica la guía.",
        "Parámetros de plantilla inválidos (132000 / 132012).",
    ),
    "template_not_found": ErrorCopy(
        "No encontramos la plantilla",
        "La plantilla no existe en ese idioma o todavía no está aprobada.",
        "Revisá el nombre y el idioma en el WhatsApp Manager.",
        "Plantilla inexistente o no aprobada (132001).",
    ),
    "template_too_long": ErrorCopy(
        "La plantilla quedó muy larga",
        "El texto con los datos completos supera el largo que permite WhatsApp.",
        "Acortá el texto de la plantilla.",
        "Texto traducido demasiado largo (132005).",
    ),
    "template_policy": ErrorCopy(
        "Meta rechazó la plantilla",
        "El contenido de la plantilla no cumple las políticas de WhatsApp.",
        "Editá la plantilla y volvé a enviarla a revisión.",
        "Plantilla viola políticas (132007).",
    ),
    "template_paused": ErrorCopy(
        "Meta pausó la plantilla",
        "La plantilla recibió muchas quejas y Meta la frenó.",
        "Revisá su calidad en el WhatsApp Manager o creá otra.",
        "Plantilla pausada o deshabilitada (132015 / 132016).",
    ),
    "number_not_registered": ErrorCopy(
        "El número no quedó registrado",
        "Meta no terminó de activar el número para usarlo con el agente.",
        "Tocá “Reintentar configuración” o volvé a conectar.",
        "Número no registrado (133010 / 131045).",
    ),
    "previous_deregistration_failed": ErrorCopy(
        "El número quedó a medio desconectar",
        "Un intento anterior de sacar el número de otra cuenta no terminó bien.",
        "Esperá unos minutos y volvé a intentar.",
        "Falló una baja anterior (133000).",
    ),
    "pin_mismatch": ErrorCopy(
        "El número tiene otro PIN",
        "El número ya tiene una verificación en dos pasos con un PIN que no es el nuestro.",
        "Desactivá la verificación en dos pasos en el WhatsApp Manager y volvé a intentar.",
        "PIN de verificación en dos pasos incorrecto (133005 / 133008 / 133009).",
    ),
    "number_not_verified": ErrorCopy(
        "Falta verificar el número",
        "Meta necesita confirmar el número con el código por SMS o llamada.",
        "Volvé a conectar y completá la verificación del número.",
        "Número sin verificar (133006).",
    ),
    "registration_limit": ErrorCopy(
        "Demasiados intentos con este número",
        "Meta frenó los intentos de registrar el número por un rato.",
        "Esperá unos minutos y tocá “Reintentar configuración”.",
        "Límite de registros o número recién borrado (133015 / 133016).",
    ),
    "number_in_other_account": ErrorCopy(
        "Ese número ya está en otra cuenta",
        "Ese número ya está registrado en otra cuenta. Eliminalo de la app de WhatsApp o "
        "elegí otro número, y volvé a intentar.",
        "Eliminá el número de la otra cuenta o elegí otro.",
        "El número ya existe en otra WABA (2388012).",
    ),
    "rate_limited": ErrorCopy(
        "Meta está limitando los envíos",
        "Se mandaron muchos mensajes seguidos y Meta pidió esperar.",
        "No hace falta hacer nada: reintentamos solos.",
        "Límite de velocidad (4 / 80007 / 130429 / 131056).",
    ),
    "meta_unavailable": ErrorCopy(
        "WhatsApp no responde",
        "El servicio de Meta está con problemas en este momento.",
        "No hace falta hacer nada: reintentamos solos.",
        "Servicio no disponible (131016 / 133004).",
    ),
    "meta_unknown": GENERIC,
    "bad_request": ErrorCopy(
        "Algo falló de nuestro lado",
        "Mandamos un pedido que Meta no aceptó.",
        "Escribinos y lo revisamos.",
        "Parámetro faltante o inválido (100 / 131008 / 131009 / 135000): bug nuestro.",
    ),
    "network_error": ErrorCopy(
        "No pudimos hablar con Meta",
        "Hubo un problema de red al conectarnos con WhatsApp.",
        "Probá de nuevo en unos minutos.",
        "Error de red hacia graph.facebook.com.",
    ),
}


@dataclass(frozen=True, slots=True)
class TranslatedError:
    code: str  # stable internal code ("unknown" when Meta's code is not mapped)
    meta_code: str
    title: str
    message: str
    action: str
    admin_detail: str


def translate(meta_code: str | None) -> TranslatedError:
    error = classify(meta_code)
    copy = COPY.get(error.code, GENERIC)
    return TranslatedError(
        code=error.code,
        meta_code=error.meta_code,
        title=copy.title,
        message=copy.message,
        action=copy.action,
        admin_detail=copy.admin_detail,
    )
