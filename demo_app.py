# demo_app.py
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# URL local del copilot
API_URL = "https://adosales-gpt-corporate-api-copilot-cr-736515301718.us-east1.run.app/v1/chat"

# Zona horaria para los timestamps
SANTIAGO_TZ = ZoneInfo("America/Santiago")


def _now_scl() -> datetime:
    """Hora actual en zona horaria de Santiago de Chile."""
    return datetime.now(SANTIAGO_TZ)


def _fmt(dt: datetime) -> str:
    """Formatea fecha y hora como dd-mm-YYYY HH:MM:SS."""
    return dt.strftime("%d-%m-%Y %H:%M:%S")


def _get_tokens() -> tuple[str, str, str]:
    """
    Obtiene los tokens desde Streamlit Secrets.
    Retorna (access_token, identity_token_cr, identity_token_airtalk).
    """
    access_token = st.secrets["ACCESS_TOKEN"]
    identity_token_cr = st.secrets["IDENTITY_TOKEN_CR"]
    identity_token_airtalk = st.secrets["IDENTITY_TOKEN_AIRTALK"]
    return access_token, identity_token_cr, identity_token_airtalk


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

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"Usuario: **{st.session_state.user_email}**")
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

                payload = {"message": prompt_from_button}
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

            except requests.exceptions.Timeout:
                st.error("El agente tardo demasiado. Intenta de nuevo.")
            except requests.exceptions.HTTPError as e:
                st.error(f"Error {e.response.status_code}: {e.response.text}")
            except KeyError:
                st.error("Los tokens han expirado. Contacta al administrador.")
            except Exception as e:
                st.error(f"Error inesperado: {e}")
            finally:
                st.session_state.is_loading = False

# Zona horaria para los timestamps
SANTIAGO_TZ = ZoneInfo("America/Santiago")


def _now_scl() -> datetime:
    """Hora actual en zona horaria de Santiago de Chile."""
    return datetime.now(SANTIAGO_TZ)


def _fmt(dt: datetime) -> str:
    """Formatea fecha y hora como dd-mm-YYYY HH:MM:SS."""
    return dt.strftime("%d-%m-%Y %H:%M:%S")


def _get_tokens() -> tuple[str, str, str]:
    """
    Obtiene los tokens desde Streamlit Secrets.
    Retorna (access_token, identity_token_cr, identity_token_airtalk).
    """
    access_token = st.secrets["ACCESS_TOKEN"]
    identity_token_cr = st.secrets["IDENTITY_TOKEN_CR"]
    identity_token_airtalk = st.secrets["IDENTITY_TOKEN_AIRTALK"]
    return access_token, identity_token_cr, identity_token_airtalk


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

st.title("✈️ Copilot - Corporate POC")
st.caption("Consulta datos corporativos en lenguaje natural")

# --- Estado de sesion ---
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None

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

# --- Sidebar ---
with st.sidebar:
    st.markdown(f"Usuario: **{st.session_state.user_email}**")
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

# --- Historial de mensajes ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        _render_caption(msg)

# --- Input del usuario ---
if prompt := st.chat_input("Escribe tu pregunta..."):

    asked_at = _now_scl()
    with st.chat_message("user"):
        st.markdown(prompt)
        st.caption(f"Enviado: {_fmt(asked_at)}")

    st.session_state.messages.append({
        "role": "user",
        "content": prompt,
        "asked_at": asked_at,
    })

    with st.chat_message("assistant"):
        with st.spinner("Consultando datos..."):
            try:
                access_token, identity_token_cr, identity_token_airtalk = _get_tokens()

                payload = {"message": prompt}
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

                st.markdown(answer)
                st.caption(
                    f"Respuesta: {_fmt(answered_at)} | Tiempo: {elapsed:.1f} s"
                )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer,
                    "answered_at": answered_at,
                    "elapsed": elapsed,
                })

            except requests.exceptions.Timeout:
                st.error("El agente tardo demasiado. Intenta de nuevo.")
            except requests.exceptions.HTTPError as e:
                st.error(f"Error {e.response.status_code}: {e.response.text}")
            except KeyError:
                st.error("Los tokens han expirado. Contacta al administrador.")
            except Exception as e:
                st.error(f"Error inesperado: {e}")
