"""
pages/9_Administracion.py
Administración del sistema — usuarios, estadísticas, actividad.

Secciones:
    Tab 1 — Usuarios: listado, edición de roles, activar/desactivar
    Tab 2 — Nuevo usuario: formulario de registro
    Tab 3 — Sistema: estadísticas y actividad reciente

Acceso mínimo: administrador.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from services.admin_service import (
    ROLES,
    get_usuarios,
    get_usuario,
    actualizar_usuario,
    actualizar_rol,
    toggle_usuario,
    crear_usuario,
    eliminar_usuario,
    resetear_password,
    get_estadisticas_sistema,
    get_actividad_reciente,
)


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Gestión de usuarios
# ─────────────────────────────────────────────────────────────────────────────

def _render_usuarios() -> None:
    st.markdown("#### Usuarios registrados")

    usuarios = get_usuarios()
    if not usuarios:
        st.info("No hay usuarios registrados.")
        return

    # ── Tabla resumen ────────────────────────────────────────────────────
    filas = []
    for u in usuarios:
        filas.append({
            "Nombre":       f"{u.get('nombre', '')} {u.get('apellido', '')}".strip() or "—",
            "Email":        u.get("email", "—"),
            "Rol":          (u.get("rol") or "visitante").capitalize(),
            "Institución":  u.get("institucion") or "—",
            "Activo":       "Si" if u.get("activo") else "No",
            "Registro":     (u.get("created_at") or "")[:10],
        })

    st.dataframe(
        pd.DataFrame(filas),
        use_container_width=True,
        hide_index=True,
    )

    # ── Selector para editar ─────────────────────────────────────────────
    st.divider()
    opciones = {
        f"{u.get('email', '')} — {u.get('nombre', '')} {u.get('apellido', '')}": u["id"]
        for u in usuarios
    }
    sel = st.selectbox("Seleccionar usuario", list(opciones.keys()), key="sel_usuario")
    usuario_id = opciones[sel]

    _render_editar_usuario(usuario_id)


def _render_editar_usuario(usuario_id: str) -> None:
    """Formulario de edición de usuario."""
    usuario = get_usuario(usuario_id)
    if not usuario:
        st.error("Usuario no encontrado.")
        return

    rol_actual = usuario.get("rol", "visitante")
    rol_idx = ROLES.index(rol_actual) if rol_actual in ROLES else 2

    with st.form("form_editar_usuario", clear_on_submit=False):
        st.markdown(f"##### Editando: {usuario.get('email', '')}")

        uc1, uc2 = st.columns(2)
        with uc1:
            nombre = st.text_input("Nombre", value=usuario.get("nombre") or "")
        with uc2:
            apellido = st.text_input("Apellido", value=usuario.get("apellido") or "")

        uc3, uc4 = st.columns(2)
        with uc3:
            nuevo_rol = st.selectbox(
                "Rol",
                [r.capitalize() for r in ROLES],
                index=rol_idx,
                key="edit_rol",
            )
        with uc4:
            institucion = st.text_input(
                "Institución",
                value=usuario.get("institucion") or "",
            )

        submitted = st.form_submit_button("Guardar cambios", type="primary")

    # ── Activar/desactivar ───────────────────────────────────────────────
    bc1, bc2 = st.columns(2)
    with bc1:
        if usuario.get("activo"):
            if st.button("Desactivar usuario", key="btn_desactivar_usr"):
                toggle_usuario(usuario_id, False)
                st.warning("Usuario desactivado.")
                st.rerun()
        else:
            if st.button("Activar usuario", key="btn_activar_usr", type="primary"):
                toggle_usuario(usuario_id, True)
                st.success("Usuario activado.")
                st.rerun()

    # ── Resetear contraseña ───────────────────────────────────────────────
    with bc2:
        with st.expander("🔑 Resetear contraseña", expanded=False):
            nueva_pass = st.text_input(
                "Nueva contraseña",
                type="password",
                placeholder="Mínimo 8 caracteres",
                key="reset_pass",
            )
            if st.button("Cambiar contraseña", key="btn_reset_pass"):
                if not nueva_pass or len(nueva_pass) < 8:
                    st.error("La contraseña debe tener al menos 8 caracteres.")
                else:
                    try:
                        resetear_password(usuario_id, nueva_pass)
                        st.success("Contraseña actualizada.")
                    except Exception as exc:
                        st.error(f"Error: {exc}")

    # ── Eliminar usuario ──────────────────────────────────────────────────
    with st.expander("🗑️ Eliminar usuario", expanded=False):
        st.warning("Esta acción eliminará al usuario de forma permanente.")
        confirmar_email = st.text_input(
            f"Escribe el email **{usuario.get('email', '')}** para confirmar:",
            key="confirmar_eliminar_usr",
        )
        if st.button("Eliminar permanentemente", key="btn_eliminar_usr", type="primary"):
            if confirmar_email.strip().lower() != (usuario.get("email") or "").lower():
                st.error("El email ingresado no coincide.")
            else:
                try:
                    eliminar_usuario(usuario_id)
                    st.success("Usuario eliminado.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    if submitted:
        try:
            # Actualizar perfil
            actualizar_usuario(usuario_id, {
                "nombre":      nombre,
                "apellido":    apellido,
                "institucion": institucion,
            })
            # Actualizar rol si cambió
            rol_lower = nuevo_rol.lower()
            if rol_lower != rol_actual:
                actualizar_rol(usuario_id, rol_lower)
            st.success("Usuario actualizado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"Error al actualizar: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Nuevo usuario
# ─────────────────────────────────────────────────────────────────────────────

def _render_nuevo_usuario() -> None:
    st.markdown("#### Registrar nuevo usuario")
    st.caption("El usuario recibirá acceso inmediato con las credenciales proporcionadas.")

    with st.form("form_nuevo_usuario", clear_on_submit=True):
        nc1, nc2 = st.columns(2)
        with nc1:
            email = st.text_input("Correo electrónico *", placeholder="usuario@autodema.gob.pe")
        with nc2:
            password = st.text_input("Contraseña *", type="password", placeholder="Mínimo 8 caracteres")

        nc3, nc4 = st.columns(2)
        with nc3:
            nombre = st.text_input("Nombre *", placeholder="Juan")
        with nc4:
            apellido = st.text_input("Apellido *", placeholder="Pérez")

        nc5, nc6 = st.columns(2)
        with nc5:
            rol = st.selectbox("Rol", [r.capitalize() for r in ROLES], index=2)
        with nc6:
            institucion = st.text_input("Institución", placeholder="AUTODEMA")

        submitted = st.form_submit_button(
            "Crear usuario", type="primary", use_container_width=True,
        )

    if submitted:
        errores = []
        if not email.strip():
            errores.append("El correo es obligatorio.")
        if not password or len(password) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if not nombre.strip():
            errores.append("El nombre es obligatorio.")
        if not apellido.strip():
            errores.append("El apellido es obligatorio.")
        if errores:
            for e in errores:
                st.error(e)
            return

        with st.spinner("Creando usuario..."):
            try:
                creado = crear_usuario(
                    email=email.strip(),
                    password=password,
                    nombre=nombre.strip(),
                    apellido=apellido.strip(),
                    rol=rol.lower(),
                    institucion=institucion.strip(),
                )
                st.success(
                    f"Usuario **{creado.get('email', email)}** creado "
                    f"con rol **{rol}**."
                )
                st.balloons()
            except Exception as exc:
                st.error(f"Error al crear usuario: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Sistema
# ─────────────────────────────────────────────────────────────────────────────

def _render_sistema() -> None:
    st.markdown("#### Estado del sistema")

    # ── Estadísticas ─────────────────────────────────────────────────────
    with st.spinner("Cargando estadísticas..."):
        try:
            stats = get_estadisticas_sistema()
        except Exception as exc:
            st.error(f"Error: {exc}")
            return

    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Usuarios", stats["usuarios"])
    sc2.metric("Campañas", stats["campanas"])
    sc3.metric("Muestras totales", stats["muestras"])

    sc4, sc5, sc6 = st.columns(3)
    sc4.metric("Resultados de lab.", stats["resultados"])
    sc5.metric("Parámetros activos", stats["parametros"])
    sc6.metric("Puntos activos", stats["puntos"])

    # ── Actividad reciente ───────────────────────────────────────────────
    st.divider()
    st.markdown("#### Actividad reciente (últimos 7 días)")

    try:
        actividad = get_actividad_reciente(dias=7)
    except Exception as exc:
        st.error(f"Error: {exc}")
        return

    # Campañas activas
    campanas_activas = actividad["campanas_activas"]
    if campanas_activas:
        with st.expander(f"Campañas activas ({len(campanas_activas)})", expanded=True):
            filas_c = []
            for c in campanas_activas:
                filas_c.append({
                    "Código":  c.get("codigo", ""),
                    "Nombre":  c.get("nombre", ""),
                    "Estado":  c.get("estado", "").replace("_", " ").capitalize(),
                    "Inicio":  (c.get("fecha_inicio") or "")[:10],
                    "Fin":     (c.get("fecha_fin") or "")[:10],
                })
            st.dataframe(
                pd.DataFrame(filas_c),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.caption("No hay campañas activas.")

    # Últimas muestras
    ultimas = actividad["ultimas_muestras"]
    if ultimas:
        with st.expander(f"Últimas muestras ({len(ultimas)})", expanded=False):
            filas_m = []
            for m in ultimas:
                pt = m.get("puntos_muestreo") or {}
                ca = m.get("campanas") or {}
                filas_m.append({
                    "Muestra":  m.get("codigo", ""),
                    "Punto":    f"{pt.get('codigo', '')} — {pt.get('nombre', '')}",
                    "Campaña":  ca.get("codigo", ""),
                    "Fecha":    (m.get("fecha_muestreo") or "")[:10],
                    "Estado":   m.get("estado", ""),
                })
            st.dataframe(
                pd.DataFrame(filas_m),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.caption("No hay muestras recientes.")

    # ── Info del entorno ─────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Configuración")
    from config.settings import APP_ENV, SUPABASE_URL
    st.caption(f"Entorno: **{APP_ENV}** | Supabase: {SUPABASE_URL[:40]}...")


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    st.title("Administración")
    st.caption("Gestión de usuarios y estado del sistema — AUTODEMA / LVCA")

    tab_usuarios, tab_nuevo, tab_sistema = st.tabs([
        "Usuarios",
        "Nuevo usuario",
        "Sistema",
    ])

    with tab_usuarios:
        _render_usuarios()

    with tab_nuevo:
        _render_nuevo_usuario()

    with tab_sistema:
        _render_sistema()


main()
