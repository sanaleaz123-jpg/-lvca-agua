"""
database/client.py
Provee dos clientes Supabase:
  - get_client()         → anon key  (usado por la app Streamlit, respeta RLS)
  - get_admin_client()   → service key (solo seeds y operaciones admin)

Ambos son singletons cacheados por Streamlit (sobreviven reruns).
Incluye reintentos automáticos ante desconexiones del servidor.
"""

from __future__ import annotations

import httpx
from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions
from config.settings import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY

try:
    from streamlit import cache_resource as _cache
except ImportError:
    # Fuera de Streamlit (scripts, seeds, tests)
    def _cache(func):  # type: ignore[misc]
        return func


def _make_options() -> SyncClientOptions:
    """Opciones con timeout extendido y transporte con reintentos."""
    transport = httpx.HTTPTransport(retries=3)
    client = httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(30.0, connect=10.0),
    )
    return SyncClientOptions(
        postgrest_client_timeout=httpx.Timeout(30.0, connect=10.0),
        httpx_client=client,
    )


@_cache
def get_client() -> Client:
    """Cliente con anon key. Respeta Row Level Security."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY, _make_options())


@_cache
def get_admin_client() -> Client:
    """Cliente con service_role key. Omite RLS — solo para seeds y admin."""
    if not SUPABASE_SERVICE_KEY:
        raise RuntimeError(
            "SUPABASE_SERVICE_KEY no está configurada. "
            "Necesaria para operaciones de administración."
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY, _make_options())


def get_user_client(access_token: str, refresh_token: str = "") -> Client:
    """
    Cliente Supabase autenticado como el usuario, usando su JWT. Las consultas
    se ejecutan bajo la identidad real del usuario, de modo que RLS aplica
    (auth.uid() y auth.role()='authenticated' funcionan, y app_rol_nivel()
    devuelve el nivel correcto — ver migración 019).

    A diferencia de get_client()/get_admin_client(), NO se cachea: cada usuario
    necesita su propio token y un singleton compartido mezclaría identidades
    entre sesiones concurrentes. Crear el cliente es barato frente a ese riesgo.

    Uso previsto (fase de cutover de RLS):
        sesion = st.session_state["sesion"]
        db = get_user_client(sesion.access_token, sesion.refresh_token)
    """
    if not access_token:
        raise ValueError("get_user_client requiere un access_token de usuario.")
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY, _make_options())
    # Inyecta el JWT en PostgREST: hace que las consultas a tablas respeten RLS
    # con la identidad del usuario.
    client.postgrest.auth(access_token)
    # Best-effort: registrar la sesión en el sub-cliente de Auth (no crítico
    # para el acceso a tablas; se ignora si la versión del SDK difiere).
    try:
        client.auth.set_session(access_token, refresh_token or access_token)
    except Exception:
        pass
    return client


def reset_clients() -> None:
    """Limpia caché de clientes (útil en tests)."""
    get_client.clear()
    get_admin_client.clear()
