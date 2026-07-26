import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ════════════════════════════════════════════════════════════
# CONFIGURACIÓN Y CARGA DE DATOS
# ════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Productivity/Department",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def cargar_datos():
    return pd.read_csv(
        'https://docs.google.com/spreadsheets/d/e/2PACX-1vSL8e5uoUExt5a-LDPCw0rEcFTm0SqAhLz8sYT8sbkYtse1pvMHY9Qij547diNhlP__DYxtuT8XojRO/pub?gid=1596580014&single=true&output=csv',
        low_memory=False,
    )


@st.cache_data
def cargar_roster():
    return pd.read_csv(
        'https://docs.google.com/spreadsheets/d/e/2PACX-1vQZQxlh339pqtikjBlsyAGEUSsJQs5RpNrfoh8SOKS9pcmwT5Wzjwlx4ZaJBWUAFE0yeOMWyhmwg88y/pub?gid=182944612&single=true&output=csv'
    )


data = cargar_datos()
roster = cargar_roster()

data['datestamp'] = pd.to_datetime(data['datestamp'])
Base_data = data.loc[data['datestamp'] >= '20260601']

nombres_excluidos = [
    'JUAN MIGUEL MENDEZ',
    'KIMBERLY MILDRED NUÑEZ GAUTREAUX',
    'YAEL JOHANNY CARO MARTINEZ', 'SAMUEL ENRIQUE SOLIS OZORIA',
    'ELAINI ENCARNACION MAYNERD', 'JOHNANGEL RAMIREZ GUTIERREZ',
    'PALMIRA MIGUELINA ECHAVARRIA VARGAS',
    'ADRIAN PEÑA PAULINO', 'NEFTALY AGUSTIN MADERA CORONADO',
    'CELUMIEL ODILET BALBUENA JAVIER',
    'EMMANUEL DAVID MARTE DIAZ', 'VICTOR JOEL CONTRERAS MALDONADO',
    'ASHLIE GABRIELA VASQUEZ SANTIAGO'
]

st.markdown('# Productividad por Departamento')

# ════════════════════════════════════════════════════════════
# FILTROS (SIDEBAR)
# ════════════════════════════════════════════════════════════

st.sidebar.title('Filtros')

fecha_min = Base_data['datestamp'].min().date()
fecha_max = Base_data['datestamp'].max().date()

rango_fechas = st.sidebar.date_input(
    'Rango de fechas:',
    value=(fecha_min, fecha_min),
    min_value=fecha_min,
    max_value=fecha_max,
    format="MM/DD/YYYY",
)

if len(rango_fechas) != 2:
    st.info('Selecciona la fecha de inicio y de fin en el calendario.')
    st.stop()

fecha_inicio, fecha_fin = rango_fechas

lob_disponibles = ['ONBOARDING', 'INBOUND & CHAT', 'RELATIONSHIP MANAGEMENT', 'SALES',
                    'ACCOUNT MANAGEMENT', 'SUBMISSION AND OPERATIONS', 'MULTIFUNCTIONS', 'FRAUD/AML']

lob_seleccionado = st.sidebar.selectbox('LOB:', sorted(lob_disponibles))

dias = pd.bdate_range(start=fecha_inicio, end=fecha_fin)
dias_laborables = len(dias)

# ════════════════════════════════════════════════════════════
# DATOS DEL PERÍODO / LOB SELECCIONADO
# ════════════════════════════════════════════════════════════

filtro_periodo = (
    Base_data['datestamp'].dt.normalize().isin(dias)
    & (~Base_data['Full Name'].isin(nombres_excluidos))
)

working_data = Base_data.loc[filtro_periodo & (Base_data['LOB'] == lob_seleccionado)].copy()

# Todo lo que reduzca el tiempo en piso (tardanzas, licencias, vacaciones,
# ausencias, etc.) afecta la productividad: un agente "trabajó" ese día solo
# si tiene marca de Clock in, sin excluir ningún status del cálculo.
trabajo_real = pd.to_timedelta(working_data['Total work time'], errors='coerce')
trabajo_real = trabajo_real.where(working_data['Clock in time'].notna(), pd.Timedelta(0))

horas_agendadas = pd.to_timedelta(working_data['Scheduled Hours'], errors='coerce')

n_empleados_depto = roster.loc[
    (roster['LOB'] == lob_seleccionado) & (~roster['Full Name'].isin(nombres_excluidos)),
    'Full Name'
].nunique()

# Horas esperadas: capacidad total del departamento si todo el personal
# trabajara su jornada completa (empleados × 8h × días laborables).
horas_esperadas = n_empleados_depto * 8 * dias_laborables
horas_realizadas = trabajo_real.sum().total_seconds() / 3600

indice = (horas_realizadas / horas_esperadas * 100) if horas_esperadas > 0 else 0


def formato_horas(horas_float):
    h = int(horas_float)
    m = int(round((horas_float - h) * 60))
    return f"{h}h {m}m"


# ════════════════════════════════════════════════════════════
# INDICADORES
# ════════════════════════════════════════════════════════════

st.markdown(f"### {lob_seleccionado} — {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Empleados del departamento", n_empleados_depto)
c2.metric("Horas esperadas", formato_horas(horas_esperadas), "capacidad con todo el personal")
c3.metric("Horas realizadas", formato_horas(horas_realizadas), "horas realmente trabajadas")
c4.metric("Índice de productividad", f"{indice:.1f}%")

st.caption(
    "**Horas esperadas**: si todo el personal del departamento trabajara su jornada completa (empleados × 8h × días laborables). "
    "**Horas realizadas**: suma de horas realmente trabajadas (con Clock in). "
    "Tardanzas, licencias, vacaciones y ausencias reducen las horas realizadas frente a lo esperado y por tanto el índice de productividad."
)

# ════════════════════════════════════════════════════════════
# ESPERADO VS REALIZADO POR DEPARTAMENTO
# ════════════════════════════════════════════════════════════

filas = []
for lob in lob_disponibles:
    df_lob = Base_data.loc[filtro_periodo & (Base_data['LOB'] == lob)]
    trabajo_lob = pd.to_timedelta(df_lob['Total work time'], errors='coerce')
    trabajo_lob = trabajo_lob.where(df_lob['Clock in time'].notna(), pd.Timedelta(0))
    n_empleados_lob = roster.loc[
        (roster['LOB'] == lob) & (~roster['Full Name'].isin(nombres_excluidos)),
        'Full Name'
    ].nunique()
    filas.append({
        'LOB': lob,
        'Esperado': round(n_empleados_lob * 8 * dias_laborables, 1),
        'Realizado': round(trabajo_lob.sum().total_seconds() / 3600, 1),
    })

df_chart = pd.DataFrame(filas).sort_values('Realizado')

fig = go.Figure()
fig.add_trace(go.Bar(
    x=df_chart['LOB'], y=df_chart['Esperado'], name='Esperado',
    marker_color='#cbd5e1',
    hovertemplate='%{x}<br>Esperado: %{y:,.1f} h<extra></extra>',
))
fig.add_trace(go.Bar(
    x=df_chart['LOB'], y=df_chart['Realizado'], name='Realizado',
    marker_color='#1e40af',
    hovertemplate='%{x}<br>Realizado: %{y:,.1f} h<extra></extra>',
))
fig.update_layout(
    barmode='group',
    plot_bgcolor='white',
    paper_bgcolor='white',
    font=dict(family='Segoe UI', size=12, color='#475569'),
    legend=dict(orientation='h', y=1.12),
    margin=dict(t=40, b=10, l=10, r=10),
    yaxis=dict(gridcolor='#e2e8f0', title='Horas'),
    height=380,
)

st.markdown("### Esperado vs Realizado por departamento")
st.plotly_chart(fig, use_container_width=True)

# ════════════════════════════════════════════════════════════
# EVENTOS QUE IMPIDIERON LLEGAR A LAS HORAS ESPERADAS
# ════════════════════════════════════════════════════════════

horas_perdidas_fila = (horas_agendadas - trabajo_real).clip(lower=pd.Timedelta(0))
horas_perdidas_h = horas_perdidas_fila.dt.total_seconds() / 3600

# Minutos excedentes: todo el tiempo que el empleado trabajó por encima de
# las 8 horas de jornada estándar (p. ej. 8h 11m 20s → 11m 20s de excedente).
# Se calcula contra las 8 horas fijas, no contra "Scheduled Hours", y se
# conserva hasta el segundo para que la suma total sea exacta.
horas_excedentes_fila = (trabajo_real - pd.Timedelta(hours=8)).clip(lower=pd.Timedelta(0))
horas_excedentes_h = horas_excedentes_fila.dt.total_seconds() / 3600

status_norm = working_data['Status'].astype(str).str.strip().str.upper()

# 'On Time' normalmente es el caso normal (sin horas perdidas), pero hay filas
# marcadas 'On Time' que igual perdieron horas: una salida temprana que nunca
# se etiquetó como excepción. Esas se reclasifican para no perderlas del reporte.
es_on_time_con_perdida = (status_norm == 'ON TIME') & (horas_perdidas_h > 0.02)
status_evento = status_norm.mask(es_on_time_con_perdida, 'EARLY OUT (NO PROGRAMADO)')

df_eventos = pd.DataFrame({
    'Status': status_evento,
    'Horas perdidas': horas_perdidas_h,
})

df_eventos = df_eventos[
    (df_eventos['Horas perdidas'] > 0.02) & ((status_norm != 'ON TIME') | es_on_time_con_perdida)
]

df_excedentes = pd.DataFrame({
    'Status': 'MINUTOS EXCEDENTES (SOBRE 8 HORAS)',
    'Horas perdidas': horas_excedentes_h,
})
# Sin el margen de 0.02h que se usa arriba: aquí interesa el total exacto,
# así que cualquier excedente mayor a cero (aunque sean segundos) se cuenta.
df_excedentes = df_excedentes[df_excedentes['Horas perdidas'] > 0]

df_eventos = pd.concat([df_eventos, df_excedentes], ignore_index=True)

st.markdown("### Eventos que impidieron llegar a las horas esperadas")

if df_eventos.empty:
    st.info('No se registraron eventos (ausencias, vacaciones, tardanzas, etc.) que redujeran las horas en el período seleccionado.')
else:
    resumen_eventos = (
        df_eventos.groupby('Status')
        .agg(Eventos=('Horas perdidas', 'size'), Horas=('Horas perdidas', 'sum'))
        .reset_index()
        .sort_values('Horas', ascending=False)
    )

    total_minutos = (resumen_eventos['Horas'] * 60).round().astype(int)
    resumen_eventos['Hora'], resumen_eventos['Minutos'] = divmod(total_minutos, 60)

    col_tabla, col_grafico = st.columns([1, 1])

    with col_tabla:
        st.dataframe(
            resumen_eventos[['Status', 'Eventos', 'Hora', 'Minutos']],
            hide_index=True,
            use_container_width=True,
            column_config={
                'Status': st.column_config.TextColumn('Evento'),
                'Eventos': st.column_config.NumberColumn('Eventos', format='%d'),
                'Hora': st.column_config.NumberColumn('Hora', format='%d'),
                'Minutos': st.column_config.NumberColumn('Minutos', format='%d'),
            },
        )

        es_excedente = resumen_eventos['Status'] == 'MINUTOS EXCEDENTES (SOBRE 8 HORAS)'
        resumen_deficit = resumen_eventos.loc[~es_excedente]
        resumen_excedente = resumen_eventos.loc[es_excedente]

        st.caption(
            f"**{int(resumen_deficit['Eventos'].sum())} eventos** → "
            f"**{formato_horas(resumen_deficit['Horas'].sum())}** por debajo de lo esperado. "
            f"Además, **{int(resumen_excedente['Eventos'].sum())} eventos** → "
            f"**{formato_horas(resumen_excedente['Horas'].sum())}** de minutos excedentes (trabajados de más)."
        )

    with col_grafico:
        fig_eventos = go.Figure(go.Bar(
            x=resumen_eventos['Horas'],
            y=resumen_eventos['Status'],
            orientation='h',
            marker_color='#f59e0b',
            hovertemplate='%{y}<br>Horas: %{x:.1f} h<extra></extra>',
        ))
        fig_eventos.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='Segoe UI', size=12, color='#475569'),
            margin=dict(t=10, b=10, l=10, r=40),
            xaxis=dict(gridcolor='#e2e8f0', title='Horas perdidas'),
            yaxis=dict(autorange='reversed'),
            height=max(220, 28 * len(resumen_eventos)),
        )
        st.plotly_chart(fig_eventos, use_container_width=True)
