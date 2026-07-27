import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# ════════════════════════════════════════════════════════════
# CONFIGURACIÓN Y CARGA DE DATOS
# ════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Conformance/Department",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data
def cargar_datos():
    return pd.read_csv('https://docs.google.com/spreadsheets/d/e/2PACX-1vSL8e5uoUExt5a-LDPCw0rEcFTm0SqAhLz8sYT8sbkYtse1pvMHY9Qij547diNhlP__DYxtuT8XojRO/pub?gid=1596580014&single=true&output=csv')


@st.cache_data
def cargar_roster():
    # FIX: el roster también se cachea para no descargarlo en cada rerun
    return pd.read_csv('https://docs.google.com/spreadsheets/d/e/2PACX-1vQZQxlh339pqtikjBlsyAGEUSsJQs5RpNrfoh8SOKS9pcmwT5Wzjwlx4ZaJBWUAFE0yeOMWyhmwg88y/pub?gid=182944612&single=true&output=csv')


data = cargar_datos()
roster = cargar_roster()

data['datestamp'] = pd.to_datetime(data['datestamp'])
Base_data = data.loc[data['datestamp'] >= '20260601']

st.markdown('# Conformance by Department')
st.markdown('## General Dashboard')

nombre_meses = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

# Valores de la columna Status que cuentan como licencia médica (no evitable).
# AJUSTAR según los valores reales del CSV: ver working_data['Status'].unique()
STATUS_LICENCIA = ['MEDICAL LICENSE', 'Sick Leave']

# Valores de la columna Status que cuentan como día de vacaciones.
# Se ven ambas variantes en el CSV real: 'Vacation' y 'Vacations'.
STATUS_VACACION = ['VACATION', 'VACATIONS']

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

# ════════════════════════════════════════════════════════════
# FILTROS (SIDEBAR)
# ════════════════════════════════════════════════════════════

st.sidebar.title('FILTROS')

# Límites del calendario según los datos disponibles
fecha_min = Base_data['datestamp'].min().date()
fecha_max = Base_data['datestamp'].max().date()

rango_fechas = st.sidebar.date_input(
    'Rango de fechas:',
    value=(fecha_min, fecha_min),   # rango completo por defecto
    min_value=fecha_min,
    max_value=fecha_max,
    format="MM/DD/YYYY",
)

# Mientras el usuario está eligiendo, date_input devuelve una sola fecha.
# Detenemos la ejecución hasta que el rango esté completo.
if len(rango_fechas) != 2:
    st.info('Selecciona la fecha de inicio y de fin en el calendario.')
    st.stop()

fecha_inicio, fecha_fin = rango_fechas

lob_disponibles = ['ONBOARDING', 'INBOUND & CHAT', 'RELATIONSHIP MANAGEMENT', 'SALES',
                   'ACCOUNT MANAGEMENT', 'SUBMISSION AND OPERATIONS', 'MULTIFUNCTIONS', 'FRAUD/AML']

lob_seleccionado = st.sidebar.selectbox('LOB:', sorted(lob_disponibles))


# ════════════════════════════════════════════════════════════
# FUNCIONES DE TRANSFORMACIÓN Y CÁLCULO
# ════════════════════════════════════════════════════════════

def a_timedelta_hora(serie):
    """Convierte una columna de hora del día (ej. '08:03:00') a timedelta
    desde medianoche. Reemplaza los 5 bloques repetidos de to_datetime + normalize."""
    s = pd.to_datetime(serie)
    return s - s.dt.normalize()


def preparar_datos(df):
    """Aplica todas las conversiones y columnas calculadas.
    Recibe un DataFrame ya filtrado y devuelve una copia procesada."""
    df = df.copy()  # FIX: evita SettingWithCopyWarning al modificar un slice

    df = df[['datestamp', 'Full Name', 'LOB', 'Status', 'Schedule In',
             'Schedule Out', 'Scheduled Hours', 'Clock in time', 'away',
             'Lunch', 'Clock out time', 'Total work time']]

    # Conversiones a timedelta (una sola función para las 5 columnas)
    for col in ['Schedule In', 'Schedule Out', 'Clock in time',
                'Clock out time', 'Lunch']:
        df[col] = a_timedelta_hora(df[col])

    df['Total work time'] = pd.to_timedelta(df['Total work time'])

    # Columnas calculadas
    df.loc[df['Clock in time'] > df['Schedule In'], 'Minutos_Tarde'] = \
        df['Clock in time'] - df['Schedule In']

    df.loc[df['Lunch'] > pd.Timedelta(hours=1), 'Exedente_lunch'] = \
        df['Lunch'] - pd.Timedelta(hours=1)

    df.loc[df['Clock out time'] > df['Schedule Out'], 'Schedule_Exed'] = \
        df['Clock out time'] - df['Schedule Out']

    df.loc[df['Clock out time'] < df['Schedule Out'], 'Early_out_minutes'] = \
        df['Schedule Out'] - df['Clock out time']

    return df


def calcular_metricas(df, lob, dias_laborables):
    """Calcula esperado, obtenido e índice para un LOB en el período dado.
    Devuelve un diccionario — así el mismo cálculo sirve para los KPIs
    (LOB seleccionado) y para el gráfico (loop sobre todos los LOBs)."""

    # Horas esperadas: empleados del roster × 8h × días laborables del mes
    # FIX: antes era × 5 días (una semana) pero el obtenido sumaba el mes
    # completo — los períodos deben coincidir para que el índice tenga sentido
    n_empleados = roster.loc[
        (roster['LOB'] == lob)
        & (~roster['Full Name'].isin(nombres_excluidos)),
        'Full Name'
    ].size
    esperado_bruto = n_empleados * 8 * dias_laborables

    # Los días de vacaciones no se esperan: por cada día de vacaciones
    # registrado en el período se descuentan 8h del esperado.
    dias_vacacion = int(
        df['Status'].str.upper().str.strip().isin(STATUS_VACACION).sum()
    )
    esperado = max(esperado_bruto - dias_vacacion * 8, 0)

    # Horas obtenidas
    total = df['Total work time'].sum()
    obtenido = total.total_seconds() / 3600 if pd.notna(total) and total != 0 else 0

    # Brecha evitable (tardanzas + lunch + early outs), en horas
    tarde = df['Minutos_Tarde'].sum()
    lunch = df['Exedente_lunch'].sum()
    early = df['Early_out_minutes'].sum()
    evitable = sum(
        t.total_seconds() / 3600 for t in [tarde, lunch, early] if pd.notna(t)
    )

    # Brecha NO evitable: licencias médicas, identificadas por la columna
    # Status. Cada día de licencia cuenta como una jornada perdida (8h).
    # IMPORTANTE: ajusta los textos de STATUS_LICENCIA a los valores
    # exactos de tu CSV — puedes verlos con: print(df['Status'].unique())
    dias_licencia = int(
        df['Status'].str.upper().str.strip().isin(STATUS_LICENCIA).sum()
    )
    no_evitable = dias_licencia * 8

    # Porcentajes sobre el TOTAL de tiempo perdido (evitable + no evitable)
    total_perdido = evitable + no_evitable
    pct_evitable = (evitable / total_perdido * 100) if total_perdido > 0 else 0
    pct_no_evitable = (no_evitable / total_perdido * 100) if total_perdido > 0 else 0

    indice = (obtenido / esperado * 100) if esperado > 0 else 0
    brecha_total = max(esperado - obtenido, 0)

    return {
        'esperado': esperado,
        'esperado_bruto': esperado_bruto,
        'dias_vacacion': dias_vacacion,
        'obtenido': obtenido,
        'indice': indice,
        'evitable': evitable,
        'no_evitable': no_evitable,
        'dias_licencia': dias_licencia,
        'total_perdido': total_perdido,
        'pct_evitable': pct_evitable,
        'pct_no_evitable': pct_no_evitable,
        'brecha_total': brecha_total,
    }


def color_semaforo(indice):
    if indice >= 90:
        return "#10b981"   # verde
    elif indice >= 85:
        return "#f59e0b"   # ámbar
    return "#ef4444"       # rojo


def formato_horas(horas_float):
    """Convierte 158.75 → '158h 45m'"""
    h = int(horas_float)
    m = int(round((horas_float - h) * 60))
    return f"{h}h {m}m"


def horas_minutos(horas_float):
    """Descompone 1.333... en (1, 20) — horas y minutos enteros.
    Se calcula sobre el total de minutos para evitar que el redondeo
    produzca 60 minutos en vez de sumar 1 a las horas."""
    total_minutos = int(round(horas_float * 60))
    return divmod(total_minutos, 60)


# ════════════════════════════════════════════════════════════
# CÁLCULOS DEL PERÍODO SELECCIONADO
# ════════════════════════════════════════════════════════════


# Días laborables (lun-vie) dentro del rango seleccionado
# busday_count excluye el día final, por eso se suma 1 día
dias_laborables = int(np.busday_count(
    fecha_inicio, fecha_fin + pd.Timedelta(days=1)
))

dias = pd.bdate_range(start=fecha_inicio, end=fecha_fin)


# FIX: el filtro ahora aplica el rango de fechas del calendario
filtro_periodo = (
    (Base_data['datestamp'].dt.normalize().isin(dias))
    & (~Base_data['Full Name'].isin(nombres_excluidos))
)

working_data = preparar_datos(
    Base_data.loc[filtro_periodo & (Base_data['LOB'] == lob_seleccionado)]
)

m = calcular_metricas(working_data, lob_seleccionado, dias_laborables)



# ════════════════════════════════════════════════════════════
# KPI CARDS
# ════════════════════════════════════════════════════════════

def kpi_card(titulo, valor, subtexto, color="#10b981"):
    st.markdown(f"""
    <div style="
        background: white;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    ">
        <p style="font-size:11px; color:#64748b; text-transform:uppercase;
                  letter-spacing:0.05em; margin:0;">{titulo}</p>
        <p style="font-size:28px; font-weight:700; color:{color}; margin:4px 0;">{valor}</p>
        <p style="font-size:12px; color:#94a3b8; margin:0;">{subtexto}</p>
    </div>
    """, unsafe_allow_html=True)


st.markdown(
    f"### {lob_seleccionado} — {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"
)

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    # FIX: subtexto coherente (antes decía "Meta ≥ 90%" en horas esperadas)
    kpi_card("Horas Esperadas", f"{m['esperado']:,}",
             f"{dias_laborables} días laborables · -{m['dias_vacacion']} días de vacaciones",
             "#1e40af")

with col2:
    # FIX: antes era "420" hardcodeado
    kpi_card("Horas Obtenidas", formato_horas(m['obtenido']),
             "Total work time del período", "#1e40af")

with col3:
    # FIX: el semáforo ahora sí se aplica al índice
    kpi_card("Índice de Productividad", f"{m['indice']:.1f}%",
             "Meta ≥ 90% · Crítico < 85%", color_semaforo(m['indice']))

with col4:
    # % sobre el total de tiempo perdido (evitable + licencias)
    kpi_card("Pérdida Evitable", f"{m['pct_evitable']:.1f}%",
             f"{formato_horas(m['evitable'])} — tardanzas + lunch + early out",
             "#f59e0b")

with col5:
    kpi_card("Pérdida No Evitable", f"{m['pct_no_evitable']:.1f}%",
             f"{formato_horas(m['no_evitable'])} — {m['dias_licencia']} días de licencia médica",
             "#64748b")


# ════════════════════════════════════════════════════════════
# GRÁFICO: ESPERADO VS OBTENIDO POR DEPARTAMENTO
# ════════════════════════════════════════════════════════════
# FIX: el gráfico comparativo se calcula para TODOS los LOBs
# (el filtro de LOB del sidebar aplica solo a los KPIs de arriba)

filas = []
for lob in lob_disponibles:
    df_lob = preparar_datos(
        Base_data.loc[filtro_periodo & (Base_data['LOB'] == lob)]
    )
    r = calcular_metricas(df_lob, lob, dias_laborables)
    filas.append({
        'LOB': lob,
        'Esperado': r['esperado'],
        'Obtenido': round(r['obtenido'], 1),
        'Indice': round(r['indice'], 1),
    })

df_chart = pd.DataFrame(filas).sort_values('Indice')

fig = go.Figure()

fig.add_trace(go.Bar(
    x=df_chart['LOB'], y=df_chart['Esperado'],
    name="Esperado",
    marker_color="#cbd5e1",
    hovertemplate="%{x}<br>Esperado: %{y:,.0f} h<extra></extra>"
))

fig.add_trace(go.Bar(
    x=df_chart['LOB'], y=df_chart['Obtenido'],
    name="Obtenido",
    marker_color=[color_semaforo(i) for i in df_chart['Indice']],
    customdata=df_chart['Indice'],
    hovertemplate="%{x}<br>Obtenido: %{y:,.0f} h<br>Índice: %{customdata:.1f}%<extra></extra>"
))

fig.update_layout(
    barmode="group",
    plot_bgcolor="white",
    paper_bgcolor="white",
    font=dict(family="Segoe UI", size=12, color="#475569"),
    legend=dict(orientation="h", y=1.12),
    margin=dict(t=40, b=10, l=10, r=10),
    yaxis=dict(gridcolor="#e2e8f0", title="Horas"),
    height=420,
)

st.markdown("### Esperado vs Obtenido por Departamento")
# FIX: sin esta línea el gráfico nunca aparece en la app
st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════
# DESGLOSE DE PÉRDIDAS POR TIPO DE EVENTO
# ════════════════════════════════════════════════════════════

def desglose_perdidas(df):
    """Cuenta los eventos y suma las horas perdidas por cada causa.
    Un 'evento' es una fila con valor en la columna correspondiente:
    las columnas calculadas solo tienen valor cuando el evento ocurrió,
    por eso .notna().sum() cuenta los eventos."""

    causas = {
        'Tardanzas': 'Minutos_Tarde',
        'Excedente de lunch': 'Exedente_lunch',
        'Early outs (salida temprana)': 'Early_out_minutes',
        # Clock out después de la hora de salida programada (Schedule_Exed,
        # ya calculada en preparar_datos): cuántos minutos se quedan de más.
        'Excedente de salida': 'Schedule_Exed',
    }

    filas = []
    for nombre, col in causas.items():
        eventos = int(df[col].notna().sum())
        suma = df[col].sum()
        horas = suma.total_seconds() / 3600 if pd.notna(suma) and eventos > 0 else 0
        h, m = horas_minutos(horas)
        filas.append({'Causa': nombre, 'Eventos': eventos, 'Horas perdidas': horas,
                      'Horas': h, 'Minutos': m})

    # Vacaciones: no es una columna timedelta, se cuenta por día (Status) a 8h c/u
    dias_vacacion = int(df['Status'].str.upper().str.strip().isin(STATUS_VACACION).sum())
    horas_vacacion = dias_vacacion * 8
    h, m = horas_minutos(horas_vacacion)
    filas.append({
        'Causa': 'Vacaciones',
        'Eventos': dias_vacacion,
        'Horas perdidas': horas_vacacion,
        'Horas': h,
        'Minutos': m,
    })

    # Licencias médicas: mismo tratamiento que Vacaciones, por día (Status) a 8h c/u
    dias_licencia = int(df['Status'].str.upper().str.strip().isin(STATUS_LICENCIA).sum())
    horas_licencia = dias_licencia * 8
    h, m = horas_minutos(horas_licencia)
    filas.append({
        'Causa': 'Medical License',
        'Eventos': dias_licencia,
        'Horas perdidas': horas_licencia,
        'Horas': h,
        'Minutos': m,
    })

    desglose = pd.DataFrame(filas)
    total_perdido = desglose['Horas perdidas'].sum()
    desglose['% de la pérdida'] = (
        desglose['Horas perdidas'] / total_perdido * 100 if total_perdido > 0 else 0
    )
    return desglose.sort_values('Horas perdidas', ascending=False), total_perdido


st.markdown(f"### Desglose de pérdidas — {lob_seleccionado}")

desglose, total_perdido = desglose_perdidas(working_data)

if total_perdido == 0:
    st.info('No se registraron pérdidas por tardanzas, lunch, early outs, excedente de salida ni vacaciones en el período seleccionado.')
else:
    col_tabla, col_grafico = st.columns([1, 1])

    with col_tabla:
        # Tabla formateada: st.dataframe con column_config controla el formato
        # de cada columna sin tener que convertir los números a texto.
        # column_order oculta 'Horas perdidas' (float, se usa internamente
        # para ordenar/calcular %) y muestra Horas/Minutos como enteros.
        st.dataframe(
            desglose,
            hide_index=True,
            use_container_width=True,
            column_order=['Causa', 'Eventos', 'Horas', 'Minutos', '% de la pérdida'],
            column_config={
                'Causa': st.column_config.TextColumn('Causa'),
                'Eventos': st.column_config.NumberColumn('Eventos', format='%d'),
                'Horas': st.column_config.NumberColumn('Horas', format='%d'),
                'Minutos': st.column_config.NumberColumn('Minutos', format='%d'),
                '% de la pérdida': st.column_config.ProgressColumn(
                    '% de la pérdida', format='%.1f%%',
                    min_value=0, max_value=100,
                ),
            },
        )
        eventos_totales = int(desglose['Eventos'].sum())
        st.caption(
            f"**{eventos_totales} eventos** en total → "
            f"**{formato_horas(total_perdido)}** perdidas en el período."
        )

    with col_grafico:
        # Barras horizontales con el peso de cada causa
        colores_causa = {
            'Tardanzas': '#f59e0b',
            'Excedente de lunch': '#fbbf24',
            'Early outs (salida temprana)': '#fb923c',
            'Excedente de salida': '#0ea5e9',
            'Vacaciones': '#8b5cf6',
            'Medical License': '#ef4444',
        }
        fig_desglose = go.Figure(go.Bar(
            x=desglose['Horas perdidas'],
            y=desglose['Causa'],
            orientation='h',
            marker_color=[colores_causa[c] for c in desglose['Causa']],
            customdata=desglose[['Eventos', '% de la pérdida']],
            texttemplate='%{customdata[1]:.1f}%',
            textposition='outside',
            hovertemplate=(
                '%{y}<br>Horas: %{x:.1f} h<br>'
                'Eventos: %{customdata[0]}<br>'
                'Peso: %{customdata[1]:.1f}%<extra></extra>'
            ),
        ))
        fig_desglose.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(family='Segoe UI', size=12, color='#475569'),
            margin=dict(t=10, b=10, l=10, r=40),
            xaxis=dict(gridcolor='#e2e8f0', title='Horas perdidas'),
            yaxis=dict(autorange='reversed'),  # la mayor causa arriba
            height=220,
        )
        st.plotly_chart(fig_desglose, use_container_width=True)

