import streamlit as st
import pandas as pd
import requests
import json
import threading #  ESTA LIBRERÍA ES LA CLAVE PARA QUE NO SE CONGELE LA WEB
from datetime import datetime

# Configuración visual
st.set_page_config(page_title="Control de Producción Yobel", layout="wide")
st.title("Reporte de Producción en Tiempo Real - Planta Plásticos")
st.markdown("---")

# ==========================================
# 1. PEGAR AQUÍ TU URL DE APPS SCRIPT 
URL_WEB_APP = "https://script.google.com/macros/s/AKfycbzzkMlrN4J0KDqDcao2_s2B9qhXOC_z4i18_bpL-E1nM-1GJB3bG9m-fs1EP7SSW9VhhQ/exec"

# 2. ID DE TU GOOGLE SHEET
SHEET_ID = "135RAldXiMWAFZ51SMeDspMDmQXMd73ob4ebOBq6m5gg"

# 1. ENVÍO "FIRE AND FORGET" EN SEGUNDO PLANO
def enviar_a_sheet(sheet_name, data_list):
    def tarea_silenciosa():
        try:
            payload = {"sheetName": sheet_name, "data": json.dumps(data_list)}
            requests.post(URL_WEB_APP, data=payload)
        except Exception as e:
            print(f"Error oculto: {e}") # Se imprime en consola para no asustar al usuario ni bloquear la app
            
    # Arranca el proceso en el fondo y le devuelve el control a la web al instante
    hilo = threading.Thread(target=tarea_silenciosa)
    hilo.start()

# 2. LECTURA OPTIMIZADA DE GOLPE (Descarga 1 vez, no 3)
@st.cache_data(ttl=60, show_spinner=False) # Mantiene la info...
def descargar_base_datos():
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=xlsx"
        # sheet_name=None hace el truco: descarga TODO el Excel de un solo viaje
        return pd.read_excel(url, sheet_name=None)
    except Exception:
        return {}

# Cargamos el paquete completo
bd_completa = descargar_base_datos()

# Función para extraer las pestañas de ese paquete
def obtener_tabla(nombre_hoja, columnas_default):
    if nombre_hoja in bd_completa:
        df = bd_completa[nombre_hoja]
        df.columns = df.columns.str.strip()
        return df.dropna(how="all")
    return pd.DataFrame(columns=columnas_default)

# Asignamos las variables de forma súper rápida
df_ordenes = obtener_tabla("Ordenes Terminadas", ["Fecha y hora", "Codigo", "Orden", "Maquina", "Cantidad", "Observaciones"])
df_paradas = obtener_tabla("Paradas de maquinas", ["Fecha y Hora", "Maquina", "Motivo", "Estado"])
df_cierre = obtener_tabla("Cierre de turno", ["Fecha y hora", "Maquina", "Codigo", "Orden", "Cantidad", "Supervisor", "Turno"])

MAQUINAS = ["Inyectora JM1", "Inyectora JM2", "Inyectora JM3", "Inyectora Haixing", "Sopladora PET", "Sopladora PARKER I", "Sopladora PARKER II", "Sopladora PB1000S", "Sopladora PB1000D", "Sopladora PB2000", "Sopladora PARKER 65", "Sopladora PARKER 75-2", "Sopladora PARKER 75-1", "Sopladora PARKER 75-3"]
TURNOS = ["1er", "2do", "3er"]

# Menú de pestañas
tab1, tab2, tab3 = st.tabs(["Notificar Evento", "Cierre de Turno", "Vista del Programador"])

# ==================== PESTAÑA 1: EVENTOS EN VIVO ====================
with tab1:
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Reportar Orden Terminada")
        with st.form("form_orden", clear_on_submit=True):
            codigo_id = st.text_input("Código:", placeholder="Ej. E016035")
            orden_id = st.text_input("Órden:", placeholder="Ej. 3368087")
            maq_sel = st.selectbox("Máquina:", MAQUINAS, key="maq_o")
            cantidad = st.number_input("Cantidad Producida:", min_value=0, step=1)
            turno_sel = st.selectbox("Turno:", TURNOS, key="turno_o")
            observaciones = st.text_area("Observaciones de Calidad:")
            
            enviar_orden = st.form_submit_button("Notificar Fin de Orden")
            if enviar_orden:
                if orden_id:
                    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    datos_orden = [ahora, codigo_id, orden_id, maq_sel, cantidad, turno_sel, observaciones]
                    enviar_a_sheet("Ordenes Terminadas", datos_orden)
                    st.toast('Registrado con éxito', icon='✅')
                else:
                    st.error("Debes colocar el Código y el Número de Orden.")

    with col2:
        st.subheader("Reportar Parada de Máquina")
        with st.form("form_parada", clear_on_submit=True):
            maq_parada = st.selectbox("Máquina Detenida:", MAQUINAS, key="maq_p")
            motivo = st.selectbox("Motivo de parada:", [
                "Falla Mecánica / Eléctrica", "Falta de Materia Prima", 
                "Cambio de Molde / Set-up", "Ajuste de Parámetros de Proceso", "Limpieza / Mantenimiento"
            ])
            estado = st.selectbox("Estado de la máquina:", ["Detenida", "En pruebas / Reiniciando"])
            
            enviar_parada = st.form_submit_button("Registrar Parada en Vivo")
            if enviar_parada:
                ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                datos_parada = [ahora, maq_parada, motivo, estado]
                enviar_a_sheet("Paradas de maquinas", datos_parada)
                st.toast('Alerta de máquina registrada', icon='🚨')

# ==================== PESTAÑA 2: CIERRE DE TURNO ====================
with tab2:
    st.subheader("Consolidado Final de Turno (Reporte 8H)")
    st.info("Ingresa los totales tomados directamente de las hojas físicas de producción.")

    # 1. INICIALIZAR LA MEMORIA TEMPORAL
    # Si es la primera vez que se abre la página, creamos una lista vacía en memoria
    if "temp_cierres" not in st.session_state:
        st.session_state.temp_cierres = []

    # 2. FORMULARIO PARA IR AGREGANDO MÁQUINAS A LA LISTA
    with st.form("form_agregar_maquina", clear_on_submit=True):
        st.markdown("### Cargar Máquina a la Lista")
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        
        with col_c1:
            maquina = st.selectbox("Seleccionar Máquina:", MAQUINAS)
        with col_c2:
            codigo = st.text_input("Código del Producto:")
        with col_c3:
            orden = st.text_input("Número de Orden:")
        with col_c4:
            cantidad = st.number_input("Cantidad Producida:", min_value=0, step=1)
            
        agregar_maquina = st.form_submit_button("Agregar Máquina a la Lista")
        
        if agregar_maquina:
            if codigo and orden:
                # Guardamos el registro temporalmente en el session_state
               st.session_state.temp_cierres.append({
                    "Maquina": maquina,
                    "Codigo": codigo,
                    "Orden": orden,
                    "Cantidad": cantidad
                }) 
               st.toast(f' {maquina} agregado', icon='✔️')
        else:
            st.error("Por favor, ingresa el Código y la Orden antes de cerrar turno.")

    st.markdown("---")

    # 3. MOSTRAR LA TABLA TEMPORAL CON LO QUE SE VA ACUMULANDO
    if st.session_state.temp_cierres:
        st.markdown("### Vista Previa del Cierre de Turno:")
        # Convertimos la lista de memoria en un DataFrame para mostrarlo bonito
        df_temp = pd.DataFrame(st.session_state.temp_cierres)
        st.dataframe(df_temp, use_container_width=True)
        
        # Botón de seguridad por si el supervisor se equivoca y quiere resetear la lista
        if st.button("Limpiar lista temporal"):
            st.session_state.temp_cierres = []
            st.success("Lista temporal limpiada.")
            st.rerun()
            
        st.markdown("---")

        # 4. FORMULARIO FINAL PARA REGISTRAR SUPERVISOR, TURNO Y ENVIAR TODO
        with st.form("form_guardar_final"):
            st.markdown("### Enviar Cierre de Turno Completo")
            col_sup1, col_sup2 = st.columns(2)
            with col_sup1:
                supervisor = st.text_input("Nombre del Supervisor Responsable:")
            with col_sup2:
                turno = st.selectbox("Turno de Operación:", ["1er", "2do", "3er"])
            
            guardar_cierre = st.form_submit_button("Enviar reporte de producción")
            
            if guardar_cierre:
                if supervisor:
                    ahora_cierre = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Recorremos cada máquina guardada en la memoria temporal y la mandamos al Sheets
                    for registro in st.session_state.temp_cierres:
                        datos_cierre = [
                            ahora_cierre,
                            registro["Maquina"],
                            registro["Codigo"],
                            registro["Orden"],
                            registro["Cantidad"],
                            supervisor,
                            turno
                        ]
                        enviar_a_sheet("Cierre de turno", datos_cierre)
                    
                    # Limpiamos la memoria temporal para el siguiente turno
                    st.session_state.temp_cierres = []
                    st.toast('- ¡Cierre de turno completado!', icon='✅')
                    st.balloons()
                else:
                    st.error("Por favor, ingresa el nombre del supervisor antes de enviar.")
    else:
        st.info("La lista está vacía. Agrega al menos una máquina arriba para poder enviar el reporte final.")

# ==================== PESTAÑA 3: VISTA DEL PROGRAMADOR ====================
with tab3:
    st.subheader("Panel de Control y Monitoreo General")
    
    if st.button("🔄 Actualizar Datos"):
        st.cache_data.clear()
        st.rerun()
        
    kpi1, kpi2, kpi3 = st.columns(3)
    
    total_ops = len(df_ordenes) if not df_ordenes.empty else 0
    
    if not df_cierre.empty and "Unidades del turno" in df_cierre.columns:
        df_cierre["Unidades del turno"] = pd.to_numeric(df_cierre["Unidades del turno"].astype(str).str.replace('.', '').str.replace(',', ''), errors='coerce').fillna(0)
        total_piezas = df_cierre["Unidades del turno"].sum()
    else:
        total_piezas = 0
        
    if not df_paradas.empty and "Estado" in df_paradas.columns:
        paradas_activas = len(df_paradas[df_paradas["Estado"] == "Detenida"])
    else:
        paradas_activas = 0
    
    kpi1.metric("Órdenes de Turno Cerradas", total_ops)
    kpi2.metric("Total de Producción Acumulada", f"{total_piezas:,.0f} und")
    kpi3.metric("Líneas Detenidas Actualmente", paradas_activas, delta_color="inverse")
    
    st.markdown("---")
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        # 1. Cambiamos el título aquí
        st.markdown("### Últimas Órdenes Terminadas")
        # 2. Nos aseguramos de que use 'df_ordenes' (esta variable ya tiene solo los datos de esa pestaña)
        st.dataframe(df_ordenes.sort_index(ascending=False).head(10) if not df_ordenes.empty else df_ordenes, use_container_width=True)
    with col_t2:
        st.markdown("### Estado de Alertas de Máquinas")
        st.dataframe(df_paradas.sort_index(ascending=False).head(10) if not df_paradas.empty else df_paradas, use_container_width=True)
        
    st.markdown("### Historial de Cierres de Turno")
    st.dataframe(df_cierre.sort_index(ascending=False).head(10) if not df_cierre.empty else df_cierre, use_container_width=True)