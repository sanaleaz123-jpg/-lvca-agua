"""
pages/11_Catalogo_Fitoplancton.py
Gestión del catálogo de taxonomía de fitoplancton (tabla taxonomia_fitoplancton).

Permite listar las especies y dar de alta especies/géneros nuevos verificando su
clasificación (División / Clase / Orden / Familia) contra AlgaeBase (si hay clave
configurada) o GBIF como respaldo libre, antes de guardar.

Acceso mínimo: administrador.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header, section_header, top_nav
from services.taxonomia_fitoplancton_service import (
    ORDEN_FILOS,
    actualizar_especie,
    crear_especie,
    desactivar_especie,
    existe_especie,
    get_especies_planas,
    verificar_clasificacion,
)

_UNIDADES = ["celula", "colonia", "filamento"]


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Listado del catálogo
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado() -> None:
    section_header("Catálogo de especies", "list")
    filas = get_especies_planas(incluir_inactivas=True)
    if not filas:
        st.info(
            "El catálogo está vacío. Aplica la migración 023 y corre el seed "
            "`python -m database.seeds.seed_taxonomia_fitoplancton`, o agrega "
            "especies en la pestaña *Nueva especie*.",
            icon=":material/info:",
        )
        return

    df = pd.DataFrame(filas)

    divisiones = ["(todas)"] + sorted(df["division"].dropna().unique().tolist())
    c1, c2 = st.columns([1, 2])
    filtro_div = c1.selectbox("Filtrar por división", divisiones, key="cat_filtro_div")
    busca = c2.text_input("Buscar especie", key="cat_busca", placeholder="Ej. Navicula")

    vista = df.copy()
    if filtro_div != "(todas)":
        vista = vista[vista["division"] == filtro_div]
    if busca:
        vista = vista[vista["especie"].str.contains(busca, case=False, na=False)]

    columnas = [
        "division", "clase", "orden", "familia", "especie", "unidad",
        "celulas_por_unidad", "volumen_celula_um3", "fuente_verificacion", "activo",
    ]
    columnas = [c for c in columnas if c in vista.columns]
    st.dataframe(
        vista[columnas].rename(columns={
            "division": "División", "clase": "Clase", "orden": "Orden",
            "familia": "Familia", "especie": "Especie", "unidad": "Unidad",
            "celulas_por_unidad": "Cél/unidad", "volumen_celula_um3": "Vol. célula (µm³)",
            "fuente_verificacion": "Verificación", "activo": "Activo",
        }),
        use_container_width=True, hide_index=True,
    )
    st.caption(f"{len(vista)} de {len(df)} especies. Total activas: {int(df['activo'].sum())}.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Nueva especie (con verificación AlgaeBase / GBIF)
# ─────────────────────────────────────────────────────────────────────────────

def _render_nueva() -> None:
    section_header("Nueva especie", "add_circle")
    st.caption(
        "Verifica la clasificación contra AlgaeBase/GBIF antes de guardar. "
        "La división (filo) la decides tú; Clase/Orden/Familia se autocompletan "
        "y puedes corregirlas."
    )

    c1, c2 = st.columns([2, 1])
    nombre = c1.text_input(
        "Nombre de la especie *",
        key="cat_new_nombre",
        placeholder="Ej. Cyclotella sp.",
        help="Nombre tal como aparecerá en el formulario de conteo y el reporte.",
    )
    division = c2.selectbox(
        "División (filo) *", ORDEN_FILOS, key="cat_new_division",
    )

    if st.button("Verificar en AlgaeBase / GBIF", icon=":material/travel_explore:",
                 key="cat_btn_verif", disabled=not nombre.strip()):
        with st.spinner("Consultando clasificación taxonómica…"):
            res = verificar_clasificacion(nombre.strip())
        st.session_state["cat_verif"] = res
        if not res:
            st.warning(
                "No se pudo resolver automáticamente (nombre no encontrado o sin "
                "género). Completa Clase/Orden/Familia manualmente.",
                icon=":material/help:",
            )
        else:
            fuente = res.get("fuente", "?")
            st.success(
                f"Coincidencia ({fuente}): {res.get('match') or nombre} — "
                f"Clase {res.get('clase') or '—'} · Orden {res.get('orden') or '—'} "
                f"· Familia {res.get('familia') or '—'}.",
                icon=":material/verified:",
            )

    verif = st.session_state.get("cat_verif") or {}

    with st.form("cat_form_nueva", clear_on_submit=False):
        st.markdown("**Clasificación** (editable)")
        f1, f2, f3 = st.columns(3)
        clase = f1.text_input("Clase", value=verif.get("clase") or "", key="cat_f_clase")
        orden = f2.text_input("Orden", value=verif.get("orden") or "", key="cat_f_orden")
        familia = f3.text_input("Familia", value=verif.get("familia") or "", key="cat_f_familia")

        st.markdown("**Parámetros de conteo**")
        g1, g2, g3 = st.columns(3)
        unidad = g1.selectbox("Unidad de conteo", _UNIDADES, key="cat_f_unidad")
        celulas_por_unidad = g2.number_input(
            "Células por unidad", min_value=1, step=1, value=1, key="cat_f_cpu",
            help="1 si es unicelular; mayor para colonias/filamentos.",
        )
        volumen = g3.number_input(
            "Volumen celular (µm³)", min_value=0.0, step=10.0, value=0.0,
            format="%.1f", key="cat_f_vol",
            help="Biovolumen promedio por célula (para OMS 2021). 0 si no se calibra.",
        )

        enviado = st.form_submit_button(
            "Guardar especie", icon=":material/save:", type="primary",
        )
        if enviado:
            nombre_limpio = (nombre or "").strip()
            if not nombre_limpio:
                st.error("El nombre de la especie es obligatorio.", icon=":material/error:")
            elif existe_especie(nombre_limpio):
                st.error(f"«{nombre_limpio}» ya está en el catálogo.", icon=":material/error:")
            else:
                try:
                    crear_especie(
                        division=division,
                        especie=nombre_limpio,
                        clase=clase or None,
                        orden=orden or None,
                        familia=familia or None,
                        unidad=unidad,
                        celulas_por_unidad=int(celulas_por_unidad),
                        volumen_celula_um3=float(volumen),
                        gbif_key=verif.get("gbif_key"),
                        algaebase_id=verif.get("algaebase_id"),
                        fuente_verificacion=verif.get("fuente") or "manual",
                    )
                    st.session_state.pop("cat_verif", None)
                    st.success(f"Especie «{nombre_limpio}» agregada al catálogo.",
                               icon=":material/check_circle:")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al guardar: {exc}", icon=":material/error:")


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header(
        "Catálogo de fitoplancton",
        "Taxonomía del método de conteo — verificada contra AlgaeBase / GBIF",
    )

    tab_lista, tab_nueva = st.tabs(["Catálogo", "Nueva especie"])
    with tab_lista:
        _render_listado()
    with tab_nueva:
        _render_nueva()


main()
