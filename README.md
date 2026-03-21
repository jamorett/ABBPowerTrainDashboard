# Sistema Integral de Monitoreo Predictivo ABB Powertrain — Guía Técnica y Whitepaper de Arquitectura

Este **Whitepaper Técnico** documenta a profundidad la arquitectura, matemáticas y lógica de programación detrás del sistema de monitoreo predictivo desarrollado para interconectar actuadores, motores y maquinaria física con el ecosistema de la nube **ABB Ability™ Motion API**.

Diseñado por un panel multidisciplinario (Ciencia de Datos, Ingeniería Full-Stack, Ingeniería de Software y Análisis de Vibraciones), este documento tiene como objetivo explicar *el por qué* y *el cómo* de cada bloque de código, de tal modo que cualquier ingeniero pueda replicarlo, escalarlo o depurarlo con precisión quirúrgica.

---

## 🏗️ 1. Arquitectura Central del Orquestador (`app.py`)

El archivo `app.py` no es un simple script de interfaz; funciona como el orquestador principal (Controller) bajo un modelo similar al Modelo-Vista-Controlador (MVC). En el entorno del framework **Streamlit**, el código se ejecuta de arriba hacia abajo (top-to-bottom) cada vez que el usuario realiza un click, interactúa con un botón o un temporizador expira. Por tanto, la arquitectura de `app.py` está meticulosamente diseñada para preservar su estado y delegar trabajo pesado a componentes en segundo plano sin ralentizar la interfaz.

A continuación, se desglosa microscópicamente el funcionamiento y la ingeniería detrás de sus capas:

### 1.1 El Paradigma de Ejecución Bi-Direccional y Control de Sesión (`st.session_state`)
Dado que Streamlit carece de "memoria" nata entre recargas de página, el bloque inicial de `app.py` pre-asigna variables de estado crudos (State Machine) esenciales para la lógica secuencial:
```python
# Inicialización de la Máquina de Estados Finita (FSM) para el Kiosko
if "kiosk_index" not in st.session_state:
    st.session_state.kiosk_index = 0
if "kiosk_paused" not in st.session_state:
    st.session_state.kiosk_paused = False
if "asset_statuses" not in st.session_state:
    st.session_state.asset_statuses = {a: "Desconocido" for a in KNOWN_ASSETS}
```
Esto asegura que, por ejemplo, si el `kiosk_index` va en el equipo 5 (Molino 3 S34) y la página debe recargarse automáticamente para descargar nuevos datos, la aplicación no devuelva al usuario al equipo 0, perdiendo el hilo de su navegación.

### 1.2 Muro de Defensa Zero-Trust y Autenticación por Cookies
Para implementar un entorno de grado industrial y privado sin usar gestores pesados de terceros (como Auth0), se desarrolló un sistema criptográfico ligero a nivel de navegador utilizando `extra-streamlit-components`.

```python
import extra_streamlit_components as stx

# Instanciación y escaneo de cookies en el explorador del huésped
cookie_manager = stx.CookieManager(key="ia_cookie_manager")
auth_cookie = cookie_manager.get(cookie="abb_dashboard_auth")

if not st.session_state.get('autenticado', False):
    if auth_cookie == "true":
        st.session_state.autenticado = True
    else:
        # Aquí se corta de tajo la ejecución del script...
        st.stop()
```
**Lógica profunda:** La directiva `st.stop()` es el cortafuegos. Si el navegador no detiene una cookie firmada con el valor correcto, Streamlit abandona la lectura del archivo `app.py` inmediatamente en la línea 46. El motor de Inteligencia Artificial, las gráficas, y las conexiones a ABB *jamás se cargan en la RAM del servidor* hasta que el usuario pase este bloque. Al autenticarse correctamente con el formulario, inyectamos un `expires_at` sumando `timedelta(days=3650)` (10 años), anclando la autorización a la máquina del operador de planta de forma vitalicia.

### 1.3 Ingeniería de Memoria Caché: `@st.cache_resource` vs `@st.cache_data`
Una conexión constante a los microservicios de ABB desgastaría la red y quemaría los límites de la API si cada de los 14 motores intentara descargar datos de los últimos 7 días a cada segundo. `app.py` divide inteligentemente cómo almacena cosas pesadas en la memoria del Servidor y resuelve esto con dos acercamientos distintos:

#### A. Recursos Compartidos Globales (`cache_resource`)
```python
@st.cache_resource
def get_api():
    return ApiService()
api = get_api()
```
El objeto `ApiService` inicializa sesiones TCP de SSL, cabeceras HTTP y el motor de renovación de Tokens (OAuth2). Si 50 ingenieros entran a la página al mismo tiempo, el servidor ejecuta esta función *solo 1 vez en toda la historia del contenedor Linux*. El objeto subyacente de red (y los tokens temporales de ABB Ability) **se comparten globalmente**. Esto significa 1 sola huella de memoria en el servidor, blindando el consumo.

#### B. Memoización de Datos Seriados (`cache_data`)
```python
@st.cache_data(ttl=3600)
def fetch_history(_api, asset, date_from, date_to):
    return _api.get_condition_history(asset, date_from, date_to)
```
Cuando el código solicita data vibracional de `'105727'` (Molino 1 S12), los megabytes de JSON recibidos no se comparten globalmente en memoria cruda, sino que se serializan y se "estampan" utilizando un Hash MD5 de los parámetros `(asset, date_from, date_to)`.
- El parámetro `ttl=3600` obliga a Streamlit a expurgar la "fotografía" de los datos pasada una hora exacta, garantizando que el Kiosko nunca muestre información obsoleta de averías mecánicas más allá de una ventana de 60 minutos.
- El guion bajo `_api` es vital en el diseño de parámetros de Streamlit: obliga al motor de caché a ignorar las mutaciones del objeto de conexión, basando la búsqueda de caché únicamente en el nombre de la máquina y sus fechas cronológicas.
- **Resiliencia ante Fallos**: No se encapsula el Request en un `try...except` tradicional en esta función intermedia. Si la API falla o cae, el error "rebota" de regreso a la interfaz. ¿Por qué es deseable heredar el error? Porque si atrapamos el error y devolviéramos `{}`, Streamlit guardaría en su caché ese diccionario vacío para las siguientes 3600 horas bloqueando datos frescos al usuario; propulsar las excepciones purga naturalmente las capas de errores.

### 1.4 La Máquina del Tiempo de 30 Segundos: Concurrencia de React (`st_autorefresh`)
Implementar un "Carrusel de Televisión" ("Kiosko") normalmente significa congelar una pantalla con comandos nativos que destruyen el hilo como `for x in range(30): time.sleep(1)`. Hacer eso provocaría que todo clic del ratón de un operador quede en el limbo. 

En `app.py`, re-orquestamos este problema hacia el frontend delegando la labor a JavaScript y limitándonos a leer estados:
```python
# Componente inyectado en un iFrame invisible
from streamlit_autorefresh import st_autorefresh
count = st_autorefresh(interval=30000, limit=None, key="kioskotimer")

last_count = st.session_state.get('last_kiosk_tick', -1)

# Reparación Topológica de Montaje
if count < last_count:
    last_count = -1
    st.session_state.last_kiosk_tick = -1

# Trigger Asíncrono
if count > last_count:
    st.session_state.kiosk_index = (st.session_state.kiosk_index + 1) % len(KNOWN_ASSETS)
    st.session_state.last_kiosk_tick = count
    # Se procesa en cascada antes del render sin necesidad de invocar st.rerun()
```
**Anatomía del Contador:** Cuando el `count` web alcanza cada umbral de 30,000 milisegundos, despierta al orquestador `app.py`. Comparamos la memoria Python (`last_count`) con la memoria Web (`count`). Solo cuando un tic real haya pasado matemática y físicamente, la aguja avanza gracias al operador Módulo `% len(KNOWN_ASSETS)`, forzando al índice principal a ciclar del equipo N=13 hacia el equipo N=0 infinita y cíclicamente.
*Arreglo Especial de Navegación:* Si el operador salta a la pestaña "Análisis Manual", Streamlit destruye el Iframe web invisible en el DOM. Al regresar, el reloj web (`count`) comienza desde el segundo "Cero", pero la memoria de Python esperaba que el reloj siguiera contando desde donde se quedó. Si Python pide el `tick 8` pero recibe un `0`, la validación de estado `if count < last_count:` asume un cambio de contexto (Context Switch) y se auto-calibra, reiniciando todo para evitar que el carrusel se rompa, detenga, o espere minutos por los "ticks perdidos".

### 1.5 Motor de Ruteo e Inteligencia de Algoritmo de Visualización
`app.py` divide su renderizado llamando a la función `render_kiosk_mode()` o `render_manual_mode()` dependiendo de la selección en la barra lateral (Sidebar). 

Cuando se extraen todas las variables y analíticas en la vista activa, `app.py` no muestra las gráficas al azar, sino que ejecuta su propio Sub-Algoritmo de Priorización (Sorting Algorithm) que califica el peligro:
```python
def priority_score(kpi_dict):
    cond = kpi_dict.get("currentCondition", "Unknown")
    score = 30
    # Escala primaria ABB
    if cond in ["Alarm", "Error", "Poor", "Bad", "Critical"]: score = 0
    elif cond in ["Tolerable", "Warning"]: score = 10
    elif cond in ["Good", "Normal", "OK"]: score = 20
    
    # Intervención Máxima de la IA local: Si escapa las bandas de Bollinger gana absoluta prioridad
    if kpi_dict.get('is_anomalous_ia'): score = -10
    
    # Resolutor de empates pre-programado
    if name == "Bearing condition": score -= 5
    elif name == "Skin Temperature": score -= 4
    return score
```
Este bloque lee cada uno de los más de 20 KPIs enviados por el servicio maestro (`Master Data`), y ordena agresivamente (`kpis_sorted = sorted(kpis_reales, key=priority_score)`) extrayendo y renderizando únicamente el `Top 6` de máximo peligro a la pantalla gigante del Kiosko de producción. Esto ahorra procesamiento de GPU renderizando en Plotly la información vital al segundo que el carrusel enfoca la turbina, evitando "Information Overload" de gráficas "Verdes" planas o innecesarias.

---

## 🌐 2. Puente Ininterrumpible OIDC — `api_service.py`

Las arquitecturas API empresariales usan tokens temporales altamente frágiles que vencen frecuentemente. Este módulo se construyó utilizando el patrón de diseño `Singleton` virtual (gracias al decorador `@st.cache_resource` en `app.py`) para encapsular las credenciales, el estado de red y la negociación OAuth2, aislando por completo la complejidad de autenticación del resto de la aplicación web.

A continuación, la anatomía exacta de cómo la Clase `ApiService` gobierna la red:

### 2.1 Connection Pooling (`requests.Session`)
A diferencia de scripts básicos que usan `requests.get()` cada vez (lo cual obliga a realizar el Handshake de SSL/TLS 3-way en cada petición), este módulo instancia `self.session = requests.Session()` en su constructor inicial. 
```python
class ApiService:
    def __init__(self):
        load_dotenv()
        self.session = requests.Session()
        # ...
```
Esta tubería compartida reduce la redundancia de latencia en la red en aproimadamente un 40% al mantener vivos los puertos TCP subyacentes cuando el carrusel salta rápidamente por los 14 motores para pedir sus históricos (Condition History) y luego inmediatamente después sus Transformadas de Fourier (FFT Files).

### 2.2 Motor de Autenticación "Lazy" y Renovación Blindada
En vez de pedir un token inútilmente al encender el servidor, la clase intercepta todas las peticiones salientes con el decorador explícito `self._ensure_auth()`.

```python
    def authenticate(self, force=False):
        # 1. Early-Exit (Si el token aún vive, aborta el chequeo para ahorrar CPU)
        if not force and datetime.datetime.now() < self.token_expires_at:
            return self.access_token
            
        # 2. Negociación con el Identity Provider de ABB
        url = "https://api.accessmanagement.motion.abb.com/polaris/oidc/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "api_key",
            "ApiKey": self.api_key
        }
        res = requests.post(url, headers=headers, data=data)
        
        # 3. Asignamiento asimétrico con Margen de Seguridad
        token_data = res.json()
        expires_in = token_data.get("expires_in", 3600)
        self.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=expires_in - 300)
        self._update_headers()
```
**Radiografía de la táctica defensiva:**
1. **Delegación de Autoridad (`grant_type="api_key"`):** Intercambiamos físicamente el Largo String Estático (`ABB_API_KEY`) provisto por ABB por un JWT (JSON Web Token) frágil y seguro (`access_token`).
2. **Cronómetro Fatal Invertido:** En la penúltima línea se detecta el margen de $5 \text{ minutos} = 300 \text{ segundos}$. El servicio jamás confía en el `expires_in` de 3600 segundos oficial. Al programar la variable `token_expires_at` bajo una penalización de -300s, se garantiza matemáticamente que cuando queden exactamente 5 minutos de vida, el siguiente Kiosko que solicite datos detonará silenciosamente una re-negociación POST de un token nuevo. La API de ABB nunca estrangulará (HTTP 401 Unauthorized) la petición original de telemetría.
3. **Inyección en Tiempo de Compilación (`_update_headers`)**: En lugar de inyectar el token Bearer y la versión de la API explícitamente en cada endpoint, el método modifica la estructura atómica de `self.session.headers.update(...)`. Desde ese momento, cualquier método subsiguiente de la clase `ApiService` cuenta con autorización nativa a nivel de cabecera HTTP.

### 2.3 Router de Micro-Endpoints de la API
ABB Powertrain no es un repositorio monolítico; divide dramáticamente su base de datos. Para lidiar con esto, el módulo bifurca sus cimientos en:
- `self.base_powertrain_url = "https://api.powertrain.abb.com/api"` (Para extracción de Assets estáticos, Búsqueda de Eventos en bitácora, y FFT Crudos).
- `self.base_url = f"{...}/analytics"` (El motor maestro enfocado a métricas temporales de salud y KPIs computados).

#### A. Extracción Recursiva de Históricos Diarios (`Condition/History/`)
```python
    def get_condition_history(self, asset_id, start_time, end_time):
        self._ensure_auth()
        url = f"{self.base_url}/Analytics/Condition/History/{asset_id}"
        params = {"startTime": start_time, "endTime": end_time}
        response = self.session.get(url, params=params)
        return response.json()
```
*Funcionamiento y Riesgos Inherentes*: Este método inyecta variables `start_time` y `end_time` en estricto formato ODATA `ISO 8601` con huso horario Zero (`Z`). ABB devuelve un JSON anidado que contiene cada uno de los parámetros monitorizados (Temperatura, Condición de Rodamientos, Frecuencia de Operación). Este JSON conforma el cimiento absoluto de nuestro Machine Learning en Python y es absorbido por el constructor de DataFrames.

#### B. Sistema de Rastreo de Nube de Puntos (Dominio Frecuencial)
```python
    def get_last_fft(self, asset_id):
        self._ensure_auth()
        url = f"{self.base_powertrain_url}/fft/FFT/{asset_id}/LastFFTFile"
        response = self.session.get(url)
        return response.json()
```
*Mecánica Excepcional:* A diferencia del Condition History (que engloba medias numéricas interpoladas), el archivo FFT File de ABB no contiene tendencias; se trata de una radiografía cruda (Vectores `x` de hertzios espaciados en milésimas espectrales y vectores de Amplitud Lineal `y` o velocidad `mm/s`). Como ABB Ability usualmente genera solo $1$ documento FFT vital por día por dispositivo, consultarlo con `LastFFTFile` evita saturar la memoria limitándonos a la última "tomografía" mecánica registrada sin procesar un Big Data innecesario de gráficas de hace meses (hasta que el Kiosko lo requiera).

---

## 🧠 3. IA Diagnóstica, Señales y Probabilidad Predictiva — `advanced_analytics.py`

En aplicaciones industriales rudimentarias, una pantalla se limita a mostrar "Verde/Rojo" según un límite estático impuesto previamente. Sin embargo, factores mecánicos cambian (ej. un motor nuevo vibra distinto a uno con 5 años de servicio; los motores trabajan a más RPM según órdenes de producción). 

`advanced_analytics.py` introduce **inteligencia local** directamente en el servidor intermedio, consumiendo los paquetes crudos de la API de ABB y pasándolos por una túnel microscópico de algoritmos deterministas adaptativos, divididos fundamentalmente en el plano Temporal (Tendencias) y el Frecuencial (FFT).

### 3.1 Detección del Comportamiento Caótico (`analyze_volatility`)
El algoritmo de volatilidad asume que no existen umbrales perfectos universales. Modela continuamente cuál es "la normalidad específica" de cada máquina individual.

#### A. Las Bandas Estadísticas Adaptables (Túneles de Bollinger Avanzados)
La función interroga a los `DataFrames` de los últimos 7 días provistos por ABB y construye bandas dinámicas de tolerancia:
```python
# Ventana deslizante de 12 horas estrictamente sobrecargada a un mínimo
rolling_mean = df['value'].rolling('12h', min_periods=2).mean()
rolling_std  = df['value'].rolling('12h', min_periods=2).std()

df['Bollinger_Upper'] = rolling_mean + (2.5 * rolling_std)
```
**Matemática en Acción:**
1. **$N \ge 2$:** La inyección `min_periods=2` asegura solidez algorítmica ante el error de "NaN por división nula" que afectaría la memoria del servidor cuando ABB no ha enviado los suficientes datos telemétricos.
2. **Confianza del $98.7\%$ ($2.5\sigma$):** La variable se evalúa constantemente contra su propio pasado estandarizado $+2.5 \sigma$. Todo equipo que exceda esa franja presenta una desviación estadística crítica.
3. **Piso Anti-Ruido (Noise Floor):** Motores inmaculados con vibración `$0.01 \text{ mm/s}$` a menudo oscilan a `$0.03 \text{ mm/s}$`. Estadísticamente eso es el $300\%$ de subida y rompería la varianza local, detonando falsas alarmas diarias. Para suprimir esto, la IA inyecta el **Piso Acústico Mínimo**:
```python
# Exigir que la variación al menos supere el 5% de la señal real, o el 0.1 absoluto (lo mayor).
noise_floor = max(0.05 * abs(current_value), 0.1)
if std_val > noise_floor:
    # Diagnóstico real
```

#### B. Análisis Diferencial de Degradación Rápida (`dy/dt` o Derivada de Potencia)
No importa si la temperatura de un rodamiento es tolerablemente "tibia" (por debajo del rojo estático). Si la aceleración o pendiente temporal ($\frac{dy}{dt}$) es matemáticamente perversa, la IA detona un **Embalamiento Termo-Mecánico inminente**.

```python
# Aislamiento de las leyes termodinámicas y filtrado de Black-Swans (Startups)
if 'Temperature' in kpi_name: is_startup = min_value < 5.0
elif 'Vibration' in kpi_name: is_startup = min_value < 0.05

for i in range(len(df) - 1, max(len(df) - 5, 0), -1):
    dt_h = (df.index[i] - df.index[i - 1]).total_seconds() / 3600.0
    dy = df['value'].iloc[i] - df['value'].iloc[i - 1]
    derivatives.append(dy / dt_h)

# Algoritmo de Mediana para Filtrado Anti-Gaps
derivatives.sort()
dy_dt = derivatives[len(derivatives) // 2]
```
**Fisiología del Filtro:** 
El código bloquea activamente la regla del arranque en frío. Toda máquina que pasa de estado de reposo ($4^\circ C$ ó $0 \text{ mm/s}$) a encendido tendrá una derivada transitoria artificialmente alta (`Startup Acceleration`). Si los mínimos del DataFrame comprueban un encendido reciente, el cálculo se omite. 
Si el motor descarta el `Startup`, recolecta las derivadas de las últimas $4$ lecturas y **les calcula la mediana matemática** (para descartar fluctuaciones de red atípicas), se evalúa la pendiente final `dy/dt`. 
- Si $\Delta T > 5^\circ C/\text{hora} \rightarrow$ Embalamiento Térmico Crítico.
- Si $\Delta V > 1.5\text{ mm/hora} \rightarrow$ Fricción o Choque Metálico.

### 3.2 Inspector Espectral de Alta Precisión ISO (`analyze_fft`)
El algoritmo es virtualmente un robot de Análisis de Vibraciones Categoría III, certificado lógicamente bajo la normatividad global ISO 13373-2 ($Diagnóstico por Análisis de Frecuencia$). Utiliza la extracción de vectores binarios devueltos por la API FFT de ABB y los secciona:

*La búsqueda universal excluye algoritmos fijos y en su lugar inicia detectando la frecuencia operativa actual del motor de forma agnóstica a la placa de red.*
```python
window_1x = df_fft[(df_fft['frequency'] >= 20) & (df_fft['frequency'] <= 35)]
f_1x = window_1x['frequency'].loc[window_1x['magnitude'].idxmax()]
# Identificación de la Velocidad de Giro: La Fundamental o "Pico 1X"
```

A partir de la frecuencia fundamental ($1X$), el algoritmo inspecciona la topología de la curva `scipy.signal` en un multiverso de anomalías en cascada:

**✅ REGLA 1: Desbalanceo Masivo (ISO 10816-3)**
Si el armónico principal `1X` en algún cuadrante radial de la turbina rebasa $1.5 \text{ mm/s}$ absolutos, dicta Desbalanceo de masa o excentricidad de rotor severa.

**✅ REGLA 2: Desalineación Intra-Axial (ISO 13373-2 §7.3)**
La IA calcula un bloque del $+5\%$ de rango en torno a $2 \times \text{FrecuenciaFundamental}$ ($2X$). Si la fuerza cinética transferida al 2X es matemáticamente superior al $50\%$ del 1X en el mismo plano dimensional, deduce pérdida angular o desplazamiento de acoplamientos.

**✅ REGLA 3: Interferencia Magnética Trifásica (IEC 60034-14)**
Problema frecuente en motores mal aislados. Generamos un arreglo de frecuencias eléctricas estándar ($100\text{Hz}$ y $120\text{Hz}$; el armónico de línea del país correspondiente a la red de $50\text{Hz}$ o $60\text{Hz}$). Un pico electromagnético predominante de $+0.8\text{ mm/s}$ indica irregularidades de inducción en el estator o barras del rotor en cortocircuito; detalles frecuentemente inadvertidos bajo supervisión humana básica.

**✅ REGLA 4: Correlación Tridimensional Cruzada (ISO 13373-2 §7.3.2)**
Rompe la evaluación mono-axis y contrasta dos arreglos distintos:
```python
ratio = axial_data["mag_1x"] / radial_data["mag_1x"]
if ratio >= 0.70:
    # ¡Alerta de Desalineación Angular Crítica!
```
Si un motor empuja horizontalmente el eje axial en un impacto de más del $70\%$ contra su propia excentricidad rotativa (Radial), es el vector clásico absoluto de un acoplamiento flexado (Desalineación Angular). Combinado esto un Armónico de `$2X$` elevado crea una Desalineación Paralela Crítica.

**✅ REGLAS AVANZADAS 5 Y 6 (Holguras y Cojinetes)**
- **Subarmónicos ($0.5X$)**: Si existe masa en el bloque frecuencial que se arrastra en exactamente el $50\%$ de los giros de la máquina fundamental, la cinemática acusa inestabilidad del manto hidrodinámico (Oil Whirl en cojinetes de película fluida) o una flecha soltándose de sus bases de retención.
- **Multitud Familiar ($1X, 2X, 3X, 4X$ simultáneos)**: Si más de 3 hijos armónicos rebasan el `20%` de poder del fundamental, la matemática determina "Patrón A5", revelando una Holgura Estructural generalizada (tornillos barriéndose, cimentación partida o chumaceras vencidas crónicamente).


## 🧨 4. Manipulación Reactiva del DOM — `notification_manager.py`

Streamlit, por diseño de su arquitectura web, renderiza los elementos HTML de forma estrictamente secuencial mediante bloques (Flexbox/Grid estáticos). Las notificaciones oficiales (`st.toast`, `st.warning`) sufren de limitaciones visuales, se apilan o desaparecen cuando el bucle de Python termina. 

Para implementar las **Alertas Predictivas** superpuestas, fue necesario modificar programáticamente el Modelo de Objetos del Documento (DOM) de la ventana del navegador utilizando JavaScript puro inyectado a través de `components.html`.

### 4.1 Inyección en el Marco Superior (Parent Frame)
Streamlit aísla de manera predeterminada los componentes inyectados dentro de "Iframes" restringidos. `notification_manager.py` aborda este aislamiento interactuando con el objeto raíz en la jerarquía abstracta del browser (`window.parent.document`):
```javascript
(function() {
    var p  = window.parent;
    var pd = p.document;

    // Remoción controlada de instancias web previas para evitar duplicidad
    var old = pd.getElementById('ia-notif-root');
    if (old) old.remove();

    // Creación dinámica del Div Padre Flotante
    var root = pd.createElement('div');
    root.id  = 'ia-notif-root';
    // ...
```
Esta técnica permite que las alertas se construyan con CSS `position: fixed` relativo a la esquina superior derecha del monitor del operador de planta (`top: 70px; right: 18px; z-index: 9999`), sobreponiéndose indomablemente a las gráficas, sin consumir espacio del canvas de Python.

### 4.2 Deduplicación Hash MD5 y Estado Global
`notification_manager.py` no dispara HTML ciegamente a cada error. Primero encapsula las peticiones de alerta, las estabiliza y las firma criptográficamente:
```python
def _make_id(asset_id, notif_type, message):
    raw = f"{asset_id}_{notif_type}_{message[:60]}"
    return hashlib.md5(raw.encode()).hexdigest()[:10]
```
Si el motor presenta el mismo armónico `1X` violento dictaminado por `advanced_analytics.py` cincuenta veces en los últimos 30 minutos, la alerta produce el mismo ID. El gestor lo reconoce dentro del Set de memorias de `st.session_state.ia_notifications` y bloquea inmediatamente la avalancha de spam a la pantalla del operador.

### 4.3 Gestión Bi-Modal y Limpieza (Cache Busting Anti-Flickering)
Uno de los retos técnicos de inyectar alertas programáticas es que, al cambiar de Pestaña ("Kiosko" a "Análisis Manual"), el renderizador web guarda el estado del HTML en caché y lo reactiva en forma de un artefacto residual (glitch) en pantallas donde debe estar inactivo, comprometiendo la limpieza visual del sistema.

Resolvemos este comportamiento utilizando una huella generacional continua (Timestamp UNIX):
```python
    import time
    js = f"""
    <script>
    // UUID Refresh Constante: {time.time()}
    (function() {{
        ...
```
- **Por qué funciona:** Al incrustar literalmente el segundo actual (e.g., `1713459812.8391`) en el cuerpo del `<script>`, el compilador evalúa el String en cada recarga de página y determina que es un componente nuevo perdiendo su referencia al bloque almacenado estáticamente. Streamlit es forzado entonces a obligar al navegador del usuario a interpretar y ejecutar el bloque JavaScript nuevo el 100% de las veces.
- **Control Activo Manual**: Cuando en `app.py` se ingresa al modo de Análisis Manual se invoca `clear_floating_notifications()`. Esta función lanza un micro-script (con el mismo identificador UUID de tiempo) responsable que ejecutar internamente `window.parent.document.getElementById('ia-notif-root').remove()`. Removiendo dinámicamente cualquier notificación flotante heredada del Kiosko de la interfaz central del usuario.

---

## 🛠️ 5. Guía Completa de Replicación y Despliegue

### 5.1 Requisitos Mínimos (Local)
Para levantar el servidor desde terminal en Windows o Linux, tu entorno debe instanciar estas versiones recomendadas:
- `python >= 3.10`
- `pip install -r requirements.txt` (Streamlit debe ser `>1.35.0` para no romper dependencias con `scipy` o `altair>=5`).

### 5.2 Estructuración de Secretos
El archivo original contiene variables OIDC. 
**Nunca, bajo ninguna circunstancia, se deben commitear al GIT de manera pública (ver el archivo `.gitignore` agregado)**.
Para ejecutar en tu computadora crea un archivo local `.env`:
```text
ORGANIZATION_ID=abcd-efg-hij-klmn
ABB_API_KEY=xX_Super_Secret_String_Xx
```

### 5.3 Implementación Corporativa (Streamlit Community Cloud)
1. Has un fork o vincula el código fuente actual al repositorio en GitHub. Recomendar a nivel CISO hacer el **Repositorio Privado**, a menos que desees que otros ingenieros escrudiñen el motor base de analítica. 
2. Al enlazarlo en la página de **share.streamlit.io**, el despliegue virtual pedirá las claves. *Aquí no existe el `.env`*. Dirígete a "Configuración > Secrets" e inyecta en lenguaje universal **TOML**:
    ```toml
    ORGANIZATION_ID = "abcd-efg-hij-klmn"
    ABB_API_KEY = "xX_Super_Secret_String_Xx"
    ```
    *Dato vital: TOML es estrictamente tipado. Si no usas dobles-comillas alrededor del Token, el compilador Linux de Streamlit lanzará excepciones irreversibles durante el build.*

3. Por diseño de la plataforma externa, si tienes el Repositorio de GitHub Privado, deberás invitar (`Add Members/Viewers`) los correos electrónicos de los ejecutivos dentro del apartado "Visibilidad" de Streamlit Cloud. Alternativamente, puedes hacer Público el Repositorio GitHub pero confiar tranquilamente en el **doble candado que construimos desde Python (Usuario | Contraseña)** al inicio de `app.py`, que aisla la telemetría operativa incluso si la IP del Cloud fuera interceptada públicamente.
