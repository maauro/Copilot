# demo_app.py
import subprocess
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# URL local del copilot
API_URL = "https://adosales-gpt-corporate-api-copilot-cr-736515301718.us-east1.run.app/v1/chat"

# Zona horaria para los timestamps
SANTIAGO_TZ = ZoneInfo("America/Santiago")

# --- Configuración de tokens gcloud ---
_GCLOUD_ACCOUNT = "mauricio.caneo@latam.com"
_IMPERSONATE_SA = "adosales-gpt-corporate-sa@adosales-data-dev.iam.gserviceaccount.com"
_AUDIENCE_CR = "https://adosales-gpt-corporate-api-copilot-cr-736515301718.us-east1.run.app"
_AUDIENCE_AIRTALK = "https://airtalk-mcp-cr-25512535102.us-central1.run.app"
_TOKEN_TTL = 55 * 60  # 55 minutos en segundos


def _now_scl() -> datetime:
    """Hora actual en zona horaria de Santiago de Chile."""
    return datetime.now(SANTIAGO_TZ)


def _fmt(dt: datetime) -> str:
    """Formatea fecha y hora como dd-mm-YYYY HH:MM:SS."""
    return dt.strftime("%d-%m-%Y %H:%M:%S")


_GCLOUD_BIN = "/opt/homebrew/bin/gcloud"


def _gcloud_run(args: list[str]) -> str:
    """Ejecuta un comando gcloud y retorna stdout limpio."""
    result = subprocess.run(
        [_GCLOUD_BIN] + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _generate_tokens() -> dict:
    """Llama a gcloud para generar los tres tokens. Siempre usa _GCLOUD_ACCOUNT."""
    access_token = _gcloud_run(["auth", "print-access-token", _GCLOUD_ACCOUNT])
    identity_token_cr = _gcloud_run([
        "auth", "print-identity-token",
        f"--impersonate-service-account={_IMPERSONATE_SA}",
        f"--audiences={_AUDIENCE_CR}",
        "--include-email",
    ])
    identity_token_airtalk = _gcloud_run([
        "auth", "print-identity-token",
        f"--impersonate-service-account={_IMPERSONATE_SA}",
        f"--audiences={_AUDIENCE_AIRTALK}",
        "--include-email",
    ])
    return {
        "access_token": access_token,
        "identity_token_cr": identity_token_cr,
        "identity_token_airtalk": identity_token_airtalk,
        "generated_at": time.monotonic(),
        "expires_at": _now_scl() + timedelta(minutes=55),
    }


def _get_tokens() -> tuple[str, str, str]:
    """
    Retorna (access_token, identity_token_cr, identity_token_airtalk).
    Genera tokens con gcloud si no existen o expiraron (TTL 55 min).
    """
    tokens = st.session_state.get("_tokens")
    expired = tokens is None or (time.monotonic() - tokens["generated_at"]) >= _TOKEN_TTL

    if expired:
        tokens = _generate_tokens()
        st.session_state._tokens = tokens

    return tokens["access_token"], tokens["identity_token_cr"], tokens["identity_token_airtalk"]


# Implementación original — lee tokens desde secrets.toml (mantenida como referencia)
# def _get_tokens_from_secrets() -> tuple[str, str, str]:
#     access_token = st.secrets["ACCESS_TOKEN"]
#     identity_token_cr = st.secrets["IDENTITY_TOKEN_CR"]
#     identity_token_airtalk = st.secrets["IDENTITY_TOKEN_AIRTALK"]
#     return access_token, identity_token_cr, identity_token_airtalk


def _render_caption(msg: dict) -> None:
    """Muestra al pie del mensaje la hora y tiempo de respuesta si aplica."""
    if msg["role"] == "user" and msg.get("asked_at"):
        st.caption(f"Enviado: {_fmt(msg['asked_at'])}")
    elif msg["role"] == "assistant" and msg.get("answered_at"):
        st.caption(
            f"Respuesta: {_fmt(msg['answered_at'])} | "
            f"Tiempo: {msg['elapsed']:.1f} s"
        )


# --- Configuracion de pagina ---
st.set_page_config(
    page_title="ADO Sales Copilot",
    page_icon="✈️",
    layout="centered",
)

st.title("✈️ Copilot - Corporate")
st.caption("Consulta datos corporativos en lenguaje natural")

# --- Estado de sesion ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "is_loading" not in st.session_state:
    st.session_state.is_loading = False
if "_tokens" not in st.session_state:
    st.session_state._tokens = None

# --- Identificacion del usuario ---
if not st.session_state.user_email:
    st.info("Ingresa tu correo LATAM para comenzar.")
    email_input = st.text_input("Correo electronico", placeholder="nombre@latam.com")
    if st.button("Ingresar", use_container_width=True):
        if email_input.endswith("@latam.com"):
            st.session_state.user_email = email_input
            st.rerun()
        else:
            st.error("Solo se permiten correos @latam.com")
    st.stop()

# --- Generación eager de tokens al iniciar sesión ---
if st.session_state._tokens is None:
    with st.spinner("Generando tokens de autenticación..."):
        try:
            st.session_state._tokens = _generate_tokens()
        except FileNotFoundError:
            st.error("gcloud no está instalado o no está en el PATH.")
            st.stop()
        except subprocess.CalledProcessError as e:
            st.error(f"Error al generar tokens con gcloud:\n\n```\n{e.stderr}\n```")
            st.stop()

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"Usuario: **{st.session_state.user_email}**")
    st.divider()

    # Estado de tokens
    tokens = st.session_state.get("_tokens")
    if tokens:
        elapsed_sec = time.monotonic() - tokens["generated_at"]
        remaining_min = max(0, (_TOKEN_TTL - elapsed_sec) / 60)
        st.caption(f"Tokens expiran: {_fmt(tokens['expires_at'])}")
        st.caption(f"Tiempo restante: {remaining_min:.0f} min")
        if st.button("Refrescar tokens", use_container_width=True):
            with st.spinner("Regenerando tokens..."):
                try:
                    st.session_state._tokens = _generate_tokens()
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error(f"Error al refrescar tokens:\n\n```\n{e.stderr}\n```")

    st.divider()
    if st.button("Nueva conversacion", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_id = None
        st.rerun()
    if st.button("Cambiar usuario", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_id = None
        st.session_state.user_email = None
        st.rerun()

# --- Botones de inicio (solo si la conversación está vacía) ---
_STARTER_QUESTIONS = [
    ("💬", "¿Qué preguntas te puedo realizar?"),
    ("📊", "¿Qué cuentas están al 85% o más de progreso hacia el siguiente tier?"),
    ("🏆", "Dame mis top 10 cuentas para contactar hoy"),
]

# Leemos pending_prompt antes de renderizar los botones:
# si ya hay una pregunta en camino, los botones arrancan deshabilitados
# en el mismo run que ejecuta el API call.
_pending_prompt = st.session_state.pending_prompt

if not st.session_state.messages:
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Sugerencias para comenzar")
    _btn_disabled = st.session_state.is_loading or bool(_pending_prompt)
    cols = st.columns(len(_STARTER_QUESTIONS))
    for col, (icon, question) in zip(cols, _STARTER_QUESTIONS):
        with col:
            if st.button(
                f"{icon} {question}",
                key=f"starter_{question}",
                use_container_width=True,
                disabled=_btn_disabled,
            ):
                st.session_state.pending_prompt = question
                st.session_state.is_loading = True
                st.rerun()

# --- Captura del prompt pendiente (desde botón) y limpieza ---
prompt_from_button = _pending_prompt
st.session_state.pending_prompt = None

# --- Historial de mensajes ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        _render_caption(msg)

# --- Input del usuario ---
# Fase 1: detectar texto escrito → guardar en pending y deshabilitar UI antes del API call
_typed_input = st.chat_input("Escribe tu pregunta...", disabled=st.session_state.is_loading)
if _typed_input:
    st.session_state.pending_prompt = _typed_input
    st.session_state.is_loading = True
    st.rerun()

# Fase 2: ejecutar API call (prompt viene de botón o de la fase 1)
if prompt_from_button:
    asked_at = _now_scl()
    with st.chat_message("user"):
        st.markdown(prompt_from_button)
        st.caption(f"Enviado: {_fmt(asked_at)}")

    st.session_state.messages.append({
        "role": "user",
        "content": prompt_from_button,
        "asked_at": asked_at,
    })

    with st.chat_message("assistant"):
        with st.spinner("Consultando datos..."):
            try:
                access_token, identity_token_cr, identity_token_airtalk = _get_tokens()

                payload = {
                    "message": prompt_from_button,
                    # TEMPORAL: envía el correo ingresado en la UI para que la API lo use en Firestore
                    "demo_email": st.session_state.user_email,
                }
                if st.session_state.conversation_id:
                    payload["conversation_id"] = st.session_state.conversation_id

                response = requests.post(
                    API_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {identity_token_cr}",
                        "X-Access-Token": f"Bearer {access_token}",
                        "X-Identity-Token": f"Bearer {identity_token_airtalk}",
                        "Content-Type": "application/json",
                    },
                    timeout=300,
                )
                response.raise_for_status()
                data = response.json()

                answered_at = _now_scl()
                elapsed = (answered_at - asked_at).total_seconds()

                answer = data["message"]
                st.session_state.conversation_id = data["conversation_id"]

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "answered_at": answered_at,
                    "elapsed": elapsed,
                })
                st.rerun()

            except FileNotFoundError:
                st.error("gcloud no está instalado o no está en el PATH.")
            except subprocess.CalledProcessError as e:
                st.error(f"Error al regenerar tokens:\n\n```\n{e.stderr}\n```")
            except requests.exceptions.Timeout:
                st.error("El agente tardo demasiado. Intenta de nuevo.")
            except requests.exceptions.HTTPError as e:
                st.error(f"Error {e.response.status_code}: {e.response.text}")
            except Exception as e:
                st.error(f"Error inesperado: {e}")
            finally:
                st.session_state.is_loading = False
